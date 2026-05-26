"use client";

// Timeline (homepage). Lists events newest-first via TanStack Query.
//
// Marked "use client" because we use the useQuery hook. A pure server component
// would also work (and skip the JS bundle for this page), but using TanStack
// here lets us:
//   - Show stale data + refetch indicator on tab focus
//   - Pre-warm the cache so /events/[id] feels instant after a click
// Server component fallback can come later if bundle size becomes an issue.

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { EventCard } from "@/components/EventCard";

export default function Home() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["events", { page: 1, per_page: 20 }],
    queryFn: () => api.listEvents(1, 20),
  });

  if (isLoading) {
    return <SkeletonTimeline />;
  }

  if (error) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800">
        Failed to load events: {error.message}
      </div>
    );
  }

  if (!data || data.data.length === 0) {
    return (
      <div className="rounded-md border border-gray-200 bg-white p-6 text-center text-sm text-gray-600">
        No events yet. The fetcher workers populate this list as new events
        arrive from FRED / SEC / FOMC.
      </div>
    );
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900">Recent events</h1>
        <span className="text-xs text-gray-500 tabular-nums">
          {data.meta.total} total
        </span>
      </div>
      <ul className="space-y-2">
        {data.data.map((event) => (
          <li key={event.id}>
            <EventCard event={event} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function SkeletonTimeline() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className="h-24 rounded-lg border border-gray-200 bg-white animate-pulse"
        />
      ))}
    </div>
  );
}
