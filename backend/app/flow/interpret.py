"""
interpret.py
============
Turn a detected population's phenotype into a ranked list of candidate
entities, with the evidence for and against each one.

What this is
------------
The detector answers "is there an abnormal population, and how big". This module
answers "what does its marker pattern most resemble". Those are different
questions with very different confidence attached, and conflating them is the
main way a tool like this becomes misleading.

What this is not
----------------
**Not a diagnosis.** Immunophenotype alone does not classify a haematological
malignancy. The WHO classification requires morphology, cytogenetics and
molecular findings as well -- two specimens with an identical flow phenotype can
be different diseases with different treatment and different prognosis. What
flow contributes is lineage and maturation stage, which narrows the field and
tells the lab which confirmatory tests to run.

So every result here carries ``requires_confirmation`` and names the tests that
would actually settle it. The output is a hypothesis with its reasoning shown,
not an answer.

Why structure is scored, not just markers
-----------------------------------------
Ranking on the marker pattern alone puts **hematogones above B-ALL** on a
textbook leukaemic clone. That is not a tuning problem, it is the biology: the
two share an immunophenotype closely enough that no weighting of marker calls
reliably separates them. A tool that ranked on markers alone would confidently
label a leukaemia as normal.

What separates them is *structure*. Hematogones are cells progressing through
maturation, so they spread along a continuum; a leukaemic clone descends from one
cell that stopped maturing, so it sits in a tight knot. Every entity therefore
declares the structure it expects (``clonal`` or ``continuum``), and the observed
compactness scales its score. Phenotype and structure are reported separately so
the two halves of the reasoning stay visible.

How the marker calls are made
-----------------------------
Calls come from each marker's mean z-score against the reference -- how far the
population sits from the average cell in healthy marrow, in units of healthy
spread. That is a *relative* call and a genuine approximation: a clinical lab
calls a marker positive against an internal negative population on the same
tube, not against a pooled average.

It works here because the reference average is dominated by cells that do not
express any given marker, so "far above the reference average" tracks "positive"
closely enough to rank candidates. It is not reliable enough to report a call as
fact, which is why the z-score is carried through to the output alongside every
call so a reader can check the reasoning rather than trust the label.
"""

from __future__ import annotations

# z-score cut-points for turning a continuous deviation into a call.
# Deliberately wide in the middle: "can't tell" is a legitimate answer and is
# far more useful than a coin-flip call presented with confidence.
_BRIGHT = 2.5
_POSITIVE = 1.2
_NEGATIVE = -0.8


def call_marker(z: float | None) -> str:
    """Turn a mean z-score into ``bright`` / ``positive`` / ``equivocal`` /
    ``negative`` / ``unknown``."""
    if z is None:
        return "unknown"
    if z >= _BRIGHT:
        return "bright"
    if z >= _POSITIVE:
        return "positive"
    if z <= _NEGATIVE:
        return "negative"
    return "equivocal"


def _is_pos(call: str) -> bool:
    return call in ("bright", "positive")


def _is_neg(call: str) -> bool:
    return call == "negative"


