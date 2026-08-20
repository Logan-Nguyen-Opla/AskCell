"""
fcs_ingest.py
=============
Read an FCS (Flow Cytometry Standard) acquisition into an AnnData container.

Pipeline
--------
    .fcs file
      -> FlowKit parse (TEXT segment metadata + event matrix)
      -> spillover compensation      (fluorescence panels; skipped for CyTOF)
      -> arcsinh(x / cofactor)       (cofactor 5 mass cytometry, 150 fluorescence)
      -> AnnData: events x channels, markers as var_names
      -> provenance recorded in adata.uns["askcell"]

Why AnnData
-----------
The existing AskCell engine, viewer and endpoints are all built around AnnData.
Cytometry fits it cleanly: one row per event (an observation, exactly like a
cell), one column per channel (taking the place of a gene). Keeping the
container lets the embedding, per-channel colouring, lasso gating and QC
histograms carry over unchanged.

Why the transform is applied here and not by FlowKit
----------------------------------------------------
FlowKit's AsinhTransform implements the GatingML asinh parameterization
(param_t / param_m / param_a), which is *not* the arcsinh(x / cofactor)
convention used throughout the mass-cytometry literature. Since the cofactor
determines where the transform is linear-vs-log -- and therefore where a
"deviation from normal" shows up -- the ambiguity is not acceptable. The
transform is applied explicitly on the array, and its parameters are recorded so
a downstream comparison can verify sample and reference were treated identically.

Compensation, by contrast, is delegated to FlowKit: parsing the spillover string
and inverting the matrix over the right channel subset is fiddly, and FlowKit
does it correctly.
"""

from __future__ import annotations

import os
import re
from typing import Any

import anndata as ad
import numpy as np
import pandas as pd

from .panel import (
    canonical_marker,
    is_scatter_channel,
    is_viability_channel,
    panel_fingerprint,
)

# Standard arcsinh cofactors. Mass cytometry counts are small integers, so a
# cofactor of 5 keeps the low end linear; fluorescence intensities span roughly
# five decades and conventionally use 150.
COFACTOR_MASS = 5.0
COFACTOR_FLUOR = 150.0

# $CYT / $CYTSN substrings that identify a mass cytometer.
_MASS_CYT_HINTS = (
    "cytof", "helios", "fluidigm", "dvs", "standard biotools", "hyperion",
)

# FCS TEXT keys worth keeping for provenance. FlowKit lowercases them and strips
# the leading "$".
_PROVENANCE_KEYS = (
    "cyt", "cytsn", "date", "btim", "etim", "src", "fil", "sys", "inst",
    "op", "proj", "smno", "tot", "par", "vol", "mode", "datatype",
)

_SPILL_KEYS = ("spillover", "spill", "comp")


def _detect_mass_cytometry(metadata: dict) -> bool:
    """True when the TEXT segment identifies a mass cytometer (CyTOF)."""
    blob = " ".join(
        str(metadata.get(k, "")) for k in ("cyt", "cytsn", "sys", "inst")
    ).lower()
    if any(h in blob for h in _MASS_CYT_HINTS):
        return True
    # Fallback: CyTOF panels name channels after metal isotopes (e.g. Nd142Di)
    # rather than optical detectors.
    pnn = " ".join(
        str(v) for k, v in metadata.items() if re.fullmatch(r"p\d+n", str(k))
    )
    return bool(re.search(r"[A-Z][a-z]\d{2,3}Di", pnn))


def _find_spillover(metadata: dict) -> Any | None:
    """Return the raw spillover value from the TEXT segment, if present."""
    for key in _SPILL_KEYS:
        val = metadata.get(key)
        if val is None:
            continue
        if isinstance(val, str) and not val.strip():
            continue
        return val
    return None


def _classify_channel(pnn: str, pns: str) -> str:
    """Label a channel as "scatter", "viability" or "marker".

    Scatter/time/bead channels describe the event physically; viability stains
    are exclusion gates. Neither is a phenotypic marker, and lumping them in
    would let instrument drift masquerade as a biological deviation.
    """
    for name in (pns, pnn):
        if name and is_scatter_channel(name):
            return "scatter"
    for name in (pns, pnn):
        if name and is_viability_channel(name):
            return "viability"
    return "marker"


def _dedupe(names: list[str]) -> list[str]:
    """Make display names unique, preserving order (CD3, CD3.1, ...).

    Panels do occasionally repeat a label across channels. AnnData requires
    unique var_names, and a silent collision would merge two channels.
    """
    seen: dict[str, int] = {}
    out: list[str] = []
    for n in names:
        base = n or "unnamed"
        if base in seen:
            seen[base] += 1
            out.append(f"{base}.{seen[base]}")
        else:
            seen[base] = 0
            out.append(base)
    return out


