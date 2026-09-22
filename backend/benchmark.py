"""
benchmark.py
============
Measure how well the detector actually works, and write the numbers down.

    python benchmark.py                 # full sweep (a few minutes)
    python benchmark.py --quick         # smaller sweep
    python benchmark.py --out results/  # where to write the report

What it measures
----------------
1. **A dilution series.** Synthetic specimens are generated with a known
   abnormal fraction, from 5% down to 0.01%, at three acquisition depths. Every
   run is scored against its own ground truth.

2. **Limit of detection.** The smallest abnormal fraction still found at each
   acquisition depth. This is the headline number, and the sweep is
   two-dimensional on purpose: the limit is not a property of the software
   alone. Finding a 0.01% population means finding roughly 5 cells in 50,000,
   and no algorithm can call 5 cells a population. Acquire 500,000 events and
   the same fraction is 50 cells, which is findable. So the honest claim is
   "this fraction, at this many events" -- and the table shows the tradeoff
   instead of quoting a single flattering figure.

3. **Specificity.** Healthy specimens, repeated. These carry hematogones -- the
   normal B-cell precursors that mimic blasts -- so a false positive here is the
   failure that matters most.

4. **Reproducibility.** The same specimen analysed repeatedly must give a
   bit-identical answer. This is a direct claim against manual gating, where
   two operators disagree, so it is worth testing rather than asserting.

5. **Throughput.** Seconds per specimen, against the 30-60 minutes a manual
   analysis takes.

Output is a console table, ``benchmark.json`` (every run), and
``benchmark.md`` (a table ready to paste into a write-up).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.flow import detect, fit_reference, gate, read_fcs  # noqa: E402
from app.flow.detect import DEFAULT_MIN_CLUSTER  # noqa: E402

BLAST = "Aberrant B-lymphoblasts"
SD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_data")

# (events acquired, abnormal fraction %). Zero-blast rows are the specificity
# controls and are repeated.
DEPTHS = [50_000, 200_000, 500_000]
FRACTIONS = [5.0, 1.0, 0.1, 0.05, 0.01]
QUICK_DEPTHS = [50_000, 200_000]
QUICK_FRACTIONS = [5.0, 0.5, 0.05]
N_HEALTHY_CONTROLS = 4
N_REPRODUCIBILITY_RUNS = 5


def generate(tmpdir: str, n_events: int, blast_pct: float, tag: str) -> tuple[str, np.ndarray]:
    """Write one synthetic specimen; return (path, per-event truth labels)."""
    from make_mock_fcs import build_sample, write_fcs

    events, labels = build_sample(n_events, blast_pct)
    path = os.path.join(tmpdir, f"{tag}.fcs")
    write_fcs(path, events)
    return path, np.asarray(labels, dtype=object)


def score_run(reference, path: str, truth: np.ndarray) -> dict:
    """Analyse one specimen and score it against ground truth."""
    t0 = time.time()
    adata = read_fcs(path, filename=os.path.basename(path))
    adata.obs["_row"] = np.arange(adata.n_obs)
    gated, qc = gate(adata)
    rows = gated.obs["_row"].to_numpy().astype(int)
    report = detect(gated, reference, already_gated=True)
    elapsed = time.time() - t0

    aligned = truth[rows]
    is_blast = aligned == BLAST
    called = np.asarray(report["per_event"]["abnormal"])

    tp = int((called & is_blast).sum())
    fp = int((called & ~is_blast).sum())
    fn = int((~called & is_blast).sum())

    return {
        "n_acquired": int(adata.n_obs),
        "n_analyzed": int(gated.n_obs),
        "pct_kept": qc["pct_kept"],
        "true_n": int(is_blast.sum()),
        "true_pct": round(float(is_blast.mean() * 100.0), 5),
        "reported_pct": report["abnormal_pct"],
        "reported_n": report["n_abnormal"],
        "stage1_n": report["stage1_flagged"],
        "detected": report["verdict"] == "abnormal_population_detected",
        "tp": tp, "fp": fp, "fn": fn,
        "sensitivity": round(tp / (tp + fn) * 100.0, 2) if (tp + fn) else None,
        "precision": round(tp / (tp + fp) * 100.0, 2) if (tp + fp) else None,
        "seconds": round(elapsed, 2),
        "verdict": report["verdict"],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true", help="smaller, faster sweep")
    ap.add_argument("--out", default=".", help="directory for the report files")
    ap.add_argument("--keep", action="store_true", help="keep generated .fcs files")
    args = ap.parse_args()

    depths = QUICK_DEPTHS if args.quick else DEPTHS
    fractions = QUICK_FRACTIONS if args.quick else FRACTIONS
    n_controls = 2 if args.quick else N_HEALTHY_CONTROLS

    normals = sorted(
        os.path.join(SD, f) for f in os.listdir(SD)
        if f.startswith("normal_bm_") and f.endswith(".fcs")
    )
    if len(normals) < 2:
        raise SystemExit(
            "need the healthy fixtures first: python make_mock_fcs.py"
        )

    print("fitting reference from", len(normals), "healthy specimens...")
    t0 = time.time()
    reference = fit_reference(
        [read_fcs(p, filename=os.path.basename(p)) for p in normals]
    )
    fit_seconds = time.time() - t0
    print(f"  fitted in {fit_seconds:.1f}s\n")

    tmpdir = tempfile.mkdtemp(prefix="askcell_bench_")
    runs: list[dict] = []

    try:
        # ---- dilution series -------------------------------------------- #
        print("DILUTION SERIES")
        header = f"  {'events':>9} {'true %':>9} {'found %':>9} {'sens':>7} {'prec':>7} {'det':>5} {'s':>6}"
        print(header)
        print("  " + "-" * (len(header) - 2))
        for depth in depths:
            for frac in fractions:
                tag = f"d{depth}_f{str(frac).replace('.', 'p')}"
                path, truth = generate(tmpdir, depth, frac, tag)
                r = score_run(reference, path, truth)
                r.update(kind="dilution", requested_pct=frac, depth=depth)
                runs.append(r)
                print(
                    f"  {r['n_acquired']:>9,} {r['true_pct']:>9.4f} "
                    f"{r['reported_pct']:>9.4f} "
                    f"{(str(r['sensitivity']) + '%') if r['sensitivity'] is not None else '-':>7} "
                    f"{(str(r['precision']) + '%') if r['precision'] is not None else '-':>7} "
                    f"{'YES' if r['detected'] else 'no':>5} {r['seconds']:>6.1f}"
                )
                if not args.keep:
                    os.remove(path)
            print()

        # ---- specificity controls --------------------------------------- #
        print("SPECIFICITY CONTROLS (healthy, containing hematogones)")
        for i in range(n_controls):
            path, truth = generate(tmpdir, 200_000, 0.0, f"healthy_{i}")
            r = score_run(reference, path, truth)
            r.update(kind="specificity", requested_pct=0.0, depth=200_000)
            runs.append(r)
            flag = "FALSE POSITIVE" if r["detected"] else "correct"
            print(
                f"  control {i + 1}: {r['n_analyzed']:>7,} cells  "
                f"stage1 flagged {r['stage1_n']:>5,}  "
                f"reported {r['reported_pct']:>6.4f}%  -> {flag}"
            )
            if not args.keep:
                os.remove(path)

        false_positives = sum(
            1 for r in runs if r["kind"] == "specificity" and r["detected"]
        )
        specificity = (n_controls - false_positives) / n_controls * 100.0
        print(f"  specificity: {specificity:.1f}%  "
              f"({n_controls - false_positives}/{n_controls} correct)\n")

        # ---- reproducibility -------------------------------------------- #
        print("REPRODUCIBILITY")
        path, truth = generate(tmpdir, 200_000, 0.1, "repro")
        results = []
        for _ in range(N_REPRODUCIBILITY_RUNS):
            r = score_run(reference, path, truth)
            results.append(r["reported_pct"])
        identical = len(set(results)) == 1
        print(f"  {N_REPRODUCIBILITY_RUNS} runs of the same specimen: {results}")
        print(f"  {'identical' if identical else 'VARIED'}\n")
        if not args.keep:
            os.remove(path)

        # ---- limit of detection ----------------------------------------- #
        lod: dict[int, float | None] = {}
        for depth in depths:
            found = [
                r["requested_pct"] for r in runs
                if r["kind"] == "dilution" and r["depth"] == depth and r["detected"]
            ]
            lod[depth] = min(found) if found else None

        print("LIMIT OF DETECTION")
        for depth, val in lod.items():
            cells = f"~{int(depth * (val or 0) / 100)} cells" if val else ""
            print(f"  {depth:>9,} events acquired -> "
                  f"{(str(val) + '%') if val else 'not detected at any level tested':<12} {cells}")
        print(f"\n  {DEFAULT_MIN_CLUSTER} cells is the hard floor: a population "
              f"smaller than that\n  is not distinguishable from a chance clump "
              f"of noise, at any depth.")

        dil = [r for r in runs if r["kind"] == "dilution" and r["detected"]]
        mean_sens = float(np.mean([r["sensitivity"] for r in dil if r["sensitivity"] is not None])) if dil else 0.0
        mean_prec = float(np.mean([r["precision"] for r in dil if r["precision"] is not None])) if dil else 0.0
        per_100k = float(np.mean([
            r["seconds"] / (r["n_acquired"] / 100_000) for r in runs
        ]))

        summary = {
            "reference": reference.summary(),
            "fit_seconds": round(fit_seconds, 2),
            "n_runs": len(runs),
            "limit_of_detection_pct": {str(k): v for k, v in lod.items()},
            "min_cluster_floor_cells": DEFAULT_MIN_CLUSTER,
            "specificity_pct": round(specificity, 2),
            "specificity_controls": n_controls,
            "false_positives": false_positives,
            "reproducible": identical,
            "reproducibility_values": results,
            "mean_sensitivity_pct": round(mean_sens, 2),
            "mean_precision_pct": round(mean_prec, 2),
            "seconds_per_100k_events": round(per_100k, 2),
            "runs": runs,
        }

        os.makedirs(args.out, exist_ok=True)
        jpath = os.path.join(args.out, "benchmark.json")
        with open(jpath, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)

        mpath = os.path.join(args.out, "benchmark.md")
        with open(mpath, "w", encoding="utf-8") as fh:
            fh.write(render_markdown(summary, runs, depths))

        print(f"\nSUMMARY")
        print(f"  mean sensitivity (detected cases)  {mean_sens:.2f}%")
        print(f"  mean precision   (detected cases)  {mean_prec:.2f}%")
        print(f"  specificity                        {specificity:.1f}%")
        print(f"  reproducible                       {'yes' if identical else 'NO'}")
        print(f"  throughput                         {per_100k:.1f}s per 100k events")
        print(f"\nwrote {jpath}\nwrote {mpath}")

    finally:
        if not args.keep:
            shutil.rmtree(tmpdir, ignore_errors=True)
        else:
            print(f"\ngenerated files kept in {tmpdir}")


def render_markdown(summary: dict, runs: list[dict], depths: list[int]) -> str:
    """A results table ready to paste into a report or poster."""
    L: list[str] = []
    L.append("# AskCell detection benchmark\n")
    L.append(
        "Synthetic specimens on a 14-colour B-ALL panel, with a known abnormal "
        "fraction. Every specimen also contains hematogones -- normal B-cell "
        "precursors whose immunophenotype closely mimics blasts -- so the "
        "healthy controls are a genuine test rather than a formality.\n"
    )

    L.append("\n## Headline\n")
    L.append("| Metric | Value |")
    L.append("| --- | --- |")
    lod = summary["limit_of_detection_pct"]
    best = [v for v in lod.values() if v is not None]
    L.append(f"| Limit of detection (deepest acquisition) | "
             f"{min(best) if best else 'n/a'}% |")
    L.append(f"| Mean sensitivity, detected cases | "
             f"{summary['mean_sensitivity_pct']}% |")
    L.append(f"| Mean precision, detected cases | "
             f"{summary['mean_precision_pct']}% |")
    L.append(f"| Specificity (healthy controls) | "
             f"{summary['specificity_pct']}% "
             f"({summary['specificity_controls'] - summary['false_positives']}"
             f"/{summary['specificity_controls']}) |")
    L.append(f"| Reproducible across repeat runs | "
             f"{'identical' if summary['reproducible'] else 'varied'} |")
    L.append(f"| Throughput | {summary['seconds_per_100k_events']}s "
             f"per 100k events |")
    L.append(f"| Reference build (one-off) | {summary['fit_seconds']}s |")

    L.append("\n## Limit of detection by acquisition depth\n")
    L.append(
        "The limit is not a property of the software alone. A 0.01% population "
        "is ~5 cells in 50,000 and cannot be called by anything; the same "
        "fraction is ~50 cells at 500,000 events. Acquiring more events is what "
        f"buys sensitivity. A population below {summary['min_cluster_floor_cells']} "
        "cells is refused at any depth, because it is not distinguishable from a "
        "chance clump of noise.\n"
    )
    L.append("| Events acquired | Lowest fraction detected | Approx. cells |")
    L.append("| --- | --- | --- |")
    cell_counts: list[int] = []
    for depth in depths:
        v = lod.get(str(depth))
        if v:
            cell_counts.append(int(depth * v / 100))
        cells = f"~{int(depth * v / 100)}" if v else "—"
        L.append(f"| {depth:,} | {str(v) + '%' if v else 'none detected'} | {cells} |")

    if cell_counts:
        L.append(
            f"\n**The limit is a cell count, not a percentage.** Across a "
            f"tenfold range of acquisition depth the smallest detectable "
            f"population stayed at roughly {min(cell_counts)}-{max(cell_counts)} "
            f"cells, while the percentage it corresponds to moved by a factor of "
            f"ten. The detector needs a certain number of cells to recognise a "
            f"population as a population; what fraction of the specimen that "
            f"represents is set by how many events were acquired, not by the "
            f"software.\n\nThe practical consequence: **to lower the detectable "
            f"percentage, acquire more events.** This is the same tradeoff "
            f"clinical MRD assays make, and it is why they run millions of "
            f"events rather than thousands."
        )

    L.append("\n## Every run\n")
    L.append("| Kind | Events | True % | Reported % | Sensitivity | Precision "
             "| Detected | Seconds |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in runs:
        sens = f"{r['sensitivity']}%" if r["sensitivity"] is not None else "—"
        prec = f"{r['precision']}%" if r["precision"] is not None else "—"
        L.append(
            f"| {r['kind']} | {r['n_acquired']:,} | {r['true_pct']} | "
            f"{r['reported_pct']} | {sens} | {prec} | "
            f"{'yes' if r['detected'] else 'no'} | {r['seconds']} |"
        )

    L.append("\n## Caveats\n")
    L.append(
        "- Synthetic data. The generator encodes a specific idea of what a blast "
        "population looks like, so these numbers measure internal consistency, "
        "not clinical accuracy. Real specimens are messier in ways a generator "
        "does not know to imitate.\n"
        "- Not clinically validated. Clinical validation needs hundreds of real "
        "cases with confirmed diagnoses and ethical approval.\n"
        "- One panel. All results are for the 14-colour B-ALL panel above; the "
        "detector must be re-characterised for any other panel.\n"
        "- Research and educational use only. Not a diagnostic device."
    )
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
