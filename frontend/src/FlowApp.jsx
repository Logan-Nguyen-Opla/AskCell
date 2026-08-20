import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import FlowViewer from "./components/FlowViewer.jsx";
import FlowReport from "./components/FlowReport.jsx";
import { API_BASE } from "./lib/api.js";

/**
 * FlowApp
 * -------
 * The cytometry workflow: a healthy reference on one side, one patient specimen
 * on the other, and the comparison between them.
 *
 * The reference is built on the server at startup from the bundled healthy
 * specimens, so the app has something to compare against the moment it opens.
 * Uploading your own healthy set replaces it -- which also invalidates any
 * result already on screen, since a result only means anything relative to the
 * reference it was measured against.
 */

export default function FlowApp() {
  const [reference, setReference] = useState(null);
  const [scatter, setScatter] = useState(null);
  const [report, setReport] = useState(null);
  const [sampleName, setSampleName] = useState(null);

  const [busy, setBusy] = useState(null);      // "sample" | "reference" | null
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState(null);
  const [dragging, setDragging] = useState(false);

  const [showReference, setShowReference] = useState(true);
  const [colorMode, setColorMode] = useState("population");
  const [pointSize, setPointSize] = useState(3);

  const sampleInput = useRef(null);
  const refInput = useRef(null);

  // ---- initial state: pick up the server-side reference ----
  const refreshScatter = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/flow/scatter`);
      if (res.ok) setScatter(await res.json());
    } catch {
      /* backend not up yet */
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const s = await fetch(`${API_BASE}/api/flow/status`).then((r) => r.json());
        if (cancelled) return;
        if (s.reference_loaded) {
          setReference(s.reference);
          await refreshScatter();
        }
        if (s.sample_loaded) {
          const rep = await fetch(`${API_BASE}/api/flow/report`).then((r) => r.json());
          if (!cancelled) {
            setReport(rep);
            setSampleName(s.sample?.filename || null);
          }
        }
      } catch {
        if (!cancelled) setError("Backend not reachable — is it running?");
      }
    })();
    return () => { cancelled = true; };
  }, [refreshScatter]);

  // ---- upload helper (XHR so we get real progress on large files) ----
  const upload = useCallback(
    (url, form, kind) =>
      new Promise((resolve, reject) => {
        setBusy(kind);
        setError(null);
        setProgress(0);

        const xhr = new XMLHttpRequest();
        xhr.open("POST", url);
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) setProgress((e.loaded / e.total) * 100);
        };
        xhr.onload = () => {
          setBusy(null);
          setProgress(null);
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              resolve(JSON.parse(xhr.responseText || "{}"));
            } catch (e) {
              reject(new Error("Malformed response from the server."));
            }
          } else {
            let detail = `Request failed (${xhr.status})`;
            try {
              detail = JSON.parse(xhr.responseText).detail || detail;
            } catch { /* non-JSON body */ }
            reject(new Error(detail));
          }
        };
        xhr.onerror = () => {
          setBusy(null);
          setProgress(null);
          reject(new Error("Network error during upload."));
        };
        xhr.send(form);
      }),
    []
  );

  const handleSample = useCallback(
    async (file) => {
      if (!file) return;
      if (!file.name.toLowerCase().endsWith(".fcs")) {
        setError("Please choose an .fcs file (the format your cytometer writes).");
        return;
      }
      setReport(null);
      const form = new FormData();
      form.append("file", file);
      try {
        const rep = await upload(`${API_BASE}/api/flow/sample`, form, "sample");
        setReport(rep);
        setSampleName(file.name);
        await refreshScatter();
      } catch (e) {
        setError(e.message);
      }
    },
    [upload, refreshScatter]
  );

  const handleReference = useCallback(
    async (files) => {
      const list = Array.from(files || []);
      if (list.length < 2) {
        setError(
          "Choose at least 2 healthy specimens. The detection threshold is " +
            "measured by holding one out, so a single file cannot calibrate it."
        );
        return;
      }
      const form = new FormData();
      list.forEach((f) => form.append("files", f));
      try {
        const res = await upload(`${API_BASE}/api/flow/reference`, form, "reference");
        setReference(res.reference);
        // The old result was measured against the old reference: drop it.
        setReport(null);
        setSampleName(null);
        await refreshScatter();
      } catch (e) {
        setError(e.message);
      }
    },
    [upload, refreshScatter]
  );

  const onDrop = useCallback(
    (e) => {
      e.preventDefault();
      setDragging(false);
      const files = Array.from(e.dataTransfer.files || []);
      if (files.length > 1) handleReference(files);
      else handleSample(files[0]);
    },
    [handleSample, handleReference]
  );

  const cells = useMemo(() => scatter?.cells || [], [scatter]);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-950 text-slate-200">
      {/* ================= left rail ================= */}
      <aside className="flex w-80 shrink-0 flex-col gap-4 overflow-y-auto border-r border-slate-800 p-4">
        <div>
          <h1 className="font-mono text-sm font-semibold tracking-tight text-slate-100">
            AskCell
          </h1>
          <p className="mt-0.5 text-[11px] leading-relaxed text-slate-500">
            Finds abnormal cell populations by comparing a specimen against
            healthy marrow.
          </p>
        </div>

        {/* ---- reference ---- */}
        <Panel title="1 · what normal looks like">
          {reference ? (
            <div className="space-y-1 font-mono text-[10px] text-slate-400">
              <Line k="specimens" v={reference.n_source_specimens} />
              <Line k="cells" v={reference.n_reference_cells.toLocaleString()} />
              <Line k="markers" v={reference.n_markers} />
              <Line k="threshold" v={reference.threshold} />
              <div className="pt-1 text-[9px] leading-relaxed text-slate-600">
                calibrated at the {reference.threshold_percentile}th percentile —
                about {reference.expected_false_flag_rate_pct}% of healthy cells
                are expected to trip stage 1
              </div>
              <div className="flex flex-wrap gap-1 pt-1">
                {(reference.markers || []).map((m) => (
                  <span key={m} className="rounded bg-slate-800/70 px-1 py-0.5 text-[9px] text-slate-400">
                    {m}
                  </span>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-[11px] text-amber-300">
              No reference loaded. Upload at least 2 healthy specimens.
            </p>
          )}

          <input
            ref={refInput}
            type="file"
            accept=".fcs"
            multiple
            className="hidden"
            onChange={(e) => handleReference(e.target.files)}
          />
          <button
            onClick={() => refInput.current?.click()}
            disabled={busy != null}
            className="mt-2 w-full rounded-lg border border-slate-700 px-3 py-1.5 text-[11px] text-slate-300 transition hover:border-indigo-500/50 hover:text-indigo-200 disabled:opacity-40"
          >
            {reference ? "replace with my own healthy files" : "choose healthy files"}
          </button>
        </Panel>

        {/* ---- specimen ---- */}
        <Panel title="2 · patient specimen">
          <input
            ref={sampleInput}
            type="file"
            accept=".fcs"
            className="hidden"
            onChange={(e) => handleSample(e.target.files?.[0])}
          />
          <button
            onClick={() => sampleInput.current?.click()}
            disabled={busy != null || !reference}
            className="w-full rounded-lg bg-indigo-600 px-3 py-2 text-xs font-medium text-white transition hover:bg-indigo-500 disabled:opacity-40"
          >
            {sampleName ? "analyse another specimen" : "choose an .fcs specimen"}
          </button>
          {sampleName && (
            <div className="mt-2 truncate font-mono text-[10px] text-slate-400">
              {sampleName}
            </div>
          )}
        </Panel>

        {/* ---- view controls ---- */}
        {cells.length > 0 && (
          <Panel title="view">
            <label className="flex cursor-pointer items-center gap-2 text-[11px] text-slate-300">
              <input
                type="checkbox"
                checked={showReference}
                onChange={(e) => setShowReference(e.target.checked)}
                className="accent-indigo-500"
              />
              show healthy reference behind
            </label>

            <div className="mt-2 flex gap-1">
              {[
                ["population", "normal / abnormal"],
                ["score", "distance scale"],
              ].map(([mode, label]) => (
                <button
                  key={mode}
                  onClick={() => setColorMode(mode)}
                  className={`flex-1 rounded border px-2 py-1 text-[10px] transition ${
                    colorMode === mode
                      ? "border-indigo-500/60 bg-indigo-500/10 text-indigo-200"
                      : "border-slate-700 text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            <label className="mt-2 block font-mono text-[10px] text-slate-500">
              point size {pointSize}
              <input
                type="range"
                min="1"
                max="8"
                value={pointSize}
                onChange={(e) => setPointSize(Number(e.target.value))}
                className="mt-1 w-full accent-indigo-500"
              />
            </label>
          </Panel>
        )}

        {error && (
          <div className="rounded-lg border border-rose-500/40 bg-rose-500/5 p-2.5 text-[11px] leading-relaxed text-rose-200">
            {error}
          </div>
        )}
      </aside>

      {/* ================= centre: the picture ================= */}
      <main
        className="relative min-w-0 flex-1"
        onDrop={onDrop}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={(e) => { e.preventDefault(); setDragging(false); }}
      >
        {scatter ? (
          <FlowViewer
            reference={scatter.reference}
            cells={cells}
            threshold={scatter.threshold ?? reference?.threshold ?? 0}
            scoreMax={scatter.score_max ?? 1}
            pointSize={pointSize}
            showReference={showReference}
            colorMode={colorMode}
          />
        ) : (
          <Empty busy={busy} progress={progress} />
        )}

        {busy && (
          <div className="absolute inset-x-0 top-0 z-20 bg-slate-900/90 px-4 py-2 backdrop-blur">
            <div className="mb-1 flex justify-between font-mono text-[10px] text-indigo-200">
              <span>
                {busy === "reference"
                  ? "building the healthy reference…"
                  : "analysing specimen…"}
              </span>
              <span>
                {progress != null && progress < 99.5
                  ? `${Math.round(progress)}% uploaded`
                  : "computing on server"}
              </span>
            </div>
            <div className="h-1 overflow-hidden rounded-full bg-slate-800">
              <div
                className="h-full rounded-full bg-indigo-500 transition-[width] duration-200"
                style={{
                  width:
                    progress != null && progress < 99.5
                      ? `${Math.max(2, progress)}%`
                      : "100%",
                }}
              />
            </div>
          </div>
        )}

        {dragging && (
          <div className="pointer-events-none absolute inset-0 z-30 flex items-center justify-center bg-slate-950/85 backdrop-blur-sm">
            <div className="rounded-2xl border-2 border-dashed border-indigo-400 px-10 py-8 text-center">
              <div className="mb-2 text-3xl">⬇</div>
              <p className="font-medium text-indigo-200">Drop an .fcs file</p>
              <p className="mt-1 text-[11px] text-slate-400">
                one file = patient specimen · several = new healthy reference
              </p>
            </div>
          </div>
        )}
      </main>

      {/* ================= right: the result ================= */}
      <aside className="flex h-full w-96 shrink-0 flex-col overflow-hidden border-l border-slate-800">
        {report ? (
          <FlowReport report={report} />
        ) : (
          <div className="flex h-full flex-col items-center justify-center px-6 text-center">
            <div className="mb-3 grid grid-cols-5 gap-1 opacity-25">
              {Array.from({ length: 25 }).map((_, i) => (
                <span
                  key={i}
                  className={`h-1.5 w-1.5 rounded-full ${
                    i === 12 || i === 17 ? "bg-rose-400" : "bg-slate-400"
                  }`}
                />
              ))}
            </div>
            <p className="text-xs text-slate-500">
              {reference
                ? "Choose a patient specimen to compare against the healthy reference."
                : "Load a healthy reference first."}
            </p>
          </div>
        )}
      </aside>
    </div>
  );
}

function Panel({ title, children }) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-widest text-slate-500">
        {title}
      </div>
      {children}
    </section>
  );
}

function Line({ k, v }) {
  return (
    <div className="flex justify-between">
      <span className="text-slate-500">{k}</span>
      <span className="text-slate-300">{v}</span>
    </div>
  );
}

function Empty({ busy, progress }) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center">
      <div className="mb-5 grid grid-cols-6 gap-1.5 opacity-25">
        {Array.from({ length: 36 }).map((_, i) => (
          <span
            key={i}
            className="h-1.5 w-1.5 rounded-full bg-slate-400"
            style={{ opacity: 0.2 + ((i * 37) % 80) / 100 }}
          />
        ))}
      </div>
      <h3 className="text-base font-medium text-slate-300">
        {busy ? "Working…" : "No reference loaded"}
      </h3>
      <p className="mt-2 max-w-sm text-center text-xs leading-relaxed text-slate-500">
        {busy
          ? progress != null
            ? `${Math.round(progress)}% uploaded`
            : "computing"
          : "Generate the bundled fixtures with `python make_mock_fcs.py`, or upload at least 2 healthy .fcs specimens to build a reference."}
      </p>
    </div>
  );
}
