import { useEffect, useMemo, useRef } from "react";

/**
 * Home
 * ----
 * A simple landing screen explaining what AskCell does, shown before the
 * tool itself. Not a marketing site -- just enough context that someone
 * opening the link for the first time knows what they're looking at before
 * being dropped into a flow-cytometry viewer. Purely about the product:
 * no personal/author content belongs here.
 *
 * The scroll motion (parallax orbs, scroll-reveal, 3D tilt, a progress bar)
 * is driven off this component's own scroll container -- the app shell sets
 * `overflow: hidden` on html/body/#root, so everything here has to scroll
 * and observe *this* div, not `window`/`document`.
 */

const SPARKLES = Array.from({ length: 14 }, (_, i) => ({
  left: Math.round((i * 37 + 13) % 97) + ((i % 3) - 1) * 2,
  top: Math.round((i * 53 + 7) % 92) + 4,
  size: 10 + ((i * 7) % 10),
  color: ["#a78bfa", "#22d3ee", "#e879f9"][i % 3],
  glyph: ["✦", "✧", "•"][i % 3],
  delay: (i % 5) * 0.6,
  duration: 3 + (i % 4),
}));

const STEPS = [
  ["1 · flag", "Score every cell by distance to the nearest healthy cells."],
  ["2 · cluster", "Keep only flagged cells that form a tight, real population."],
  ["3 · explain", "Ask questions — every number traces back to a tool call."],
];

const STATS = [
  ["97.94%", "mean sensitivity"],
  ["100%", "mean precision"],
  ["100%", "specificity (4/4 healthy controls)"],
  ["1.5s", "per 100,000 cells"],
];

