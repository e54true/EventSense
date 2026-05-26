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
      className="group block rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition-all hover:border-slate-300 hover:shadow-md hover:-translate-y-0.5"
    >
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <SourceBadge source={event.source} />
          <span className="text-xs font-medium text-slate-500 tracking-wide">
            {event.event_type.replace(/_/g, " ")}
          </span>
        </div>
        <span className="text-xs text-slate-500 tabular-nums" title={event.published_at}>
          {publishedAgo}
        </span>
      </div>

      <h3 className="text-sm font-semibold text-slate-900 leading-snug line-clamp-2 group-hover:text-indigo-700 transition-colors">
        {event.title}
      </h3>

      {event.affected_tickers.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {event.affected_tickers.map((t) => (
            <span
              key={t}
              className="inline-flex rounded-md bg-slate-100 px-2 py-0.5 text-xs font-mono font-medium text-slate-700"
            >
              {t}
            </span>
          ))}
        </div>
      )}
    </Link>
  );
}