# --------------------------------------------------------------------------- #
# Candidate entities
# --------------------------------------------------------------------------- #
# Each entry lists the markers that support the entity and the markers that
# argue against it. Only entities distinguishable with a general leukaemia
# screening panel are included -- an entity whose defining markers are absent
# from the panel cannot be ranked, and pretending otherwise would invent
# precision the data does not carry.
#
# "confirm" names the tests that would actually establish the entity. This is
# the part that keeps the output honest: flow narrows, it does not conclude.
ENTITIES: list[dict] = [
    {
        "name": "B-lymphoblastic leukaemia / lymphoma (B-ALL)",
        "short": "B-ALL",
        "lineage": "B-lymphoid precursor",
        "expects": "clonal",
        "supports": {"CD19": 3, "CD10": 3, "CD34": 2, "HLA-DR": 1},
        "supports_negative": {"CD20": 2, "CD3": 1, "CD13": 1, "CD33": 1},
        "supports_dim": {"CD45": 2},
        "against": {"CD3": 3, "CD117": 1},
        "confirm": [
            "morphology of a bone marrow aspirate and blast percentage",
            "cytogenetics / FISH (e.g. BCR::ABL1, ETV6::RUNX1, KMT2A rearrangement)",
            "TdT and cytoplasmic CD79a to confirm precursor B lineage",
        ],
        "note": (
            "CD10 brighter than any normal B-cell precursor reaches, with CD20 "
            "absent and CD45 dim, is the classic separation from hematogones. "
            "The genetic subtype -- not the phenotype -- drives prognosis and "
            "treatment intensity."
        ),
    },
    {
        "name": "T-lymphoblastic leukaemia / lymphoma (T-ALL)",
        "short": "T-ALL",
        "lineage": "T-lymphoid precursor",
        "expects": "clonal",
        "supports": {"CD7": 3, "CD5": 2, "CD3": 2, "CD34": 1},
        "supports_negative": {"CD19": 2, "CD13": 1, "CD33": 1},
        "supports_dim": {"CD45": 1},
        "against": {"CD19": 3, "CD10": 1},
        "confirm": [
            "cytoplasmic CD3 (the lineage-defining marker)",
            "morphology and blast percentage",
            "cytogenetics / molecular studies",
            "imaging for a mediastinal mass",
        ],
        "note": (
            "CD7 is the most consistently expressed marker but is not specific "
            "on its own; cytoplasmic CD3 is what defines T lineage and is not "
            "measurable on a surface-stain panel."
        ),
    },
    {
        "name": "Acute myeloid leukaemia (AML)",
        "short": "AML",
        "lineage": "myeloid precursor",
        "expects": "clonal",
        "supports": {"CD117": 3, "CD34": 2, "CD13": 2, "CD33": 2, "HLA-DR": 1},
        "supports_negative": {"CD19": 2, "CD3": 2, "CD10": 1},
        "supports_dim": {"CD45": 1},
        "against": {"CD19": 3, "CD3": 3},
        "confirm": [
            "myeloperoxidase (MPO) by cytochemistry or flow",
            "morphology and blast percentage",
            "cytogenetics and molecular panel (NPM1, FLT3, CEBPA, ...)",
        ],
        "note": (
            "CD117 with CD13/CD33 and no lymphoid markers points at myeloid "
            "lineage. MPO is the confirmatory marker and is not on a surface "
            "panel."
        ),
    },
    {
        "name": "Acute promyelocytic leukaemia (APL) — urgent consideration",
        "short": "APL",
        "lineage": "myeloid precursor (promyelocytic)",
        "expects": "clonal",
        "supports": {"CD117": 2, "CD33": 3, "CD13": 2},
        "supports_negative": {"HLA-DR": 3, "CD34": 3, "CD19": 1, "CD3": 1},
        "supports_dim": {},
        "against": {"HLA-DR": 3, "CD34": 2},
        "confirm": [
            "PML::RARA by FISH, PCR or karyotype — this is the urgent test",
            "coagulation screen (DIC risk)",
            "morphology",
        ],
        "note": (
            "A myeloid phenotype that is HLA-DR negative AND CD34 negative "
            "raises APL specifically. It matters because APL carries a risk of "
            "life-threatening coagulopathy and has its own targeted treatment, "
            "so it is the one pattern where the phenotype changes what happens "
            "next before genetics return."
        ),
    },
    {
        "name": "Chronic lymphocytic leukaemia / small lymphocytic lymphoma",
        "short": "CLL/SLL",
        "lineage": "mature B cell",
        "expects": "clonal",
        "supports": {"CD19": 3, "CD5": 3},
        "supports_negative": {"CD10": 2, "CD34": 2},
        "supports_dim": {"CD20": 2},
        "against": {"CD34": 3, "CD10": 1},
        "confirm": [
            "CD23, and surface kappa/lambda to establish light-chain restriction",
            "FMC7 and CD200",
            "cyclin D1 / SOX11 or FISH for CCND1 to exclude mantle cell lymphoma",
        ],
        "note": (
            "A CD5-positive, CD10-negative mature B population without CD34. "
            "CD23 and light-chain restriction are needed to separate this from "
            "mantle cell lymphoma, and neither is on this panel."
        ),
    },
    {
        "name": "Plasma cell neoplasm (myeloma)",
        "short": "Plasma cell neoplasm",
        "lineage": "plasma cell",
        "expects": "clonal",
        "supports": {"CD38": 3},
        "supports_negative": {"CD19": 3, "CD20": 2, "CD34": 2, "CD3": 1},
        "supports_dim": {"CD45": 3},
        "against": {"CD34": 2, "CD3": 2},
        "confirm": [
            "CD138 and CD56",
            "cytoplasmic kappa/lambda for clonality",
            "serum/urine protein electrophoresis and free light chains",
            "marrow morphology and plasma cell percentage",
        ],
        "note": (
            "CD38 very bright with CD45 dim and no CD19 is suggestive, but "
            "CD138 is the marker that identifies plasma cells and is not on "
            "this panel. Treat this as a prompt to run a myeloma panel."
        ),
    },
    {
        "name": "Hematogones (normal B-cell precursors) — not a neoplasm",
        "short": "Hematogones",
        "lineage": "normal B-lymphoid precursor",
        "expects": "continuum",
        "supports": {"CD19": 3, "CD10": 2, "HLA-DR": 1},
        "supports_negative": {"CD3": 1, "CD13": 1, "CD33": 1},
        "supports_dim": {"CD34": 2},
        "against": {},
        "benign": True,
        "confirm": [
            "review the CD10/CD20/CD45 maturation pattern for a continuum",
            "compare against an age-matched normal marrow",
        ],
        "note": (
            "These are normal and expand after chemotherapy or marrow "
            "recovery, and in healthy children. They resemble B-ALL closely. "
            "The separation is structural: hematogones form a smooth maturation "
            "continuum, a leukaemic clone is tightly clustered. Weigh the "
            "population's compactness heavily here, not the marker pattern."
        ),
    },
]


