"""
ddpr_explore.py
===============
One-off exploration script: fit an AskCell reference matched to the DDPR
dataset's own 35-marker CyTOF panel (Good et al. 2018, Nat Med), then run a
handful of real pediatric B-ALL diagnostic samples through detection.

Why a separate reference
-------------------------
AskCell's built-in reference (sample_data/reference.npz) was fitted on a
13-marker diagnostic differential panel (CD3/5/7/13/19/20/33/34/38/45/117 +
HLA-DR). DDPR used a different 35-marker developmental/signaling panel for a
different scientific question, and five of AskCell's markers (CD5, CD7, CD13,
CD33, CD117) simply do not exist in it -- so no DDPR file can ever compare
against the built-in reference; app.flow.panel's fingerprint guard correctly
refuses that comparison rather than faking one.

A reference built *from DDPR's own healthy donors, on DDPR's own panel* sidesteps
that: same panel on both sides, so the comparison is actually meaningful.

Caveat this script cannot remove
---------------------------------
DDPR ships sample-level files only -- there is no per-cell "this cell is a
leukemic blast" label (unlike our synthetic fixtures' .labels.npy). So this can
report *whether a sample shows a distinct, clustered population unlike healthy
marrow*, and how large it is, but not per-cell sensitivity/precision the way
run_detection.py does against simulated data.

Usage (from backend/, with the venv active)::

    python ddpr_explore.py --data-dir "C:\\Users\\LOGAN\\Downloads\\ddpr_data"
"""

from __future__ import annotations

import argparse
import glob
import os
import time

import anndata as ad
import numpy as np
import pandas as pd

from app.flow import NormalReference, detect, fit_reference, gate, marker_matrix, read_fcs

HEALTHY_DONORS = ["Healthy1", "Healthy2", "Healthy3", "Healthy4", "Healthy5"]

# The real, stable antibody panel shared across every DDPR file (README's
# "Phenotypic and Developmental Markers"), in canonical form. Deliberately
# excludes: barcode channels (BC1-6, used for debarcoding upstream), bead
# distance, a lineage-exclusion dump channel that DDPR itself labelled
# inconsistently across batches (seen directly: "CD33-CD16" in one file,
# "FITC_myeloid" in others), a few unlabelled leftover isotope slots that
# appear/disappear between batches (I127, Ce140, Gd157), and the
# phospho-signaling markers -- those move with ex-vivo treatment, not cell
# identity, so they don't belong in a "what does a resting cell look like"
# reference even though this script only ever uses Basal (unstimulated) files.
DDPR_PHENOTYPE_MARKERS = {
    "CD3", "CD10", "CD19", "CD20", "CD22", "CD24", "CD34", "CD38", "CD43",
    "CD45", "CD58", "CD79B", "CD123", "CD127", "CD179A", "CD179B", "HLADR",
    "IGMI", "IGMS", "KI67", "PAX5", "RAG1", "TDT", "TSLPR", "TIKAROS",
}

BOLD, DIM, RED, GREEN, YELLOW, OFF = (
    "\033[1m", "\033[2m", "\033[31m", "\033[32m", "\033[33m", "\033[0m"
)


def restrict_to_phenotype(adata: ad.AnnData, allowlist=DDPR_PHENOTYPE_MARKERS) -> ad.AnnData:
    """Keep scatter/viability channels untouched (gate() needs them by name),
    and reduce "marker"-type channels to the allowlist above, renamed to their
    canonical token in a fixed (sorted) order -- so two files that spell the
    same antigen differently, or carry different extra junk channels, end up
    with byte-identical marker matrices instead of tripping the "healthy
    specimens do not share one marker set" check for a reason that has
    nothing to do with the actual biology.
    """
    var = adata.var
    passthrough_idx, passthrough_names = [], []
    marker_idx, marker_canon = [], []
    for i, name in enumerate(adata.var_names):
        if var["channel_type"].iat[i] != "marker":
            passthrough_idx.append(i)
            passthrough_names.append(name)
        else:
            canon = var["canonical"].iat[i]
            if canon in allowlist:
                marker_idx.append(i)
                marker_canon.append(canon)
    order = sorted(range(len(marker_idx)), key=lambda k: marker_canon[k])
    marker_idx = [marker_idx[k] for k in order]
    marker_canon = [marker_canon[k] for k in order]
    sub = adata[:, passthrough_idx + marker_idx].copy()
    sub.var_names = passthrough_names + marker_canon
    return sub


