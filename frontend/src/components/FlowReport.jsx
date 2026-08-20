import React from "react";

/**
 * FlowReport
 * ----------
 * The result readout for one specimen.
 *
 * Layout follows the argument the detector actually makes, in order:
 *
 *   1. the verdict and the headline percentage;
 *   2. the two-stage breakdown -- how many cells were flagged, and how many
 *      survived clustering;
 *   3. each population's phenotype: which markers are abnormal, by how much;
 *   4. quality control, so a bad specimen is visible rather than implied.
 *
 * Stage 1 and stage 2 are shown side by side deliberately. The threshold is
 * calibrated to let roughly one healthy cell in a thousand through, so on a
 * large file stage 1 always flags cells -- including in a healthy person. The
 * gap between the two numbers is the noise the clustering removed, and showing
 * it is what lets someone check the result instead of trusting it.
 */

export default function FlowReport({ report, onHighlightPopulation }) {
  if (!report) return null;

  if (report.ok === false) {
    return (
      <div className="m-4 rounded-xl border border-amber-500/40 bg-amber-500/5 p-4">
        <div className="mb-1 font-mono text-[10px] uppercase tracking-widest text-amber-400">
          cannot compare
        </div>
        <p className="text-sm leading-relaxed text-amber-100">{report.message}</p>
      </div>
    );
  }

  const detected = report.verdict === "abnormal_population_detected";
  const notClonal = report.verdict === "abnormal_events_not_clonal";

  return (
    <div className="space-y-4 overflow-y-auto p-4">
      {/* ---------- headline ---------- */}
      <div
        className={`rounded-xl border p-4 ${
          detected
            ? "border-rose-500/40 bg-rose-500/5"
            : notClonal
              ? "border-amber-500/40 bg-amber-500/5"
              : "border-emerald-500/40 bg-emerald-500/5"
        }`}
      >
        <div
          className={`mb-2 font-mono text-[10px] uppercase tracking-widest ${
            detected ? "text-rose-400" : notClonal ? "text-amber-400" : "text-emerald-400"
          }`}
        >
          {report.verdict.replace(/_/g, " ")}
        </div>

        <div className="flex items-baseline gap-2">
          <span
            className={`font-mono text-4xl font-bold ${
              detected ? "text-rose-300" : "text-emerald-300"
            }`}
          >
            {report.abnormal_pct}%
          </span>
          <span className="text-xs text-slate-400">
            of {report.n_analyzed.toLocaleString()} cells
          </span>
        </div>

        <p className="mt-2 text-xs leading-relaxed text-slate-300">
          {report.summary}
        </p>
      </div>

      {/* ---------- two-stage breakdown ---------- */}
      <Section title="how the number was reached">
        <Stage
          n={report.stage1_flagged}
          pct={report.stage1_flagged_pct}
          label="unlike any healthy cell"
          sub="stage 1 — distance from the reference"
          tone="amber"
        />
        <div className="py-1 pl-3 font-mono text-[10px] text-slate-500">
          ↓ &nbsp;{report.noise_removed_by_clustering.toLocaleString()} scattered
          cells discarded as noise
        </div>
        <Stage
          n={report.n_abnormal}
          pct={report.abnormal_pct}
          label="in a clustered population"
          sub="stage 2 — grouped together, i.e. a clone"
          tone={detected ? "rose" : "emerald"}
        />
        <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
          The threshold is set so about{" "}
          {(100 - (report.parameters?.threshold_percentile ?? 99.9)).toFixed(2)}%
          of healthy cells are flagged by stage 1. Those false flags land
          scattered; a real population lands clustered, which is what stage 2
          keeps.
        </p>
      </Section>

      {/* ---------- populations ---------- */}
      {report.populations?.length > 0 && (
        <Section title={`${report.populations.length} population${report.populations.length > 1 ? "s" : ""} found`}>
          <div className="space-y-3">
            {report.populations.map((pop, i) => (
              <div
                key={pop.label}
                className="rounded-lg border border-slate-700 bg-slate-900/60 p-3"
              >
                <div className="mb-2 flex items-center justify-between">
                  <span className="font-mono text-xs text-slate-200">
                    population {i + 1}
                  </span>
                  <span className="font-mono text-xs text-rose-300">
                    {pop.n_events.toLocaleString()} cells · {pop.pct_of_analyzed}%
                  </span>
                </div>

                <div className="mb-2 flex items-center gap-2 font-mono text-[10px]">
                  <span
                    className={
                      pop.is_clonal ? "text-rose-300" : "text-slate-400"
                    }
                  >
                    {pop.is_clonal ? "◆ clonal" : "○ not clonal"}
                  </span>
                  <span className="text-slate-500">
                    spread {pop.compactness_vs_normal}× normal
                  </span>
                </div>

                <div className="mb-1 font-mono text-[9px] uppercase tracking-widest text-slate-500">
                  phenotype
                </div>
                <div className="space-y-1">
                  {pop.deviant_markers.map((d) => (
                    <MarkerBar key={d.marker} {...d} />
                  ))}
                </div>

                {onHighlightPopulation && (
                  <button
                    onClick={() => onHighlightPopulation(pop.label)}
                    className="mt-2 w-full rounded border border-slate-700 px-2 py-1 font-mono text-[10px] text-slate-400 transition hover:border-rose-500/50 hover:text-rose-300"
                  >
                    show these cells
                  </button>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* ---------- quality control ---------- */}
      {report.qc && (
        <Section title="quality control">
          <div className="font-mono text-[11px] text-slate-400">
            {report.qc.n_input.toLocaleString()} acquired →{" "}
            <span className="text-slate-200">
              {report.qc.n_kept.toLocaleString()}
            </span>{" "}
            intact single live cells ({report.qc.pct_kept}%)
          </div>
          <div className="mt-1.5 space-y-0.5">
            {Object.entries(report.qc.gates || {}).map(([name, g]) => (
              <div
                key={name}
                className="flex justify-between font-mono text-[10px] text-slate-500"
              >
                <span>{name}</span>
                <span>
                  {g.removed != null
                    ? `−${g.removed.toLocaleString()}`
                    : g.skipped || "—"}
                </span>
              </div>
            ))}
          </div>
          {report.qc.warning && (
            <div className="mt-2 rounded border border-amber-500/30 bg-amber-500/5 px-2 py-1 text-[10px] text-amber-200">
              ⚠ {report.qc.warning}
            </div>
          )}
        </Section>
      )}

      {/* ---------- reference provenance ---------- */}
      {report.reference && (
        <Section title="compared against">
          <div className="font-mono text-[11px] text-slate-400">
            {report.reference.n_specimens} healthy specimens ·{" "}
            {report.reference.n_cells.toLocaleString()} reference cells
          </div>
          <div className="mt-1 flex flex-wrap gap-1">
            {(report.reference.sources || []).map((s) => (
              <span
                key={s}
                className="rounded bg-slate-800/70 px-1.5 py-0.5 font-mono text-[9px] text-slate-400"
              >
                {s}
              </span>
            ))}
          </div>
        </Section>
      )}

      <p className="pb-2 text-[10px] leading-relaxed text-slate-600">
        Research and educational use only. Not a diagnostic device and not
        clinically validated.
      </p>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div>
      <div className="mb-2 font-mono text-[10px] uppercase tracking-widest text-slate-500">
        {title}
      </div>
      {children}
    </div>
  );
}

function Stage({ n, pct, label, sub, tone }) {
  const colors = {
    amber: "text-amber-300 border-amber-500/30",
    rose: "text-rose-300 border-rose-500/30",
    emerald: "text-emerald-300 border-emerald-500/30",
  }[tone];
  return (
    <div className={`rounded-lg border ${colors} bg-slate-900/40 px-3 py-2`}>
      <div className="flex items-baseline justify-between">
        <span className="text-xs text-slate-300">{label}</span>
        <span className={`font-mono text-sm font-semibold ${colors.split(" ")[0]}`}>
          {n.toLocaleString()}
          <span className="ml-1 text-[10px] font-normal opacity-70">({pct}%)</span>
        </span>
      </div>
      <div className="mt-0.5 font-mono text-[9px] text-slate-500">{sub}</div>
    </div>
  );
}

function MarkerBar({ marker, z, direction, strength }) {
  // Bars run outward from a centre line so "too bright" and "too dim" are
  // immediately distinguishable without reading the number.
  const magnitude = Math.min(Math.abs(z) / 7, 1) * 50;
  const up = direction === "brighter";
  return (
    <div className="flex items-center gap-2 font-mono text-[10px]">
      <span className="w-14 shrink-0 text-slate-300">{marker}</span>
      <div className="relative h-2 flex-1 rounded bg-slate-800/60">
        <div className="absolute inset-y-0 left-1/2 w-px bg-slate-600" />
        <div
          className={`absolute inset-y-0 rounded ${
            up ? "bg-rose-500/70" : "bg-sky-500/70"
          }`}
          style={
            up
              ? { left: "50%", width: `${magnitude}%` }
              : { right: "50%", width: `${magnitude}%` }
          }
        />
      </div>
      <span
        className={`w-12 shrink-0 text-right ${
          up ? "text-rose-300" : "text-sky-300"
        }`}
      >
        {z > 0 ? "+" : ""}
        {z.toFixed(1)}σ
      </span>
      <span className="w-14 shrink-0 text-slate-600">{strength}</span>
    </div>
  );
}
