"""
flow_agent.py
=============
Claude agent for explaining a cytometry result in plain language and answering
follow-up questions about it.

Design
------
The agent has no access to raw events and cannot compute anything. It reads the
finished report through tools and explains it. Everything numeric it says has to
come from a tool call, because the one failure mode that matters here is a
fluent, confident paragraph containing a number nobody measured.

The system prompt therefore does two jobs: it forbids inventing figures, and it
forbids diagnosing. Those are different constraints. The first is about
accuracy; the second is about scope -- immunophenotype cannot classify a
haematological malignancy on its own, so a confident-sounding diagnosis would be
wrong even if every number in it were right.
"""

from __future__ import annotations

import json
import os

import anthropic

from .flow_engine import flow_session

# Opus 5 with adaptive thinking. This is reasoning over a multi-part result --
# two detection stages, a structural argument, and a ranked differential where
# the top two candidates can be distinguished only by cluster geometry. A
# cheaper model handles the summary fine and mishandles exactly the part that
# matters, which is explaining *why* the benign lookalike was ruled out.
MODEL = "claude-opus-5"
MAX_TOKENS = 4096

SYSTEM_PROMPT = """\
You are AskCell, explaining a flow-cytometry result to someone who is not a \
haematologist.

WHAT THE SOFTWARE DID
It compared every cell in a patient specimen against a reference built from \
healthy specimens, in two stages:
  Stage 1 flagged cells far from any healthy cell. The threshold is calibrated \
so roughly 0.1% of healthy cells are flagged, so stage 1 ALWAYS flags some \
cells, including in a completely healthy person.
  Stage 2 kept only flagged cells that form a dense cluster. This is the real \
test: a cancerous population descends from one cell and is therefore tightly \
clustered, while stage-1 false flags are scattered.

HARD RULES
1. Never state a number that did not come from a tool call. If you do not have \
a figure, say so and call the relevant tool.
2. Never give a diagnosis. Immunophenotype alone cannot classify a blood \
cancer -- morphology, cytogenetics and molecular tests are required. You may \
say a pattern "resembles" or "is consistent with" an entity, and you should \
name the confirmatory tests that would settle it.
3. Never give treatment advice or a prescription. You may describe what \
published literature says is used for an entity, clearly framed as background.
4. If the result is negative, say so plainly and do not hedge it into sounding \
worrying. A healthy specimen with scattered stage-1 flags is a NORMAL result \
and should be described as one.
5. Say what would change the answer -- a low cell count, a poor QC pass rate, \
an intermediate compactness. Uncertainty stated up front is more useful than \
confidence.

STYLE
Plain language, short paragraphs. Explain jargon the first time you use it \
(a "blast" is an immature cell; "CD10" is a protein on the cell surface). \
Bold the key figures. Do not open with a preamble about what you are about to \
do -- answer directly. Aim for 150-250 words unless asked for more.

This is a research and educational tool, not a diagnostic device. Mention that \
once, at the end, not in every paragraph.\
"""