def score_entity(entity: dict, calls: dict[str, str]) -> tuple[float, list[str], list[str]]:
    """Score one entity against the observed marker calls.

    Returns ``(fraction_of_available_evidence_met, for_reasons, against_reasons)``.
    Markers absent from the panel are excluded from both numerator and
    denominator, so an entity is never penalised for a marker nobody measured.
    """
    earned = 0.0
    possible = 0.0
    for_: list[str] = []
    against: list[str] = []

    for marker, weight in entity.get("supports", {}).items():
        call = calls.get(marker, "unknown")
        if call == "unknown":
            continue
        possible += weight
        if _is_pos(call):
            earned += weight
            for_.append(f"{marker} {call}")
        elif _is_neg(call):
            against.append(f"{marker} negative (expected positive)")

    for marker, weight in entity.get("supports_negative", {}).items():
        call = calls.get(marker, "unknown")
        if call == "unknown":
            continue
        possible += weight
        if _is_neg(call):
            earned += weight
            for_.append(f"{marker} negative")
        elif _is_pos(call):
            against.append(f"{marker} {call} (expected negative)")

    for marker, weight in entity.get("supports_dim", {}).items():
        call = calls.get(marker, "unknown")
        if call == "unknown":
            continue
        possible += weight
        if call in ("negative", "equivocal"):
            earned += weight
            for_.append(f"{marker} dim/low")
        elif call == "bright":
            against.append(f"{marker} bright (expected dim)")

    # Hard negatives: a marker that effectively rules the entity out.
    for marker, weight in entity.get("against", {}).items():
        call = calls.get(marker, "unknown")
        if _is_pos(call) and weight >= 3:
            against.append(f"{marker} {call} — argues strongly against")
            earned -= weight

    score = max(earned, 0.0) / possible if possible else 0.0
    return score, for_, against


# Compactness bands, as a multiple of the spread of normal cells.
_CLONAL_BELOW = 0.5      # tighter than this reads as a clone
_DIFFUSE_ABOVE = 1.0     # looser than this reads as a maturing/reactive population

# How much of the final score structure is allowed to move. Phenotype keeps a
# floor (_PHENOTYPE_FLOOR) so a structurally-inconsistent candidate is demoted
# rather than erased -- hematogones must stay visible on a clonal population,
# because "this is the thing it could be mistaken for" is useful to a reader.
_PHENOTYPE_FLOOR = 0.35


def _structure_band(compactness: float | None) -> str:
    if compactness is None:
        return "unknown"
    if compactness < _CLONAL_BELOW:
        return "clonal"
    if compactness > _DIFFUSE_ABOVE:
        return "continuum"
    return "intermediate"


