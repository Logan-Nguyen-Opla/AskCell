"""
ddpr_remeasure_radius.py
=========================
Re-measure DEFAULT_RADIUS_FRACTION on real DDPR data instead of trusting the
value measured on synthetic fixtures (detect.py says, in its own words, that
this "must be re-measured on real specimens before the number is trusted").

No per-cell ground truth exists for DDPR (unlike the synthetic fixtures'
.labels.npy), so this substitutes real proxies for "true blast" and "true
noise":

  blast proxy  cells already accepted into a clustered population on files
               with an overwhelming, unambiguous signal (>=20% abnormal) --
               at that burden the vast majority of flagged cells really are
               the clone, so their mutual 8th-nearest-neighbour distance
               stands in for "how tight a real clone is" here.

  noise proxy  flagged cells from specimens with no real disease signal:
               the 19 held-out healthy (non-cancer) specimens from the
               specificity check, restricted to the ones that were NOT
               falsely flagged, so this can't be contaminated by the two
               real IL-7 false positives.

Prints the same blast_max / noise_min quantities the existing synthetic-data
test computes, and what a radius_fraction in that real gap would be -- so any
change to DEFAULT_RADIUS_FRACTION (or a DDPR-specific override) is grounded
in a number, not a guess.
"""

from __future__ import annotations

import glob
import os
import re
from collections import defaultdict

import anndata as ad
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from app.flow import NormalReference, detect, gate, marker_matrix, read_fcs
from app.flow.detect import DEFAULT_MIN_NEIGHBOURS
from ddpr_explore import restrict_to_phenotype

DATA = r"C:\Users\LOGAN\Downloads\ddpr_data"
REF_PATH = os.path.join(DATA, "ddpr_reference.npz")
_PART_RE = re.compile(r"_Part\d+$")

STRONG_POSITIVES = [
    "UPN68_Basal.fcs", "UPN10-Relapse_Basal.fcs", "UPN10_Basal.fcs",
    "UPN45_Basal.fcs", "UPN45-Relapse_Basal.fcs", "UPN22_Basal.fcs",
    "UPN22-Relapse_Basal.fcs",
]

HEALTHY_FALSE_POSITIVES = {"Healthy1_IL-7", "Healthy4_IL-7"}  # exclude these


def load_merged(stem_paths: list[str]) -> ad.AnnData:
    mats, names_ref = [], None
    for p in stem_paths:
        a = restrict_to_phenotype(read_fcs(p, filename=os.path.basename(p)))
        g, _ = gate(a)
        X, names = marker_matrix(g)
        if names_ref is None:
            names_ref = names
        elif names != names_ref:
            raise SystemExit(f"marker mismatch in {stem_paths}")
        mats.append(X)
    merged = ad.AnnData(
        X=np.vstack(mats), var=pd.DataFrame({"channel_type": "marker"}, index=names_ref)
    )
    merged.obs_names = [str(i) for i in range(merged.n_obs)]
    return merged


def kdist(Z: np.ndarray, k: int) -> np.ndarray:
    kk = min(k, Z.shape[0])
    dist, _ = cKDTree(Z).query(Z, k=kk, workers=-1)
    return dist[:, -1] if dist.ndim > 1 else dist


def main() -> None:
    ref = NormalReference.load(REF_PATH)
    k = DEFAULT_MIN_NEIGHBOURS + 1
    print(f"current reference.neighbour_radius = {ref.neighbour_radius:.4f}")
    print(f"current default linking radius (x2.0) = {ref.neighbour_radius * 2.0:.4f}\n")

    # ---- blast proxy: cluster members in overwhelming-signal real files ---- #
    blast_dists: list[np.ndarray] = []
    for fname in STRONG_POSITIVES:
        a = restrict_to_phenotype(read_fcs(os.path.join(DATA, fname)))
        g, qc = gate(a)
        report = detect(g, ref, already_gated=True)
        if not report["ok"] or report["abnormal_pct"] < 20:
            continue
        X, markers = marker_matrix(g)
        Z = ref.standardize(X, markers)
        pop = np.asarray(report["per_event"]["population"])
        member_z = Z[pop >= 0]
        if member_z.shape[0] > k:
            blast_dists.append(kdist(member_z, k))
    blast = np.concatenate(blast_dists)
    blast_max = float(np.quantile(blast, 0.90))
    print(f"blast proxy: {len(blast_dists)} files, {blast.size} cluster-member cells")
    print(f"  p10={np.quantile(blast,0.10):.3f} median={np.median(blast):.3f} "
          f"p90={blast_max:.3f}\n")

    # ---- noise proxy: flagged cells from real healthy, non-flagged specimens ---- #
    groups: dict[str, list[str]] = defaultdict(list)
    for p in glob.glob(os.path.join(DATA, "Healthy*_*.fcs")):
        stem = _PART_RE.sub("", os.path.splitext(os.path.basename(p))[0])
        if stem.endswith("_Basal"):
            continue
        groups[stem].append(p)

    noise_dists: list[np.ndarray] = []
    for stem, paths in groups.items():
        if stem in HEALTHY_FALSE_POSITIVES:
            continue
        specimen = load_merged(sorted(paths))
        X, markers = marker_matrix(specimen)
        scores = ref.score(X, markers)
        flagged = scores > ref.threshold
        if flagged.sum() > k:
            Z = ref.standardize(X, markers)[flagged]
            noise_dists.append(kdist(Z, k))
    noise = np.concatenate(noise_dists)
    noise_min = float(np.quantile(noise, 0.10))
    print(f"noise proxy: {len(noise_dists)} healthy specimens, {noise.size} flagged cells")
    print(f"  p10={noise_min:.3f} median={np.median(noise):.3f} "
          f"p90={np.quantile(noise,0.90):.3f}\n")

    if blast_max < noise_min:
        mid = (blast_max + noise_min) / 2
        print(f"GAP EXISTS: blast_max={blast_max:.3f} < noise_min={noise_min:.3f}")
        print(f"  a radius of {mid:.3f} sits in the middle of it "
              f"({mid / ref.neighbour_radius:.3f}x neighbour_radius, "
              f"vs the current 2.0x = {ref.neighbour_radius*2.0:.3f})")
    else:
        print(f"NO GAP: blast_max={blast_max:.3f} >= noise_min={noise_min:.3f}")
        print("  real blast tightness and real noise spacing overlap on this "
              "panel/reference -- no radius value can cleanly separate them.")


if __name__ == "__main__":
    main()