def load_donor_basal(data_dir: str, donor: str) -> ad.AnnData:
    """Read every Basal-condition part for one healthy donor, gate each part
    on its own (QC quantiles are file-specific), and stack the *gated marker
    matrices* into one already-gated specimen.

    Parts are the same acquisition split by file size (README: "can be merged
    during downstream analysis"), not independent donors -- merging them here
    keeps leave-one-out calibration honest (one fold per real donor, not per
    file fragment). Gating per part before merging, rather than concatenating
    raw AnnData objects first, sidesteps batch-to-batch drift in channels this
    script never needs anyway (e.g. Part1 of Healthy3 labels its singlet gate
    "Event_length", every other part calls it "Cell_length") -- only the
    phenotype marker matrix has to agree across parts, and after
    ``restrict_to_phenotype`` it always does.
    """
    parts = sorted(glob.glob(os.path.join(data_dir, f"{donor}_Basal*.fcs")))
    if not parts:
        raise SystemExit(f"no Basal files found for {donor} in {data_dir}")

    mats: list[np.ndarray] = []
    names_ref: list[str] | None = None
    for p in parts:
        adata = restrict_to_phenotype(read_fcs(p, filename=os.path.basename(p)))
        gated, _ = gate(adata)
        X, names = marker_matrix(gated)
        if names_ref is None:
            names_ref = names
        elif names != names_ref:
            raise SystemExit(
                f"{donor}: {os.path.basename(p)} marker set "
                f"({names}) differs from its sibling parts ({names_ref})"
            )
        mats.append(X)

    assert names_ref is not None
    merged = ad.AnnData(
        X=np.vstack(mats),
        var=pd.DataFrame({"channel_type": "marker"}, index=names_ref),
    )
    merged.obs_names = [str(i) for i in range(merged.n_obs)]
    merged.uns["askcell"] = {
        "filename": f"{donor}_Basal (merged {len(parts)} parts, pre-gated)"
    }
    return merged


def build_ddpr_reference(data_dir: str, cache_path: str, refit: bool) -> NormalReference:
    if not refit and os.path.exists(cache_path):
        ref = NormalReference.load(cache_path)
        print(f"{DIM}loaded cached DDPR reference from {cache_path}{OFF}")
        return ref

    print(f"building DDPR-panel reference from {len(HEALTHY_DONORS)} healthy donors...")
    t0 = time.time()
    donors = [load_donor_basal(data_dir, d) for d in HEALTHY_DONORS]
    ref = fit_reference(donors, already_gated=True)
    ref.save(cache_path)
    print(f"{DIM}fitted in {time.time() - t0:.1f}s, cached to {cache_path}{OFF}")
    return ref


def print_reference(ref: NormalReference) -> None:
    s = ref.summary()
    print(f"\n{BOLD}WHAT NORMAL LOOKS LIKE (DDPR panel){OFF}")
    print(f"  built from      {s['n_source_specimens']} healthy donors "
          f"({', '.join(s['sources'])})")
    print(f"  reference cells {s['n_reference_cells']:,}")
    print(f"  markers ({s['n_markers']}): {', '.join(s['markers'])}")
    print(f"  threshold       {s['threshold']} "
          f"({s['threshold_percentile']}th percentile of healthy cells)")


