"""
flow_engine.py
==============
Session state for the cytometry workflow: holds the healthy reference and one
patient specimen *at the same time*, and serves the results to the front-end.

Why this exists alongside cell_engine
-------------------------------------
``cell_engine.py`` holds exactly one dataset, which is fine for browsing a
single scRNA-seq file but makes a comparison impossible by construction -- you
cannot diff a patient against a reference if only one of them can be in memory.
This module holds both, plus the detection report and a shared 2-D embedding.

The embedding is deliberately fitted on the *reference*, not on the patient.
Both are then projected through the same axes, so a patient's cells land where
they belong relative to healthy tissue. Fitting per-sample would give each
specimen its own arbitrary axes and the two clouds could not be overlaid --
which would throw away the one picture that explains the whole method: a grey
cloud of healthy cells with the abnormal population sitting outside it.
"""

from __future__ import annotations

import os
import tempfile

import anndata as ad
import numpy as np
from scipy.sparse.linalg import svds

from .flow import (
    NormalReference,
    compare_panels,
    detect,
    fit_reference,
    gate,
    marker_matrix,
    read_fcs,
)

# Points streamed to the browser. The reference is only a visual backdrop so it
# is thinned harder than the specimen, whose individual cells are the subject.
_REF_DISPLAY_CAP = 20_000
_SAMPLE_DISPLAY_CAP = 120_000


