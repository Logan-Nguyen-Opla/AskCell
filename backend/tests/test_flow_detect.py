"""
test_flow_detect.py
===================
End-to-end checks on reference building and abnormal-population detection.

Run from ``backend/``::

    .venv/Scripts/python -m pytest tests -v

These are the tests that decide whether the project works. They assert three
different things, and all three matter:

* **sensitivity** -- the overt and MRD cases are found;
* **specificity** -- the healthy specimen is *not* flagged, even though it is
  full of hematogones that look almost identical to blasts;
* **calibration** -- the numbers reported are close to the known truth, not just
  non-zero.

A detector that passes the first and fails the second is worthless, which is why
the healthy control is treated as a first-class test rather than a footnote.
"""

from __future__ import annotations

import glob
import os

import numpy as np
import pytest
from scipy.spatial import cKDTree

from app.flow import detect, fit_reference, gate, marker_matrix, read_fcs
from app.flow.detect import DEFAULT_MIN_NEIGHBOURS, DEFAULT_RADIUS_FRACTION
from app.flow.reference import NormalReference, fit_reference

SAMPLE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data"
)
NORMALS = sorted(glob.glob(os.path.join(SAMPLE_DIR, "normal_bm_*.fcs")))
OVERT = os.path.join(SAMPLE_DIR, "patient_overt.fcs")
MRD = os.path.join(SAMPLE_DIR, "patient_mrd.fcs")
HEALTHY = os.path.join(SAMPLE_DIR, "patient_normal.fcs")

BLAST = "Aberrant B-lymphoblasts"

pytestmark = pytest.mark.skipif(
    len(NORMALS) < 2 or not os.path.exists(OVERT),
    reason="fixtures missing -- run `python make_mock_fcs.py` first",
)


# --------------------------------------------------------------------------- #
# Fixtures (fitting the reference is the slow part -- do it once)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def reference() -> NormalReference:
    return fit_reference(
        [read_fcs(p, filename=os.path.basename(p)) for p in NORMALS]
    )


def _load(path: str):
    """Read a specimen and return (gated_adata, aligned_truth_labels)."""
    adata = read_fcs(path, filename=os.path.basename(path))
    truth = np.load(path.replace(".fcs", ".labels.npy"), allow_pickle=True)
    adata.obs["_row"] = np.arange(adata.n_obs)
    gated, _ = gate(adata)
    rows = gated.obs["_row"].to_numpy().astype(int)
    return gated, truth[rows]


@pytest.fixture(scope="module")
def overt():
    return _load(OVERT)


@pytest.fixture(scope="module")
def mrd():
    return _load(MRD)


@pytest.fixture(scope="module")
def healthy():
    return _load(HEALTHY)


# --------------------------------------------------------------------------- #
# Reference model
# --------------------------------------------------------------------------- #
def test_reference_needs_two_specimens():
    """One specimen cannot calibrate a threshold, so it must be refused.

    Accepting it would mean inventing a cutoff, which is the easiest possible
    way to build a detector that scores perfectly on its own data.
    """
    one = read_fcs(NORMALS[0], filename="a.fcs")
    with pytest.raises(ValueError, match="at least 2"):
        fit_reference([one])


def test_reference_threshold_matches_its_stated_false_flag_rate(reference, healthy):
    """The promise of the 99.9th percentile is ~0.1% of healthy cells flagged.

    This is the test that proves the threshold was measured rather than guessed.
    """
    gated, truth = healthy
    X, markers = marker_matrix(gated)
    scores = reference.score(X, markers)
    rate = float((scores > reference.threshold).mean() * 100.0)

    assert not (truth == BLAST).any()          # genuinely a healthy specimen
    expected = 100.0 - reference.percentile    # 0.1%
    assert rate == pytest.approx(expected, abs=0.08), (
        f"flagged {rate:.4f}% of healthy cells, expected ~{expected}%"
    )


def test_reference_quantiles_increase(reference):
    q = reference.null_quantiles
    vals = [q[k] for k in ("p50", "p90", "p99", "p99.9", "p99.99")]
    assert vals == sorted(vals)


def test_reference_roundtrip(reference, tmp_path):
    path = str(tmp_path / "ref.npz")
    reference.save(path)
    loaded = NormalReference.load(path)

    assert loaded.markers == reference.markers
    assert loaded.threshold == pytest.approx(reference.threshold)
    assert loaded.neighbour_radius == pytest.approx(reference.neighbour_radius)
    np.testing.assert_allclose(loaded.center, reference.center)

    # A reloaded reference must score identically, or saved results drift.
    X = reference.cloud[:500] * reference.scale + reference.center
    np.testing.assert_allclose(
        loaded.score(X, reference.markers),
        reference.score(X, reference.markers),
        rtol=1e-5,
    )


