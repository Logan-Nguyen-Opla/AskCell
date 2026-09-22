"""
run_detection.py
================
Run the whole detection pipeline from the command line and print a report.

    python run_detection.py                          # every fixture specimen
    python run_detection.py sample_data/patient_overt.fcs
    python run_detection.py my_patient.fcs --reference my_normals/*.fcs

By default the healthy reference is built from ``sample_data/normal_bm_*.fcs``
and cached to ``sample_data/reference.npz``, so only the first run pays for the
fit. Pass ``--refit`` to rebuild it.

When a ``<name>.labels.npy`` ground-truth file sits beside the specimen, the
report scores itself against it -- sensitivity, precision, and the reported
burden versus the true burden.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.flow import NormalReference, detect, fit_reference, gate, read_fcs

SD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_data")
CACHE = os.path.join(SD, "reference.npz")
BLAST = "Aberrant B-lymphoblasts"

BOLD, DIM, RED, GREEN, YELLOW, CYAN, OFF = (
    "\033[1m", "\033[2m", "\033[31m", "\033[32m", "\033[33m", "\033[36m", "\033[0m"
)


def build_reference(paths: list[str], refit: bool) -> NormalReference:
    if not refit and os.path.exists(CACHE):
        ref = NormalReference.load(CACHE)
        print(f"{DIM}loaded cached reference from {CACHE}{OFF}")
        return ref

    if len(paths) < 2:
        raise SystemExit(
            "need at least 2 healthy specimens to calibrate a threshold "
            f"(found {len(paths)})"
        )
    print(f"building reference from {len(paths)} healthy specimens...")
    t0 = time.time()
    ref = fit_reference([read_fcs(p, filename=os.path.basename(p)) for p in paths])
    ref.save(CACHE)
    print(f"{DIM}fitted in {time.time() - t0:.1f}s, cached to {CACHE}{OFF}")
    return ref


def print_reference(ref: NormalReference) -> None:
    s = ref.summary()
    print(f"\n{BOLD}WHAT NORMAL LOOKS LIKE{OFF}")
    print(f"  built from      {s['n_source_specimens']} healthy specimens "
          f"({', '.join(s['sources'])})")
    print(f"  reference cells {s['n_reference_cells']:,}")
    print(f"  markers         {s['n_markers']}: {', '.join(s['markers'])}")
    print(f"  threshold       {s['threshold']} "
          f"({s['threshold_percentile']}th percentile of healthy cells)")
    print(f"  {DIM}by construction ~{s['expected_false_flag_rate_pct']}% of healthy "
          f"cells trip the flag -- stage 2 exists to remove them{OFF}")


def truth_for(path: str, n_gated: int, rows: np.ndarray) -> np.ndarray | None:
    lp = path.replace(".fcs", ".labels.npy")
    if not os.path.exists(lp):
        return None
    return np.load(lp, allow_pickle=True)[rows]


def run_one(path: str, ref: NormalReference) -> None:
    name = os.path.basename(path)
    print(f"\n{BOLD}{'=' * 68}{OFF}")
    print(f"{BOLD}{name}{OFF}")

    t0 = time.time()
    adata = read_fcs(path, filename=name)
    adata.obs["_row"] = np.arange(adata.n_obs)
    gated, qc = gate(adata)
    rows = gated.obs["_row"].to_numpy().astype(int)
    report = detect(gated, ref, already_gated=True)
    elapsed = time.time() - t0

    if not report["ok"]:
        print(f"  {RED}{report['error']}{OFF}: {report['message']}")
        return

    print(f"\n  {BOLD}QUALITY CONTROL{OFF}")
    print(f"    {qc['n_input']:,} events acquired -> {qc['n_kept']:,} intact "
          f"single live cells ({qc['pct_kept']}% kept)")
    for gname, g in qc["gates"].items():
        if "removed" in g:
            print(f"      {DIM}-{g['removed']:>6,} {gname}{OFF}")
    if qc["warning"]:
        print(f"    {YELLOW}! {qc['warning']}{OFF}")

    print(f"\n  {BOLD}DETECTION{OFF}")
    print(f"    stage 1  flagged as unlike normal   {report['stage1_flagged']:>8,}"
          f"  ({report['stage1_flagged_pct']}%)")
    print(f"    stage 2  in a clustered population  {report['n_abnormal']:>8,}"
          f"  ({report['abnormal_pct']}%)")
    print(f"    {DIM}         scattered noise discarded    "
          f"{report['noise_removed_by_clustering']:>8,}{OFF}")

    detected = report["verdict"] == "abnormal_population_detected"
    colour = RED if detected else GREEN
    print(f"\n  {colour}{BOLD}{report['verdict'].replace('_', ' ').upper()}{OFF}")
    print(f"  {report['summary']}")

    for i, pop in enumerate(report["populations"], 1):
        print(f"\n    {BOLD}population {i}{OFF}: {pop['n_events']:,} cells "
              f"({pop['pct_of_analyzed']}% of analysed)")
        print(f"      spread          {pop['compactness_vs_normal']}x normal "
              f"-> {'clonal' if pop['is_clonal'] else 'not clonal'}")
        print(f"      {BOLD}phenotype{OFF}")
        for d in pop["deviant_markers"]:
            arrow = "^" if d["direction"] == "brighter" else "v"
            bar = "#" * min(int(abs(d["z"]) * 3), 24)
            print(f"        {d['marker']:<8} {arrow} {d['z']:>+6.2f} sd  "
                  f"{CYAN}{bar}{OFF} {DIM}{d['strength']}{OFF}")

    # ---- self-scoring against ground truth, when available ---------------- #
    truth = truth_for(path, gated.n_obs, rows)
    if truth is not None:
        is_blast = truth == BLAST
        called = report["per_event"]["abnormal"]
        tp = int((called & is_blast).sum())
        fp = int((called & ~is_blast).sum())
        fn = int((~called & is_blast).sum())
        print(f"\n  {BOLD}SCORED AGAINST GROUND TRUTH{OFF}")
        print(f"    true abnormal cells   {int(is_blast.sum()):,} "
              f"({is_blast.mean() * 100:.4f}%)")
        print(f"    reported              {tp + fp:,} "
              f"({report['abnormal_pct']}%)")
        if is_blast.any():
            print(f"    sensitivity           {tp / (tp + fn) * 100:.2f}%  "
                  f"{DIM}(of real abnormal cells, how many we found){OFF}")
        if tp + fp:
            print(f"    precision             {tp / (tp + fp) * 100:.2f}%  "
                  f"{DIM}(of cells we called abnormal, how many were real){OFF}")
        elif not is_blast.any():
            print(f"    {GREEN}correctly reported no population{OFF} "
                  f"{DIM}(specificity: healthy specimen not flagged){OFF}")

    print(f"\n  {DIM}analysed in {elapsed:.1f}s{OFF}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("specimens", nargs="*", help="FCS file(s) to analyse")
    ap.add_argument("--reference", nargs="*", default=None,
                    help="healthy FCS files to build the reference from")
    ap.add_argument("--refit", action="store_true",
                    help="rebuild the reference instead of using the cache")
    args = ap.parse_args()

    ref_paths = args.reference or sorted(glob.glob(os.path.join(SD, "normal_bm_*.fcs")))
    specimens = args.specimens or [
        p for p in sorted(glob.glob(os.path.join(SD, "patient_*.fcs")))
    ]

    if not specimens:
        raise SystemExit(
            "no specimens found. Generate the fixtures first:\n"
            "    python make_mock_fcs.py"
        )

    ref = build_reference(ref_paths, args.refit)
    print_reference(ref)
    for path in specimens:
        run_one(path, ref)
    print()


if __name__ == "__main__":
    main()