class FlowSession:
    """Holds a fitted reference plus the specimen currently being examined."""

    def __init__(self) -> None:
        self.reference: NormalReference | None = None
        self.sample: ad.AnnData | None = None      # post-QC
        self.sample_name: str | None = None
        self.qc: dict | None = None
        self.report: dict | None = None

        # Embedding basis, learned from the reference.
        self._basis: np.ndarray | None = None      # (2, n_markers)
        self._basis_mean: np.ndarray | None = None
        self._ref_xy: np.ndarray | None = None
        self._sample_xy: np.ndarray | None = None

    # ------------------------------------------------------------------ #
    # Reference
    # ------------------------------------------------------------------ #
    def load_reference_from_paths(self, paths: list[str]) -> dict:
        """Fit the healthy reference from FCS files on disk."""
        if len(paths) < 2:
            raise ValueError(
                "at least 2 healthy specimens are needed: the detection "
                "threshold is calibrated by holding one out"
            )
        samples = [read_fcs(p, filename=os.path.basename(p)) for p in paths]
        self.reference = fit_reference(samples)
        self._fit_basis()
        # A new reference invalidates any result computed against the old one.
        self._clear_sample()
        return self.reference.summary()

    def set_reference(self, reference: NormalReference) -> dict:
        self.reference = reference
        self._fit_basis()
        self._clear_sample()
        return reference.summary()

    def _fit_basis(self) -> None:
        """Learn 2 principal axes from the reference cell cloud."""
        assert self.reference is not None
        Z = self.reference.cloud
        mean = Z.mean(axis=0)
        centered = Z - mean
        k = min(2, min(centered.shape) - 1)
        if k < 1:
            self._basis = np.zeros((2, Z.shape[1]), dtype=np.float32)
            self._basis_mean = mean
            self._ref_xy = np.zeros((Z.shape[0], 2), dtype=np.float32)
            return
        _, _, Vt = svds(centered.astype(np.float64), k=k)
        Vt = Vt[::-1]  # descending variance
        if Vt.shape[0] < 2:  # pad when only one component exists
            Vt = np.vstack([Vt, np.zeros((2 - Vt.shape[0], Vt.shape[1]))])
        self._basis = Vt.astype(np.float32)
        self._basis_mean = mean.astype(np.float32)
        self._ref_xy = (centered @ self._basis.T).astype(np.float32)

    def _project(self, Z: np.ndarray) -> np.ndarray:
        assert self._basis is not None and self._basis_mean is not None
        return ((Z - self._basis_mean) @ self._basis.T).astype(np.float32)

    # ------------------------------------------------------------------ #
    # Specimen
    # ------------------------------------------------------------------ #
    def load_sample_from_path(self, path: str, filename: str) -> dict:
        """Read, gate, detect. Returns the detection report."""
        if self.reference is None:
            raise RuntimeError(
                "no healthy reference is loaded -- build one before analysing "
                "a specimen"
            )

        raw = read_fcs(path, filename=filename)
        gated, qc = gate(raw)

        X, markers = marker_matrix(gated)
        panel = compare_panels(markers, self.reference.markers)
        missing = [m for m in self.reference.markers if m not in markers]
        if missing:
            # Refused rather than guessed: a comparison missing one of the
            # reference's markers is not the comparison that was calibrated.
            raise ValueError(
                "this specimen was acquired with a different antibody panel "
                f"than the reference. Missing markers: {', '.join(missing)}. "
                "Marker intensities are not comparable across panels, so no "
                "meaningful comparison is possible."
            )

        report = detect(gated, self.reference, already_gated=True)
        # detect() gates nothing when already_gated, so it has no QC report to
        # return -- attach the one produced by the gate() call above.
        report["qc"] = qc
        report["panel"] = panel

        self.sample = gated
        self.sample_name = filename
        self.qc = qc
        self.report = report
        self._sample_xy = self._project(
            self.reference.standardize(X, markers)
        )
        return self.public_report()

    def _clear_sample(self) -> None:
        self.sample = None
        self.sample_name = None
        self.qc = None
        self.report = None
        self._sample_xy = None

    def reset(self) -> None:
        self.reference = None
        self._basis = None
        self._basis_mean = None
        self._ref_xy = None
        self._clear_sample()

    # ------------------------------------------------------------------ #
    # Serialization for the front-end
    # ------------------------------------------------------------------ #
    def has_reference(self) -> bool:
        return self.reference is not None

    def has_sample(self) -> bool:
        return self.sample is not None and self.report is not None

    def status(self) -> dict:
        out: dict = {
            "reference_loaded": self.has_reference(),
            "sample_loaded": self.has_sample(),
        }
        if self.reference is not None:
            out["reference"] = self.reference.summary()
        if self.report is not None:
            out["sample"] = {
                "filename": self.sample_name,
                "verdict": self.report["verdict"],
                "abnormal_pct": self.report["abnormal_pct"],
                "n_analyzed": self.report["n_analyzed"],
            }
        return out

    def public_report(self) -> dict:
        """The detection report without the big per-event arrays."""
        if self.report is None:
            raise RuntimeError("no specimen has been analysed yet")
        return {k: v for k, v in self.report.items() if k != "per_event"}

    def scatter(self) -> dict:
        """Points for the viewer: healthy backdrop plus the specimen's cells.

        ``reference`` points are the grey cloud of healthy cells. ``cells`` are
        the specimen's, each carrying its abnormality score and which population
        it was assigned to (``-1`` when it is not in one), so the front-end can
        colour the abnormal cells without a second request.
        """
        if self.reference is None:
            raise RuntimeError("no reference loaded")

        rng = np.random.default_rng(0)  # deterministic across requests
        out: dict = {"markers": self.reference.markers}

        ref_xy = self._ref_xy
        assert ref_xy is not None
        if ref_xy.shape[0] > _REF_DISPLAY_CAP:
            pick = np.sort(
                rng.choice(ref_xy.shape[0], _REF_DISPLAY_CAP, replace=False)
            )
            ref_xy = ref_xy[pick]
        out["reference"] = {
            "n_total": int(self._ref_xy.shape[0]),
            "points": [[round(float(x), 3), round(float(y), 3)] for x, y in ref_xy],
        }

        if not self.has_sample():
            out["cells"] = []
            out["n_cells_total"] = 0
            return out

        assert self.report is not None and self._sample_xy is not None
        per = self.report["per_event"]
        scores = np.asarray(per["score"])
        pops = np.asarray(per["population"])
        xy = self._sample_xy
        n = xy.shape[0]

        idx = np.arange(n)
        if n > _SAMPLE_DISPLAY_CAP:
            # Keep every abnormal cell -- they are the finding, and a rare
            # population would be thinned into invisibility by a flat
            # subsample. Only the normal majority is reduced.
            abnormal = np.flatnonzero(pops >= 0)
            normal = np.flatnonzero(pops < 0)
            budget = max(_SAMPLE_DISPLAY_CAP - abnormal.size, 0)
            if normal.size > budget:
                normal = rng.choice(normal, budget, replace=False)
            idx = np.sort(np.concatenate([abnormal, normal]))

        smax = float(scores.max()) if n else 1.0
        out["cells"] = [
            {
                "id": int(i),
                "x": round(float(xy[i, 0]), 3),
                "y": round(float(xy[i, 1]), 3),
                "s": round(float(scores[i]), 3),
                "p": int(pops[i]),
            }
            for i in idx
        ]
        out["n_cells_total"] = int(n)
        out["n_cells_shown"] = len(out["cells"])
        out["subsampled"] = len(out["cells"]) < n
        out["score_max"] = round(smax, 3)
        out["threshold"] = round(self.reference.threshold, 3)
        return out

    def population_events(self, label: int) -> dict:
        """Original event indices belonging to one detected population."""
        if not self.has_sample():
            raise RuntimeError("no specimen loaded")
        assert self.report is not None
        pops = np.asarray(self.report["per_event"]["population"])
        ids = np.flatnonzero(pops == label)
        return {"label": int(label), "n": int(ids.size),
                "ids": [int(i) for i in ids[:10_000]]}


def read_upload_to_temp(fileobj, suffix: str = ".fcs") -> str:
    """Stream an upload to a temp file and return its path."""
    import shutil

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(fileobj, tmp)
        return tmp.name


# Module-level singleton shared across routes.
flow_session = FlowSession()
