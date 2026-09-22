import React, { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE } from "../lib/api.js";

/**
 * FlowChat
 * --------
 * Plain-language explanation of the current result, plus follow-up questions.
 *
 * The agent reads the finished report through tools; it cannot see raw events
 * and cannot compute anything. Which tools it consulted are shown under each
 * answer, so a claim can be traced back to the part of the report it came from
 * rather than taken on trust.
 *
 * A missing API key is a normal state, not an error: detection works entirely
 * without one, and only this panel needs it.
 */

const SUGGESTIONS = [
  "Explain this result in simple terms",
  "How confident is this, and what would change it?",
  "What does the marker pattern resemble?",
  "Why weren't the stage 1 flags counted?",
  "What tests would confirm this?",
];

export default function FlowChat({ hasSample, sampleName }) {
  const [turns, setTurns] = useState([]);   // {role, text, tools?}
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const scrollRef = useRef(null);

  // A new specimen invalidates the whole conversation -- it was about the
  // previous result, and answers referring to it would be actively misleading.
  useEffect(() => {
    setTurns([]);
    setError(null);
  }, [sampleName]);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [turns, busy]);

  const send = useCallback(
    async (message, { explain = false } = {}) => {
      if (busy || !hasSample) return;
      setBusy(true);
      setError(null);
      if (!explain) {
        setTurns((t) => [...t, { role: "user", text: message }]);
      }

      try {
        const res = await fetch(
          `${API_BASE}/api/flow/${explain ? "explain" : "chat"}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: explain ? "{}" : JSON.stringify({ message }),
          }
        );
        const body = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`);
        setTurns((t) => [
          ...t,
          { role: "assistant", text: body.reply, tools: body.tools_used || [] },
        ]);
      } catch (e) {
        setError(e.message);
      } finally {
        setBusy(false);
      }
    },
    [busy, hasSample]
  );

  const onSubmit = useCallback(
    (e) => {
      e.preventDefault();
      const m = input.trim();
      if (!m) return;
      setInput("");
      send(m);
    },
    [input, send]
  );

  if (!hasSample) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center">
        <p className="text-xs text-slate-500">
          Analyse a specimen, then ask about the result.
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
        {turns.length === 0 && !busy && (
          <div className="space-y-3">
            <button
              onClick={() => send(null, { explain: true })}
              className="w-full animate-glow-pulse rounded-lg bg-brand-gradient bg-200 bg-[position:0%_50%] px-3 py-2.5 text-xs font-semibold text-white transition-all duration-300 hover:scale-[1.02] hover:bg-[position:100%_50%]"
            >
              Explain this result
            </button>
            <div className="space-y-1">
              <div className="font-mono text-[9px] uppercase tracking-widest text-slate-600">
                or ask
              </div>
              {SUGGESTIONS.slice(1).map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="block w-full rounded border border-slate-800 px-2.5 py-1.5 text-left text-[11px] text-slate-400 transition hover:border-violet-500/40 hover:text-slate-200"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((t, i) =>
          t.role === "user" ? (
            <div key={i} className="flex animate-fade-up justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-brand-gradient px-3 py-2 text-xs text-white shadow-glow-violet">
                {t.text}
              </div>
            </div>
          ) : (
            <div key={i} className="animate-fade-up space-y-1.5">
              <div className="glass-panel rounded-2xl rounded-bl-sm px-3 py-2.5">
                <Markdownish text={t.text} />
              </div>
              {t.tools?.length > 0 && (
                <div className="flex flex-wrap items-center gap-1 pl-1">
                  <span className="font-mono text-[9px] text-slate-600">
                    read:
                  </span>
                  {[...new Set(t.tools)].map((tool) => (
                    <span
                      key={tool}
                      className="rounded bg-slate-800/60 px-1.5 py-0.5 font-mono text-[9px] text-slate-500"
                    >
                      {tool.replace(/^get_/, "")}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )
        )}

        {busy && (
          <div className="flex items-center gap-2 px-1">
            <div className="h-3 w-3 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
            <span className="font-mono text-[10px] text-slate-500">
              reading the report…
            </span>
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-2.5">
            <p className="text-[11px] leading-relaxed text-amber-200">{error}</p>
            {/^ANTHROPIC_API_KEY/.test(error) && (
              <p className="mt-1.5 text-[10px] leading-relaxed text-slate-500">
                Detection works without a key — only this panel needs one. Add
                it to <span className="font-mono">backend/.env</span> and
                restart the backend.
              </p>
            )}
          </div>
        )}
      </div>

      <form
        onSubmit={onSubmit}
        className="shrink-0 border-t border-violet-950/60 p-3"
      >
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about this result…"
            disabled={busy}
            className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs text-slate-200 placeholder:text-slate-600 focus:border-violet-500/60 focus:outline-none disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="rounded-lg bg-brand-gradient px-3 py-1.5 text-xs font-semibold text-white shadow-glow-violet transition hover:scale-105 disabled:opacity-40 disabled:hover:scale-100"
          >
            ask
          </button>
        </div>
        <p className="mt-1.5 text-[9px] leading-relaxed text-slate-600">
          Every figure comes from the report, not the model. Not a diagnosis.
        </p>
      </form>
    </div>
  );
}

/**
 * Minimal renderer for the subset of markdown the agent actually emits:
 * **bold**, bullet lists, and paragraph breaks. A full markdown dependency
 * would be several hundred kilobytes for three constructs.
 */
function Markdownish({ text }) {
  const blocks = String(text || "").split(/\n\n+/);
  return (
    <div className="space-y-2">
      {blocks.map((block, i) => {
        const lines = block.split("\n");
        const isList = lines.every((l) => /^\s*[-*•]\s+/.test(l));
        if (isList) {
          return (
            <ul key={i} className="space-y-1">
              {lines.map((l, j) => (
                <li
                  key={j}
                  className="flex gap-1.5 text-xs leading-relaxed text-slate-300"
                >
                  <span className="text-slate-600">·</span>
                  <span>{bold(l.replace(/^\s*[-*•]\s+/, ""))}</span>
                </li>
              ))}
            </ul>
          );
        }
        return (
          <p key={i} className="text-xs leading-relaxed text-slate-300">
            {bold(block)}
          </p>
        );
      })}
    </div>
  );
}

function bold(s) {
  return String(s)
    .split(/(\*\*[^*]+\*\*)/g)
    .map((part, i) =>
      /^\*\*[^*]+\*\*$/.test(part) ? (
        <strong key={i} className="font-semibold text-slate-100">
          {part.slice(2, -2)}
        </strong>
      ) : (
        part
      )
    );
}
