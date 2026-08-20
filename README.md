# 🧬 AskCell

Two analysis surfaces over one backend, switchable from the button at the bottom
of the screen:

1. **Cytometry** *(default)* — finds abnormal cell populations in a flow or mass
   cytometry specimen by comparing it against a reference built from healthy
   specimens. This is the workflow the project is built around.
2. **scRNA-seq** — the original single-cell gene-expression browser: a WebGL
   scatterplot with gene colouring, gating, dot plots and a Claude chat agent.

> **Comes with built-in data on both sides.** The backend fits a healthy
> cytometry reference and loads a sample scRNA-seq dataset on startup, so both
> screens work the moment you open the app.

---

## 🩸 Cytometry: detecting abnormal populations

### What it does

Your cytometer measures ~14 surface proteins on a few hundred thousand cells and
writes one `.fcs` file — effectively a spreadsheet, one row per cell. AskCell
compares those cells against healthy marrow and reports any population that does
not belong.

```
.fcs file
  -> QC gating          drop debris, doublets, dead cells
  -> compensation       undo dye bleed between detectors
  -> arcsinh transform  compress ~5 decades onto a usable scale
  -> stage 1: flag      cells far from every healthy cell
  -> stage 2: cluster   keep only the flagged cells grouped together
  -> report             percentage + phenotype + picture
```

### Why two stages

The threshold is *measured*, not guessed: each healthy specimen is scored against
a reference built from the others, and the cutoff is the 99.9th percentile of the
resulting distribution. That makes the false-flag rate a chosen quantity — about
one healthy cell in a thousand.

Which means **stage 1 alone is not a detector.** On a 400,000-event file it flags
several hundred cells in a *perfectly healthy* person, and the rate cannot be
tuned away: pushing the threshold high enough to silence it also pushes it past
the small populations that matter most.

Stage 2 is the real test. Cancer is one cell that stopped maturing and started
copying itself, so its descendants land in a tight knot in marker space. Spurious
flags come from unrelated cells and land scattered. Same score, different shape.

This is also what separates a clone from **hematogones** — normal B-cell
precursors that are CD19+CD10+ with dim CD45, near enough the blast phenotype to
fool a single-marker rule. They are odd too, but spread smoothly along a
maturation path instead of knotted at one point.

### What comes out

Three things, from the same computation:

1. **A picture.** The healthy reference as a dim grey cloud, the patient's cells
   on top, abnormal ones in red. A red clump outside the grey cloud is the whole
   result in one frame.
2. **A percentage** — the number clinical practice actually uses.
3. **A phenotype**, recovered rather than assumed: which markers deviate and by
   how many standard deviations, plus a ranked list of entities the pattern
   resembles and the confirmatory tests each would need.

Ask about any of it in plain language (`Ask AskCell` tab). The agent reads the
finished report through tools and cannot invent a figure — every number it
quotes came from a tool call, and the calls it made are listed under each answer.

### Try it

```bash
cd backend
python make_mock_fcs.py        # generate the fixtures (~52 MB, seeded)
python run_detection.py        # run the pipeline, print reports
python benchmark.py            # full validation sweep -> benchmark/
```

### Measured performance

From `benchmark.py` — a dilution series at three acquisition depths, healthy
controls, and repeat runs. Full table in [`backend/benchmark/benchmark.md`](backend/benchmark/benchmark.md).

| Metric | Value |
| --- | --- |
| Limit of detection (500k events) | **0.01%** |
| Mean sensitivity, detected cases | 97.94% |
| Mean precision, detected cases | 100.00% |
| Specificity (healthy controls) | 100% (4/4) |
| Reproducibility | bit-identical across repeat runs |
| Throughput | ~1.5 s per 100k events |

**The limit is a cell count, not a percentage:**

| Events acquired | Lowest fraction found | ≈ cells |
| --- | --- | --- |
| 50,000 | 0.1% | ~50 |
| 200,000 | 0.05% | ~100 |
| 500,000 | 0.01% | ~50 |

Across a tenfold range of depth the smallest detectable population stayed at
roughly 50–100 cells while the *percentage* moved by a factor of ten. The
detector needs a certain number of cells to recognise a population as a
population; what fraction that represents is set by how many events you
acquired. So to lower the detectable percentage, acquire more events — the same
tradeoff clinical MRD assays make, and why they run millions of events.

The healthy controls contain hematogones on purpose. Not flagging them is the
harder half of the problem, and the reason specificity is reported alongside
sensitivity rather than after it.

### Using your own data

Drop files onto the centre pane, or use the left rail:

- **one file** → analysed as a patient specimen
- **several files** → used to build a new healthy reference (minimum 2)

