import React, { useCallback, useEffect, useRef, useState } from "react";
import UmapViewer from "./components/UmapViewer.jsx";
import ChatSidebar from "./components/ChatSidebar.jsx";
import ControlsPanel from "./components/ControlsPanel.jsx";
import ExpressionPlots from "./components/ExpressionPlots.jsx";
import QcHistograms from "./components/QcHistograms.jsx";
import { API_BASE } from "./lib/api.js";

// Files bigger than this trigger a "this will take a while" confirmation.
const BIG_FILE_BYTES = 200 * 1024 * 1024; // 200 MB
// Rough upstream assumption for the *pre-upload* estimate (~16 Mbps). The live
// ETA during upload uses the real measured rate.
const EST_UPLOAD_BPS = 2 * 1024 * 1024;

function formatBytes(b) {
  if (b >= 1024 ** 3) return (b / 1024 ** 3).toFixed(1) + " GB";
  return Math.round(b / (1024 * 1024)) + " MB";
}
function formatDuration(sec) {
  if (sec < 60) return Math.ceil(sec) + "s";
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return s ? `${m}m ${s}s` : `${m}m`;
}

export default function App() {
  // dataset
  const [cells, setCells] = useState([]);
  const [categories, setCategories] = useState([]);
  const [labelField, setLabelField] = useState(null);
  const [status, setStatus] = useState("idle");
  const [filename, setFilename] = useState(null);
  const [error, setError] = useState(null);
  const [dragging, setDragging] = useState(false);

  // upload progress
  const [uploadPct, setUploadPct] = useState(null); // 0-100 while sending
  const [uploadEta, setUploadEta] = useState(null);
  const [uploadPhase, setUploadPhase] = useState(null); // "sending" | "processing"
  const [pendingFile, setPendingFile] = useState(null); // big file awaiting confirm

  // coloring / genes
  const [colorMode, setColorMode] = useState("celltype");
  const [umapAuto, setUmapAuto] = useState(false);
  const [allGenes, setAllGenes] = useState([]);
  const [geneInput, setGeneInput] = useState("");
  const [genes, setGenes] = useState([]);
  const [activeGene, setActiveGene] = useState(null);
  const [geneData, setGeneData] = useState({}); // gene -> {gene,values,vmin,vmax}
  const [geneError, setGeneError] = useState(null);
  const [grouped, setGrouped] = useState(null);

  // viewer controls
  const [hidden, setHidden] = useState(() => new Set());
  const [pointSize, setPointSize] = useState(4);
  const [selectMode, setSelectMode] = useState(false);
  const [selection, setSelection] = useState(null);

  // right rail
  const [rightTab, setRightTab] = useState("chat");

  const datasetReady = status === "ready";
  const geneCells = activeGene ? geneData[activeGene] || null : null;

  // Reset all derived analysis state when a new dataset loads.
  const resetAnalysis = useCallback(() => {
    setColorMode("celltype");
    setUmapAuto(false);
    setAllGenes([]);
    setGeneInput("");
    setGenes([]);
    setActiveGene(null);
    setGeneData({});
    setGeneError(null);
    setGrouped(null);
    setHidden(new Set());
    setSelectMode(false);
    setSelection(null);
  }, []);

  // On first load, pick up an already-cached dataset (bundled sample).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await fetch(`${API_BASE}/api/status`).then((r) => r.json());
        if (!cancelled && s.loaded) {
          const [u, g] = await Promise.all([
            fetch(`${API_BASE}/api/umap`).then((r) => r.json()),
            fetch(`${API_BASE}/api/genes`).then((r) => r.json()),
          ]);
          if (!cancelled) {
            setCells(u.cells);
            setCategories(u.categories || []);
            setLabelField(u.label_field || null);
            setFilename(s.filename);
            setAllGenes(g.genes || []);
            setUmapAuto(!!s.umap_auto);
            setStatus("ready");
          }
        }
      } catch {
        /* backend not up yet — stay idle */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Actual upload via XHR so we can show real upload progress + a live ETA.
  const doUpload = useCallback(
    (file) => {
      setStatus("uploading");
      setError(null);
      resetAnalysis();
      setUploadPct(0);
      setUploadPhase("sending");
      setUploadEta(null);

      const form = new FormData();
      form.append("file", file);
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE}/api/upload`);
      const startedAt = performance.now();

      xhr.upload.onprogress = (e) => {
        if (!e.lengthComputable) return;
        const pct = (e.loaded / e.total) * 100;
        setUploadPct(pct);
        const elapsed = (performance.now() - startedAt) / 1000;
        const rate = e.loaded / Math.max(elapsed, 0.001);
        const remain = (e.total - e.loaded) / Math.max(rate, 1);
        setUploadEta(remain > 1 ? formatDuration(remain) : null);
        if (pct >= 99.9) setUploadPhase("processing"); // server parsing now
      };

      xhr.onload = async () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          setUploadPhase("processing");
          setUploadEta(null);
          try {
            const upData = JSON.parse(xhr.responseText || "{}");
            const umapRes = await fetch(`${API_BASE}/api/umap`);
            if (!umapRes.ok) {
              const err = await umapRes.json().catch(() => ({}));
              throw new Error(err.detail || `UMAP fetch failed (${umapRes.status})`);
            }
            const [umapData, genesData] = await Promise.all([
              umapRes.json(),
              fetch(`${API_BASE}/api/genes`).then((r) => r.json()),
            ]);
            setCells(umapData.cells);
            setCategories(umapData.categories || []);
            setLabelField(umapData.label_field || null);
            setAllGenes(genesData.genes || []);
            setUmapAuto(!!umapData.umap_auto);
            setFilename(upData.filename || file.name);
            setStatus("ready");
          } catch (e) {
            setStatus("error");
            setError(e.message);
          }
        } else {
          let detail = `Upload failed (${xhr.status})`;
          try {
            detail = JSON.parse(xhr.responseText).detail || detail;
          } catch {
            /* non-JSON error body */
          }
          setStatus("error");
          setError(detail);
        }
        setUploadPct(null);
        setUploadPhase(null);
      };

      xhr.onerror = () => {
        setStatus("error");
        setError(
          "Upload failed — network dropped or the file exceeded the server limit."
        );
        setUploadPct(null);
        setUploadPhase(null);
      };

      xhr.send(form);
    },
    [resetAnalysis]
  );

  const handleFile = useCallback(
    (file) => {
      if (!file) return;
      if (!file.name.endsWith(".h5ad")) {
        setStatus("error");
        setError("Please upload an .h5ad file");
        return;
      }
      if (file.size > BIG_FILE_BYTES) {
        setPendingFile(file); // ask before committing to a long upload
        return;
      }
      doUpload(file);
    },
    [doUpload]
  );

  const confirmPending = useCallback(() => {
    const f = pendingFile;
    setPendingFile(null);
    if (f) doUpload(f);
  }, [pendingFile, doUpload]);

  // ---- Gene handling ----
  const fetchGene = useCallback(
    async (sym) => {
      const res = await fetch(`${API_BASE}/api/gene/${encodeURIComponent(sym)}`);
      if (!res.ok) throw new Error(`lookup failed (${res.status})`);
      return res.json();
    },
    []
  );

  const onSubmitGene = useCallback(
    async (raw) => {
      const sym = (raw || "").trim();
      if (!sym || !datasetReady) return;
      setGeneError(null);
      try {
        const data = await fetchGene(sym);
        if (data.error) {
          setGeneError(`“${sym}” not found`);
          return;
        }
        setGeneData((prev) => ({ ...prev, [data.gene]: data }));
        setGenes((prev) => (prev.includes(data.gene) ? prev : [...prev, data.gene]));
        setActiveGene(data.gene);
        setColorMode("gene");
        setGeneInput("");
      } catch (e) {
        setGeneError(e.message);
      }
    },
    [datasetReady, fetchGene]
  );

  const onPickGene = useCallback(
    async (g) => {
      setActiveGene(g);
      setColorMode("gene");
      if (!geneData[g]) {
        try {
          const data = await fetchGene(g);
          if (!data.error) setGeneData((prev) => ({ ...prev, [g]: data }));
        } catch {
          /* ignore */
        }
      }
    },
    [geneData, fetchGene]
  );

  const onRemoveGene = useCallback(
    (g) => {
      setGenes((prev) => {
        const next = prev.filter((x) => x !== g);
        if (activeGene === g) {
          const fallback = next[next.length - 1] || null;
          setActiveGene(fallback);
          if (!fallback) setColorMode("celltype");
        }
        return next;
      });
    },
    [activeGene]
  );

  const handleGeneInput = useCallback(
    (v) => {
      setGeneInput(v);
      if (geneError) setGeneError(null);
    },
    [geneError]
  );

  // Refetch grouped (dot/heatmap) whenever the gene set changes.
  useEffect(() => {
    if (!datasetReady || genes.length === 0) {
      setGrouped(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/expression/grouped`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ genes }),
        });
        if (!res.ok) return;
        const data = await res.json();
        if (!cancelled) setGrouped(data);
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [genes, datasetReady]);

  // ---- Legend + selection ----
  const onToggleCategory = useCallback((idx) => {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  }, []);

  const onSelect = useCallback(async (ids) => {
    if (!ids || ids.length === 0) {
      setSelection(null);
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/selection`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cell_ids: ids }),
      });
      if (!res.ok) return;
      const data = await res.json();
      setSelection(data);
      setRightTab("chat");
    } catch {
      /* ignore */
    }
  }, []);

  // ---- Drag & drop ----
  const onDrop = useCallback(
    (e) => {
      e.preventDefault();
      setDragging(false);
      handleFile(e.dataTransfer.files?.[0]);
    },
    [handleFile]
  );
  const onDragOver = useCallback((e) => {
    e.preventDefault();
    setDragging(true);
  }, []);
  const onDragLeave = useCallback((e) => {
    e.preventDefault();
    setDragging(false);
  }, []);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-950 text-slate-200">
      {/* ---------------- Left controls rail ---------------- */}
      <ControlsPanel
        status={status}
        filename={filename}
        cellCount={cells.length}
        error={error}
        datasetReady={datasetReady}
        onFile={handleFile}
        colorMode={colorMode}
        onUseCellType={() => setColorMode("celltype")}
        geneInput={geneInput}
        setGeneInput={handleGeneInput}
        onSubmitGene={onSubmitGene}
        genes={genes}
        activeGene={activeGene}
        onPickGene={onPickGene}
        onRemoveGene={onRemoveGene}
        geneError={geneError}
        allGenes={allGenes}
        categories={categories}
        labelField={labelField}
        hidden={hidden}
        onToggleCategory={onToggleCategory}
        pointSize={pointSize}
        setPointSize={setPointSize}
        selectMode={selectMode}
        setSelectMode={setSelectMode}
      />

      {/* ---------------- Center: embedding + plots ---------------- */}
      <div className="flex min-w-0 flex-1 flex-col">
        <div
          className="relative flex-1"
          onDrop={onDrop}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
        >
          {datasetReady ? (
            <UmapViewer
              cells={cells}
              categories={categories}
              labelField={labelField}
              colorMode={colorMode}
              geneValues={geneCells}
              hidden={hidden}
              pointSize={pointSize}
              selectMode={selectMode}
              onSelect={onSelect}
            />
          ) : (
            <EmptyState
              status={status}
              error={error}
              uploadPct={uploadPct}
              uploadPhase={uploadPhase}
              uploadEta={uploadEta}
            />
          )}

          {pendingFile && (
            <BigFilePrompt
              file={pendingFile}
              onConfirm={confirmPending}
              onCancel={() => setPendingFile(null)}
            />
          )}

          {dragging && (
            <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm">
              <div className="rounded-2xl border-2 border-dashed border-indigo-400 px-10 py-8 text-center">
                <div className="mb-2 text-4xl">⬇</div>
                <p className="font-medium text-indigo-200">Drop your .h5ad dataset</p>
              </div>
            </div>
          )}
        </div>

        {datasetReady && umapAuto && (
          <UmapAutoBanner
            filename={filename}
            onComputed={(newUmapData) => {
              setCells(newUmapData.cells);
              setCategories(newUmapData.categories || []);
              setLabelField(newUmapData.label_field || null);
              setUmapAuto(false);
            }}
          />
        )}

        {datasetReady && (
          <div className="h-72 shrink-0 border-t border-slate-800 bg-slate-900/30">
            <ExpressionPlots
              genes={genes}
              grouped={grouped}
              activeGene={activeGene}
              geneCells={geneCells}
              cells={cells}
              categories={categories}
            />
          </div>
        )}
      </div>

      {/* ---------------- Right rail: selection + Chat/QC ---------------- */}
      <div className="flex h-full w-96 shrink-0 flex-col border-l border-slate-800">
        {selection && (
          <SelectionCard selection={selection} onClear={() => setSelection(null)} />
        )}

        <div className="flex border-b border-slate-800">
          {["chat", "qc"].map((t) => (
            <button
              key={t}
              onClick={() => setRightTab(t)}
              className={`flex-1 px-3 py-2.5 text-xs font-medium uppercase tracking-wide transition ${
                rightTab === t
                  ? "border-b-2 border-indigo-400 text-indigo-200"
                  : "text-slate-500 hover:text-slate-300"
              }`}
            >
              {t === "chat" ? "AI Chat" : "QC"}
            </button>
          ))}
        </div>

        <div className="flex min-h-0 flex-1 flex-col">
          {rightTab === "chat" ? (
            <ChatSidebar datasetReady={datasetReady} />
          ) : (
            <QcHistograms
              apiUrl={API_BASE}
              reloadKey={filename}
              datasetReady={datasetReady}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function SelectionCard({ selection, onClear }) {
  return (
    <div className="border-b border-emerald-500/30 bg-emerald-500/5 px-4 py-3">
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs text-emerald-200">
          {selection.n.toLocaleString()} cells selected
        </span>
        <button
          onClick={onClear}
          className="font-mono text-[10px] text-slate-400 hover:text-rose-400"
        >
          clear
        </button>
      </div>
      {selection.by_cell_type?.length > 0 && (
        <div className="mt-2 space-y-0.5">
          {selection.by_cell_type.slice(0, 5).map((b) => (
            <div key={b.cell_type} className="flex justify-between font-mono text-[10px] text-slate-300">
              <span className="truncate">{b.cell_type}</span>
              <span className="text-slate-500">{b.count}</span>
            </div>
          ))}
        </div>
      )}
      {selection.top_genes?.length > 0 && (
        <div className="mt-2">
          <div className="mb-1 font-mono text-[9px] uppercase tracking-widest text-slate-500">
            enriched genes
          </div>
          <div className="flex flex-wrap gap-1">
            {selection.top_genes.slice(0, 8).map((g) => (
              <span
                key={g.gene}
                className="rounded bg-slate-800/70 px-1.5 py-0.5 font-mono text-[10px] text-emerald-200"
                title={
                  g.enrichment != null
                    ? `mean ${g.mean} · +${g.enrichment} vs all`
                    : `mean ${g.mean}`
                }
              >
                {g.gene}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function EmptyState({ status, error, uploadPct, uploadPhase, uploadEta }) {
  const uploading = status === "uploading";

  return (
    <div className="flex h-full w-full flex-col items-center justify-center bg-slate-950">
      <div className="mb-5 grid grid-cols-6 gap-1.5 opacity-30">
        {Array.from({ length: 36 }).map((_, i) => (
          <span
            key={i}
            className="h-1.5 w-1.5 rounded-full bg-indigo-400"
            style={{ opacity: 0.2 + ((i * 37) % 80) / 100 }}
          />
        ))}
      </div>

      {uploading ? (
        <div className="w-80 max-w-[80%] text-center">
          <h3 className="mb-3 text-lg font-medium text-slate-300">
            {uploadPhase === "processing"
              ? "Processing on server…"
              : "Uploading…"}
          </h3>
          <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
            <div
              className="h-full rounded-full bg-indigo-500 transition-[width] duration-200"
              style={{
                width:
                  uploadPhase === "processing"
                    ? "100%"
                    : `${Math.max(2, uploadPct || 0)}%`,
              }}
            />
          </div>
          <div className="mt-2 font-mono text-xs text-slate-500">
            {uploadPhase === "processing"
              ? "parsing the dataset — almost there"
              : `${Math.round(uploadPct || 0)}% uploaded${
                  uploadEta ? ` · ~${uploadEta} left` : ""
                }`}
          </div>
        </div>
      ) : (
        <>
          <h3 className="text-lg font-medium text-slate-300">
            Drop an .h5ad file to begin
          </h3>
          <p className="mt-2 max-w-sm text-center text-sm text-slate-500">
            {status === "error"
              ? error
              : "Upload a single-cell RNA-seq dataset with pre-computed UMAP coordinates to explore it in real time."}
          </p>
        </>
      )}
    </div>
  );
}

function UmapAutoBanner({ filename, onComputed }) {
  // "computing" | "no_lib" | "too_large" | "error"
  const [state, setState] = useState("computing");
  const [script, setScript] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const timerRef = useRef(null);
  const onComputedRef = useRef(onComputed);
  onComputedRef.current = onComputed;

  // Auto-trigger UMAP computation as soon as the banner mounts.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/compute_umap`, { method: "POST" });
        const data = await res.json();
        if (cancelled) return;
        if (data.success) {
          const umapRes = await fetch(`${API_BASE}/api/umap`);
          const umapData = await umapRes.json();
          if (!cancelled) onComputedRef.current(umapData);
        } else {
          setScript(data.script || "");
          setState(data.reason === "too_large" ? "too_large" : "no_lib");
        }
      } catch {
        if (!cancelled) setState("error");
      }
    })();
    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleCopy = () => {
    navigator.clipboard.writeText(script);
    setCopied(true);
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob([script], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `generate_umap_${(filename || "dataset").replace(".h5ad", "")}.py`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (state === "computing") {
    return (
      <div className="shrink-0 border-t border-indigo-500/30 bg-indigo-500/5 flex items-center gap-3 px-4 py-2.5">
        <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent shrink-0" />
        <span className="text-xs text-indigo-200">Computing UMAP coordinates — this may take a minute…</span>
      </div>
    );
  }

  if (state === "error") {
    return (
      <div className="shrink-0 border-t border-amber-500/30 bg-amber-500/5 flex items-center gap-2 px-4 py-2.5">
        <span className="text-amber-400 text-xs">⚠</span>
        <span className="text-xs text-amber-200">PCA projection shown — UMAP computation failed. Layout may not reflect true biology.</span>
      </div>
    );
  }

  // no_lib or too_large — guide non-technical users step by step
  return (
    <div className="shrink-0 border-t border-amber-500/30 bg-amber-500/5">
      <div className="flex items-center gap-2 px-4 py-2">
        <span className="text-amber-400 text-xs">⚠</span>
        <span className="text-xs text-amber-200 font-medium">
          PCA projection shown — accurate UMAP needs extra processing
        </span>
        <button
          onClick={() => setExpanded((v) => !v)}
          className="ml-auto text-xs text-slate-400 hover:text-slate-200 underline"
        >
          {expanded ? "Hide guide" : "How to fix"}
        </button>
      </div>

      {expanded && script && (
        <div className="border-t border-amber-500/20 px-4 pb-4 pt-3 space-y-3">
          <p className="text-xs font-medium text-slate-200">
            How to generate accurate UMAP coordinates:
          </p>

          <div className="space-y-2.5">
            {[
              {
                label: "Install Python (if you haven't already)",
                detail: 'Download from python.org — tick "Add to PATH" during setup',
              },
              {
                label: "Open a terminal and install scanpy",
                code: "pip install scanpy",
              },
              {
                label: "Download and run the script below",
                detail: "Double-click the .py file, or in a terminal: python generate_umap_….py",
              },
              {
                label: 'Re-upload the new file ending in "_umap.h5ad" here',
              },
            ].map((step, i) => (
              <div key={i} className="flex gap-2.5">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-[10px] font-bold text-white">
                  {i + 1}
                </span>
                <div>
                  <p className="text-xs text-slate-200">{step.label}</p>
                  {step.detail && (
                    <p className="mt-0.5 text-[11px] text-slate-400">{step.detail}</p>
                  )}
                  {step.code && (
                    <pre className="mt-1 rounded bg-slate-950 px-2 py-1 font-mono text-[11px] text-emerald-300">{step.code}</pre>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div className="flex gap-2">
            <button
              onClick={handleDownload}
              className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-indigo-500"
            >
              Download script
            </button>
            <button
              onClick={handleCopy}
              className="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:bg-slate-800"
            >
              {copied ? "Copied!" : "Copy script"}
            </button>
          </div>

          <pre className="overflow-x-auto rounded-lg bg-slate-950 p-3 font-mono text-[11px] leading-relaxed text-emerald-300">
            {script}
          </pre>
        </div>
      )}
    </div>
  );
}

function BigFilePrompt({ file, onConfirm, onCancel }) {
  const estSec = file.size / EST_UPLOAD_BPS;
  return (
    <div className="absolute inset-0 z-30 flex items-center justify-center bg-slate-950/85 backdrop-blur-sm">
      <div className="w-[26rem] max-w-[88%] rounded-2xl border border-slate-700 bg-slate-900 p-6 shadow-xl">
        <h3 className="mb-1 text-base font-semibold text-slate-100">
          Large file — heads up
        </h3>
        <p className="text-sm leading-relaxed text-slate-400">
          <span className="font-mono text-slate-200">{file.name}</span> is{" "}
          <span className="font-semibold text-amber-300">
            {formatBytes(file.size)}
          </span>
          . Uploading the whole thing will take roughly{" "}
          <span className="font-semibold text-amber-300">
            ~{formatDuration(estSec)}
          </span>{" "}
          on a typical connection (could be longer on slower upload speeds).
        </p>
        <p className="mt-3 text-xs leading-relaxed text-slate-500">
          The viewer only displays up to 150k cells anyway. For a much faster
          experience you can shrink it first with{" "}
          <span className="font-mono text-slate-400">downsample_h5ad.py</span>{" "}
          (see the README), then upload the smaller file.
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-300 transition hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="rounded-lg bg-indigo-600 px-3.5 py-1.5 text-sm font-medium text-white transition hover:bg-indigo-500"
          >
            Upload full file (~{formatDuration(estSec)})
          </button>
        </div>
      </div>
    </div>
  );
}
