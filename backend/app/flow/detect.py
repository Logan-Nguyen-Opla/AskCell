"""
detect.py
=========
Compare one patient specimen against a fitted :class:`NormalReference` and
decide whether an abnormal cell population is present.

Two stages, and the second is the one that matters
--------------------------------------------------
**Stage 1 -- flag.** Score every gated cell by its distance from healthy cells
and flag the ones past the reference's calibrated threshold.

Stage 1 on its own is not a detector. The threshold was calibrated to let a
fixed fraction of healthy cells through, so on a 400,000-event file several
hundred flags are *expected from a completely healthy person*. Reporting stage 1
as a result would mean diagnosing everybody. The rate cannot be tuned away
either: pushing the threshold up until healthy samples come back clean also
pushes it past the 200-cell populations that matter most.

**Stage 2 -- cluster.** So the question is not "are there odd cells" but "are
the odd cells *many, and all odd in the same way*".

That distinction is the whole method, and it is a geometric one. Cancer is one
cell that stopped maturing and started copying itself, so its descendants are
near-identical -- they land in a tight knot in marker space. Spurious flags come
from unrelated cells in sparse corners of the reference, so they are scattered
with nothing near them. Both look identical to stage 1 and completely different
to stage 2.

This is also what separates a real clone from hematogones -- normal B-cell
precursors, which are the reason naive detectors flag healthy children. Those
are odd-ish too, but they are spread smoothly along a maturation path rather
than knotted at one point.

Clusters are found with a density rule (a cell needs enough flagged neighbours
nearby to count as part of a population) rather than plain single-linkage,
because single-linkage lets a chain of scattered noise fuse into one bogus
"population".
"""

from __future__ import annotations

import anndata as ad
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from .qc import gate, marker_matrix
from .reference import NormalReference

# Flagged neighbours (including itself) a cell needs within the linking radius
# to count as part of a population rather than an isolated oddity.
DEFAULT_MIN_NEIGHBOURS = 8

# Smallest cluster reported as a population. Below this a "cluster" is not
# distinguishable from a chance clump of noise. 30 events out of 400,000 is
# 0.0075%, comfortably under the MRD levels that matter clinically.
DEFAULT_MIN_CLUSTER = 30

# Linking radius, as a multiple of the median healthy neighbour distance.
#
# Above 1, which is initially counter-intuitive: a clone is *tighter* than normal
# tissue, so the radius "should" be small. That reasoning conflates two
# different distances. The reference neighbour distance is measured in a dense
# 60,000-point cloud, whereas clustering runs over the *flagged* cells only --
# a far sparser set in the same space. Fewer points means larger spacing, so the
# linking radius has to be bigger than the reference's, not smaller.
#
# Measured on the synthetic fixtures, the 8th-neighbour distance inside the
# flagged set separates the two classes cleanly:
#
#     true blast populations   0.20 - 0.43
#     scattered false flags    0.86 - 6.45
#
# 2.0x the reference neighbour distance lands in that gap with margin at both
# ends. Expressing it as a multiple rather than an absolute number lets it track
# panel size and data density instead of being a magic constant.
#
# CAVEAT: this gap was measured on synthetic data. It must be re-measured on
# real specimens before the number is trusted -- see
# tests/test_flow_detect.py::test_radius_sits_in_the_measured_gap, which fails
# loudly if the separation stops holding.
DEFAULT_RADIUS_FRACTION = 2.0


def _cluster(
    Z: np.ndarray, radius: float, min_neighbours: int
) -> np.ndarray:
    """Density-based clustering. Returns a label per row, ``-1`` for noise.

    A point is "core" when at least ``min_neighbours`` flagged points (itself
    included) sit within ``radius``. Core points that are within radius of each
    other join the same cluster; non-core points attach to an adjacent cluster
    if they touch one, and are otherwise noise.
    """
    n = Z.shape[0]
    labels = np.full(n, -1, dtype=int)
    if n == 0:
        return labels

    tree = cKDTree(Z)
    counts = tree.query_ball_point(Z, radius, return_length=True, workers=-1)
    core = counts >= min_neighbours
    if not core.any():
        return labels

    pairs = tree.query_pairs(radius, output_type="ndarray")
    if pairs.size:
        both_core = core[pairs[:, 0]] & core[pairs[:, 1]]
        pairs = pairs[both_core]

    core_idx = np.flatnonzero(core)
    remap = -np.ones(n, dtype=int)
    remap[core_idx] = np.arange(core_idx.size)

    if pairs.size:
        a, b = remap[pairs[:, 0]], remap[pairs[:, 1]]
        graph = coo_matrix(
            (np.ones(a.size), (a, b)), shape=(core_idx.size, core_idx.size)
        )
    else:
        graph = coo_matrix((core_idx.size, core_idx.size))

    n_comp, comp = connected_components(graph, directed=False)
    labels[core_idx] = comp

    # Attach border points to the cluster of a nearby core point.
    border = np.flatnonzero(~core)
    if border.size and core_idx.size:
        core_tree = cKDTree(Z[core_idx])
        dist, nearest = core_tree.query(Z[border], k=1, workers=-1)
        close = dist <= radius
        labels[border[close]] = comp[nearest[close]]

    return labels


