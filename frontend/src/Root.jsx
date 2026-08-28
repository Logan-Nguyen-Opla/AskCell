import React, { useState } from "react";
import FlowApp from "./FlowApp.jsx";
import App from "./App.jsx";

/**
 * Root
 * ----
 * Chooses between the two analysis surfaces.
 *
 * Cytometry is the default: it is the workflow the project is built around --
 * compare a specimen against healthy marrow and report abnormal populations.
 * The original scRNA-seq browser is kept reachable rather than deleted, because
 * it is a working gene-expression explorer and the two share the backend.
 *
 * They are deliberately separate screens. The data are not interchangeable --
 * one measures surface proteins on hundreds of thousands of cells, the other
 * measures gene expression -- so a single merged UI would only invite comparing
 * numbers that are not comparable.
 */

const MODES = [
  { id: "flow", label: "Cytometry", hint: "detect abnormal populations (.fcs)" },
  { id: "rna", label: "scRNA-seq", hint: "explore gene expression (.h5ad)" },
];

export default function Root() {
  const [mode, setMode] = useState("flow");
  const [open, setOpen] = useState(false);

  return (
    <div className="relative h-screen w-screen overflow-hidden">
      {mode === "flow" ? <FlowApp /> : <App />}

      {/* Mode switcher — floating so neither screen needs a layout change. */}
      <div className="absolute bottom-3 left-1/2 z-50 -translate-x-1/2">
        {open && (
          <div className="glass-panel animate-fade-up mb-2 w-64 overflow-hidden rounded-xl shadow-glow-violet">
            {MODES.map((m) => (
              <button
                key={m.id}
                onClick={() => {
                  setMode(m.id);
                  setOpen(false);
                }}
                className={`block w-full px-3 py-2.5 text-left transition ${
                  mode === m.id
                    ? "bg-brand-gradient-soft text-violet-200"
                    : "text-slate-300 hover:bg-slate-800/60"
                }`}
              >
                <div
                  className={`font-mono text-[11px] font-semibold ${
                    mode === m.id ? "bg-brand-gradient bg-clip-text text-transparent" : ""
                  }`}
                >
                  {m.label}
                </div>
                <div className="mt-0.5 text-[10px] text-slate-500">{m.hint}</div>
              </button>
            ))}
          </div>
        )}

        <button
          onClick={() => setOpen((v) => !v)}
          className="glass-panel-soft flex items-center gap-2 rounded-full px-3 py-1.5 font-mono text-[10px] text-slate-300 transition hover:scale-105 hover:text-violet-200 hover:shadow-glow-violet"
        >
          <span className="h-1.5 w-1.5 animate-glow-pulse rounded-full bg-brand-gradient" />
          <span className="bg-brand-gradient bg-clip-text font-semibold text-transparent">
            {MODES.find((m) => m.id === mode)?.label}
          </span>
          <span className="text-slate-600">{open ? "▾" : "▴"}</span>
        </button>
      </div>
    </div>
  );
}
