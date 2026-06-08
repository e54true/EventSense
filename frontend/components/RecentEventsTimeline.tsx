import { format } from "date-fns";

import type { RecentEventRead } from "@/lib/types";
import { SourceBadge } from "./SourceBadge";

type Props = {
  events: RecentEventRead[];
  lookbackDays: number;
};

export function RecentEventsTimeline({ events, lookbackDays }: Props) {
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
      <div className="flex items-baseline justify-between mb-4">
        <h2 className="text-sm font-semibold text-slate-900 uppercase tracking-wide">
          Recent event window
        </h2>
        <span className="text-xs text-slate-500">past {lookbackDays}d, newest first</span>
      </div>
      {events.length === 0 ? (
        <p className="text-sm text-slate-500">
          No prior events in the lookback window — the analyzer had a clean slate.
        </p>
      ) : (
        <ol className="space-y-2.5 max-h-96 overflow-y-auto">
          {events.map((e, i) => (
            <li
              key={`${e.published_at}-${i}`}
              className="flex items-start gap-3 text-sm"
            >
              <span className="text-xs text-slate-400 font-mono tabular-nums shrink-0 mt-0.5 w-20">
                {format(new Date(e.published_at), "MMM d")}
              </span>
              <SourceBadge source={e.source as "FRED" | "SEC_EDGAR" | "FOMC" | "EARNINGS"} />
              <span className="text-slate-700 leading-snug flex-1 min-w-0">
                {e.title}
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