def run_one(path: str, ref: NormalReference, radius_fraction: float | None = None) -> dict:
    name = os.path.basename(path)
    t0 = time.time()
    adata = restrict_to_phenotype(read_fcs(path, filename=name))
    gated, qc = gate(adata)
    kwargs = {} if radius_fraction is None else {"radius_fraction": radius_fraction}
    report = detect(gated, ref, already_gated=True, **kwargs)
    elapsed = time.time() - t0

    print(f"\n{BOLD}{name}{OFF}  {DIM}({elapsed:.1f}s){OFF}")
    if not report["ok"]:
        print(f"  {RED}{report['error']}{OFF}: {report['message']}")
        return {"file": name, "ok": False, "error": report["error"]}

    print(f"  {qc['n_input']:,} events -> {qc['n_kept']:,} after QC "
          f"({qc['pct_kept']}% kept)")
    print(f"  stage 1 flagged: {report['stage1_flagged']:,} "
          f"({report['stage1_flagged_pct']}%)  "
          f"stage 2 abnormal: {report['n_abnormal']:,} "
          f"({report['abnormal_pct']}%)")
    colour = RED if report["verdict"] == "abnormal_population_detected" else GREEN
    print(f"  {colour}{report['verdict']}{OFF}: {report['summary']}")
    for i, pop in enumerate(report["populations"], 1):
        top = ", ".join(
            f"{d['marker']}{'^' if d['direction'] == 'brighter' else 'v'}{d['z']:+.1f}"
            for d in pop["deviant_markers"][:5]
        )
        print(f"    population {i}: {pop['n_events']:,} cells "
              f"({pop['pct_of_analyzed']}%), {pop['compactness_vs_normal']}x normal, "
              f"{top}")

    return {
        "file": name,
        "ok": True,
        "n_input": qc["n_input"],
        "n_kept": qc["n_kept"],
        "stage1_pct": report["stage1_flagged_pct"],
        "n_abnormal": report["n_abnormal"],
        "abnormal_pct": report["abnormal_pct"],
        "verdict": report["verdict"],
        "n_populations": len(report["populations"]),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", required=True, help="path to extracted ddpr_data/")
    ap.add_argument("--cache", default=None, help="where to cache the fitted reference")
    ap.add_argument("--refit", action="store_true")
    ap.add_argument(
        "--radius-fraction", type=float, default=None,
        help="override the clustering linking-radius multiplier (default: "
             "detect.py's DEFAULT_RADIUS_FRACTION=2.0, measured on synthetic "
             "data only -- see ddpr_remeasure_radius.py for the real-data gap)",
    )
    ap.add_argument("patients", nargs="*", help="patient FCS files to run (default: a sample)")
    args = ap.parse_args()

    cache = args.cache or os.path.join(args.data_dir, "ddpr_reference.npz")
    ref = build_ddpr_reference(args.data_dir, cache, args.refit)
    print_reference(ref)

    patients = args.patients or sorted(
        p for p in glob.glob(os.path.join(args.data_dir, "UPN*_Basal.fcs"))
        if "-Blood" not in os.path.basename(p)
    )
    if not patients:
        raise SystemExit("no patient files matched")

    results = [run_one(p, ref, args.radius_fraction) for p in patients]

    print(f"\n{BOLD}{'=' * 68}{OFF}\n{BOLD}SUMMARY{OFF}")
    for r in results:
        if not r["ok"]:
            print(f"  {r['file']:<40} {RED}FAILED{OFF} ({r['error']})")
        else:
            flag = RED if r["verdict"] == "abnormal_population_detected" else GREEN
            print(f"  {r['file']:<40} {flag}{r['verdict']:<32}{OFF} "
                  f"abnormal={r['abnormal_pct']}% ({r['n_abnormal']:,} cells)")

    n_ok = sum(1 for r in results if r["ok"])
    n_detected = sum(1 for r in results if r.get("verdict") == "abnormal_population_detected")
    print(f"\n{BOLD}{n_detected}/{n_ok} real diagnostic/relapse B-ALL marrow samples "
          f"flagged an abnormal population{OFF} ({len(results) - n_ok} failed to parse/score)")

    csv_path = os.path.join(args.data_dir, "ddpr_results.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("file,ok,verdict,n_input,n_kept,abnormal_pct,n_abnormal,n_populations\n")
        for r in results:
            if r["ok"]:
                f.write(f"{r['file']},1,{r['verdict']},{r['n_input']},{r['n_kept']},"
                        f"{r['abnormal_pct']},{r['n_abnormal']},{r['n_populations']}\n")
            else:
                f.write(f"{r['file']},0,{r['error']},,,,,\n")
    print(f"{DIM}wrote {csv_path}{OFF}")


if __name__ == "__main__":
    main()
