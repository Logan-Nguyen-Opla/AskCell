import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import DeckGL from "@deck.gl/react";
import { OrthographicView } from "@deck.gl/core";
import { ScatterplotLayer } from "@deck.gl/layers";

/**
 * FlowViewer
 * ----------
 * The picture that explains the whole method, in one frame.
 *
 * Two layers are drawn in the same coordinate space:
 *
 *   1. the healthy reference cloud, dim grey, behind everything -- this is
 *      "where cells from healthy people live";
 *   2. the patient's own cells on top, grey where they fall inside that
 *      healthy region and red where they do not.
 *
 * Both sets are projected through axes fitted on the *reference*, which is what
 * makes the overlay meaningful: a red clump sitting outside the grey cloud is
 * literally "these cells are unlike anything in a healthy person", not an
 * artifact of two plots being scaled differently.
 *
 * Props:
 *   reference: { n_total, points: [[x,y], ...] }
 *   cells:     Array<{ id, x, y, s, p }>   // s = score, p = population (-1 = none)
 *   threshold: number
 *   scoreMax:  number
 *   pointSize: number
 *   showReference: boolean
 *   colorMode: "population" | "score"
 *   focusPopulation: number | null   // zoom to one population, dim the rest
 *   onClearFocus: () => void
 */

const REF_RGB = [71, 85, 105];        // slate-600, the healthy backdrop
const NORMAL_RGB = [148, 163, 184];   // slate-400, patient cells that look fine
const ABNORMAL_RGB = [244, 63, 94];   // rose-500, the finding

// Warm ramp for continuous score mode: cool where a cell resembles healthy
// tissue, hot where it does not.
const SCORE_RAMP = [
  [56, 89, 138],
  [86, 140, 170],
  [214, 191, 105],
  [232, 128, 62],
  [244, 63, 94],
];

function rampRgb(t) {
  if (!Number.isFinite(t)) return NORMAL_RGB;
  const x = Math.max(0, Math.min(1, t));
  const scaled = x * (SCORE_RAMP.length - 1);
  const i = Math.floor(scaled);
  const f = scaled - i;
  const a = SCORE_RAMP[i];
  const b = SCORE_RAMP[Math.min(i + 1, SCORE_RAMP.length - 1)];
  return [
    Math.round(a[0] + (b[0] - a[0]) * f),
    Math.round(a[1] + (b[1] - a[1]) * f),
    Math.round(a[2] + (b[2] - a[2]) * f),
  ];
}

function boundsOf(refPoints, cells) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  const bump = (x, y) => {
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  };
  for (const p of refPoints || []) bump(p[0], p[1]);
  for (const c of cells || []) bump(c.x, c.y);
  if (minX === Infinity) return null;
  return [minX, minY, maxX, maxY];
}

function fitViewState(bounds, width, height, padding = 0.88) {
  if (!bounds || !width || !height) {
    return { target: [0, 0, 0], zoom: 0, minZoom: -10, maxZoom: 20 };
  }
  const [minX, minY, maxX, maxY] = bounds;
  const rangeX = Math.max(maxX - minX, 1e-6);
  const rangeY = Math.max(maxY - minY, 1e-6);
  return {
    target: [(minX + maxX) / 2, (minY + maxY) / 2, 0],
    zoom: Math.min(
      Math.log2((width * padding) / rangeX),
      Math.log2((height * padding) / rangeY)
    ),
    minZoom: -10,
    maxZoom: 20,
  };
}

