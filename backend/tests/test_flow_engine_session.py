"""
test_flow_engine_session.py
============================
End-to-end FlowSession tests: a real alt-panel reference and specimen, built
with flowio directly (no FCS fixtures for a second panel exist otherwise),
run through the actual load_sample_from_path() path -- not just the pure
choose_reference() selection rule, but the session wiring around it.
"""

from __future__ import annotations

import os

import flowio
import numpy as np
import pytest

from app.flow_engine import FlowSession

SAMPLE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data"
)
NORMAL_FILES = sorted(
    os.path.join(SAMPLE_DIR, f"normal_bm_{i:02d}.fcs") for i in (1, 2)
)
DEFAULT_PATIENT = os.path.join(SAMPLE_DIR, "patient_overt.fcs")

pytestmark = pytest.mark.skipif(
    not all(os.path.exists(p) for p in [*NORMAL_FILES, DEFAULT_PATIENT]),
    reason="fixtures missing -- run `python make_mock_fcs.py` first",
)

# A small, made-up panel sharing no markers with the default one, so a
# specimen written on it can only ever satisfy an alt reference built on it.
_ALT_CHANNELS = ["CD99", "CD66b", "CD123"]


def _write_alt_fcs(path: str, n_events: int, seed: int) -> None:
    rng = np.random.default_rng(seed)
    events = rng.lognormal(mean=5.0, sigma=0.5, size=(n_events, len(_ALT_CHANNELS)))
    with open(path, "wb") as fh:
        flowio.create_fcs(
            fh,
            events.flatten().tolist(),
            channel_names=_ALT_CHANNELS,
            opt_channel_names=_ALT_CHANNELS,
            metadata_dict={"$CYT": "MockAltPanel"},
        )


@pytest.fixture()
def alt_files(tmp_path):
    paths = [str(tmp_path / f"alt_healthy_{i}.fcs") for i in range(2)]
    for i, p in enumerate(paths):
        _write_alt_fcs(p, n_events=500, seed=100 + i)
    patient = str(tmp_path / "alt_patient.fcs")
    _write_alt_fcs(patient, n_events=200, seed=999)
    return paths, patient


def test_default_upload_still_works_after_an_alt_panel_upload(alt_files):
    """Regression: load_sample_from_path() used to match a specimen's panel
    against `self.reference` -- whatever the *last* upload happened to leave
    active -- instead of a stable default. Analysing one alt-panel specimen
    would then permanently strand the session: the very next default-panel
    upload found no default reference to fall back to.
    """
    alt_healthy_paths, alt_patient_path = alt_files

    session = FlowSession()
    session.load_reference_from_paths(NORMAL_FILES)

    # Build the alt reference on a *second* session so building it doesn't
    # disturb the default we just established on `session`.
    builder = FlowSession()
    builder.load_reference_from_paths(alt_healthy_paths)
    session.add_alt_reference("alt", builder.reference)

    # 1) an alt-panel specimen should auto-switch to the alt reference.
    report1 = session.load_sample_from_path(alt_patient_path, "alt_patient.fcs")
    assert report1["reference_profile"] == "alt"

    # 2) a default-panel specimen uploaded right after must still work --
    # this is the exact regression: it used to 422 with "different antibody
    # panel" because `self.reference` was left pointed at "alt".
    report2 = session.load_sample_from_path(DEFAULT_PATIENT, "patient_overt.fcs")
    assert report2["reference_profile"] == "default"
    assert report2["ok"] is not False