def _deviant_markers(
    cluster_z: np.ndarray, markers: list[str], top: int = 6
) -> list[dict]:
    """Which markers set this population apart, and in which direction.

    Values are already z-scored against the reference, so the cluster mean *is*
    the deviation in units of healthy spread: +3 means three standard deviations
    brighter than a healthy cell.
    """
    mean_z = cluster_z.mean(axis=0)
    order = np.argsort(-np.abs(mean_z))[:top]
    out = []
    for i in order:
        z = float(mean_z[i])
        out.append(
            {
                "marker": markers[i],
                "z": round(z, 2),
                "direction": "brighter" if z > 0 else "dimmer",
                "strength": (
                    "strong" if abs(z) >= 2 else
                    "moderate" if abs(z) >= 1 else "weak"
                ),
            }
        )
    return out


def detect(
    sample: ad.AnnData,
    reference: NormalReference,
    *,
    min_neighbours: int = DEFAULT_MIN_NEIGHBOURS,
    min_cluster: int = DEFAULT_MIN_CLUSTER,
    radius_fraction: float = DEFAULT_RADIUS_FRACTION,
    already_gated: bool = False,
    return_per_event: bool = True,
) -> dict:
    """Run the full comparison and return a structured report.

    The report separates ``flagged`` (stage 1) from ``abnormal`` (stage 2,
    clustered) on purpose. The gap between them is the noise the clustering
    removed, and showing it is what makes the result auditable rather than a
    number to be taken on faith.
    """
    gated, qc_report = (sample, None) if already_gated else gate(sample)
    X, markers = marker_matrix(gated)

    missing = [m for m in reference.markers if m not in markers]
    if missing:
        return {
            "ok": False,
            "error": "panel_mismatch",
            "message": (
                "this specimen does not carry every marker the reference was "
                f"built on; missing: {missing}"
            ),
            "qc": qc_report,
        }

    n = int(X.shape[0])
    scores = reference.score(X, markers)
    flagged = scores > reference.threshold
    n_flagged = int(flagged.sum())

    Z = reference.standardize(X, markers)
    radius = reference.neighbour_radius * radius_fraction

    labels = np.full(n, -1, dtype=int)
    populations: list[dict] = []
    if n_flagged:
        sub = _cluster(Z[flagged], radius, min_neighbours)
        labels[np.flatnonzero(flagged)] = sub

        for lab in np.unique(sub[sub >= 0]):
            members = np.flatnonzero(labels == lab)
            if members.size < min_cluster:
                labels[members] = -1  # too small to call a population
                continue
            cz = Z[members]
            populations.append(
                {
                    "label": int(lab),
                    "n_events": int(members.size),
                    "pct_of_analyzed": round(members.size / n * 100.0, 4),
                    "mean_score": round(float(scores[members].mean()), 3),
                    # Spread relative to healthy tissue. Below 1 means the
                    # population is tighter than normal cells -- the signature
                    # of a clone rather than a maturing lineage.
                    "compactness": round(
                        float(cz.std(axis=0).mean()), 3
                    ),
                    "deviant_markers": _deviant_markers(cz, reference.markers),
                }
            )

    populations.sort(key=lambda p: -p["n_events"])
    n_abnormal = sum(p["n_events"] for p in populations)
    abnormal_pct = round(n_abnormal / n * 100.0, 4) if n else 0.0

    # Reference cells' own spread, as the yardstick for "tighter than normal".
    normal_spread = float(reference.cloud.std(axis=0).mean())
    for p in populations:
        p["compactness_vs_normal"] = round(p["compactness"] / normal_spread, 3)
        p["is_clonal"] = bool(p["compactness_vs_normal"] < 1.0)

    if not populations:
        verdict = "no_abnormal_population"
        summary = (
            f"No abnormal population found. {n_flagged:,} of {n:,} cells "
            f"({n_flagged / n * 100:.3f}%) scored above threshold, but they are "
            "scattered rather than clustered -- consistent with the expected "
            "false-flag rate for a healthy specimen."
        ) if n else "No cells left after QC gating."
    else:
        top = populations[0]
        clonal = any(p["is_clonal"] for p in populations)
        verdict = (
            "abnormal_population_detected" if clonal
            else "abnormal_events_not_clonal"
        )
        traits = ", ".join(
            f"{d['marker']} {d['direction']}"
            for d in top["deviant_markers"][:3]
        )
        summary = (
            f"Abnormal population detected: {n_abnormal:,} of {n:,} cells "
            f"({abnormal_pct:.3f}%). Largest population {top['n_events']:,} "
            f"cells, {top['compactness_vs_normal']:.2f}x the spread of normal "
            f"cells ({'clonal' if top['is_clonal'] else 'not clonal'}). "
            f"Distinguishing markers: {traits}."
        )

    report: dict = {
        "ok": True,
        "verdict": verdict,
        "summary": summary,
        "abnormal_pct": abnormal_pct,
        "n_abnormal": n_abnormal,
        "n_analyzed": n,
        "stage1_flagged": n_flagged,
        "stage1_flagged_pct": round(n_flagged / n * 100.0, 4) if n else 0.0,
        "noise_removed_by_clustering": n_flagged - n_abnormal,
        "populations": populations,
        "qc": qc_report,
        "parameters": {
            "threshold": round(reference.threshold, 4),
            "threshold_percentile": reference.percentile,
            "k": reference.k,
            "link_radius": round(radius, 4),
            "min_neighbours": min_neighbours,
            "min_cluster": min_cluster,
        },
        "reference": {
            "n_specimens": len(reference.sources),
            "sources": reference.sources,
            "n_cells": int(reference.cloud.shape[0]),
        },
    }
    if return_per_event:
        report["per_event"] = {
            "score": scores,
            "abnormal": labels >= 0,
            "population": labels,
        }
    return report
