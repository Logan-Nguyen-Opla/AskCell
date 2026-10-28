"""
flow_engine.py
==============
Session state for the cytometry workflow: holds the healthy reference and one
patient specimen *at the same time*, and serves the results to the front-end.

Why this holds both at once
----------------------------
A single-dataset session would make a comparison impossible by construction --
you cannot diff a patient against a reference if only one of them can be in
memory. This module holds both, plus the detection report and a shared 2-D
embedding.

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
from .flow.panel import canonical_marker

# Points streamed to the browser. The reference is only a visual backdrop so it
# is thinned harder than the specimen, whose individual cells are the subject.
_REF_DISPLAY_CAP = 20_000
_SAMPLE_DISPLAY_CAP = 120_000


def choose_reference(
    markers: list[str],
    canonical_markers: set[str],
    primary: NormalReference,
    primary_name: str,
    alt_references: dict[str, NormalReference],
) -> tuple[str, NormalReference, list[str]]:
    """Pick the first reference a specimen's markers actually satisfy.

    Tries ``primary`` first by its own (raw-label) marker names, so the common
    case never touches the alternates or canonicalization. Each alternate is
    matched by canonical token instead, on *both* sides -- the alt's own
    marker list is canonicalized here too, rather than assumed to already be
    canonical, since nothing about registering an alt reference guarantees
    that. (A reference's marker list is whatever label its own healthy
    specimens happened to use at fit time; the real DDPR reference bundled
    with this app happens to have been fitted on canonical tokens, but that's
    an implementation detail of how it was built, not a contract this
    function should assume every alt reference follows.) Matching real data
    needs this: the same antigen is spelled differently from acquisition to
    acquisition (``HLA-DR`` vs ``HLADR``, ``tIkaros`` vs ``tIKAROS``).

    Returns ``(name, reference, [])`` on a match, or ``(primary_name, primary,
    missing)`` when nothing matches -- ``missing`` is reported against
    ``primary`` since that is the one the caller was actually trying to use.
    """
    missing = [m for m in primary.markers if m not in markers]
    if not missing:
        return primary_name, primary, []
    for name, alt in alt_references.items():
        alt_canon = {canonical_marker(m) for m in alt.markers}
        if alt_canon <= canonical_markers:
            return name, alt, []
    return primary_name, primary, missing


def _canonicalize_for_reference(gated: ad.AnnData, reference: NormalReference) -> ad.AnnData:
    """Rename a gated specimen's marker channels to match an alt reference's
    own marker spelling, by canonical token.

    ``marker_matrix``/``reference.standardize`` both match by exact, literal
    name. A specimen's channel is "HLA-DR", the reference's own marker list
    might say "HLADR" (or some other spelling its fitting files happened to
    use) -- renaming each of the specimen's channels to *the reference's own
    string* for the same canonical antigen is what makes that literal lookup
    succeed, regardless of which spelling either side happened to use.
    """
    ref_by_canon = {canonical_marker(m): m for m in reference.markers}
    var = gated.var
    keep_idx: list[int] = []
    keep_names: list[str] = []
    seen: set[str] = set()
    for i, raw_name in enumerate(gated.var_names):
        if var["channel_type"].iat[i] != "marker":
            continue
        canon = (
            var["canonical"].iat[i]
            if "canonical" in var.columns
            else canonical_marker(str(raw_name))
        )
        target = ref_by_canon.get(canon)
        if target is not None and target not in seen:
            keep_idx.append(i)
            keep_names.append(target)
            seen.add(target)
    sub = gated[:, keep_idx].copy()
    sub.var_names = keep_names
    sub.var["channel_type"] = "marker"
    return sub


def _canonical_marker_names(gated: ad.AnnData) -> set[str]:
    """Canonical tokens for every "marker"-type channel in a gated specimen."""
    var = gated.var
    out: set[str] = set()
    for i, raw_name in enumerate(gated.var_names):
        if var["channel_type"].iat[i] != "marker":
            continue
        canon = (
            var["canonical"].iat[i]
            if "canonical" in var.columns
            else canonical_marker(str(raw_name))
        )
        if canon:
            out.add(canon)
    return out


class FlowSession:
    """Holds a fitted reference plus the specimen currently being examined."""

    def __init__(self) -> None:
        self.reference: NormalReference | None = None
        self.reference_profile: str = "default"
        # The reference explicitly chosen by set_reference()/
        # load_reference_from_paths() (startup, or a user building their own).
        # Kept separate from `reference`, which load_sample_from_path() may
        # swap to an alt reference for one upload's embedding/display --
        # without this, that swap would permanently lose the ability to
        # analyse a *default*-panel specimen again in the same session.
        self.default_reference: NormalReference | None = None
        # Other fitted references, keyed by name, tried in load_sample_from_path
        # when a specimen's panel doesn't match the default one. A specimen
        # acquired on a different antibody panel isn't unusable -- it just
        # needs a reference that was built on *its* panel instead.
        self.alt_references: dict[str, NormalReference] = {}
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
        self.default_reference = self.reference
        self.reference_profile = "default"
        self._fit_basis()
        # A new reference invalidates any result computed against the old one.
        self._clear_sample()
        return self.reference.summary()

    def set_reference(
        self, reference: NormalReference, *, profile: str = "default", as_default: bool = True
    ) -> dict:
        """Make ``reference`` the active one.

        ``as_default`` (the normal case: startup, or a user explicitly
        building/uploading a reference) also makes it the fallback candidate
        for future specimens whose panel doesn't match whatever is active at
        the time. Internal auto-fallback switches (see
        load_sample_from_path) pass ``as_default=False`` so they don't
        overwrite that fallback with a reference matched to just one upload.
        """
        self.reference = reference
        self.reference_profile = profile
        if as_default:
            self.default_reference = reference
        self._fit_basis()
        self._clear_sample()
        return reference.summary()

    def add_alt_reference(self, name: str, reference: NormalReference) -> None:
        """Register a reference for a different panel, tried as a fallback.

        Does not change the active reference -- it only becomes active if a
        future specimen's panel matches it instead of the current one.
        """
        self.alt_references[name] = reference

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

        # Matched against the stable default reference plus the alt pool --
        # not against `self.reference`, which a *previous* upload may have
        # left pointed at an alt. Otherwise, analysing one DDPR file would
        # permanently strand the session: the next default-panel upload would
        # find no default reference to fall back to, since it was never
        # trying anything but whatever happened to still be active.
        name, chosen, missing = choose_reference(
            markers,
            _canonical_marker_names(gated),
            self.default_reference,
            "default",
            self.alt_references,
        )
        if missing:
            # Refused rather than guessed: a comparison missing one of the
            # reference's markers is not the comparison that was calibrated.
            raise ValueError(
                "this specimen was acquired with a different antibody panel "
                f"than the reference. Missing markers: {', '.join(missing)}. "
                "Marker intensities are not comparable across panels, so no "
                "meaningful comparison is possible."
            )
        if chosen is not self.reference:
            self.set_reference(chosen, profile=name, as_default=False)
            gated = _canonicalize_for_reference(gated, chosen)
            X, markers = marker_matrix(gated)

        panel = compare_panels(markers, self.reference.markers)
        report = detect(gated, self.reference, already_gated=True)
        # detect() gates nothing when already_gated, so it has no QC report to
        # return -- attach the one produced by the gate() call above.
        report["qc"] = qc
        report["panel"] = panel
        report["reference_profile"] = self.reference_profile

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
        self.reference_profile = "default"
        self.default_reference = None
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
            out["reference_profile"] = self.reference_profile
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
