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
      className="block rounded-lg border border-gray-200 bg-white p-4 shadow-sm transition hover:border-gray-300 hover:shadow-md"
    >
      <div className="flex items-center justify-between gap-3 mb-2">
        <div className="flex items-center gap-2">
          <SourceBadge source={event.source} />
          <span className="text-xs text-gray-500">{event.event_type}</span>
        </div>
        <span className="text-xs text-gray-500" title={event.published_at}>
          {publishedAgo}
        </span>
      </div>
      <h3 className="text-sm font-medium text-gray-900 line-clamp-2">
        {event.title}
      </h3>
      {event.affected_tickers.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {event.affected_tickers.map((t) => (
            <span
              key={t}
              className="inline-flex rounded bg-gray-100 px-1.5 py-0.5 text-xs font-mono text-gray-700"
            >
              {t}
            </span>
          ))}
        </div>
      )}
    </Link>
  );
}