The reference needs at least two specimens because the threshold is calibrated by
holding one out. Marker intensities are not comparable across antibody panels, so
a specimen is refused outright if it lacks any marker the reference was built on.

### What it will not do

The tool reports what a population *resembles*, never what it *is*.
Immunophenotype alone cannot classify a blood cancer — morphology, cytogenetics
and molecular tests are required, and two specimens with an identical flow
phenotype can be different diseases. So every candidate entity is reported with
the evidence for and against it and the tests that would actually settle it.

It also gives no treatment advice. It will describe what published literature
says is used for an entity, framed as background.

> ⚠️ **Research and educational use only.** Not a diagnostic device, and not
> clinically validated. All performance figures are on synthetic data, which
> measures internal consistency rather than clinical accuracy. One parameter
> (the cluster-linking radius) is calibrated against synthetic data and must be
> re-measured on real specimens; the guard test is
> `tests/test_flow_detect.py::test_radius_sits_in_the_measured_gap`.

---

## 🔬 scRNA-seq browser

An interactive **Single-Cell RNA-seq** analytics platform. Visualize massive
biomedical datasets in real time with hardware-accelerated WebGL (Deck.gl), and
query biological insights in natural language via a **Claude** agent with tool
use.

---

## ⚡ Quick start (Windows)

You need two free things installed first:

1. **Python 3.10–3.13** — https://www.python.org/downloads/
   (during install, tick **"Add Python to PATH"**)
2. **Node.js 18+** — https://nodejs.org (the "LTS" button)

Then:

1. **Unzip** this folder and **open it in VS Code** (File → Open Folder).
2. **Double-click `run-backend.bat`** (or in a terminal: `.\run-backend.bat`).
   A window opens, installs everything, and starts the API. Leave it open.
3. **Double-click `run-frontend.bat`** (or: `.\run-frontend.bat`) in a *second*
   window. Leave it open too.
4. Open your browser to **http://localhost:5173**.

That's it. The cytometry screen opens with a healthy reference already built.
Pick a specimen from `backend/sample_data/` — start with `patient_overt.fcs`,
then try `patient_normal.fcs` and `patient_mrd.fcs`.

Pan by dragging, zoom with the scroll wheel, hover a cell for its details. The
button at the bottom switches to the scRNA-seq browser.

> **First run only:** if `sample_data/` has no `.fcs` files, generate them with
> `cd backend && python make_mock_fcs.py`.

### To turn on the AI explanation (optional)

Detection works with **no key** — only the `Ask AskCell` panel needs one.

1. Get an Anthropic API key: https://console.anthropic.com/settings/keys
2. Copy `backend\.env.example` to `backend\.env` and put your key in it.
3. Restart `run-backend.bat`.

Then click **Explain this result**, or ask things like *"how confident is this,
and what would change it?"*

---

## 🍎 Quick start (macOS / Linux)

Same idea, run each block in its own terminal:

```bash
# Terminal 1 — backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # optional: add GEMINI_API_KEY for chat
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm install
cp .env.example .env
npm run dev                     # open http://localhost:5173
```

---

## Architecture

```
AskCell/
├── run-backend.bat / run-frontend.bat   # one-click launch (Windows)
├── backend/                             # FastAPI Python core
│   ├── app/
│   │   ├── main.py            # gateway; reference fitted at startup
│   │   ├── flow/              # ---- the cytometry pipeline ----
│   │   │   ├── panel.py           marker names + panel fingerprinting
│   │   │   ├── fcs_ingest.py      FCS -> AnnData, compensation, arcsinh
│   │   │   ├── qc.py              debris / doublet / dead-cell gating
│   │   │   ├── reference.py       "what normal looks like" + calibration
│   │   │   ├── detect.py          two-stage detection
│   │   │   └── interpret.py       candidate entities + evidence
│   │   ├── flow_engine.py     holds reference + specimen, shared embedding
│   │   ├── flow_agent.py      Claude agent over the finished report
│   │   ├── cell_engine.py     scRNA-seq engine (single dataset)
│   │   └── ai_agent.py        scRNA-seq gene-expression agent
│   ├── make_mock_fcs.py       generates the cytometry fixtures
│   ├── run_detection.py       CLI: whole pipeline, printed report
│   ├── benchmark.py           validation sweep -> benchmark/
│   ├── tests/                 92 tests
│   └── sample_data/
└── frontend/                            # React (Vite)
    └── src/
        ├── Root.jsx           mode switch between the two surfaces
        ├── FlowApp.jsx        the cytometry screen
        ├── App.jsx            the scRNA-seq browser
        └── components/
            ├── FlowViewer.jsx     healthy cloud + specimen, abnormal in red
            ├── FlowReport.jsx     verdict, stages, phenotype, differential
            ├── FlowChat.jsx       plain-language explanation + follow-ups
            └── UmapViewer.jsx     scRNA-seq scatterplot
```

