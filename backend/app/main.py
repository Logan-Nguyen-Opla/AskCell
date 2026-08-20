"""
main.py
=======
FastAPI gateway for AskCell.

Two workflows share this app.

Cytometry (``/api/flow/*``) is the primary one: compare a patient .fcs specimen
against a reference built from healthy specimens and report abnormal cell
populations.

    GET  /api/flow/status               reference / specimen state
    POST /api/flow/reference            build "normal" from 2+ healthy .fcs
    POST /api/flow/sample               analyse one patient .fcs
    GET  /api/flow/report               the detection report
    GET  /api/flow/interpret            ranked candidate entities
    POST /api/flow/explain              plain-language interpretation (Claude)
    POST /api/flow/chat                 follow-up questions about the result
    GET  /api/flow/scatter              viewer points, reference + specimen
    GET  /api/flow/population/{label}   event ids in one population

scRNA-seq (the original browser) reads a single .h5ad at a time:

    POST /api/upload   multipart .h5ad  -> parse + cache matrix in memory
    GET  /api/umap                      -> lean {id, x, y} coordinate array
    POST /api/chat     {message}        -> Claude reply (with tool execution)
    GET  /api/status                    -> dataset metadata

``ALLOWED_ORIGINS`` defaults to localhost only; set it before any real
deployment.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import ai_agent
from .cell_engine import cell_engine_instance
from .flow_engine import flow_session, read_upload_to_temp

load_dotenv()  # read backend/.env (ANTHROPIC_API_KEY, etc.)

# Path to the bundled sample dataset (auto-loaded on startup so the app shows
# data with zero setup). Override with the SAMPLE_H5AD env var, or set it to an
# empty string to disable auto-loading.
_DEFAULT_SAMPLE = (
    Path(__file__).resolve().parent.parent / "sample_data" / "mock_pbmc.h5ad"
)
SAMPLE_H5AD = os.environ.get("SAMPLE_H5AD", str(_DEFAULT_SAMPLE))

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
    """On startup, auto-load the bundled sample dataset and healthy reference."""
    try:
        if (
            SAMPLE_H5AD
            and not cell_engine_instance.is_loaded()
            and os.path.exists(SAMPLE_H5AD)
        ):
            cell_engine_instance.load(SAMPLE_H5AD, os.path.basename(SAMPLE_H5AD))
            print(f"[AskCell] Auto-loaded sample dataset: {SAMPLE_H5AD}")
        elif SAMPLE_H5AD and not os.path.exists(SAMPLE_H5AD):
            print(
                f"[AskCell] No sample dataset at {SAMPLE_H5AD} "
                "(upload an .h5ad to begin)."
            )
    except Exception as exc:  # never let a bad sample crash startup
        print(f"[AskCell] Could not auto-load sample dataset: {exc}")

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
class ChatRequest(BaseModel):
    message: str


class GenesRequest(BaseModel):
    genes: list[str]


class SelectionRequest(BaseModel):
    cell_ids: list[int]


class FlowChatRequest(BaseModel):
    message: str
    history: list[dict] | None = None


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@app.get("/")
def root() -> dict:
    return {"service": "AskCell API", "status": "ok", "version": "1.0.0"}


@app.post("/api/upload")
async def upload_dataset(file: UploadFile = File(...)) -> dict:
    """Accept an .h5ad upload, parse it, and cache it in memory."""
    if not file.filename or not file.filename.endswith(".h5ad"):
        raise HTTPException(
            status_code=400,
            detail="Only .h5ad (AnnData) files are supported.",
        )

    # Stream the upload to a temp file, then hand the path to the engine.
    # The engine takes ownership (owns_file=True): it deletes the temp itself
    # once loaded in-memory, or keeps it alive for backed (big-file) mode. We
    # only clean up here if load() fails before taking ownership.
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=".h5ad"
        ) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name

        cell_engine_instance.load(tmp_path, file.filename, owns_file=True)

    except ValueError as exc:
        # Validation failure (e.g. missing UMAP) -> 422.
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise HTTPException(
            status_code=500, detail=f"Failed to process file: {exc}"
        ) from exc
    finally:
        await file.close()

    return {"message": "File processed successfully", "filename": file.filename}


@app.get("/api/umap")
def get_umap() -> dict:
    """Return the cached UMAP coordinates for the GPU scatterplot."""
    if not cell_engine_instance.is_loaded():
        raise HTTPException(
            status_code=400,
            detail="No dataset loaded. Upload an .h5ad file first.",
        )
    return cell_engine_instance.get_umap_coordinates()


@app.get("/api/status")
def get_status() -> dict:
    """Lightweight dataset metadata for the front-end state indicators."""
    if not cell_engine_instance.is_loaded():
        return {"loaded": False}
    return {"loaded": True, **cell_engine_instance.summary()}


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    """Run a user message through the Claude agent (with tool execution)."""
    if not cell_engine_instance.is_loaded():
        raise HTTPException(
            status_code=400,
            detail="No dataset loaded. Upload an .h5ad file before chatting.",
        )

    message = (req.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    try:
        reply = ai_agent.run_chat(message)
    except RuntimeError as exc:
        # Missing API key, etc.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Agent error: {exc}"
        ) from exc

    return {"reply": reply}


# --------------------------------------------------------------------------- #
# Visualization endpoints (VIP-style features)
# --------------------------------------------------------------------------- #
def _require_loaded() -> None:
    if not cell_engine_instance.is_loaded():
        raise HTTPException(
            status_code=400, detail="No dataset loaded. Upload an .h5ad first."
        )


@app.post("/api/compute_umap")
def compute_umap() -> dict:
    """Attempt to compute real UMAP via scanpy and replace the PCA fallback."""
    _require_loaded()
    return cell_engine_instance.compute_umap()


@app.get("/api/genes")
def list_genes() -> dict:
    """All gene symbols in the loaded dataset (for autocomplete)."""
    _require_loaded()
    return {"genes": cell_engine_instance.list_genes()}


@app.get("/api/gene/{gene}")
def gene_per_cell(gene: str) -> dict:
    """Per-cell expression vector for one gene (colors the embedding)."""
    _require_loaded()
    return cell_engine_instance.gene_per_cell(gene)


@app.post("/api/expression/grouped")
def grouped_expression(req: GenesRequest) -> dict:
    """Per-cell-type mean / % expressing for the requested genes."""
    _require_loaded()
    if not req.genes:
        raise HTTPException(status_code=400, detail="No genes requested.")
    return cell_engine_instance.grouped_expression(req.genes)


@app.post("/api/selection")
def selection(req: SelectionRequest) -> dict:
    """Summary stats for a set of selected cell ids (lasso/box select)."""
    _require_loaded()
    return cell_engine_instance.selection_stats(req.cell_ids)


@app.get("/api/qc")
def qc() -> dict:
    """Numeric per-cell QC metrics for the right-panel histograms."""
    _require_loaded()
    return cell_engine_instance.qc_metrics()


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
