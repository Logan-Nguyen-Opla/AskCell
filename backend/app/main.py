"""
main.py
=======
FastAPI gateway for AskCell.

Cytometry (``/api/flow/*``) is the app's single workflow: compare a patient
.fcs specimen against a reference built from healthy specimens and report
abnormal cell populations.

    GET  /api/flow/status               reference / specimen state
    POST /api/flow/reference            build "normal" from 2+ healthy .fcs
    POST /api/flow/sample               analyse one patient .fcs
    GET  /api/flow/report               the detection report
    GET  /api/flow/interpret            ranked candidate entities
    POST /api/flow/explain              plain-language interpretation (Claude)
    POST /api/flow/chat                 follow-up questions about the result
    GET  /api/flow/scatter              viewer points, reference + specimen
    GET  /api/flow/population/{label}   event ids in one population

``ALLOWED_ORIGINS`` defaults to localhost only; set it before any real
deployment.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .flow_engine import flow_session, read_upload_to_temp

load_dotenv()  # read backend/.env (ANTHROPIC_API_KEY, etc.)

# Bundled healthy cytometry reference. Fitting takes a few seconds, so a fitted
# model is cached to disk and reused; delete the .npz (or POST a new reference)
# to force a rebuild.
_SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"
_REFERENCE_CACHE = _SAMPLE_DIR / "reference.npz"
_NORMAL_GLOB = "normal_bm_*.fcs"


def _autoload_reference() -> None:
    """Load or fit the bundled healthy reference so the app works on open."""
    from .flow import NormalReference

    if _REFERENCE_CACHE.exists():
        flow_session.set_reference(NormalReference.load(str(_REFERENCE_CACHE)))
        print(f"[AskCell] Loaded cached reference: {_REFERENCE_CACHE.name}")
        return

    paths = sorted(str(p) for p in _SAMPLE_DIR.glob(_NORMAL_GLOB))
    if len(paths) < 2:
        print(
            "[AskCell] No bundled healthy reference found. Generate the "
            "fixtures with `python make_mock_fcs.py`, or upload at least 2 "
            "healthy .fcs files to /api/flow/reference."
        )
        return

    flow_session.load_reference_from_paths(paths)
    if flow_session.reference is not None:
        flow_session.reference.save(str(_REFERENCE_CACHE))
    print(f"[AskCell] Fitted reference from {len(paths)} healthy specimens.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """On startup, auto-load the bundled healthy reference."""
    try:
        _autoload_reference()
    except Exception as exc:  # a bad reference must not stop the server
        print(f"[AskCell] Could not load the healthy reference: {exc}")

    yield


app = FastAPI(title="AskCell API", version="1.0.0", lifespan=lifespan)

# --------------------------------------------------------------------------- #
# CORS
# --------------------------------------------------------------------------- #
_origins = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class FlowChatRequest(BaseModel):
    message: str
    history: list[dict] | None = None


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.get("/")
def root() -> dict:
    return {"service": "AskCell API", "status": "ok", "version": "1.0.0"}


# --------------------------------------------------------------------------- #
# Cytometry: healthy reference + patient comparison
# --------------------------------------------------------------------------- #
def _cleanup(paths: list[str]) -> None:
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except Exception:
            pass


def _require_fcs(name: str | None) -> None:
    if not name or not name.lower().endswith(".fcs"):
        raise HTTPException(
            status_code=400,
            detail="Only .fcs (Flow Cytometry Standard) files are supported.",
        )


@app.get("/api/flow/status")
def flow_status() -> dict:
    """Whether a reference and/or a specimen is currently loaded."""
    return flow_session.status()


@app.post("/api/flow/reference")
async def flow_build_reference(files: list[UploadFile] = File(...)) -> dict:
    """Fit the 'what normal looks like' model from healthy .fcs specimens.

    At least two are required: the detection threshold is calibrated by holding
    one specimen out and scoring it against the others, so with a single file
    the cutoff could only be guessed.
    """
    if len(files) < 2:
        raise HTTPException(
            status_code=400,
            detail=(
                "At least 2 healthy specimens are required. The detection "
                "threshold is measured by holding one out, which is impossible "
                "with a single file."
            ),
        )

    tmp_paths: list[str] = []
    try:
        for f in files:
            _require_fcs(f.filename)
            tmp_paths.append(read_upload_to_temp(f.file))

        # Preserve the original names so the report can cite its sources.
        named: list[str] = []
        for tmp, f in zip(tmp_paths, files):
            target = os.path.join(
                os.path.dirname(tmp), os.path.basename(f.filename or "normal.fcs")
            )
            if target != tmp:
                try:
                    os.replace(tmp, target)
                    named.append(target)
                    continue
                except Exception:
                    pass
            named.append(tmp)
        tmp_paths = named

        summary = flow_session.load_reference_from_paths(tmp_paths)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to build reference: {exc}"
        ) from exc
    finally:
        for f in files:
            await f.close()
        _cleanup(tmp_paths)

    return {"message": "Reference built", "reference": summary}


@app.post("/api/flow/sample")
async def flow_upload_sample(file: UploadFile = File(...)) -> dict:
    """Upload one patient specimen, gate it, and compare it to the reference."""
    _require_fcs(file.filename)
    if not flow_session.has_reference():
        raise HTTPException(
            status_code=400,
            detail=(
                "No healthy reference is loaded. Build one from at least 2 "
                "healthy specimens before analysing a patient sample."
            ),
        )

    tmp_path = None
    try:
        tmp_path = read_upload_to_temp(file.file)
        report = flow_session.load_sample_from_path(tmp_path, file.filename)
    except ValueError as exc:
        # Panel mismatch and similar: the request is well-formed but the data
        # cannot be compared, which is a 422 rather than a server error.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to analyse specimen: {exc}"
        ) from exc
    finally:
        await file.close()
        _cleanup([tmp_path] if tmp_path else [])

    return report


@app.get("/api/flow/report")
def flow_report() -> dict:
    """The detection report for the loaded specimen."""
    if not flow_session.has_sample():
        raise HTTPException(
            status_code=400, detail="No specimen has been analysed yet."
        )
    return flow_session.public_report()


@app.get("/api/flow/scatter")
def flow_scatter() -> dict:
    """Viewer points: the healthy cloud plus the specimen's cells."""
    if not flow_session.has_reference():
        raise HTTPException(
            status_code=400, detail="No healthy reference is loaded."
        )
    return flow_session.scatter()


