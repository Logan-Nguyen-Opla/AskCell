"""
reference.py
============
Build the "what normal looks like" model from a set of healthy specimens.

The idea
--------
Every gated cell is a point in marker space -- 13 numbers, so a point in 13
dimensions. Pool the cells from several healthy people and you get a cloud of
points describing every cell type a healthy specimen contains, and in what
proportions.

To ask whether a patient's cell is normal, ask how far it sits from that cloud:
take its ``k`` nearest neighbours among the healthy cells and average the
distance. A cell that lands in the middle of a healthy population has near
neighbours and scores low. A cell whose combination of markers exists in nobody
healthy has no near neighbours and scores high.

That is deliberately the same sentence as the plain-English description of the
method -- "does a cell like this exist in a healthy person?" -- because a
detector whose code and whose explanation are the same thing is one you can
actually defend.

Where the threshold comes from
------------------------------
The scores are distances, so "high" is meaningless without a scale. Hard-coding
a cutoff would be guessing, so the threshold is *measured* instead, by
leave-one-out: each healthy specimen is scored against a reference built from
only the *other* healthy specimens. That produces the distribution of scores
healthy cells get when they are genuinely unseen data, and the cutoff is a high
percentile of it.

This makes the false-positive rate a chosen quantity rather than a surprise. At
the 99.9th percentile, one healthy cell in a thousand is expected to trip the
flag -- so on a 400,000-event file, roughly 400 spurious flags are *expected*.
That is not a bug and it cannot be tuned away; it is why detection cannot stop
at flagging single cells. See ``detect.py``.
"""

from __future__ import annotations

import json
import os

import anndata as ad
import numpy as np
from scipy.spatial import cKDTree

from .panel import panel_fingerprint
from .qc import gate, marker_matrix

# Neighbours averaged per cell. Large enough that one stray reference event
# cannot make a genuinely abnormal cell look normal; small enough to still
# resolve a rare-but-real healthy population.
DEFAULT_K = 15

# Cap on reference events held in the tree. A KD-tree in 13 dimensions degrades
# as it grows, and a healthy marrow's cell types are well covered long before
# this -- the cap buys a large speed-up for almost no loss of coverage.
DEFAULT_CLOUD_CAP = 60_000

# Fraction of healthy cells allowed to exceed the threshold, by construction.
DEFAULT_PERCENTILE = 99.9