def test_standardize_uses_reference_statistics(reference):
    """Z-scoring must never use the sample's own spread.

    Standardising a patient against itself would rescale away the shift being
    looked for -- a specimen where every cell is abnormal would come out
    looking perfectly average.
    """
    X = reference.cloud[:1000] * reference.scale + reference.center
    Z = reference.standardize(X, reference.markers)
    shifted = reference.standardize(X + 5.0, reference.markers)
    # A uniform +5 shift must survive standardisation as a visible offset.
    assert float(np.mean(shifted - Z)) == pytest.approx(
        float(np.mean(5.0 / reference.scale)), rel=1e-4
    )


def test_standardize_rejects_missing_markers(reference):
    X = np.zeros((10, len(reference.markers) - 1), dtype=np.float32)
    with pytest.raises(ValueError, match="missing markers"):
        reference.standardize(X, reference.markers[:-1])


# --------------------------------------------------------------------------- #
# Specificity -- the test that matters most
# --------------------------------------------------------------------------- #
def test_healthy_specimen_is_not_flagged(reference, healthy):
    """No population in a healthy specimen, despite it being full of lookalikes.

    ``patient_normal.fcs`` contains hematogones -- normal B precursors that are
    CD19+CD10+ with dim CD45, near enough the blast phenotype. Any detector that
    reports a population here would diagnose healthy children.
    """
    gated, truth = healthy
    assert (truth == "Hematogones").sum() > 100   # lookalikes really are present

    report = detect(gated, reference, already_gated=True)
    assert report["ok"] is True
    assert report["verdict"] == "no_abnormal_population"
    assert report["n_abnormal"] == 0
    assert report["populations"] == []


def test_healthy_specimen_still_flags_some_cells(reference, healthy):
    """Stage 1 alone is *not* a detector, and this pins down why.

    Healthy cells do trip the flag, by design. If this ever reached zero the
    threshold would have drifted so high that real MRD populations would be
    missed too.
    """
    gated, _ = healthy
    report = detect(gated, reference, already_gated=True)
    assert report["stage1_flagged"] > 0
    assert report["noise_removed_by_clustering"] == report["stage1_flagged"]


# --------------------------------------------------------------------------- #
# Sensitivity
# --------------------------------------------------------------------------- #
def test_overt_case_detected(reference, overt):
    gated, truth = overt
    n_true = int((truth == BLAST).sum())
    report = detect(gated, reference, already_gated=True)

    assert report["verdict"] == "abnormal_population_detected"
    # Reported burden must match the truth, not merely be non-zero.
    true_pct = n_true / len(truth) * 100.0
    assert report["abnormal_pct"] == pytest.approx(true_pct, abs=0.5)
    assert len(report["populations"]) >= 1


def test_mrd_case_detected_at_five_hundredths_of_a_percent(reference, mrd):
    """The limit-of-detection claim: 200 cells in 400,000."""
    gated, truth = mrd
    n_true = int((truth == BLAST).sum())
    assert n_true < 250 and len(truth) > 300_000

    report = detect(gated, reference, already_gated=True)
    assert report["verdict"] == "abnormal_population_detected"
    assert report["abnormal_pct"] == pytest.approx(
        n_true / len(truth) * 100.0, abs=0.01
    )


@pytest.mark.parametrize("case", ["overt", "mrd"])
def test_sensitivity_and_precision(reference, case, request):
    """Per-event accuracy against ground truth."""
    gated, truth = request.getfixturevalue(case)
    report = detect(gated, reference, already_gated=True)
    called = report["per_event"]["abnormal"]
    is_blast = truth == BLAST

    tp = int((called & is_blast).sum())
    fp = int((called & ~is_blast).sum())
    fn = int((~called & is_blast).sum())

    sensitivity = tp / (tp + fn)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    assert sensitivity > 0.95, f"{case}: sensitivity {sensitivity:.3f}"
    assert precision > 0.95, f"{case}: precision {precision:.3f}"