def _structure_consistency(expects: str | None, band: str) -> float:
    """How well the observed structure matches what the entity requires."""
    if band == "unknown" or not expects:
        return 1.0                      # no information: do not penalise
    if expects == band:
        return 1.0
    if band == "intermediate":
        return 0.6
    return 0.1                          # clone where a continuum is required, or vice versa


def interpret_population(population: dict, *, compactness: float | None = None) -> dict:
    """Rank candidate entities for one detected population.

    Ranking combines two independent lines of evidence: how well the marker
    pattern fits, and whether the population's shape is what that entity
    produces. Both are reported, because the combined number alone would hide
    which half of the argument is doing the work.
    """
    marker_z = population.get("marker_z") or {}
    calls = {m: call_marker(z) for m, z in marker_z.items()}
    band = _structure_band(compactness)

    ranked = []
    for entity in ENTITIES:
        score, for_, against = score_entity(entity, calls)
        if score <= 0.25:
            continue  # too little support to be worth showing

        expects = entity.get("expects")
        consistency = _structure_consistency(expects, band)
        combined = score * (_PHENOTYPE_FLOOR + (1 - _PHENOTYPE_FLOOR) * consistency)

        structure_reason = None
        if band != "unknown" and expects and consistency < 1.0:
            if expects == "continuum" and band == "clonal":
                structure_reason = (
                    f"argues against: this population is tightly clustered "
                    f"({compactness:.2f}x normal spread), whereas normal "
                    f"maturing cells spread along a continuum"
                )
            elif expects == "clonal" and band == "continuum":
                structure_reason = (
                    f"argues against: this population is diffuse "
                    f"({compactness:.2f}x normal spread), whereas a neoplastic "
                    f"clone is tightly clustered"
                )
            else:
                structure_reason = (
                    f"partly consistent: {compactness:.2f}x normal spread is "
                    f"between clonal and continuum"
                )
        elif band != "unknown" and expects:
            structure_reason = (
                f"consistent: {compactness:.2f}x normal spread matches the "
                f"{expects} pattern expected"
            )

        ranked.append(
            {
                "name": entity["name"],
                "short": entity["short"],
                "lineage": entity["lineage"],
                "match": round(combined * 100, 1),
                "phenotype_match": round(score * 100, 1),
                "structure_expected": expects,
                "structure_observed": band,
                "structure_consistency": round(consistency, 2),
                "structure_reason": structure_reason,
                "benign": bool(entity.get("benign")),
                "evidence_for": for_,
                "evidence_against": against,
                "confirm_with": entity["confirm"],
                "note": entity["note"],
            }
        )

    ranked.sort(key=lambda e: -e["match"])

    clonal_note = None
    if compactness is not None:
        if band == "clonal":
            clonal_note = (
                f"The population is {compactness:.2f}x the spread of normal "
                "cells — tightly clustered, consistent with a clone. This is "
                "the main evidence separating it from normal maturing cells "
                "with a similar marker pattern."
            )
        elif band == "continuum":
            clonal_note = (
                f"The population is {compactness:.2f}x the spread of normal "
                "cells — diffuse rather than clonal. A reactive or normal "
                "population is more likely than a neoplasm, whatever the "
                "marker pattern suggests."
            )
        else:
            clonal_note = (
                f"The population is {compactness:.2f}x the spread of normal "
                "cells — between clonal and continuum, so structure does not "
                "settle the question either way."
            )

    return {
        "calls": calls,
        "marker_z": marker_z,
        "candidates": ranked[:4],
        "structure": band,
        "compactness_vs_normal": compactness,
        "clonality_note": clonal_note,
        "requires_confirmation": True,
        "disclaimer": (
            "Immunophenotype alone does not classify a haematological "
            "malignancy. These are the entities whose published marker patterns "
            "most resemble this population, ranked by how much of the expected "
            "pattern is present. Morphology, cytogenetics and molecular studies "
            "are required to establish any diagnosis. Research and educational "
            "use only."
        ),
    }


def interpret_report(report: dict) -> dict:
    """Interpret every population in a detection report."""
    if not report.get("ok", True):
        return {"populations": [], "error": report.get("error")}

    out = []
    for pop in report.get("populations", []):
        out.append(
            {
                "label": pop["label"],
                "n_events": pop["n_events"],
                "pct": pop["pct_of_analyzed"],
                **interpret_population(
                    pop, compactness=pop.get("compactness_vs_normal")
                ),
            }
        )
    return {"populations": out}
