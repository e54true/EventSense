// The "thesis paragraph" the v2 analyzer produces for each event.
// Phase A6 added events.llm_summary persistence — older events (analyzed
// pre-fix) may still have null; render a friendly empty state in that case.

export function LLMSummaryPanel({ summary }: { summary: string | null }) {
  if (!summary) {
    return (
      <section className="border border-term-border bg-term-panel p-5">
        <h2 className="font-mono text-xs font-bold tracking-[0.2em] text-term-muted">
          <span className="text-term-amber">▮</span> LLM THESIS
        </h2>
        <p className="mt-2 text-sm text-term-muted">
          No thesis paragraph stored for this event — it was analyzed before
          the summary-persistence fix landed. New analyses (and any
          re-analyzed events) will populate this section.
        </p>
      </section>
    );
  }
  return (
    <section className="border border-term-amber/30 border-l-2 border-l-term-amber bg-term-panel p-5">
      <div className="flex items-baseline justify-between mb-3">
        <h2 className="font-mono text-xs font-bold tracking-[0.2em] text-term-amber">
          ▮ LLM THESIS
        </h2>
        <span className="font-mono text-[10px] tracking-wider text-term-dim uppercase">
          analyst-grade walkthrough — read this first
        </span>
      </div>
      <p className="text-sm text-term-text/90 leading-relaxed whitespace-pre-wrap">
        {summary}
      </p>
    </section>
  );
}
