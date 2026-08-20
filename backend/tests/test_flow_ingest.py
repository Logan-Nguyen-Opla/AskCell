"""
test_flow_ingest.py
===================
Checks on the FCS ingest path and the synthetic fixtures it reads.

Run from ``backend/``::

    .venv/Scripts/python -m pytest tests -v

The fixtures come from ``make_mock_fcs.py``; generate them first if absent.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from app.flow import (
    COFACTOR_FLUOR,
    canonical_marker,
    compare_panels,
    panel_fingerprint,
    read_fcs,
)

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "sample_data")

NORMAL = os.path.join(SAMPLE_DIR, "normal_bm_01.fcs")
OVERT = os.path.join(SAMPLE_DIR, "patient_overt.fcs")
MRD = os.path.join(SAMPLE_DIR, "patient_mrd.fcs")

pytestmark = pytest.mark.skipif(
    not os.path.exists(NORMAL),
    reason="fixtures missing -- run `python make_mock_fcs.py` first",
)


def labels_for(path: str) -> np.ndarray:
    return np.load(path.replace(".fcs", ".labels.npy"), allow_pickle=True)


# --------------------------------------------------------------------------- #
# Marker canonicalization
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("CD3", "CD3"),
        ("cd3", "CD3"),
        ("CD 3", "CD3"),
        ("APC-CD8a", "CD8A"),
        ("Anti-CD19", "CD19"),
        ("CD19-FITC", "CD19"),
        ("HLA-DR", "HLADR"),
        ("Live/Dead", "LIVEDEAD"),
    ],
)
def test_canonical_marker(raw, expected):
    assert canonical_marker(raw) == expected


def test_canonical_marker_keeps_metal_only_channel():
    """A CyTOF channel named only for its isotope must not collapse to empty."""
    assert canonical_marker("Nd142Di") == "ND142DI"


@pytest.mark.parametrize("raw", ["CD 3", "CD-3", "CD 45", "CD 8a", "cd 19"])
def test_cd_prefix_survives_canonicalization(raw):
    """Regression: "Cd" is Cadmium as well as the CD antigen prefix.

    Listing bare element symbols as strippable conjugate tokens reduced "CD 3"
    to "3", so every spaced or hyphenated CD marker mis-fingerprinted and would
    have failed to match its own reference panel.
    """
    assert canonical_marker(raw).startswith("CD")


def test_unlabelled_detector_channels_stay_distinct():
    """All-conjugate names must not collapse onto the same token."""
    assert canonical_marker("PE-Cy7-A") != canonical_marker("APC-Cy7-A")


def test_fingerprint_is_order_independent():
    a, _ = panel_fingerprint(["CD3", "CD19", "CD45"])
    b, _ = panel_fingerprint(["CD45", "CD3", "CD19"])
    assert a == b


def test_fingerprint_ignores_scatter():
    a, _ = panel_fingerprint(["CD3", "CD19"])
    b, _ = panel_fingerprint(["FSC-A", "SSC-A", "CD3", "CD19", "Time"])
    assert a == b


def test_fingerprint_distinguishes_different_panels():
    a, _ = panel_fingerprint(["CD3", "CD19"])
    b, _ = panel_fingerprint(["CD3", "CD20"])
    assert a != b


# --------------------------------------------------------------------------- #
# Ingest
# --------------------------------------------------------------------------- #
def test_read_fcs_shape_and_var():
    adata = read_fcs(NORMAL)
    assert adata.n_obs == 60_000
    assert adata.n_vars == 17          # 14 markers + 3 scatter

    # Markers are addressable by antigen, not by detector name.
    for antigen in ("CD45", "CD19", "CD10", "CD34", "CD3"):
        assert antigen in adata.var_names

    types = adata.var["channel_type"].value_counts().to_dict()
    assert types["scatter"] == 3
    assert types["viability"] == 1     # Live/Dead
    assert types["marker"] == 13


def test_scatter_left_untransformed():
    """FSC/SSC must stay linear -- the doublet gate depends on the raw ratio."""
    adata = read_fcs(NORMAL)
    fsc = adata[:, "FSC-A"].X.ravel()
    cd45 = adata[:, "CD45"].X.ravel()
    assert fsc.max() > 10_000          # still on the native 18-bit scale
    assert cd45.max() < 20             # arcsinh compresses to single digits


def test_transform_is_recorded_and_reproducible():
    adata = read_fcs(NORMAL)
    tf = adata.uns["askcell"]["preprocessing"]["transform"]
    assert tf["kind"] == "arcsinh"
    assert tf["cofactor"] == COFACTOR_FLUOR
    assert "FSC-A" in tf["excluded"]
    assert "CD45" in tf["applied_to"]

    # Recomputing the transform from the recorded parameters must reproduce X.
    import flowkit
    sample = flowkit.Sample(NORMAL, subsample=1)
    sample.apply_compensation(sample.metadata["spillover"])
    raw = np.asarray(sample.get_events(source="comp"))
    col = list(adata.var_names).index("CD45")
    expected = np.arcsinh(raw[:, col] / tf["cofactor"])
    np.testing.assert_allclose(adata[:, "CD45"].X.ravel(), expected,
                               rtol=1e-5, atol=1e-5)


def test_cofactor_override():
    a = read_fcs(NORMAL, cofactor=5.0)
    assert a.uns["askcell"]["preprocessing"]["transform"]["cofactor"] == 5.0
    with pytest.raises(ValueError):
        read_fcs(NORMAL, cofactor=0)


def test_compensation_applied_when_available():
    adata = read_fcs(NORMAL)
    comp = adata.uns["askcell"]["preprocessing"]["compensation"]
    assert comp["available"] is True
    assert comp["applied"] is True
    assert comp["error"] is None


def test_instrument_provenance_captured():
    adata = read_fcs(NORMAL)
    inst = adata.uns["askcell"]["instrument"]
    assert inst["cyt"] == "MockFACS-A5"
    assert adata.uns["askcell"]["modality"] == "flow_cytometry"


def test_filename_recorded_separately_from_path():
    adata = read_fcs(NORMAL, filename="uploaded_by_user.fcs")
    assert adata.uns["askcell"]["filename"] == "uploaded_by_user.fcs"


# --------------------------------------------------------------------------- #
# Panel matching -- the precondition for any reference comparison
# --------------------------------------------------------------------------- #
def test_all_fixtures_share_one_panel():
    """Sample and reference must fingerprint identically, or no comparison is
    valid. All fixtures come off the same mock instrument, so they must match."""
    prints = {
        os.path.basename(p): read_fcs(p).uns["askcell"]["panel_fingerprint"]
        for p in (NORMAL, OVERT, os.path.join(SAMPLE_DIR, "patient_normal.fcs"))
    }
    assert len(set(prints.values())) == 1, prints


def test_compare_panels_flags_a_missing_marker():
    result = compare_panels(["CD3", "CD19", "CD10"], ["CD3", "CD19"])
    assert result["compatible"] is False
    assert result["missing_from_reference"] == ["CD10"]
    assert 0 < result["similarity"] < 1


def test_compare_panels_exact_match():
    result = compare_panels(["CD3", "cd19"], ["CD19", "CD 3"])
    assert result["compatible"] is True
    assert result["similarity"] == 1.0


# --------------------------------------------------------------------------- #
# The fixture must actually pose the hard problem
# --------------------------------------------------------------------------- #
def test_blasts_are_not_separable_by_cd10_alone():
    """Guards the fixture's realism.

    If a single-marker threshold cleanly split blasts from hematogones, the mock
    would be a strawman and any detector trained on it would be worthless. CD10
    is the strongest single discriminator by design, and it must still overlap.
    """
    adata = read_fcs(OVERT)
    labels = labels_for(OVERT)
    cd10 = adata[:, "CD10"].X.ravel()

    blast = cd10[labels == "Aberrant B-lymphoblasts"]
    hema = cd10[labels == "Hematogones"]
    assert blast.size > 0 and hema.size > 0

    # Blasts are brighter on average...
    assert blast.mean() > hema.mean()
    # ...but the distributions must still overlap.
    assert hema.max() > blast.min(), "CD10 alone separates the classes"


def test_blasts_are_a_tighter_cluster_than_hematogones():
    """The real discriminator is structure: clonal homogeneity vs a continuum."""
    adata = read_fcs(OVERT)
    labels = labels_for(OVERT)
    markers = ["CD45", "CD19", "CD10", "CD34", "CD38"]
    X = adata[:, markers].X

    blast = X[labels == "Aberrant B-lymphoblasts"]
    hema = X[labels == "Hematogones"]
    # Mean per-marker spread: the clone must be measurably more compact.
    assert blast.std(axis=0).mean() < hema.std(axis=0).mean()


def test_hematogone_maturation_is_correlated():
    """CD10 must fall as CD20 rises -- the continuum that mimics nothing else."""
    adata = read_fcs(OVERT)
    labels = labels_for(OVERT)
    hema = labels == "Hematogones"
    cd10 = adata[hema, "CD10"].X.ravel()
    cd20 = adata[hema, "CD20"].X.ravel()
    assert np.corrcoef(cd10, cd20)[0, 1] < -0.5


def test_mrd_fixture_is_needle_in_haystack():
    """The 0.05% file is the sensitivity floor the detector has to reach."""
    labels = labels_for(MRD)
    n_blasts = int((labels == "Aberrant B-lymphoblasts").sum())
    assert labels.size == 400_000
    assert n_blasts == 200
    assert n_blasts / labels.size < 0.001


def test_specificity_control_has_no_blasts():
    labels = labels_for(os.path.join(SAMPLE_DIR, "patient_normal.fcs"))
    assert not (labels == "Aberrant B-lymphoblasts").any()
    assert (labels == "Hematogones").sum() > 0   # but it does have look-alikes