class NormalReference:
    """A fitted model of healthy marrow, ready to score patient cells."""

    def __init__(
        self,
        markers: list[str],
        center: np.ndarray,
        scale: np.ndarray,
        cloud: np.ndarray,
        threshold: float,
        *,
        k: int = DEFAULT_K,
        percentile: float = DEFAULT_PERCENTILE,
        panel: str = "",
        sources: list[str] | None = None,
        null_quantiles: dict | None = None,
        neighbour_radius: float = 0.0,
    ) -> None:
        self.markers = list(markers)
        self.center = np.asarray(center, dtype=np.float32)
        self.scale = np.asarray(scale, dtype=np.float32)
        self.cloud = np.asarray(cloud, dtype=np.float32)
        self.threshold = float(threshold)
        self.k = int(k)
        self.percentile = float(percentile)
        self.panel = panel
        self.sources = list(sources or [])
        self.null_quantiles = dict(null_quantiles or {})
        self.neighbour_radius = float(neighbour_radius)
        self._tree = cKDTree(self.cloud)

    # ------------------------------------------------------------------ #
    # Scoring
    # ------------------------------------------------------------------ #
    def standardize(self, X: np.ndarray, markers: list[str]) -> np.ndarray:
        """Reorder a sample's markers to reference order, then z-score.

        Z-scoring uses the *reference's* mean and spread, never the sample's.
        Standardising a patient against itself would rescale away the very shift
        the comparison is looking for -- a sample where every cell is abnormal
        would come out looking perfectly average.
        """
        missing = [m for m in self.markers if m not in markers]
        if missing:
            raise ValueError(
                f"sample is missing markers the reference needs: {missing}"
            )
        idx = [markers.index(m) for m in self.markers]
        return (X[:, idx] - self.center) / self.scale

    def score(self, X: np.ndarray, markers: list[str]) -> np.ndarray:
        """Mean distance from each cell to its k nearest healthy neighbours."""
        Z = self.standardize(X, markers)
        k = min(self.k, self.cloud.shape[0])
        dist, _ = self._tree.query(Z, k=k, workers=-1)
        if dist.ndim == 1:  # k == 1
            return dist.astype(np.float32)
        return dist.mean(axis=1).astype(np.float32)

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def save(self, path: str) -> None:
        np.savez_compressed(
            path,
            markers=np.array(self.markers, dtype=object),
            center=self.center,
            scale=self.scale,
            cloud=self.cloud,
            meta=np.array(
                json.dumps(
                    {
                        "threshold": self.threshold,
                        "k": self.k,
                        "percentile": self.percentile,
                        "panel": self.panel,
                        "sources": self.sources,
                        "null_quantiles": self.null_quantiles,
                        "neighbour_radius": self.neighbour_radius,
                    }
                ),
                dtype=object,
            ),
        )

    @classmethod
    def load(cls, path: str) -> NormalReference:
        z = np.load(path, allow_pickle=True)
        meta = json.loads(str(z["meta"].item()))
        return cls(
            markers=[str(m) for m in z["markers"]],
            center=z["center"],
            scale=z["scale"],
            cloud=z["cloud"],
            threshold=meta["threshold"],
            k=meta["k"],
            percentile=meta["percentile"],
            panel=meta.get("panel", ""),
            sources=meta.get("sources", []),
            null_quantiles=meta.get("null_quantiles", {}),
            neighbour_radius=meta.get("neighbour_radius", 0.0),
        )

    def summary(self) -> dict:
        return {
            "n_markers": len(self.markers),
            "markers": self.markers,
            "n_reference_cells": int(self.cloud.shape[0]),
            "n_source_specimens": len(self.sources),
            "sources": self.sources,
            "panel_fingerprint": self.panel,
            "k": self.k,
            "threshold": round(self.threshold, 4),
            "threshold_percentile": self.percentile,
            "expected_false_flag_rate_pct": round(100.0 - self.percentile, 4),
            "null_quantiles": self.null_quantiles,
        }


# --------------------------------------------------------------------------- #
# Fitting
# --------------------------------------------------------------------------- #
def _subsample(X: np.ndarray, cap: int, seed: int = 0) -> np.ndarray:
    if X.shape[0] <= cap:
        return X
    rng = np.random.default_rng(seed)
    return X[np.sort(rng.choice(X.shape[0], size=cap, replace=False))]


def fit_reference(
    samples: list[ad.AnnData],
    *,
    k: int = DEFAULT_K,
    cloud_cap: int = DEFAULT_CLOUD_CAP,
    percentile: float = DEFAULT_PERCENTILE,
    already_gated: bool = False,
) -> NormalReference:
    """Fit a :class:`NormalReference` from healthy specimens.

    At least two specimens are required. With one there is nothing to hold out,
    so the threshold could only be guessed -- and a threshold nobody measured is
    the single easiest way to produce a detector that looks excellent on its own
    test data and fails on the first real sample.

    Parameters
    ----------
    samples
        Healthy specimens, as returned by :func:`app.flow.read_fcs`.
    already_gated
        Set when the caller has already run :func:`app.flow.qc.gate`.
    """
    if len(samples) < 2:
        raise ValueError(
            "at least 2 healthy specimens are required: the threshold is "
            "calibrated by holding one out, which is impossible with one file"
        )

    mats: list[np.ndarray] = []
    names_ref: list[str] | None = None
    sources: list[str] = []
    for s in samples:
        g = s if already_gated else gate(s)[0]
        X, names = marker_matrix(g)
        if names_ref is None:
            names_ref = names
        elif names != names_ref:
            raise ValueError(
                "healthy specimens do not share one marker set -- a reference "
                f"cannot mix panels ({names_ref} vs {names})"
            )
        mats.append(X)
        sources.append(str(g.uns.get("askcell", {}).get("filename", "?")))

    return _fit_from_matrices(
        mats, names_ref, sources, k=k, cloud_cap=cloud_cap, percentile=percentile
    )