def test_clustering_removes_the_expected_noise(reference, mrd):
    """Stage 2 must strip the false flags stage 1 is guaranteed to produce.

    This is the single clearest argument for the two-stage design: on the MRD
    file, stage 1 alone over-reports the disease burden by roughly threefold.
    """
    gated, truth = mrd
    report = detect(gated, reference, already_gated=True)
    n_true = int((truth == BLAST).sum())

    assert report["stage1_flagged"] > 2 * n_true      # mostly noise
    assert report["noise_removed_by_clustering"] > 0
    assert report["n_abnormal"] < report["stage1_flagged"]
    # Stage 2 lands on the truth; stage 1 would not have.
    assert abs(report["n_abnormal"] - n_true) < 0.1 * n_true


# --------------------------------------------------------------------------- #
# Characterisation
# --------------------------------------------------------------------------- #
def test_population_is_reported_as_clonal_and_compact(reference, overt):
    """Clonality is the discriminator, so it has to be measured and reported."""
    gated, _ = overt
    report = detect(gated, reference, already_gated=True)
    pop = report["populations"][0]

    assert pop["is_clonal"] is True
    assert pop["compactness_vs_normal"] < 1.0


def test_deviant_markers_recover_the_designed_phenotype(reference, overt):
    """The report must name *which* markers are abnormal, and get them right.

    make_mock_fcs.py builds the blasts as CD10-overbright / CD34+ / CD19+ with
    dim CD45. Nothing tells the detector that -- it has to recover it, which is
    what makes the output an explanation rather than just a score.
    """
    gated, _ = overt
    report = detect(gated, reference, already_gated=True)
    devs = {d["marker"]: d for d in report["populations"][0]["deviant_markers"]}

    for marker in ("CD10", "CD34", "CD19"):
        assert marker in devs, f"{marker} not among top deviations: {list(devs)}"
        assert devs[marker]["direction"] == "brighter"

    assert devs["CD10"]["strength"] == "strong"
    if "CD45" in devs:
        assert devs["CD45"]["direction"] == "dimmer"


def test_report_summary_is_human_readable(reference, overt):
    gated, _ = overt
    report = detect(gated, reference, already_gated=True)
    assert "Abnormal population detected" in report["summary"]
    assert "%" in report["summary"]


# --------------------------------------------------------------------------- #
# The tuned parameter -- guarded, because it was calibrated on synthetic data
# --------------------------------------------------------------------------- #
def test_radius_sits_in_the_measured_gap(reference, overt, mrd, healthy):
    """DEFAULT_RADIUS_FRACTION relies on a gap that must actually be there.

    The linking radius works because, inside the flagged set, true blast
    populations sit far closer together than scattered false flags. That gap was
    measured on synthetic data. This test re-measures it, so if the fixtures or
    the panel change and the separation collapses, the failure is loud and
    specific rather than a quietly degraded detector.
    """
    radius = reference.neighbour_radius * DEFAULT_RADIUS_FRACTION
    blast_max, noise_min = 0.0, np.inf

    for gated, truth in (overt, mrd, healthy):
        X, markers = marker_matrix(gated)
        scores = reference.score(X, markers)
        flagged = scores > reference.threshold
        if flagged.sum() <= DEFAULT_MIN_NEIGHBOURS:
            continue

        Z = reference.standardize(X, markers)[flagged]
        k = min(DEFAULT_MIN_NEIGHBOURS + 1, Z.shape[0])
        dist, _ = cKDTree(Z).query(Z, k=k, workers=-1)
        kdist = dist[:, -1]

        is_blast = (truth == BLAST)[flagged]
        if is_blast.any():
            blast_max = max(blast_max, float(np.quantile(kdist[is_blast], 0.90)))
        if (~is_blast).any():
            noise_min = min(noise_min, float(np.quantile(kdist[~is_blast], 0.10)))

    assert blast_max < radius < noise_min, (
        f"radius {radius:.3f} outside the gap: blasts reach {blast_max:.3f}, "
        f"noise starts at {noise_min:.3f}"
    )


# --------------------------------------------------------------------------- #
# Failure modes
# --------------------------------------------------------------------------- #
def test_panel_mismatch_is_refused_not_guessed(reference, overt):
    """A reference may only serve a specimen carrying all of its markers."""
    gated, _ = overt
    trimmed = gated[:, [v != reference.markers[0] for v in gated.var_names]].copy()
    report = detect(trimmed, reference, already_gated=True)

    assert report["ok"] is False
    assert report["error"] == "panel_mismatch"
    assert reference.markers[0] in report["message"]


def test_detect_is_deterministic(reference, mrd):
    """Same input, same answer -- the reproducibility claim, tested."""
    gated, _ = mrd
    a = detect(gated, reference, already_gated=True, return_per_event=False)
    b = detect(gated, reference, already_gated=True, return_per_event=False)
    assert a == b
