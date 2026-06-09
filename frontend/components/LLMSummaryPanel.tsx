// The "thesis paragraph" the v2 analyzer produces for each event.
// Phase A6 added events.llm_summary persistence — older events (analyzed
// pre-fix) may still have null; render a friendly empty state in that case.

export function LLMSummaryPanel({ summary }: { summary: string | null }) {
  if (!summary) {
    return (
      <section className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900 uppercase tracking-wide">
          LLM thesis
        </h2>
        <p className="mt-2 text-sm text-slate-500">
          No thesis paragraph stored for this event — it was analyzed before
          the summary-persistence fix landed. New analyses (and any
          re-analyzed events) will populate this section.
        </p>
      </section>
    );
  }
  return (
    <section className="rounded-2xl border border-indigo-200/60 bg-gradient-to-br from-indigo-50 via-white to-purple-50 p-6 shadow-sm">
      <div className="flex items-baseline justify-between mb-3">
        <h2 className="text-sm font-semibold text-indigo-900 uppercase tracking-wide">
          LLM thesis
        </h2>
        <span className="text-xs text-indigo-700/70">
          analyst-grade walkthrough — read this first
        </span>
      </div>
      <p className="text-sm text-slate-800 leading-relaxed whitespace-pre-wrap">
        {summary}
      </p>
    </section>
  );
}
