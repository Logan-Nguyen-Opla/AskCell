"""
make_mock_fcs.py
================
Generate synthetic FCS files for developing and testing AskCell's cytometry
pipeline, so the app works before any real acquisition is available.

    python make_mock_fcs.py

Writes into ``sample_data/``:
    normal_bm_01.fcs .. normal_bm_20.fcs   normal marrow -- the reference set
    patient_overt.fcs                      25% aberrant B-lymphoblasts
    patient_mrd.fcs                        0.05% blasts (residual-disease level)
    patient_normal.fcs                     no blasts (specificity control)

Why this panel
--------------
A 14-colour B-lymphoblastic-leukaemia screening panel, which is close to what a
clinical flow lab actually runs. The point of the mock is not to look pretty: it
is to reproduce the one thing that makes "difference from normal" genuinely
hard, so the detector is developed against the real problem rather than a
strawman.

That hard thing is **hematogones** -- normal B-cell precursors found in marrow.
They are CD19+ CD10+ CD34-dim with dim CD45, which is *almost* the immunophenotype
of a B-ALL blast. Any detector that merely asks "are there CD19+CD10+ events with
dim CD45" will flag every healthy paediatric marrow on the planet.

What separates them is *structure*, not any single marker:

* hematogones form a smooth **maturation continuum** -- as CD10 falls, CD20
  rises and CD45 brightens, all correlated, because the cells are progressing
  through development;
* blasts form a **tight, homogeneous cluster** -- a clone, frozen at one point,
  with CD10 brighter than any normal precursor reaches and CD20 absent.

So the mock generates hematogones along a correlated trajectory and blasts as a
compact blob. A detector that gets these two apart is doing the real task.

Intensities are written on the native linear scale (18-bit, 0..262144); the
arcsinh transform is applied at ingest, not here.
"""

from __future__ import annotations

import os

import numpy as np

try:
    import flowio
except ImportError:  # pragma: no cover
    raise SystemExit("flowio is required: pip install flowio")

rng = np.random.default_rng(42)

# --------------------------------------------------------------------------- #
# Panel definition
# --------------------------------------------------------------------------- #
# (detector channel, antigen). Scatter channels carry no antigen label, matching
# how a real instrument writes PnN without a PnS.
PANEL: list[tuple[str, str]] = [
    ("FSC-A", ""),
    ("FSC-H", ""),
    ("SSC-A", ""),
    ("FITC-A", "CD45"),
    ("PE-A", "CD34"),
    ("PerCP-A", "CD19"),
    ("PE-Cy7-A", "CD10"),
    ("APC-A", "CD20"),
    ("APC-Cy7-A", "CD3"),
    ("BV421-A", "CD5"),
    ("BV510-A", "CD7"),
    ("BV605-A", "CD13"),
    ("BV711-A", "CD33"),
    ("BV786-A", "CD117"),
    ("BUV395-A", "HLA-DR"),
    ("BUV496-A", "CD38"),
    ("Zombie-A", "Live/Dead"),
]

CHANNELS = [c for c, _ in PANEL]
MARKERS = [m for _, m in PANEL]
MARKER_IDX = {m: i for i, (_, m) in enumerate(PANEL) if m}
SCATTER_IDX = {c: i for i, (c, m) in enumerate(PANEL) if not m}

# Staining intensity tiers on the linear scale. Real cytometry data is roughly
# log-normal within a population, so these are geometric means.
NEG, DIM, MOD, BRIGHT, VBRIGHT = 30.0, 450.0, 3500.0, 25000.0, 90000.0

# Per-population marker profile. Anything unlisted defaults to NEG.
# Percentages are of total nucleated events in normal marrow.
POPULATIONS: dict[str, dict] = {
    "Granulocytes": {
        "pct": 52.0,
        "fsc": (65000, 9000), "ssc": (55000, 9000),
        "markers": {"CD45": MOD, "CD13": BRIGHT, "CD33": MOD, "HLA-DR": NEG},
    },
    "T cells": {
        "pct": 15.0,
        "fsc": (42000, 5000), "ssc": (14000, 3000),
        "markers": {"CD45": VBRIGHT, "CD3": BRIGHT, "CD5": BRIGHT, "CD7": BRIGHT,
                    "CD38": DIM},
    },
    "Mature B cells": {
        "pct": 5.0,
        "fsc": (44000, 5000), "ssc": (15000, 3000),
        "markers": {"CD45": VBRIGHT, "CD19": BRIGHT, "CD20": BRIGHT,
                    "HLA-DR": BRIGHT, "CD38": DIM},
    },
    "Monocytes": {
        "pct": 8.0,
        "fsc": (60000, 8000), "ssc": (28000, 6000),
        "markers": {"CD45": VBRIGHT, "CD33": VBRIGHT, "CD13": BRIGHT,
                    "HLA-DR": BRIGHT, "CD38": MOD},
    },
    "NK cells": {
        "pct": 3.0,
        "fsc": (45000, 5000), "ssc": (16000, 3500),
        "markers": {"CD45": VBRIGHT, "CD7": BRIGHT, "CD38": MOD},
    },
    "Myeloid blasts": {
        "pct": 2.0,
        "fsc": (50000, 6000), "ssc": (20000, 4000),
        "markers": {"CD45": DIM, "CD34": MOD, "CD117": MOD, "CD13": DIM,
                    "CD33": DIM, "HLA-DR": MOD, "CD38": MOD},
    },
    "Erythroid / other": {
        "pct": 7.0,
        "fsc": (35000, 7000), "ssc": (12000, 3000),
        "markers": {"CD45": NEG},
    },
}

