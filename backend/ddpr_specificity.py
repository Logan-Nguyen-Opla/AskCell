"""
ddpr_specificity.py
====================
False-positive check: run the DDPR-fitted reference against real healthy
human cells it was *not* fit on -- the same 5 donors' non-Basal conditions
(BCR-Crosslink, IL-7, TSLP, Pervanadate, BEZ-235, Dasatinib, Tofacitinib).

Caveat this script cannot remove: these are ex-vivo *stimulated* conditions,
not a second resting/basal draw. A false positive here could in principle be
a real stimulation-induced shift rather than a detector error -- though the
25-marker panel used (see ddpr_explore.DDPR_PHENOTYPE_MARKERS) deliberately
excludes every phospho-signaling channel, which is where a stimulation
response would actually show up, so this is about as clean a held-out
specificity check as this dataset allows.

Usage: python ddpr_specificity.py --data-dir "C:\\Users\\LOGAN\\Downloads\\ddpr_data"
"""

from __future__ import annotations

import argparse
import glob
import os
import re
from collections import defaultdict

import anndata as ad
import numpy as np

from app.flow import NormalReference, detect, gate, marker_matrix, read_fcs
from ddpr_explore import restrict_to_phenotype

BOLD, DIM, RED, GREEN, OFF = "\033[1m", "\033[2m", "\033[31m", "\033[32m", "\033[0m"

_PART_RE = re.compile(r"_Part\d+$")


def group_by_condition(data_dir: str) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for p in glob.glob(os.path.join(data_dir, "Healthy*_*.fcs")):
        stem = os.path.splitext(os.path.basename(p))[0]
        stem = _PART_RE.sub("", stem)
        if stem.endswith("_Basal"):
            continue  # used to fit the reference -- not a held-out test
        groups[stem].append(p)
    return {k: sorted(v) for k, v in sorted(groups.items())}


def load_condition(paths: list[str]) -> ad.AnnData:
    mats, names_ref = [], None
    for p in paths:
        a = restrict_to_phenotype(read_fcs(p, filename=os.path.basename(p)))
        g, _ = gate(a)
        X, names = marker_matrix(g)
        if names_ref is None:
            names_ref = names
        elif names != names_ref:
            raise SystemExit(f"{paths}: part marker sets differ")
        mats.append(X)
    import pandas as pd
    merged = ad.AnnData(
        X=np.vstack(mats), var=pd.DataFrame({"channel_type": "marker"}, index=names_ref)
    )
    merged.obs_names = [str(i) for i in range(merged.n_obs)]
    return merged


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--reference", default=None)
    ap.add_argument("--radius-fraction", type=float, default=None)
    args = ap.parse_args()

    ref_path = args.reference or os.path.join(args.data_dir, "ddpr_reference.npz")
    ref = NormalReference.load(ref_path)
    print(f"{DIM}loaded reference from {ref_path}{OFF}")
    kwargs = {} if args.radius_fraction is None else {"radius_fraction": args.radius_fraction}

    groups = group_by_condition(args.data_dir)
    print(f"{len(groups)} held-out healthy conditions (not used to fit the reference)\n")

    n_fp = 0
    for stem, paths in groups.items():
        specimen = load_condition(paths)
        report = detect(specimen, ref, already_gated=True, **kwargs)
        detected = report["verdict"] == "abnormal_population_detected"
        n_fp += detected
        colour = RED if detected else GREEN
        print(f"  {stem:<28} n={specimen.n_obs:>7,}  "
              f"{colour}{report['verdict']:<32}{OFF} "
              f"abnormal={report['abnormal_pct']}% ({report['n_abnormal']:,} cells)")

    print(f"\n{BOLD}{n_fp}/{len(groups)} real healthy (non-cancer) specimens "
          f"falsely flagged an abnormal population{OFF}")
    print(f"{DIM}specificity = {(len(groups) - n_fp) / len(groups) * 100:.1f}%{OFF}")


if __name__ == "__main__":
    main()
