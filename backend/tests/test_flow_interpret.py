"""
test_flow_interpret.py
======================
Checks on subtype matching and the agent's report-reading tools.

The central test here is
:func:`test_structure_flips_the_ranking_on_identical_markers`. Ranking on marker
calls alone puts hematogones above B-ALL on a textbook leukaemic clone, because
the two genuinely share an immunophenotype. Only cluster geometry separates them,
so that behaviour is pinned down rather than left to drift.
"""

from __future__ import annotations

import json
import os

import pytest

from app.flow.interpret import (
    ENTITIES,
    call_marker,
    interpret_population,
    interpret_report,
)

SAMPLE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data"
)
OVERT = os.path.join(SAMPLE_DIR, "patient_overt.fcs")
CACHE = os.path.join(SAMPLE_DIR, "reference.npz")

# The B-ALL phenotype the detector actually recovers from patient_overt.fcs.
BALL_Z = {
    "CD45": -1.71, "CD34": 6.11, "CD19": 2.56, "CD10": 4.93, "CD20": -0.30,
    "CD3": -0.35, "CD5": -0.33, "CD7": -0.40, "CD13": -1.27, "CD33": -1.17,
    "CD117": -0.30, "HLA-DR": 0.55, "CD38": -0.55,
}


# --------------------------------------------------------------------------- #
# Marker calls
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "z,expected",
    [
        (6.0, "bright"), (2.5, "bright"), (1.5, "positive"), (1.2, "positive"),
        (0.5, "equivocal"), (0.0, "equivocal"), (-0.5, "equivocal"),
        (-0.8, "negative"), (-3.0, "negative"), (None, "unknown"),
    ],
)
def test_call_marker(z, expected):
    assert call_marker(z) == expected


def test_equivocal_band_is_wide_enough_to_be_useful():
    """"Can't tell" must be reachable.

    If every z-score resolved to positive or negative, the module would present
    coin-flips as calls.
    """
    assert call_marker(0.6) == "equivocal"
    assert call_marker(-0.6) == "equivocal"


# --------------------------------------------------------------------------- #
# The core behaviour
# --------------------------------------------------------------------------- #
def test_structure_flips_the_ranking_on_identical_markers():
    """Same phenotype, opposite conclusion, decided purely by compactness.

    This is the project's central claim made testable. B-ALL and hematogones
    share a marker pattern; a tight cluster means clone, a diffuse spread means
    normal maturation.
    """
    clonal = interpret_population({"marker_z": BALL_Z}, compactness=0.10)
    diffuse = interpret_population({"marker_z": BALL_Z}, compactness=1.40)

    assert clonal["candidates"][0]["short"] == "B-ALL"
    assert diffuse["candidates"][0]["short"] == "Hematogones"

    # The phenotype score itself must be unchanged -- only structure moved.
    def phen(res, short):
        return next(c["phenotype_match"] for c in res["candidates"] if c["short"] == short)

    assert phen(clonal, "B-ALL") == phen(diffuse, "B-ALL")
    assert phen(clonal, "Hematogones") == phen(diffuse, "Hematogones")


def test_benign_lookalike_is_demoted_not_hidden():
    """Hematogones must stay in the list on a clonal population.

    "This is what it could be mistaken for" is useful to a reader; silently
    dropping it would hide the one differential that matters most.
    """
    res = interpret_population({"marker_z": BALL_Z}, compactness=0.10)
    shorts = [c["short"] for c in res["candidates"]]
    assert "Hematogones" in shorts
    assert shorts.index("B-ALL") < shorts.index("Hematogones")


def test_structure_reason_is_stated():
    res = interpret_population({"marker_z": BALL_Z}, compactness=0.10)
    hema = next(c for c in res["candidates"] if c["short"] == "Hematogones")
    assert "tightly clustered" in hema["structure_reason"]
    ball = next(c for c in res["candidates"] if c["short"] == "B-ALL")
    assert "consistent" in ball["structure_reason"]


def test_unknown_compactness_penalises_nobody():
    """Missing structure information must not silently favour one entity."""
    res = interpret_population({"marker_z": BALL_Z}, compactness=None)
    assert res["structure"] == "unknown"
    for c in res["candidates"]:
        assert c["structure_consistency"] == 1.0
        assert c["match"] == c["phenotype_match"]


# --------------------------------------------------------------------------- #
# Phenotype matching
# --------------------------------------------------------------------------- #
def test_ball_phenotype_ranks_ball_first():
    res = interpret_population({"marker_z": BALL_Z}, compactness=0.10)
    assert res["candidates"][0]["short"] == "B-ALL"
    assert res["candidates"][0]["lineage"] == "B-lymphoid precursor"


def test_t_lineage_phenotype_ranks_tall_first():
    z = dict.fromkeys(BALL_Z, -0.2)
    z.update({"CD7": 4.0, "CD5": 3.0, "CD3": 2.5, "CD34": 1.5, "CD45": -1.0,
              "CD19": -1.5, "CD10": -0.5})
    res = interpret_population({"marker_z": z}, compactness=0.15)
    assert res["candidates"][0]["short"] == "T-ALL"


def test_myeloid_phenotype_ranks_aml_first():
    z = dict.fromkeys(BALL_Z, -0.2)
    z.update({"CD117": 3.5, "CD13": 2.5, "CD33": 2.5, "CD34": 2.0,
              "HLA-DR": 2.0, "CD45": -1.0, "CD19": -1.5, "CD3": -1.5})
    res = interpret_population({"marker_z": z}, compactness=0.2)
    assert res["candidates"][0]["short"] == "AML"


