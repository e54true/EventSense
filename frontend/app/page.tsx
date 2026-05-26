"use client";

// Timeline (homepage). Lists events newest-first via TanStack Query.

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { EventCard } from "@/components/EventCard";
import { AccuracyPill } from "@/components/AccuracyPill";
import type { EventSource } from "@/lib/types";

const SOURCE_OPTIONS: { value: EventSource; label: string }[] = [
  { value: "FRED", label: "FRED" },
  { value: "SEC_EDGAR", label: "SEC" },
  { value: "FOMC", label: "FOMC" },
  { value: "EARNINGS", label: "Earnings" },
];

export default function Home() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["events", { page: 1, per_page: 20 }],
    queryFn: () => api.listEvents(1, 20),
  });

  return (
    <div className="space-y-8">
      <HeroSection />

      <div>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">
            Recent events
          </h2>
          <span className="text-xs text-slate-500 tabular-nums">
            {data ? `${data.meta.total} total` : ""}
          </span>
        </div>

        {isLoading && <SkeletonTimeline />}

        {error && (
          <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
            Failed to load events: {error.message}
          </div>
        )}

        {data && data.data.length === 0 && (
          <div className="rounded-xl border border-slate-200 bg-white p-10 text-center">
            <p className="text-sm text-slate-600">
              No events yet. The fetcher workers populate this list as new
              events arrive from FRED / SEC / FOMC.
            </p>
          </div>
        )}

        {data && data.data.length > 0 && (
          <ul className="space-y-3">
            {data.data.map((event) => (
              <li key={event.id}>
                <EventCard event={event} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function HeroSection() {
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
      <div className="flex flex-col gap-1">
        <p className="text-xs font-semibold uppercase tracking-wider text-indigo-600">
          Live pipeline
        </p>
        <h1 className="text-2xl font-bold text-slate-900">
          Market events &amp; LLM predictions
        </h1>
        <p className="mt-1 text-sm text-slate-600 max-w-2xl">
          Macro and corporate events from FRED, SEC EDGAR, FOMC, and earnings
          calendars. Each event is automatically analyzed by an LLM and validated
          against real price movement.
        </p>
      </div>

      <div className="mt-5 grid grid-cols-2 sm:grid-cols-4 gap-3">
        {SOURCE_OPTIONS.map((s) => (
          <AccuracyPill key={s.value} source={s.value} label={s.label} />
        ))}
      </div>
    </section>
  );
}

function SkeletonTimeline() {
  return (
    <ul className="space-y-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <li
          key={i}
          className="h-28 rounded-xl border border-slate-200 bg-white animate-pulse"
        />
      ))}
    </ul>
  );
}
