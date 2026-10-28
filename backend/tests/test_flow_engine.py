"""
test_flow_engine.py
====================
Unit tests for FlowSession's reference-selection logic.

choose_reference() is tested directly, with small synthetic NormalReference
objects, rather than through full FCS files: the thing worth pinning down is
the *selection rule* (try the active reference, then each alternate, in
order), independent of parsing or gating.
"""

from __future__ import annotations

import numpy as np

from app.flow import NormalReference
from app.flow_engine import choose_reference


def _tiny_reference(markers: list[str]) -> NormalReference:
    n = len(markers)
    return NormalReference(
        markers=markers,
        center=np.zeros(n, dtype=np.float32),
        scale=np.ones(n, dtype=np.float32),
        cloud=np.zeros((5, n), dtype=np.float32),
        threshold=1.0,
    )


DEFAULT = _tiny_reference(["CD45", "CD34", "CD19", "CD5", "CD7"])
DDPR = _tiny_reference(["CD45", "CD34", "CD19", "CD10", "PAX5"])


def test_matches_primary_reference_without_touching_alternates():
    name, ref, missing = choose_reference(
        ["CD45", "CD34", "CD19", "CD5", "CD7", "extra"],
        {"CD45", "CD34", "CD19", "CD5", "CD7"},
        DEFAULT, "default", {"ddpr": DDPR},
    )
    assert (name, ref, missing) == ("default", DEFAULT, [])


def test_falls_back_to_an_alternate_whose_canonical_panel_matches():
    """Regression: a specimen acquired on a different panel than the active
    reference used to be refused outright, even when a registered alternate
    reference was built on exactly that panel (e.g. real DDPR CyTOF data
    against AskCell's default B-ALL differential panel). The raw label list
    ("HLA-DR") deliberately does not literally contain the alt reference's
    canonical tokens ("HLADR", "PAX5") -- only the canonical set does, which
    is what a real upload's labels would need to be matched through.
    """
    name, ref, missing = choose_reference(
        ["CD45", "CD34", "CD19", "CD10", "HLA-DR", "pS6"],
        {"CD45", "CD34", "CD19", "CD10", "PAX5", "HLADR"},
        DEFAULT, "default", {"ddpr": DDPR},
    )
    assert (name, ref, missing) == ("ddpr", DDPR, [])


def test_reports_missing_against_primary_when_nothing_matches():
    name, ref, missing = choose_reference(
        ["CD45", "CD34"], {"CD45", "CD34"}, DEFAULT, "default", {"ddpr": DDPR},
    )
    assert name == "default"
    assert ref is DEFAULT
    assert set(missing) == {"CD19", "CD5", "CD7"}


def test_no_alternates_registered_behaves_as_before():
    name, ref, missing = choose_reference(
        ["CD45", "CD34"], {"CD45", "CD34"}, DEFAULT, "default", {},
    )
    assert name == "default"
    assert ref is DEFAULT
    assert set(missing) == {"CD19", "CD5", "CD7"}