def read_fcs(
    path: str,
    *,
    filename: str | None = None,
    cofactor: float | None = None,
    compensate: bool | None = None,
) -> ad.AnnData:
    """Parse one FCS file into a transformed AnnData object.

    Parameters
    ----------
    path
        Location of the .fcs file on disk.
    filename
        Original client-side name, recorded for provenance (``path`` is usually
        a temp file).
    cofactor
        arcsinh cofactor. Defaults to 5 for mass cytometry and 150 for
        fluorescence, chosen from the instrument named in the TEXT segment.
    compensate
        Force spillover compensation on or off. By default it is applied
        whenever the file carries a spillover matrix and the instrument is not a
        mass cytometer.

    Returns
    -------
    AnnData
        ``X`` is the arcsinh-transformed matrix (events x channels, float32).
        ``var_names`` are marker labels where the file provides them (PnS),
        falling back to the channel name (PnN). ``uns["askcell"]`` records the
        panel fingerprint and every preprocessing decision.
    """
    import flowkit  # imported lazily: heavy, and only ingest needs it

    # subsample=1 stops FlowKit building its own 10k-event subsample on load. We
    # always read the full event array and subsample later, for display only.
    sample = flowkit.Sample(path, subsample=1)
    metadata = dict(sample.metadata)

    pnn_labels = [str(s) for s in sample.pnn_labels]
    raw_pns = sample.pns_labels or [""] * len(pnn_labels)
    pns_labels = [str(s or "").strip() for s in raw_pns]

    is_mass = _detect_mass_cytometry(metadata)
    spillover = _find_spillover(metadata)

    # ---- compensation ----------------------------------------------------- #
    if compensate is None:
        compensate = bool(spillover) and not is_mass
    comp_applied = False
    comp_error: str | None = None
    source = "raw"
    if compensate:
        if not spillover:
            comp_error = "no spillover matrix in the FCS TEXT segment"
        else:
            try:
                sample.apply_compensation(spillover)
                comp_applied = True
                source = "comp"
            except Exception as exc:  # keep ingest alive; record the failure
                comp_error = f"{type(exc).__name__}: {exc}"

    events = np.asarray(sample.get_events(source=source), dtype=np.float64)

    # ---- transform -------------------------------------------------------- #
    if cofactor is None:
        cofactor = COFACTOR_MASS if is_mass else COFACTOR_FLUOR
    cofactor = float(cofactor)
    if cofactor <= 0:
        raise ValueError("cofactor must be positive")

    channel_types = [
        _classify_channel(pnn, pns) for pnn, pns in zip(pnn_labels, pns_labels)
    ]

    # Scatter/time channels stay on their native linear scale -- arcsinh on
    # FSC-A would distort the debris and doublet gates that depend on it.
    X = events.copy()
    transform_cols = [i for i, t in enumerate(channel_types) if t != "scatter"]
    if transform_cols:
        idx = np.asarray(transform_cols)
        X[:, idx] = np.arcsinh(X[:, idx] / cofactor)

    # ---- assemble --------------------------------------------------------- #
    display_names = [
        pns if pns else pnn for pnn, pns in zip(pnn_labels, pns_labels)
    ]
    var = pd.DataFrame(
        {
            "channel": pnn_labels,
            "marker": pns_labels,
            "channel_type": channel_types,
            "canonical": [canonical_marker(n) for n in display_names],
        },
        index=pd.Index(_dedupe(display_names)),
    )

    adata = ad.AnnData(X=X.astype(np.float32), var=var)
    adata.obs_names = [str(i) for i in range(adata.n_obs)]

    marker_labels = [
        d for d, t in zip(display_names, channel_types) if t == "marker"
    ]
    fingerprint, canon = panel_fingerprint(marker_labels)

    adata.uns["askcell"] = {
        "modality": "mass_cytometry" if is_mass else "flow_cytometry",
        "filename": filename or os.path.basename(path),
        "n_events": int(adata.n_obs),
        "n_channels": int(adata.n_vars),
        "panel_fingerprint": fingerprint,
        "panel_markers": canon,
        "preprocessing": {
            "compensation": {
                "applied": comp_applied,
                "requested": bool(compensate),
                "available": bool(spillover),
                "error": comp_error,
            },
            "transform": {
                "kind": "arcsinh",
                "cofactor": cofactor,
                "applied_to": [display_names[i] for i in transform_cols],
                "excluded": [
                    d
                    for d, t in zip(display_names, channel_types)
                    if t == "scatter"
                ],
            },
        },
        "instrument": {
            k: str(metadata[k]) for k in _PROVENANCE_KEYS if k in metadata
        },
    }
    return adata
