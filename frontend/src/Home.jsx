/**
 * Home
 * ----
 * A simple landing screen explaining what AskCell does, shown before the
 * tool itself. Not a marketing site -- just enough context that someone
 * opening the link for the first time knows what they're looking at before
 * being dropped into a flow-cytometry viewer.
 */
export default function Home({ onLaunch }) {
  return (
    <div className="flex h-screen w-screen items-center justify-center overflow-y-auto bg-slate-950 px-6 py-10 text-slate-200">
      <div className="w-full max-w-2xl">
        <h1 className="bg-brand-gradient bg-clip-text text-center font-mono text-4xl font-bold tracking-tight text-transparent">
          AskCell
        </h1>
        <p className="mt-3 text-center text-sm leading-relaxed text-slate-400">
          Finds abnormal cell populations in a flow-cytometry specimen by
          comparing it against a reference built from healthy bone marrow.
        </p>

        <div className="glass-panel mt-8 rounded-xl p-5">
          <p className="text-sm leading-relaxed text-slate-300">
            After leukemia treatment, doctors check bone marrow for{" "}
            <span className="text-violet-300">minimal residual disease</span>{" "}
            (MRD) -- cancer cells that survived, often only 0.01-0.1% of the
            sample. A flow cytometer measures ~17 values per cell on hundreds
            of thousands of cells; today an expert sorts them by hand, which
            takes 30-60 minutes and isn't always consistent between experts.
          </p>
          <p className="mt-3 text-sm leading-relaxed text-slate-300">
            AskCell does it in about 1.5 seconds per 100,000 cells, and
            distinguishes real cancer clones from{" "}
            <span className="text-violet-300">hematogones</span> -- normal
            cells that carry almost the same markers and fool simpler rules.
          </p>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
          {[
            ["1 · flag", "Score every cell by distance to the nearest healthy cells."],
            ["2 · cluster", "Keep only flagged cells that form a tight, real population."],
            ["3 · explain", "Ask questions -- every number traces back to a tool call."],
          ].map(([title, body]) => (
            <div key={title} className="glass-panel-soft rounded-lg p-3">
              <div className="font-mono text-[11px] uppercase tracking-wider text-cyan-300">
                {title}
              </div>
              <div className="mt-1 text-xs leading-relaxed text-slate-400">
                {body}
              </div>
            </div>
          ))}
        </div>

        <button
          onClick={onLaunch}
          className="mt-8 w-full rounded-lg bg-brand-gradient bg-200 bg-[position:0%_50%] px-4 py-3 text-sm font-semibold text-white shadow-glow-violet transition-all duration-300 hover:scale-[1.01] hover:bg-[position:100%_50%]"
        >
          Launch AskCell →
        </button>

        <p className="mt-4 text-center text-[11px] text-slate-600">
          Research and educational use only. Not a diagnostic device.
        </p>
      </div>
    </div>
  );
}
