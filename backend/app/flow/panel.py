"""
panel.py
========
Antibody-panel identification for flow / mass cytometry samples.

Why this exists
---------------
A "difference from normal" comparison is only meaningful when the patient tube
and the normal reference were acquired with the *same* antibody panel. Marker
intensities are not portable across panels: the same antigen measured with a
different fluorophore, on a different instrument, at different voltages lands in
a different place in marker space. Comparing across panels produces confident
nonsense.

So every acquisition is fingerprinted by its panel, and a reference can only be
matched to a sample carrying a compatible fingerprint. This module owns that
identity.

Marker names in the wild are messy -- the same antigen appears as ``CD3``,
``cd3``, ``CD 3``, ``CD3-FITC``, ``APC-CD8a``, ``Anti-CD19``. Canonicalization
folds those to one token so the fingerprint is stable across operators who typed
the panel in slightly differently.
"""

from __future__ import annotations

import hashlib
import re

# Fluorophore tokens that decorate a marker name but say nothing about which
# antigen was measured. Stripped before fingerprinting.
#
# Deliberately excludes bare chemical-element symbols. Metal isotope tags do
# appear in mass-cytometry channel names, but as a compound token ("Nd142Di"),
# never as a standalone fragment -- and several element symbols collide with
# real antigen-name fragments. "Cd" is Cadmium *and* the CD antigen prefix, so
# listing it here silently reduced "CD 3" to "3" and mis-fingerprinted every
# spaced or hyphenated CD marker. Only unambiguous, multi-character fluorophore
# names belong in this set.
_CONJUGATE_TOKENS = {
    "fitc", "pe", "apc", "percp", "pacblue", "pacificblue", "amcyan",
    "alexa", "af", "bv", "bb", "buv", "buc", "pecy5", "pecy7", "pecf594",
    "apccy7", "apcr700", "apcfire", "percpcy55", "percpef710", "ef450",
    "ef506", "ef660", "ef780", "vioblue", "viogreen", "krome",
    "cy3", "cy5", "cy55", "cy7", "texasred", "ecd",
    "superbright", "nfb", "nir", "spark", "starbright", "zombie",
}

# A mass-cytometry detector channel, e.g. "Nd142Di" / "Ir193Di". When a CyTOF
# channel carries no antigen label its metal *is* its identity, so the token is
# preserved intact rather than decomposed.
_MASS_CHANNEL = re.compile(r"^[A-Z][a-z]?\d{2,3}Di$")

# Channels that describe the event physically rather than an antigen. These are
# used for debris/doublet gating, not phenotype, and are tracked separately.
_SCATTER_PATTERNS = (
    re.compile(r"^fsc", re.I),
    re.compile(r"^ssc", re.I),
    re.compile(r"^time$", re.I),
    re.compile(r"^event[_\s-]*(no|number|length|id)$", re.I),
    re.compile(r"^cell[_\s-]*length$", re.I),      # CyTOF event length
    re.compile(r"^(beads?|eq[_\s-]*beads?)$", re.I),
    re.compile(r"^(dna\d?|ir19[13])$", re.I),      # CyTOF DNA intercalator
)

# Viability / live-dead stains: real channels, but exclusionary gates rather
# than phenotypic markers. Flagged so downstream stats can skip them.
_VIABILITY_PATTERNS = (
    re.compile(r"live[_\s/-]*dead", re.I),
    re.compile(r"^(dapi|7aad|propidium|pi|zombie|viability|viakrome)", re.I),
)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def is_scatter_channel(name: str) -> bool:
    """True for physical/instrument channels (FSC, SSC, Time, bead, DNA)."""
    n = (name or "").strip()
    return any(p.search(n) for p in _SCATTER_PATTERNS)


def is_viability_channel(name: str) -> bool:
    """True for live/dead discriminators (gating channels, not phenotype)."""
    n = (name or "").strip()
    return any(p.search(n) for p in _VIABILITY_PATTERNS)


def canonical_marker(raw: str) -> str:
    """Fold a free-text marker label to a stable canonical token.

    ``"APC-CD8a"``, ``"cd8a"``, ``"CD 8a"`` and ``"Anti-CD8a"`` all become
    ``"CD8A"``. Scatter channels are returned upper-cased but otherwise intact,
    since their names are already instrument-canonical.
    """
    name = (raw or "").strip()
    if not name:
        return ""
    if is_scatter_channel(name):
        return name.upper()
    if _MASS_CHANNEL.match(name):
        return name.upper()

    name = re.sub(r"^\s*anti[-\s]*", "", name, flags=re.I)

    # Split on separators and drop pure-conjugate fragments. The stripped form
    # is only accepted when something substantive survives -- for an unlabelled
    # detector channel like "PE-Cy7-A" every fragment is a conjugate, and
    # collapsing it to "A" would make two unrelated channels collide.
    parts = [p for p in re.split(r"[-_/\s.]+", name) if p]
    kept = [p for p in parts if _NON_ALNUM.sub("", p.lower()) not in _CONJUGATE_TOKENS]
    if kept and len("".join(kept)) >= 2:
        parts = kept

    token = _NON_ALNUM.sub("", "".join(parts).lower())
    return token.upper()


def panel_fingerprint(markers: list[str]) -> tuple[str, list[str]]:
    """Return ``(fingerprint, canonical_markers)`` for a set of marker labels.

    The fingerprint is order-independent (acquisition order is an artifact of
    instrument setup, not of panel identity) and ignores scatter channels, so
    the same panel run with FSC-A vs FSC-H still matches. Returns a short hex
    digest suitable for use as a database key.
    """
    canon = sorted(
        {
            c
            for c in (canonical_marker(m) for m in markers)
            if c and not is_scatter_channel(c)
        }
    )
    digest = hashlib.sha256("|".join(canon).encode("utf-8")).hexdigest()[:16]
    return digest, canon


def compare_panels(
    sample_markers: list[str], reference_markers: list[str]
) -> dict:
    """Assess whether a reference panel can serve a sample panel.

    Returns the shared / missing / extra canonical markers plus a Jaccard
    ``similarity``. ``compatible`` is True only on an exact match of the
    phenotypic marker set -- anything less means at least one marker the
    comparison would rely on is absent from one side, and the caller must decide
    whether to proceed on the shared subset.
    """
    _, s = panel_fingerprint(sample_markers)
    _, r = panel_fingerprint(reference_markers)
    ss, rs = set(s), set(r)
    union = ss | rs
    return {
        "shared": sorted(ss & rs),
        "missing_from_reference": sorted(ss - rs),
        "extra_in_reference": sorted(rs - ss),
        "similarity": round(len(ss & rs) / len(union), 4) if union else 0.0,
        "compatible": ss == rs and bool(ss),
    }
