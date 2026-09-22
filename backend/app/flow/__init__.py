"""Flow / mass cytometry ingest, reference building and detection for AskCell."""

from .detect import detect
from .interpret import call_marker, interpret_population, interpret_report
from .fcs_ingest import COFACTOR_FLUOR, COFACTOR_MASS, read_fcs
from .panel import (
    canonical_marker,
    compare_panels,
    is_scatter_channel,
    is_viability_channel,
    panel_fingerprint,
)
from .qc import gate, marker_matrix
from .reference import NormalReference, fit_reference, fit_reference_from_files

__all__ = [
    # ingest
    "read_fcs",
    "COFACTOR_FLUOR",
    "COFACTOR_MASS",
    # panel identity
    "canonical_marker",
    "compare_panels",
    "is_scatter_channel",
    "is_viability_channel",
    "panel_fingerprint",
    # quality control
    "gate",
    "marker_matrix",
    # reference model
    "NormalReference",
    "fit_reference",
    "fit_reference_from_files",
    # detection
    "detect",
    # interpretation
    "interpret_report",
    "interpret_population",
    "call_marker",
]