TOOLS = [
    {
        "name": "get_detection_summary",
        "description": (
            "The headline result for the loaded specimen: verdict, the "
            "percentage of abnormal cells, both stage counts, and quality-"
            "control figures. Call this first for any question about the result."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_population_phenotype",
        "description": (
            "For one detected population: its size, how tightly clustered it is "
            "relative to normal cells, and every marker's deviation from the "
            "healthy reference in standard deviations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {
                    "type": "integer",
                    "description": "Population label from get_detection_summary.",
                }
            },
            "required": ["label"],
        },
    },
    {
        "name": "get_candidate_entities",
        "description": (
            "The ranked differential for one population: which entities its "
            "marker pattern resembles, the evidence for and against each, "
            "whether the population's structure fits, and the confirmatory "
            "tests each would need. Use this for 'what kind is it' questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {
                    "type": "integer",
                    "description": "Population label from get_detection_summary.",
                }
            },
            "required": ["label"],
        },
    },
    {
        "name": "get_reference_info",
        "description": (
            "What the specimen was compared against: how many healthy "
            "specimens, how many reference cells, which markers, and the "
            "calibrated threshold with its expected false-flag rate."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]


# --------------------------------------------------------------------------- #
# Tool implementations
# --------------------------------------------------------------------------- #
def _summary() -> dict:
    if not flow_session.has_sample():
        return {"error": "No specimen has been analysed yet."}
    r = flow_session.public_report()
    return {
        "filename": flow_session.sample_name,
        "verdict": r["verdict"],
        "summary": r["summary"],
        "abnormal_pct": r["abnormal_pct"],
        "n_abnormal": r["n_abnormal"],
        "n_analyzed": r["n_analyzed"],
        "stage1_flagged": r["stage1_flagged"],
        "stage1_flagged_pct": r["stage1_flagged_pct"],
        "noise_removed_by_clustering": r["noise_removed_by_clustering"],
        "populations": [
            {
                "label": p["label"],
                "n_events": p["n_events"],
                "pct": p["pct_of_analyzed"],
                "is_clonal": p["is_clonal"],
                "compactness_vs_normal": p["compactness_vs_normal"],
            }
            for p in r["populations"]
        ],
        "qc": {
            "n_acquired": r["qc"]["n_input"] if r.get("qc") else None,
            "n_kept": r["qc"]["n_kept"] if r.get("qc") else None,
            "pct_kept": r["qc"]["pct_kept"] if r.get("qc") else None,
            "warning": r["qc"].get("warning") if r.get("qc") else None,
        },
        # Rounded: the agent is instructed to quote figures verbatim, and
        # 100.0 - 99.9 is 0.09999999999999432 in binary floating point.
        "expected_false_flag_rate_pct": round(
            100.0 - r["parameters"]["threshold_percentile"], 4
        ),
    }


def _population(label: int) -> dict:
    if not flow_session.has_sample():
        return {"error": "No specimen has been analysed yet."}
    for p in flow_session.public_report()["populations"]:
        if p["label"] == label:
            return {
                "label": p["label"],
                "n_events": p["n_events"],
                "pct_of_analyzed": p["pct_of_analyzed"],
                "is_clonal": p["is_clonal"],
                "compactness_vs_normal": p["compactness_vs_normal"],
                "deviant_markers": p["deviant_markers"],
                "marker_z_all": p.get("marker_z", {}),
            }
    return {"error": f"No population with label {label}."}


def _entities(label: int) -> dict:
    """Ranked differential for one population.

    Reads the population straight from the report rather than via
    :func:`_population`, which renames ``marker_z`` to ``marker_z_all`` for the
    agent's benefit. Passing that renamed dict to ``interpret_population`` left
    it unable to find any marker values, so it returned an empty differential
    with no error -- a silent failure that looked like "nothing resembles this".
    """
    from .flow.interpret import interpret_population

    if not flow_session.has_sample():
        return {"error": "No specimen has been analysed yet."}
    for p in flow_session.public_report()["populations"]:
        if p["label"] == label:
            return interpret_population(
                p, compactness=p.get("compactness_vs_normal")
            )
    return {"error": f"No population with label {label}."}


def _reference() -> dict:
    if not flow_session.has_reference():
        return {"error": "No healthy reference is loaded."}
    return flow_session.reference.summary()


TOOL_REGISTRY = {
    "get_detection_summary": lambda: _summary(),
    "get_population_phenotype": lambda label: _population(int(label)),
    "get_candidate_entities": lambda label: _entities(int(label)),
    "get_reference_info": lambda: _reference(),
}

_MAX_TOOL_ROUNDS = 6

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to backend/.env to enable "
                "the explanation feature. Detection itself does not need a key."
            )
        _client = anthropic.Anthropic()
    return _client


def _text(message) -> str:
    return "".join(
        b.text for b in message.content if b.type == "text"
    ).strip()


EXPLAIN_PROMPT = (
    "Explain this specimen's result to someone with no haematology training. "
    "Cover: what was found (or not found), how confident that is and why, what "
    "the marker pattern resembles, and what would need to be done to confirm "
    "it. If nothing abnormal was found, say so clearly and explain why the "
    "stage-1 flags do not change that."
)


def run_flow_chat(message: str, history: list[dict] | None = None) -> dict:
    """Run one turn through Claude with the report tools available.

    Returns ``{"reply": str, "tools_used": [...]}`` so the caller can show which
    parts of the report the answer was actually built from.
    """
    client = _get_client()
    messages: list[dict] = list(history or [])
    messages.append({"role": "user", "content": message})
    used: list[str] = []

    for _ in range(_MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            thinking={"type": "adaptive"},
            messages=messages,
        )

        if response.stop_reason == "refusal":
            return {
                "reply": (
                    "I can't respond to that. Try asking about the detection "
                    "result itself."
                ),
                "tools_used": used,
                "refused": True,
            }

        if response.stop_reason != "tool_use":
            return {"reply": _text(response), "tools_used": used}

        messages.append({"role": "assistant", "content": response.content})

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            fn = TOOL_REGISTRY.get(block.name)
            if fn is None:
                out = {"error": f"Unknown tool '{block.name}'."}
            else:
                try:
                    out = fn(**dict(block.input))
                    used.append(block.name)
                except Exception as exc:
                    out = {"error": f"{type(exc).__name__}: {exc}"}
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(out, default=str),
                }
            )
        messages.append({"role": "user", "content": results})

    # Tool budget exhausted: ask once more with no tools so the user still gets
    # an answer built from what was already gathered.
    final = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        messages=messages,
    )
    return {"reply": _text(final), "tools_used": used}


def explain_current() -> dict:
    """One-shot plain-language interpretation of the loaded specimen."""
    return run_flow_chat(EXPLAIN_PROMPT)
