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
        <div className="mb-3 flex items-center justify-between border-b border-term-border pb-2">
          <h2 className="font-mono text-xs font-bold tracking-[0.2em] text-term-muted">
            <span className="text-term-amber">▮</span> LIVE FEED
          </h2>
          <span className="font-mono text-[11px] text-term-dim tabular-nums">
            {data ? `${data.meta.total} TOTAL` : ""}
          </span>
        </div>

        {isLoading && <SkeletonTimeline />}

        {error && (
          <div className="border border-term-down/40 bg-term-down/10 p-4 font-mono text-sm text-term-down">
            FAILED TO LOAD EVENTS: {error.message}
          </div>
        )}

        {data && data.data.length === 0 && (
          <div className="border border-term-border bg-term-panel p-10 text-center">
            <p className="text-sm text-term-muted">
              No events yet. The fetcher workers populate this list as new
              events arrive from FRED / SEC / FOMC.
            </p>
          </div>
        )}

        {data && data.data.length > 0 && (
          <ul className="space-y-2">
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
    <section className="border border-term-border bg-term-panel p-6">
      <div className="flex flex-col gap-1">
        <p className="font-mono text-[10px] font-bold tracking-[0.3em] text-term-amber">
          ▮ LIVE PIPELINE
        </p>
        <h1 className="text-2xl font-bold text-term-text tracking-tight">
          Market events &amp; LLM predictions
        </h1>
        <p className="mt-1 text-sm text-term-muted max-w-2xl leading-relaxed">
          Macro and corporate events from FRED, SEC EDGAR, FOMC, and earnings
          calendars. Each event is automatically analyzed by an LLM and validated
          against real price movement.
        </p>
      </div>

      <div className="mt-5 grid grid-cols-2 sm:grid-cols-4 gap-2">
        {SOURCE_OPTIONS.map((s) => (
          <AccuracyPill key={s.value} source={s.value} label={s.label} />
        ))}
      </div>
    </section>
  );
}

function SkeletonTimeline() {
  return (
    <ul className="space-y-2">
      {Array.from({ length: 5 }).map((_, i) => (
        <li
          key={i}
          className="h-24 border border-term-border bg-term-panel animate-pulse"
        />
      ))}
    </ul>
  );
}