HEMATOGONE_PCT = 8.0  # normal B precursors -- the blast look-alike


def _lognormal(gmean: float, n: int, sigma: float = 0.42) -> np.ndarray:
    """Draw n intensities log-normally distributed about a geometric mean."""
    return rng.lognormal(np.log(max(gmean, 1e-6)), sigma, n)


def _blank(n: int) -> np.ndarray:
    """Event block pre-filled with background autofluorescence."""
    block = np.zeros((n, len(PANEL)), dtype=np.float64)
    for i in range(len(PANEL)):
        block[:, i] = _lognormal(NEG, n, sigma=0.55)
    return block


def _apply_scatter(block: np.ndarray, fsc: tuple, ssc: tuple) -> None:
    n = block.shape[0]
    fsc_a = rng.normal(fsc[0], fsc[1], n)
    block[:, SCATTER_IDX["FSC-A"]] = fsc_a
    # FSC-H tracks FSC-A closely for singlets; the ratio is the doublet gate.
    block[:, SCATTER_IDX["FSC-H"]] = fsc_a * rng.normal(0.94, 0.02, n)
    block[:, SCATTER_IDX["SSC-A"]] = rng.normal(ssc[0], ssc[1], n)


def _standard_population(name: str, spec: dict, n: int) -> np.ndarray:
    """A normal population: independent log-normal draws per marker."""
    block = _blank(n)
    _apply_scatter(block, spec["fsc"], spec["ssc"])
    for marker, level in spec["markers"].items():
        block[:, MARKER_IDX[marker]] = _lognormal(level, n)
    return block


def _hematogones(n: int) -> np.ndarray:
    """Normal B precursors along a correlated maturation continuum.

    A single latent maturation coordinate t in [0, 1] drives CD10 down, CD20 and
    CD45 up, and CD34 off early -- so the population appears as a smooth arc in
    marker space rather than a blob. This correlated structure is the signal that
    distinguishes them from a leukaemic clone.
    """
    block = _blank(n)
    t = rng.beta(1.6, 1.6, n)  # 0 = earliest precursor, 1 = nearly mature

    _apply_scatter(block, (43000, 5500), (15000, 3500))

    # CD10 bright early, fading with maturation (never reaches blast brightness).
    block[:, MARKER_IDX["CD10"]] = _lognormal(1.0, n, 0.30) * (
        BRIGHT * (1 - t) + DIM * t
    )
    # CD20 acquired late.
    block[:, MARKER_IDX["CD20"]] = _lognormal(1.0, n, 0.35) * (
        NEG * (1 - t) + BRIGHT * t
    )
    # CD45 dim early, brightening steadily.
    block[:, MARKER_IDX["CD45"]] = _lognormal(1.0, n, 0.25) * (
        DIM * (1 - t) + VBRIGHT * t
    )
    # CD34 only on the earliest fraction.
    early = t < 0.3
    block[early, MARKER_IDX["CD34"]] = _lognormal(DIM, int(early.sum()), 0.5)
    block[:, MARKER_IDX["CD19"]] = _lognormal(BRIGHT, n)
    block[:, MARKER_IDX["HLA-DR"]] = _lognormal(BRIGHT, n)
    block[:, MARKER_IDX["CD38"]] = _lognormal(MOD, n)
    return block


def _blasts(n: int) -> np.ndarray:
    """Aberrant B-lymphoblasts: a tight, homogeneous clone.

    Deliberately narrow sigma -- clonality *is* the phenotype. CD10 is brighter
    than any hematogone reaches, CD20 is absent, and none of it co-varies.
    """
    block = _blank(n)
    _apply_scatter(block, (47000, 3500), (16000, 2500))
    tight = 0.16  # far tighter than the 0.42 of a normal population
    block[:, MARKER_IDX["CD45"]] = _lognormal(DIM * 0.7, n, tight)
    block[:, MARKER_IDX["CD19"]] = _lognormal(BRIGHT, n, tight)
    block[:, MARKER_IDX["CD10"]] = _lognormal(VBRIGHT, n, tight)   # over-bright
    block[:, MARKER_IDX["CD34"]] = _lognormal(MOD, n, tight)
    block[:, MARKER_IDX["CD38"]] = _lognormal(DIM, n, tight)       # aberrantly dim
    block[:, MARKER_IDX["HLA-DR"]] = _lognormal(MOD, n, tight)
    # CD20 stays at background -- the discriminator against mature B cells.
    return block


