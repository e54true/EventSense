import Link from "next/link";
import { format } from "date-fns";

import type { EventSource, RecentEventRead } from "@/lib/types";
import { SourceBadge } from "./SourceBadge";

type Props = {
  events: RecentEventRead[];
  lookbackDays: number;
};

const KNOWN_SOURCES: ReadonlySet<string> = new Set([
  "FRED",
  "SEC_EDGAR",
  "FOMC",
  "EARNINGS",
]);

export function RecentEventsTimeline({ events, lookbackDays }: Props) {
  return (
    <section className="border border-term-border bg-term-panel p-5">
      <div className="flex items-baseline justify-between mb-4">
        <h2 className="font-mono text-xs font-bold tracking-[0.2em] text-term-muted uppercase">
          <span className="text-term-amber">▮</span> Recent event window
        </h2>
        <span className="font-mono text-[10px] tracking-wider text-term-dim">
          past {lookbackDays}d, newest first
        </span>
      </div>
      {events.length === 0 ? (
        <p className="text-sm text-term-muted">
          No prior events in the lookback window — the analyzer had a clean slate.
        </p>
      ) : (
        <ol className="space-y-1 max-h-96 overflow-y-auto">
          {events.map((e) => (
            <li key={e.id}>
              <Link
                href={`/events/${e.id}`}
                className="group flex items-start gap-3 text-sm px-1.5 py-1 -mx-1.5 hover:bg-term-panel2 transition-colors"
              >
                <span className="font-mono text-[11px] text-term-dim tabular-nums shrink-0 mt-0.5 w-16">
                  {format(new Date(e.published_at), "MMM d")}
                </span>
                {KNOWN_SOURCES.has(e.source) ? (
                  <SourceBadge source={e.source as EventSource} />
                ) : (
                  <span className="inline-flex items-center border border-term-border px-1.5 py-px font-mono text-[10px] font-bold tracking-widest text-term-muted">
                    {e.source}
                  </span>
                )}
                <span className="text-term-text/90 leading-snug flex-1 min-w-0 group-hover:text-term-amber transition-colors">
                  {e.title}
                </span>
                <span
                  aria-hidden
                  className="text-term-dim opacity-0 group-hover:opacity-100 group-hover:text-term-amber transition-opacity shrink-0"
                >
                  →
                </span>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