export default function FlowViewer({
  reference = null,
  cells = [],
  threshold = 0,
  scoreMax = 1,
  pointSize = 3,
  showReference = true,
  colorMode = "population",
  focusPopulation = null,
  onClearFocus,
}) {
  const containerRef = useRef(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [viewState, setViewState] = useState(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const refPoints = reference?.points || [];
  const bounds = useMemo(() => boundsOf(refPoints, cells), [refPoints, cells]);

  const focused = focusPopulation != null;
  const focusBounds = useMemo(() => {
    if (!focused) return null;
    const members = cells.filter((c) => c.p === focusPopulation);
    if (!members.length) return null;
    const b = boundsOf([], members);
    if (!b) return null;
    // Pad outward so the population is framed with context around it rather
    // than filling the viewport edge to edge.
    const padX = Math.max((b[2] - b[0]) * 1.4, 0.5);
    const padY = Math.max((b[3] - b[1]) * 1.4, 0.5);
    return [b[0] - padX, b[1] - padY, b[2] + padX, b[3] + padY];
  }, [focused, focusPopulation, cells]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setSize({ width, height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (bounds && size.width && size.height) {
      setViewState(fitViewState(bounds, size.width, size.height));
    }
  }, [bounds, size.width, size.height]);

  // Zoom to a population when one is picked from the report.
  useEffect(() => {
    if (focusBounds && size.width && size.height) {
      setViewState(fitViewState(focusBounds, size.width, size.height));
    }
  }, [focusBounds, size.width, size.height]);

  const resetView = useCallback(() => {
    onClearFocus?.();
    if (bounds && size.width && size.height) {
      setViewState(fitViewState(bounds, size.width, size.height));
    }
  }, [bounds, size.width, size.height, onClearFocus]);

  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) containerRef.current?.requestFullscreen();
    else document.exitFullscreen();
  }, []);

  useEffect(() => {
    const onChange = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const nAbnormal = useMemo(
    () => cells.reduce((n, c) => n + (c.p >= 0 ? 1 : 0), 0),
    [cells]
  );

  const getFillColor = useCallback(
    (d) => {
      // When one population is focused, everything else fades to a backdrop so
      // the population under examination is unambiguous.
      if (focused && d.p !== focusPopulation) return [51, 65, 85];
      if (colorMode === "score") return rampRgb(d.s / (scoreMax || 1));
      return d.p >= 0 ? ABNORMAL_RGB : NORMAL_RGB;
    },
    [colorMode, scoreMax, focused, focusPopulation]
  );

  // Abnormal cells are drawn larger so a 189-cell population stays visible
  // against several hundred thousand normal ones. Without this the finding is
  // technically on screen and practically invisible.
  const getRadius = useCallback(
    (d) => (d.p >= 0 ? pointSize + 2 : pointSize),
    [pointSize]
  );

  const layers = useMemo(() => {
    const out = [];
    if (showReference && refPoints.length) {
      out.push(
        new ScatterplotLayer({
          id: "healthy-reference",
          data: refPoints,
          getPosition: (p) => [p[0], p[1]],
          getFillColor: REF_RGB,
          getRadius: pointSize,
          radiusUnits: "pixels",
          radiusMinPixels: pointSize,
          radiusMaxPixels: pointSize,
          stroked: false,
          filled: true,
          antialiasing: true,
          pickable: false,
          opacity: 0.32,
          updateTriggers: { getRadius: pointSize },
        })
      );
    }
    if (cells.length) {
      out.push(
        new ScatterplotLayer({
          id: "specimen-cells",
          data: cells,
          getPosition: (d) => [d.x, d.y],
          getFillColor,
          getRadius,
          radiusUnits: "pixels",
          radiusMinPixels: pointSize,
          radiusMaxPixels: pointSize + 2,
          stroked: false,
          filled: true,
          antialiasing: true,
          pickable: true,
          autoHighlight: true,
          highlightColor: [255, 255, 255, 255],
          opacity: 0.85,
          updateTriggers: {
            getFillColor: [colorMode, scoreMax, focused, focusPopulation],
            getRadius: pointSize,
          },
        })
      );
    }
    return out;
  }, [
    refPoints, cells, showReference, pointSize, getFillColor, getRadius,
    colorMode, scoreMax, focused, focusPopulation,
  ]);

  return (
    <div ref={containerRef} className="relative h-full w-full bg-slate-950">
      {viewState && (
        <DeckGL
          views={new OrthographicView({ id: "ortho", flipY: false })}
          viewState={viewState}
          controller={{ scrollZoom: true, dragPan: true, doubleClickZoom: true }}
          onViewStateChange={({ viewState: vs }) => setViewState(vs)}
          layers={layers}
          getTooltip={({ object }) =>
            object &&
            object.id != null && {
              html: `<div style="font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.6">
                       <b style="color:${object.p >= 0 ? "#fb7185" : "#94a3b8"}">
                         ${object.p >= 0 ? "ABNORMAL" : "looks normal"}
                       </b><br/>
                       distance from normal: <b>${object.s.toFixed(3)}</b><br/>
                       threshold: ${threshold.toFixed(3)}<br/>
                       event #${object.id}
                     </div>`,
              style: {
                backgroundColor: "#0f172a",
                color: "#e2e8f0",
                border: `1px solid ${object.p >= 0 ? "#9f1239" : "#312e81"}`,
                borderRadius: "8px",
                padding: "8px 10px",
              },
            }
          }
        />
      )}

      {/* Focus banner -- a zoomed view must never look like the full picture */}
      {focused && (
        <div className="absolute left-1/2 top-4 z-10 flex -translate-x-1/2 items-center gap-3 rounded-full border border-rose-500/50 bg-slate-900/90 px-4 py-1.5 backdrop-blur">
          <span className="font-mono text-[11px] text-rose-300">
            showing population {focusPopulation + 1} only
          </span>
          <button
            onClick={onClearFocus}
            className="font-mono text-[10px] text-slate-400 underline transition hover:text-slate-200"
          >
            show all cells
          </button>
        </div>
      )}

      {/* Legend */}
      <div className="absolute right-4 top-4 rounded-xl border border-slate-800 bg-slate-900/85 p-3 backdrop-blur">
        {colorMode === "score" ? (
          <>
            <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wider text-slate-400">
              distance from normal
            </div>
            <div
              className="h-2.5 w-40 rounded"
              style={{
                background: `linear-gradient(to right, ${SCORE_RAMP.map(
                  ([r, g, b]) => `rgb(${r},${g},${b})`
                ).join(", ")})`,
              }}
            />
            <div className="mt-1 flex w-40 justify-between font-mono text-[9px] text-slate-500">
              <span>0</span>
              <span className="text-amber-400">thr {threshold.toFixed(2)}</span>
              <span>{scoreMax.toFixed(1)}</span>
            </div>
          </>
        ) : (
          <div className="space-y-1.5 font-mono text-[11px]">
            {showReference && (
              <Row rgb={REF_RGB} label="healthy reference" dim />
            )}
            <Row rgb={NORMAL_RGB} label="patient — normal" />
            <Row rgb={ABNORMAL_RGB} label="patient — abnormal" />
          </div>
        )}
      </div>

      {/* Counters */}
      <div className="pointer-events-none absolute bottom-4 left-4 rounded-lg border border-slate-800 bg-slate-900/85 px-3 py-1.5 font-mono text-xs backdrop-blur">
        <span className="text-slate-300">
          {cells.length.toLocaleString()} cells
        </span>
        {nAbnormal > 0 && (
          <span className="ml-2 text-rose-400">
            · {nAbnormal.toLocaleString()} abnormal
          </span>
        )}
        {showReference && refPoints.length > 0 && (
          <span className="ml-2 text-slate-500">
            · {refPoints.length.toLocaleString()} reference
          </span>
        )}
      </div>

      <button
        onClick={resetView}
        className="absolute bottom-4 right-4 rounded-lg border border-slate-800 bg-slate-900/85 px-3 py-1.5 font-mono text-xs text-slate-300 backdrop-blur transition hover:border-emerald-500/50 hover:text-emerald-300"
      >
        reset view
      </button>

      <button
        onClick={toggleFullscreen}
        title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
        className="absolute left-4 top-4 rounded-lg border border-slate-800 bg-slate-900/85 p-1.5 text-slate-400 backdrop-blur transition hover:border-indigo-500/50 hover:text-indigo-300"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none"
             viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round"
                d={isFullscreen
                  ? "M9 9L4 4m0 0h5m-5 0v5M15 9l5-5m0 0h-5m5 0v5M9 15l-5 5m0 0h5m-5 0v-5M15 15l5 5m0 0h-5m5 0v-5"
                  : "M4 8V4m0 0h4M4 4l5 5M20 8V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5M20 16v4m0 0h-4m4 0l-5-5"} />
        </svg>
      </button>
    </div>
  );
}

function Row({ rgb, label, dim = false }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className="h-2.5 w-2.5 shrink-0 rounded-full"
        style={{
          backgroundColor: `rgb(${rgb.join(",")})`,
          opacity: dim ? 0.5 : 1,
        }}
      />
      <span className={dim ? "text-slate-500" : "text-slate-300"}>{label}</span>
    </div>
  );
}