def build_sample(n_events: int, blast_pct: float) -> tuple[np.ndarray, list[str]]:
    """Assemble one specimen. Returns (events, per-event population label)."""
    blocks: list[np.ndarray] = []
    labels: list[str] = []

    n_blasts = int(round(n_events * blast_pct / 100.0))
    remaining = n_events - n_blasts

    normal_total = sum(s["pct"] for s in POPULATIONS.values()) + HEMATOGONE_PCT
    spec_items = list(POPULATIONS.items()) + [("Hematogones", None)]

    assigned = 0
    for i, (name, spec) in enumerate(spec_items):
        pct = HEMATOGONE_PCT if spec is None else spec["pct"]
        # Last population absorbs the rounding remainder.
        n = (remaining - assigned) if i == len(spec_items) - 1 else int(
            round(remaining * pct / normal_total)
        )
        n = max(n, 0)
        assigned += n
        if n == 0:
            continue
        blocks.append(_hematogones(n) if spec is None
                      else _standard_population(name, spec, n))
        labels.extend([name] * n)

    if n_blasts > 0:
        blocks.append(_blasts(n_blasts))
        labels.extend(["Aberrant B-lymphoblasts"] * n_blasts)

    events = np.vstack(blocks)

    # Shuffle: acquisition order must not encode the population, or a model
    # could learn event index instead of phenotype.
    order = rng.permutation(events.shape[0])
    events = events[order]
    labels = [labels[i] for i in order]

    # A viability stain is dim on live cells; kill a small fraction outright.
    dead = rng.random(events.shape[0]) < 0.03
    events[dead, MARKER_IDX["Live/Dead"]] = _lognormal(BRIGHT, int(dead.sum()))

    # Time increases monotonically through the run, as on a real instrument.
    np.clip(events, 0.0, 262143.0, out=events)
    return events, labels


def _spillover_string() -> str:
    """Identity spillover over the fluorescence channels.

    Real files carry genuine off-diagonal spill; an identity matrix keeps the
    mock honest (compensation runs and is a no-op) without inventing a
    plausible-looking matrix that no instrument produced.
    """
    fluor = [c for c, m in PANEL if m]
    n = len(fluor)
    eye = np.eye(n).flatten()
    return ",".join([str(n)] + fluor + [f"{v:g}" for v in eye])


def write_fcs(path: str, events: np.ndarray, cyt: str = "MockFACS-A5") -> None:
    with open(path, "wb") as fh:
        flowio.create_fcs(
            fh,
            events.flatten().tolist(),
            channel_names=CHANNELS,
            opt_channel_names=[m if m else None for m in MARKERS],
            metadata_dict={
                "$CYT": cyt,
                "$CYTSN": "MOCK-0001",
                "$SRC": "synthetic bone marrow",
                "$SPILLOVER": _spillover_string(),
                "$PROJ": "AskCell development fixture",
            },
        )


def main() -> None:
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_data")
    os.makedirs(out_dir, exist_ok=True)

    n_normals = 20
    plan = [
        *[(f"normal_bm_{i:02d}.fcs", 60_000, 0.0) for i in range(1, n_normals + 1)],
        ("patient_overt.fcs", 60_000, 25.0),
        ("patient_mrd.fcs", 400_000, 0.05),
        ("patient_normal.fcs", 60_000, 0.0),
    ]

    manifest: list[str] = []
    for name, n_events, blast_pct in plan:
        events, labels = build_sample(n_events, blast_pct)
        path = os.path.join(out_dir, name)
        write_fcs(path, events)
        n_blasts = sum(1 for l in labels if l.startswith("Aberrant"))
        manifest.append(
            f"  {name:24s} {events.shape[0]:>7,d} events  "
            f"{n_blasts:>6,d} blasts ({blast_pct:g}%)  "
            f"{os.path.getsize(path) / 1e6:5.1f} MB"
        )

        # Ground-truth labels alongside each file, for scoring the detector.
        np.save(path.replace(".fcs", ".labels.npy"), np.array(labels, dtype=object))

    print(f"Wrote {len(plan)} FCS files to {out_dir}")
    print("\n".join(manifest))
    print(f"\n  panel: {len([m for m in MARKERS if m])} markers, "
          f"{len(SCATTER_IDX)} scatter channels")
    print("  ground truth per file: <name>.labels.npy")


if __name__ == "__main__":
    main()
