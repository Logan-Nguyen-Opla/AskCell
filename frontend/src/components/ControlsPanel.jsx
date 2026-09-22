import React, { useRef, useMemo, useState } from "react";
import { categoryHex } from "../lib/viz.js";

/**
 * ControlsPanel (left rail)
 * -------------------------
 * cellxgene-VIP-style control column: branding, dataset upload/status, the
 * color-by control (cell type vs gene), the gene list, the annotation legend
 * (show/hide cell types), point size, and the box-select toggle.
 *
 * It is fully controlled — every piece of state lives in App and is threaded
 * down as props so the embedding, plots, and chat all stay in sync.
 */

const palHex = (i) => categoryHex(i);

const STATUS = {
  idle: { dot: "bg-slate-600", label: "No dataset" },
  uploading: { dot: "bg-amber-400 animate-pulse-dot", label: "Processing…" },
  ready: { dot: "bg-emerald-400", label: "Ready" },
  error: { dot: "bg-rose-500", label: "Error" },
};

function GeneAutocomplete({ value, onChange, onSubmit, allGenes, disabled }) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);

  const suggestions = useMemo(() => {
    const q = value.trim().toLowerCase();
    if (!q || !allGenes.length) return [];
    return allGenes.filter((g) => g.toLowerCase().startsWith(q)).slice(0, 12);
  }, [value, allGenes]);

  const pick = (g) => {
    setOpen(false);
    onSubmit(g);
  };

  return (
    <div ref={containerRef} className="relative mt-2">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setOpen(false);
          onSubmit(value);
        }}
      >
        <input
          value={value}
          onChange={(e) => { onChange(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          disabled={disabled}
          placeholder="Add a gene (e.g. CD3D)…"
          className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-1.5 font-mono text-xs text-slate-100 placeholder:text-slate-600 focus:border-violet-500/60 focus:outline-none disabled:opacity-50"
        />
      </form>
      {open && suggestions.length > 0 && (
        <ul className="glass-panel absolute z-50 mt-1 w-full rounded-lg py-1">
          {suggestions.map((g) => (
            <li key={g}>
              <button
                type="button"
                onMouseDown={() => pick(g)}
                className="w-full px-3 py-1 text-left font-mono text-xs text-slate-200 hover:bg-brand-gradient-soft hover:text-violet-200"
              >
                {g}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function ControlsPanel({
  status,
  filename,
  cellCount,
  error,
  datasetReady,
  onFile,
  // coloring
  colorMode,
  onUseCellType,
  geneInput,
  setGeneInput,
  onSubmitGene,
  genes,
  activeGene,
  onPickGene,
  onRemoveGene,
  geneError,
  allGenes,
  // legend
  categories,
  labelField,
  hidden,
  onToggleCategory,
  // viewer controls
  pointSize,
  setPointSize,
  selectMode,
  setSelectMode,
}) {
  const fileRef = useRef(null);
  const s = STATUS[status] || STATUS.idle;
  const hasCategories = categories && categories.length > 0;

  return (
    <div className="flex h-full w-72 shrink-0 flex-col border-r border-violet-950/60 bg-slate-900/40">
      {/* Branding */}
      <div className="flex items-center gap-2 border-b border-violet-950/60 px-4 py-3.5">
        <span className="text-lg">🧬</span>
        <span className="bg-brand-gradient bg-clip-text font-bold tracking-tight text-transparent">AskCell</span>
        <span className="rounded bg-brand-gradient-soft px-1.5 py-0.5 font-mono text-[10px] text-cyan-300">
          VIP
        </span>
      </div>

      <div className="askcell-scroll flex-1 space-y-5 overflow-y-auto px-4 py-4">
        {/* Dataset */}
        <Section title="dataset">
          <div className="glass-panel-soft flex items-center gap-2 rounded-lg px-3 py-2">
            <span className={`h-2 w-2 shrink-0 rounded-full ${s.dot}`} />
            <span className="truncate font-mono text-xs text-slate-300">
              {status === "ready" ? filename || "Ready" : status === "error" ? error || "Error" : s.label}
            </span>
          </div>
          {datasetReady && (
            <div className="mt-1 font-mono text-[10px] text-cyan-300/80">
              {cellCount.toLocaleString()} cells
            </div>
          )}
          <button
            onClick={() => fileRef.current?.click()}
            disabled={status === "uploading"}
            className="mt-2 w-full rounded-lg bg-brand-gradient bg-200 bg-[position:0%_50%] px-3 py-1.5 text-sm font-semibold text-white shadow-glow-violet transition-all duration-300 hover:scale-[1.02] hover:bg-[position:100%_50%] disabled:opacity-50 disabled:hover:scale-100"
          >
            Upload .h5ad
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".h5ad"
            className="hidden"
            onChange={(e) => onFile(e.target.files?.[0])}
          />
        </Section>

        {/* Color by */}
        <Section title="color by">
          <div className="flex gap-1.5">
            <button
              onClick={onUseCellType}
              className={`flex-1 rounded-md px-2 py-1.5 text-xs font-medium transition ${
                colorMode === "celltype"
                  ? "bg-brand-gradient text-white shadow-glow-violet"
                  : "border border-slate-800 text-slate-400 hover:border-violet-500/40 hover:text-slate-200"
              }`}
            >
              Cell type
            </button>
            <button
              onClick={() => activeGene && onPickGene(activeGene)}
              disabled={!activeGene}
              className={`flex-1 rounded-md px-2 py-1.5 text-xs font-medium transition ${
                colorMode === "gene"
                  ? "bg-brand-gradient text-white shadow-glow-violet"
                  : activeGene
                  ? "border border-slate-800 text-slate-400 hover:border-violet-500/40 hover:text-slate-200"
                  : "border border-slate-800 text-slate-600 cursor-not-allowed"
              }`}
            >
              Gene {activeGene ? `· ${activeGene}` : ""}
            </button>
          </div>

          <GeneAutocomplete
            value={geneInput}
            onChange={setGeneInput}
            onSubmit={onSubmitGene}
            allGenes={allGenes}
            disabled={!datasetReady}
          />
          {geneError && (
            <div className="mt-1 font-mono text-[10px] text-rose-400">{geneError}</div>
          )}
          {genes.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {genes.map((g) => (
                <span
                  key={g}
                  className={`flex items-center gap-1 rounded-md px-1.5 py-0.5 font-mono text-[11px] transition ${
                    g === activeGene
                      ? "bg-emerald-500/20 text-emerald-200"
                      : "bg-slate-800/70 text-slate-300"
                  }`}
                >
                  <button onClick={() => onPickGene(g)} className="hover:underline">
                    {g}
                  </button>
                  <button
                    onClick={() => onRemoveGene(g)}
                    className="text-slate-500 hover:text-rose-400"
                    aria-label={`remove ${g}`}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}
        </Section>

        {/* Annotations / legend */}
        {hasCategories && (
          <Section title={labelField || "cell type"}>
            <div className="space-y-0.5">
              {categories.map((name, i) => {
                const isHidden = hidden.has(i);
                return (
                  <button
                    key={name}
                    onClick={() => onToggleCategory(i)}
                    className={`flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-xs transition hover:bg-slate-800/60 ${
                      isHidden ? "opacity-35" : "opacity-100"
                    }`}
                  >
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-full"
                      style={{ backgroundColor: palHex(i) }}
                    />
                    <span className="truncate text-slate-200">{name}</span>
                  </button>
                );
              })}
            </div>
          </Section>
        )}

        {/* Point size */}
        <Section title="point size">
          <div className="flex items-center gap-3">
            <input
              type="range"
              min="1"
              max="12"
              step="0.5"
              value={pointSize}
              onChange={(e) => setPointSize(parseFloat(e.target.value))}
              className="h-1 flex-1 cursor-pointer accent-violet-500"
            />
            <span className="w-6 text-center font-mono text-xs text-cyan-300">
              {pointSize}
            </span>
          </div>
        </Section>

        {/* Selection */}
        <Section title="selection">
          <button
            onClick={() => setSelectMode(!selectMode)}
            disabled={!datasetReady}
            className={`w-full rounded-lg px-3 py-1.5 text-xs transition disabled:opacity-50 ${
              selectMode
                ? "bg-emerald-500/20 text-emerald-200"
                : "border border-slate-800 text-slate-300 hover:text-emerald-200"
            }`}
          >
            {selectMode ? "Box-select: ON (drag on plot)" : "Enable box-select"}
          </button>
        </Section>
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div>
      <div className="mb-1.5 font-mono text-[10px] font-medium uppercase tracking-widest text-slate-400">
        {title}
      </div>
      {children}
    </div>
  );
}