def _fit_from_matrices(
    mats: list[np.ndarray],
    names_ref: list[str] | None,
    sources: list[str],
    *,
    k: int,
    cloud_cap: int,
    percentile: float,
) -> NormalReference:
    """Shared tail of fitting, once every specimen is reduced to a marker matrix."""
    assert names_ref is not None

    # Every specimen contributes at most its even share of cloud_cap from here
    # on. Pooling every full specimen and subsampling *afterward* (the
    # obvious way to write this) means peak memory during fitting scales with
    # the number of specimens -- fine for 2, not fine for a reference meant to
    # grow. Capping per-specimen up front bounds the pooled cloud, the final
    # training cloud, and every leave-one-out comparison set to ~cloud_cap
    # regardless of how many specimens go in. Only the held-out side of each
    # leave-one-out fold stays at full resolution (below), since that is the
    # side whose precision the calibrated threshold actually depends on.
    per_specimen_cap = max(500, cloud_cap // len(mats))
    capped = [_subsample(m, per_specimen_cap, seed=42 + j) for j, m in enumerate(mats)]
    pooled = np.vstack(capped)

    # Reference location and spread, so every marker contributes comparably to
    # the distance instead of the widest-ranging one dominating it.
    center = pooled.mean(axis=0)
    scale = pooled.std(axis=0)
    scale[scale < 1e-6] = 1.0  # a constant channel must not divide by ~0

    # ---- leave-one-out calibration ---------------------------------------- #
    # Score each specimen (at full resolution) against the others (capped) to
    # see how unusual healthy cells look as genuinely unseen data.
    null_parts: list[np.ndarray] = []
    for i in range(len(mats)):
        others_z = np.vstack(
            [(capped[j] - center) / scale for j in range(len(mats)) if j != i]
        )
        held_z = (mats[i] - center) / scale
        tree = cKDTree(others_z)
        kk = min(k, others_z.shape[0])
        dist, _ = tree.query(held_z, k=kk, workers=-1)
        null_parts.append(dist.mean(axis=1) if dist.ndim > 1 else dist)

    null = np.concatenate(null_parts)
    threshold = float(np.percentile(null, percentile))

    # Typical spacing between neighbouring healthy cells, used by the clustering
    # step in detect.py to decide what "close together" means in this panel.
    neighbour_radius = float(np.median(null))

    null_quantiles = {
        f"p{p}": round(float(np.percentile(null, p)), 4)
        for p in (50, 90, 99, 99.9, 99.99)
    }

    cloud = _subsample((pooled - center) / scale, cloud_cap, seed=7)
    panel, _ = panel_fingerprint(names_ref)

    return NormalReference(
        markers=names_ref,
        center=center,
        scale=scale,
        cloud=cloud,
        threshold=threshold,
        k=k,
        percentile=percentile,
        panel=panel,
        sources=sources,
        null_quantiles=null_quantiles,
        neighbour_radius=neighbour_radius,
    )


def fit_reference_from_files(
    paths: list[str],
    *,
    k: int = DEFAULT_K,
    cloud_cap: int = DEFAULT_CLOUD_CAP,
    percentile: float = DEFAULT_PERCENTILE,
) -> NormalReference:
    """Read, gate, and reduce each FCS path to a marker matrix one at a time.

    Reading every specimen into memory as a full AnnData before fitting (the
    obvious way to write this) scales badly: a reference of a couple dozen
    specimens comfortably exceeds a constrained deploy target's RAM before
    fitting even starts, because each raw+gated AnnData carries every channel
    and every compensation/transform intermediate, not just the handful of
    marker columns the fit actually needs. Processing one file at a time and
    keeping only the reduced (n_events, n_markers) float32 matrix means peak
    memory is one specimen's raw data plus every specimen's *reduced* data,
    not every specimen's raw data at once.
    """
    from .fcs_ingest import read_fcs

    mats: list[np.ndarray] = []
    names_ref: list[str] | None = None
    sources: list[str] = []
    for p in paths:
        s = read_fcs(p, filename=os.path.basename(p))
        g, _ = gate(s)
        X, names = marker_matrix(g)
        if names_ref is None:
            names_ref = names
        elif names != names_ref:
            raise ValueError(
                "healthy specimens do not share one marker set -- a reference "
                f"cannot mix panels ({names_ref} vs {names})"
            )
        mats.append(X)
        sources.append(str(g.uns.get("askcell", {}).get("filename", "?")))

    return _fit_from_matrices(
        mats, names_ref, sources, k=k, cloud_cap=cloud_cap, percentile=percentile
    )