@app.get("/api/flow/interpret")
def flow_interpret() -> dict:
    """Ranked candidate entities for each detected population.

    Kept separate from /api/flow/report because it is a different kind of claim:
    the report is a measurement, this is a hypothesis about what the measurement
    resembles. Merging them would blur that line.
    """
    if not flow_session.has_sample():
        raise HTTPException(
            status_code=400, detail="No specimen has been analysed yet."
        )
    from .flow.interpret import interpret_report

    return interpret_report(flow_session.public_report())


@app.post("/api/flow/explain")
def flow_explain() -> dict:
    """Plain-language interpretation of the loaded specimen, via Claude."""
    if not flow_session.has_sample():
        raise HTTPException(
            status_code=400, detail="No specimen has been analysed yet."
        )
    from . import flow_agent

    try:
        return flow_agent.explain_current()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc


@app.post("/api/flow/chat")
def flow_chat(req: FlowChatRequest) -> dict:
    """Ask a follow-up question about the loaded specimen's result."""
    if not flow_session.has_sample():
        raise HTTPException(
            status_code=400,
            detail="Analyse a specimen before asking questions about it.",
        )
    message = (req.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    from . import flow_agent

    try:
        return flow_agent.run_flow_chat(message, req.history)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}") from exc


@app.get("/api/flow/population/{label}")
def flow_population(label: int) -> dict:
    """Event indices belonging to one detected abnormal population."""
    if not flow_session.has_sample():
        raise HTTPException(
            status_code=400, detail="No specimen has been analysed yet."
        )
    return flow_session.population_events(label)
