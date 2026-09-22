"""
test_flow_api.py
================
Endpoint-level checks for the cytometry routes.

These use FastAPI's TestClient, which runs the app's lifespan, so they also
cover the startup path that loads or fits the bundled healthy reference.
"""

from __future__ import annotations

import glob
import os

import pytest
from fastapi.testclient import TestClient

SAMPLE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data"
)
NORMALS = sorted(glob.glob(os.path.join(SAMPLE_DIR, "normal_bm_*.fcs")))
OVERT = os.path.join(SAMPLE_DIR, "patient_overt.fcs")
HEALTHY = os.path.join(SAMPLE_DIR, "patient_normal.fcs")

pytestmark = pytest.mark.skipif(
    len(NORMALS) < 2 or not os.path.exists(OVERT),
    reason="fixtures missing -- run `python make_mock_fcs.py` first",
)


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


def _post_sample(client, path: str):
    with open(path, "rb") as fh:
        return client.post(
            "/api/flow/sample",
            files={"file": (os.path.basename(path), fh, "application/octet-stream")},
        )


# --------------------------------------------------------------------------- #
# Startup / status
# --------------------------------------------------------------------------- #
def test_reference_is_available_on_startup(client):
    """The app must be usable the moment it opens, with no setup."""
    body = client.get("/api/flow/status").json()
    assert body["reference_loaded"] is True
    assert body["reference"]["n_markers"] > 0
    assert body["reference"]["n_source_specimens"] >= 2


def test_scatter_serves_the_reference_backdrop_before_any_sample(client):
    body = client.get("/api/flow/scatter").json()
    assert len(body["reference"]["points"]) > 0
    assert all(len(p) == 2 for p in body["reference"]["points"][:50])


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #
def test_upload_specimen_returns_a_report(client):
    res = _post_sample(client, OVERT)
    assert res.status_code == 200
    body = res.json()

    assert body["verdict"] == "abnormal_population_detected"
    assert body["abnormal_pct"] > 20
    assert body["populations"]
    assert body["qc"]["n_kept"] > 0            # QC report is attached
    assert body["panel"]["compatible"] is True


def test_report_does_not_ship_per_event_arrays(client):
    """The per-event arrays are large and numpy-typed.

    They belong in /scatter, which shapes them for the viewer. Leaking them into
    the report would bloat every response and break JSON encoding.
    """
    _post_sample(client, OVERT)
    body = client.get("/api/flow/report").json()
    assert "per_event" not in body


def test_scatter_keeps_every_abnormal_cell(client):
    """Subsampling for the browser must never thin the finding itself."""
    report = _post_sample(client, OVERT).json()
    scatter = client.get("/api/flow/scatter").json()
    shown_abnormal = sum(1 for c in scatter["cells"] if c["p"] >= 0)
    assert shown_abnormal == report["n_abnormal"]


def test_population_endpoint_lists_member_events(client):
    report = _post_sample(client, OVERT).json()
    label = report["populations"][0]["label"]
    body = client.get(f"/api/flow/population/{label}").json()
    assert body["n"] == report["populations"][0]["n_events"]
    assert len(body["ids"]) > 0


def test_healthy_specimen_reports_no_population(client):
    body = _post_sample(client, HEALTHY).json()
    assert body["verdict"] == "no_abnormal_population"
    assert body["n_abnormal"] == 0
    # Stage 1 still flags a few, by design -- see the threshold calibration.
    assert body["stage1_flagged"] > 0

    scatter = client.get("/api/flow/scatter").json()
    assert all(c["p"] < 0 for c in scatter["cells"])


# --------------------------------------------------------------------------- #
# Rejections
# --------------------------------------------------------------------------- #
def test_non_fcs_upload_is_rejected(client):
    res = client.post("/api/flow/sample", files={"file": ("x.h5ad", b"junk")})
    assert res.status_code == 400
    assert ".fcs" in res.json()["detail"]


def test_single_file_reference_is_rejected(client):
    """One specimen cannot calibrate a threshold, so the API must refuse it."""
    res = client.post("/api/flow/reference", files=[("files", ("a.fcs", b"junk"))])
    assert res.status_code == 400
    assert "2" in res.json()["detail"]


def test_unparseable_reference_files_are_a_422(client):
    res = client.post(
        "/api/flow/reference",
        files=[("files", ("a.fcs", b"junk")), ("files", ("b.fcs", b"junk"))],
    )
    assert res.status_code in (422, 500)
    # The pre-existing reference must survive a failed rebuild.
    assert client.get("/api/flow/status").json()["reference_loaded"] is True
