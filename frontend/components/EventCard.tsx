import Link from "next/link";
import { formatDistanceToNow } from "date-fns";

import type { EventRead } from "@/lib/types";
import { SourceBadge } from "./SourceBadge";

export function EventCard({ event }: { event: EventRead }) {
  const publishedAgo = formatDistanceToNow(new Date(event.published_at), {
    addSuffix: true,
  });

  return (
    <Link
      href={`/events/${event.id}`}
      className="group block border border-term-border bg-term-panel p-4 transition-colors hover:border-term-amber/60 hover:bg-term-panel2"
    >
      <div className="flex items-center justify-between gap-3 mb-2.5">
        <div className="flex items-center gap-2">
          <SourceBadge source={event.source} />
          <span className="font-mono text-[10px] tracking-widest text-term-dim uppercase">
            {event.event_type.replace(/_/g, " ")}
          </span>
        </div>
        <span
          className="font-mono text-[11px] text-term-dim tabular-nums"
          title={event.published_at}
        >
          {publishedAgo}
        </span>
      </div>

      <h3 className="text-sm font-semibold text-term-text leading-snug line-clamp-2 group-hover:text-term-amber transition-colors">
        {event.title}
      </h3>

      {event.affected_tickers.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {event.affected_tickers.map((t) => (
            <span
              key={t}
              className="inline-flex border border-term-border bg-term-panel2 px-1.5 py-px font-mono text-[11px] font-semibold text-term-muted"
            >
              {t}
            </span>
          ))}
        </div>
      )}
    </Link>
  );
}
