"""
qc.py
=====
Quality-control gating: throw away events that are not intact single live cells
before any comparison happens.

This runs first for a blunt reason. A dead cell genuinely *is* abnormal -- its
membrane is leaking and its surface proteins read wrong -- so a detector that
skips this step will faithfully report "abnormal cells found" on a perfectly
healthy specimen that was simply handled badly. Same for debris, and same for
two cells stuck together, which the machine measures as one cell carrying both
their proteins and therefore an antigen combination that exists in nobody.

None of that is cancer. All of it looks like cancer to a distance metric. So it
goes out first, and the counts are reported rather than silently dropped -- a
sample that loses 60% of its events to gating is a sample worth re-running, and
the operator needs to be told.

The gates here are deliberately simple and are the same three a human draws by
hand at the start of a manual analysis.
"""

from __future__ import annotations

import anndata as ad
import numpy as np

# Fraction of events at each tail of the FSC-H / FSC-A ratio treated as
# doublets/irregulars. Singlets sit in a tight band; the tails are aggregates.
_DOUBLET_TAIL = 0.01

# A viability stain is *dim* on live cells and bright on dead ones. Events above
# this quantile of the viability channel are treated as dead.
_DEAD_QUANTILE = 0.97


def _col(adata: ad.AnnData, name: str) -> np.ndarray | None:
    if name not in adata.var_names:
        return None
    return np.asarray(adata[:, name].X).ravel()


def _viability_channel(adata: ad.AnnData) -> str | None:
    hits = adata.var_names[adata.var["channel_type"] == "viability"]
    return str(hits[0]) if len(hits) else None


def gate(
    adata: ad.AnnData,
    *,
    remove_debris: bool = True,
    remove_doublets: bool = True,
    remove_dead: bool = True,
) -> tuple[ad.AnnData, dict]:
    """Return ``(gated_view, report)`` keeping only intact single live cells.

    Each gate is skipped without complaint when the channels it needs are
    absent, and the report records what ran so a later comparison can confirm
    the sample and the reference were gated the same way.
    """
    n0 = int(adata.n_obs)
    keep = np.ones(n0, dtype=bool)
    report: dict = {"n_input": n0, "gates": {}}

    fsc_a = _col(adata, "FSC-A")
    fsc_h = _col(adata, "FSC-H")

    # ---- debris: very low forward scatter means it is not a whole cell ---- #
    if remove_debris and fsc_a is not None:
        cut = float(np.quantile(fsc_a, 0.02))
        g = fsc_a > cut
        report["gates"]["debris"] = {
            "removed": int((~g & keep).sum()), "fsc_a_min": round(cut, 1)
        }
        keep &= g
    elif remove_debris:
        report["gates"]["debris"] = {"skipped": "no FSC-A channel"}

    # ---- doublets: two cells through the laser together ------------------- #
    # Height scales with peak brightness, area with total signal. For a singlet
    # the ratio is near-constant; a doublet has roughly twice the area for the
    # same height, so it falls out of the band.
    if remove_doublets and fsc_a is not None and fsc_h is not None:
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(fsc_a > 0, fsc_h / fsc_a, np.nan)
        finite = np.isfinite(ratio)
        if finite.sum() > 100:
            lo, hi = np.quantile(
                ratio[finite], [_DOUBLET_TAIL, 1.0 - _DOUBLET_TAIL]
            )
            g = finite & (ratio >= lo) & (ratio <= hi)
            report["gates"]["doublets"] = {
                "removed": int((~g & keep).sum()),
                "ratio_range": [round(float(lo), 4), round(float(hi), 4)],
            }
            keep &= g
        else:
            report["gates"]["doublets"] = {"skipped": "too few finite ratios"}
    elif remove_doublets:
        report["gates"]["doublets"] = {"skipped": "needs FSC-A and FSC-H"}

    # ---- dead cells ------------------------------------------------------- #
    via_name = _viability_channel(adata)
    if remove_dead and via_name:
        via = _col(adata, via_name)
        cut = float(np.quantile(via, _DEAD_QUANTILE))
        g = via <= cut
        report["gates"]["dead"] = {
            "removed": int((~g & keep).sum()),
            "channel": via_name,
            "max_viability": round(cut, 4),
        }
        keep &= g
    elif remove_dead:
        report["gates"]["dead"] = {"skipped": "no viability channel"}

    n1 = int(keep.sum())
    report["n_kept"] = n1
    report["n_removed"] = n0 - n1
    report["pct_kept"] = round(n1 / n0 * 100.0, 2) if n0 else 0.0
    # A sample that loses most of its events was probably mishandled; the
    # percentage is more useful to an operator than a silent pass.
    report["warning"] = (
        "more than half of all events failed QC gating -- check sample handling"
        if n0 and n1 < n0 * 0.5
        else None
    )

    return adata[keep].copy(), report


def marker_matrix(adata: ad.AnnData) -> tuple[np.ndarray, list[str]]:
    """Return ``(X, marker_names)`` for phenotypic marker channels only.

    Scatter channels are excluded because they were left on a linear scale and
    describe size rather than phenotype; viability is excluded because it was
    already used as a gate. Including either would let handling artefacts weigh
    as heavily as biology.
    """
    mask = (adata.var["channel_type"] == "marker").to_numpy()
    names = [str(n) for n in adata.var_names[mask]]
    X = np.asarray(adata.X[:, mask], dtype=np.float32)
    return X, names