---

## How it works

**Cytometry:**

```
[open app] → reference fitted from healthy .fcs (cached) → grey cloud renders
                              │
[drop patient .fcs] → gate → score every cell → cluster the flagged ones
                              │
                        red clump + percentage + phenotype
                              │
[Ask: "how confident is this?"] → Claude reads the report through tools
                              → answer, with the tools it consulted shown
```

**scRNA-seq:**

```
[switch mode] → mock_pbmc.h5ad auto-loaded → Deck.gl renders @ 60 FPS
                              │
[Chat: "Check expression of CD3D"] → Claude calls get_gene_expression
        → real mean/max metrics from the matrix → synthesized answer
```

The cytometry fixtures are 60k–400k events on a 14-colour B-ALL panel; the
scRNA-seq mock has 3,000 immune cells in 5 clusters with real marker genes
(CD3D, MS4A1, NKG7, LYZ, PDCD1, GAPDH, …), so both agents answer from real
numbers.

---

## Using your own data

Drag any `.h5ad` file onto the left pane to replace the sample. The only
requirement: it must already contain 2D UMAP coordinates in
`adata.obsm['X_umap']` (the dot positions on the map). Standard processed
datasets like `pbmc3k` have this. A raw count matrix does not — run it through
the standard UMAP step first (e.g. in scanpy on Python 3.12 or Google Colab).

### Large files

Uploads are bottlenecked by your **internet upload speed** — a 2 GB file can
take ~20 minutes to send before parsing even starts. The viewer only displays
up to 150k cells, so for huge datasets it's far faster to **downsample first**:

```bash
cd backend
.venv/Scripts/python downsample_h5ad.py /path/to/big.h5ad
# -> writes big.subsampled.h5ad (100k cells) — upload that instead
```

Pass a custom output name / cell count: `python downsample_h5ad.py big.h5ad out.h5ad 150000`.
The app also warns you before a large upload and shows a live progress bar + ETA.

---

## API reference

### Cytometry

| Method | Endpoint                      | Body                          | Returns                                        |
| ------ | ----------------------------- | ----------------------------- | ---------------------------------------------- |
| GET    | `/api/flow/status`            | —                             | `{ reference_loaded, sample_loaded, ... }`     |
| POST   | `/api/flow/reference`         | `multipart` 2+ `.fcs` files   | `{ message, reference }`                       |
| POST   | `/api/flow/sample`            | `multipart` one `.fcs` file   | full detection report                          |
| GET    | `/api/flow/report`            | —                             | the report for the loaded specimen             |
| GET    | `/api/flow/interpret`         | —                             | ranked candidate entities per population       |
| POST   | `/api/flow/explain`           | —                             | `{ reply, tools_used }` — plain-language       |
| POST   | `/api/flow/chat`              | `{ "message": "..." }`        | `{ reply, tools_used }`                        |
| GET    | `/api/flow/scatter`           | —                             | `{ reference, cells: [{id,x,y,s,p}] }`         |
| GET    | `/api/flow/population/{n}`    | —                             | `{ label, n, ids }`                            |

In `/api/flow/scatter`, `s` is the cell's distance from normal and `p` is the
population it belongs to (`-1` for none). Abnormal cells are never thinned by the
display subsample — a 189-cell population would otherwise vanish.

### scRNA-seq

| Method | Endpoint       | Body                       | Returns                                   |
| ------ | -------------- | -------------------------- | ----------------------------------------- |
| POST   | `/api/upload`  | `multipart` `.h5ad` file   | `{ message, filename }`                   |
| GET    | `/api/umap`    | —                          | `{ total_cells, cells: [{id,x,y}] }`      |
| POST   | `/api/chat`    | `{ "message": "..." }`     | `{ reply }`                               |
| GET    | `/api/status`  | —                          | `{ loaded, filename, n_cells, n_genes }`  |

---

## Notes & guardrails

- **Zero-config demo**: the bundled sample auto-loads on startup; disable by
  setting `SAMPLE_H5AD=` (empty) in `backend/.env`.
- **In-memory lifecycle**: the dataset lives in a process-global singleton;
  chat queries never re-read from disk.
- **JSON serialization**: all NumPy scalars are cast to Python `float`/`int`
  before leaving the backend, preventing FastAPI encoder crashes.
- **No fabrication**: the agent is instructed never to guess metrics — every
  number comes from the real matrix via the tool.
- **Python 3.13 friendly**: no package here needs a C compiler.