export default function Home({ onLaunch }) {
  const scrollRef = useRef(null);
  const progressRef = useRef(null);
  const orbRefs = useRef([]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    let raf;
    function tick() {
      const max = el.scrollHeight - el.clientHeight;
      const pct = max > 0 ? (el.scrollTop / max) * 100 : 0;
      if (progressRef.current) progressRef.current.style.width = pct + "%";
      orbRefs.current.forEach((orb) => {
        if (!orb) return;
        const speed = parseFloat(orb.dataset.speed || "0.1");
        orb.style.transform = `translateY(${el.scrollTop * speed}px)`;
      });
      raf = requestAnimationFrame(tick);
    }
    raf = requestAnimationFrame(tick);

    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("home-visible");
            io.unobserve(entry.target);
          }
        });
      },
      { root: el, threshold: 0.2 }
    );
    el.querySelectorAll(".home-reveal").forEach((node) => io.observe(node));

    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
    };
  }, []);

  function handleTilt(e) {
    const card = e.currentTarget;
    const r = card.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - 0.5;
    const y = (e.clientY - r.top) / r.height - 0.5;
    card.style.transform = `perspective(700px) rotateX(${(-y * 6).toFixed(2)}deg) rotateY(${(x * 6).toFixed(2)}deg) translateY(-2px)`;
  }
  function resetTilt(e) {
    e.currentTarget.style.transform = "";
  }

  return (
    <div
      ref={scrollRef}
      className="home-scroll relative h-screen w-screen overflow-y-auto bg-slate-950 text-slate-200"
    >
      <div ref={progressRef} className="home-progress" />

      <div className="home-orb-field">
        <div ref={(n) => (orbRefs.current[0] = n)} data-speed="0.12" className="home-orb home-orb-1" />
        <div ref={(n) => (orbRefs.current[1] = n)} data-speed="0.08" className="home-orb home-orb-2" />
        <div ref={(n) => (orbRefs.current[2] = n)} data-speed="0.15" className="home-orb home-orb-3" />
      </div>

      <div className="home-sparkle-field">
        {SPARKLES.map((s, i) => (
          <span
            key={i}
            className="home-sparkle"
            style={{
              left: s.left + "%",
              top: s.top + "%",
              fontSize: s.size,
              color: s.color,
              animationDelay: s.delay + "s",
              animationDuration: s.duration + "s",
            }}
          >
            {s.glyph}
          </span>
        ))}
      </div>

      <div className="relative z-10 mx-auto max-w-2xl px-6 pb-16">
        {/* ---- hero ---- */}
        <section className="flex min-h-[85vh] flex-col items-center justify-center text-center">
          <div className="home-badge-wrap mb-5">
            <div className="home-badge-dot" />
            <div className="home-badge-pin" />
            <div className="glass-panel-soft rounded-full px-4 py-1.5 font-mono text-[11px] uppercase tracking-wider text-cyan-300">
              Flow Cytometry · Abnormal Population Detector
            </div>
          </div>
          <h1 className="home-hero-title font-mono text-5xl font-bold tracking-tight sm:text-6xl">
            AskCell
          </h1>
          <p className="mt-4 max-w-md text-sm leading-relaxed text-slate-400 sm:text-base">
            Finds abnormal cell populations in a flow-cytometry specimen by
            comparing it against a reference built from healthy bone marrow.
          </p>
          <button
            onClick={onLaunch}
            className="mt-8 rounded-lg bg-brand-gradient bg-200 bg-[position:0%_50%] px-6 py-3 text-sm font-semibold text-white shadow-glow-violet transition-all duration-300 hover:scale-[1.02] hover:bg-[position:100%_50%]"
          >
            Launch AskCell →
          </button>
          <div className="home-scroll-cue mt-14 font-mono text-[10px] uppercase tracking-widest text-slate-600">
            <span>scroll</span>
            <span>↓</span>
          </div>
        </section>

        {/* ---- the problem ---- */}
        <h2 className="home-reveal home-h2">The problem</h2>
        <div
          className="home-reveal glass-panel home-tilt rounded-xl p-5"
          onMouseMove={handleTilt}
          onMouseLeave={resetTilt}
        >
          <p className="text-sm leading-relaxed text-slate-300">
            After leukemia treatment, doctors check bone marrow for{" "}
            <span className="text-violet-300">minimal residual disease</span>{" "}
            (MRD) — cancer cells that survived, often only 0.01–0.1% of the
            sample. A flow cytometer measures ~17 values per cell on hundreds
            of thousands of cells; today an expert sorts them by hand, which
            takes 30–60 minutes and isn't always consistent between experts.
          </p>
          <p className="mt-3 text-sm leading-relaxed text-slate-300">
            The hard case is{" "}
            <span className="text-violet-300">hematogones</span> — normal
            cells that carry almost the same markers and fool simpler rules.
          </p>
        </div>

        {/* ---- how it works ---- */}
        <h2 className="home-reveal home-h2">How it works</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {STEPS.map(([title, body], i) => (
            <div
              key={title}
              className={`home-reveal home-reveal-delay-${i} glass-panel-soft home-tilt rounded-lg p-3`}
              onMouseMove={handleTilt}
              onMouseLeave={resetTilt}
            >
              <div className="font-mono text-[11px] uppercase tracking-wider text-cyan-300">
                {title}
              </div>
              <div className="mt-1 text-xs leading-relaxed text-slate-400">{body}</div>
            </div>
          ))}
        </div>

        {/* ---- measured results ---- */}
        <h2 className="home-reveal home-h2">Measured, not claimed</h2>
        <div className="home-stat-grid">
          {STATS.map(([num, label], i) => (
            <div
              key={label}
              className={`home-reveal home-reveal-delay-${i} home-stat-card glass-panel-soft home-tilt`}
              onMouseMove={handleTilt}
              onMouseLeave={resetTilt}
            >
              <div className="home-stat-num">{num}</div>
              <div className="home-stat-label">{label}</div>
            </div>
          ))}
        </div>

        <button
          onClick={onLaunch}
          className="home-reveal mt-10 w-full rounded-lg bg-brand-gradient bg-200 bg-[position:0%_50%] px-4 py-3 text-sm font-semibold text-white shadow-glow-violet transition-all duration-300 hover:scale-[1.01] hover:bg-[position:100%_50%]"
        >
          Launch AskCell →
        </button>

        <p className="home-reveal mt-4 text-center text-[11px] text-slate-600">
          Research and educational use only. Not a diagnostic device.
        </p>
      </div>
    </div>
  );
}