def test_hla_dr_and_cd34_negative_myeloid_raises_apl():
    """The one pattern where phenotype alone changes what happens next.

    A myeloid population that is HLA-DR AND CD34 negative suggests APL, which
    carries a coagulopathy risk and its own targeted treatment.
    """
    z = dict.fromkeys(BALL_Z, -0.2)
    z.update({"CD33": 4.0, "CD13": 2.5, "CD117": 2.0,
              "HLA-DR": -2.0, "CD34": -2.0, "CD19": -1.5, "CD3": -1.5})
    res = interpret_population({"marker_z": z}, compactness=0.2)
    shorts = [c["short"] for c in res["candidates"]]
    assert "APL" in shorts
    assert shorts.index("APL") <= 1
    apl = next(c for c in res["candidates"] if c["short"] == "APL")
    assert any("PML::RARA" in t for t in apl["confirm_with"])


def test_cd5_positive_mature_b_raises_cll():
    z = dict.fromkeys(BALL_Z, -0.2)
    z.update({"CD19": 3.0, "CD5": 3.0, "CD20": -0.3, "CD10": -1.5,
              "CD34": -1.5, "CD45": 0.5})
    res = interpret_population({"marker_z": z}, compactness=0.2)
    assert res["candidates"][0]["short"] == "CLL/SLL"


# --------------------------------------------------------------------------- #
# Honesty guarantees
# --------------------------------------------------------------------------- #
def test_every_entity_names_confirmatory_tests():
    """Flow narrows the field; it does not conclude.

    An entity with no confirmatory tests listed would present a hypothesis as an
    answer.
    """
    for entity in ENTITIES:
        assert entity["confirm"], f"{entity['short']} lists no confirmatory tests"
        assert entity["note"]


def test_result_always_requires_confirmation():
    res = interpret_population({"marker_z": BALL_Z}, compactness=0.10)
    assert res["requires_confirmation"] is True
    assert "does not classify" in res["disclaimer"]


def test_marker_z_is_carried_through_for_checking():
    """The z-scores behind every call must be visible, not just the labels."""
    res = interpret_population({"marker_z": BALL_Z}, compactness=0.10)
    assert res["marker_z"] == BALL_Z
    assert res["calls"]["CD34"] == "bright"
    assert res["calls"]["CD13"] == "negative"


def test_empty_report_interprets_cleanly():
    assert interpret_report({"ok": True, "populations": []}) == {"populations": []}
    bad = interpret_report({"ok": False, "error": "panel_mismatch"})
    assert bad["error"] == "panel_mismatch"


# --------------------------------------------------------------------------- #
# Agent tools
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(
    not (os.path.exists(OVERT) and os.path.exists(CACHE)),
    reason="fixtures missing -- run make_mock_fcs.py then run_detection.py",
)
class TestAgentTools:
    @pytest.fixture(autouse=True)
    def loaded(self):
        from app.flow import NormalReference
        from app.flow_engine import flow_session

        flow_session.set_reference(NormalReference.load(CACHE))
        flow_session.load_sample_from_path(OVERT, "patient_overt.fcs")
        yield flow_session

    def test_every_tool_returns_json_serialisable_output(self):
        """Tool results are JSON-encoded before being sent back to the model.

        A stray numpy scalar anywhere in a report would raise at encode time,
        mid-conversation.
        """
        from app import flow_agent

        for name, fn in flow_agent.TOOL_REGISTRY.items():
            out = fn(label=0) if "label" in fn.__code__.co_varnames else fn()
            json.dumps(out)  # must not raise

    def test_candidate_entities_tool_is_populated(self):
        """Regression: a key rename left this returning an empty differential.

        _population() exposes marker values as ``marker_z_all`` for the agent,
        but interpret_population() reads ``marker_z``. Passing one to the other
        produced no candidates and no error -- indistinguishable from "nothing
        resembles this population".
        """
        from app import flow_agent

        out = flow_agent.TOOL_REGISTRY["get_candidate_entities"](label=0)
        assert out["candidates"], "differential is empty"
        assert out["candidates"][0]["short"] == "B-ALL"

    def test_false_flag_rate_is_rounded(self):
        """The agent quotes figures verbatim, so 100.0 - 99.9 must not leak."""
        from app import flow_agent

        rate = flow_agent.TOOL_REGISTRY["get_detection_summary"]()[
            "expected_false_flag_rate_pct"
        ]
        assert rate == 0.1
        assert len(str(rate)) < 8

    def test_tools_report_missing_state_rather_than_raising(self):
        """A tool error becomes a message to the model, so it must be readable."""
        from app import flow_agent
        from app.flow_engine import flow_session

        flow_session._clear_sample()
        for name in ("get_detection_summary", "get_population_phenotype",
                     "get_candidate_entities"):
            fn = flow_agent.TOOL_REGISTRY[name]
            out = fn(label=0) if "label" in fn.__code__.co_varnames else fn()
            assert "error" in out
            assert "specimen" in out["error"].lower()

    def test_bad_population_label_is_handled(self):
        from app import flow_agent

        for name in ("get_population_phenotype", "get_candidate_entities"):
            out = flow_agent.TOOL_REGISTRY[name](label=99)
            assert "error" in out

    def test_system_prompt_forbids_diagnosis_and_invention(self):
        """The two constraints that matter are stated, not assumed."""
        from app import flow_agent

        p = flow_agent.SYSTEM_PROMPT
        assert "Never give a diagnosis" in p
        assert "Never state a number that did not come from a tool call" in p
        assert "Never give treatment advice" in p
