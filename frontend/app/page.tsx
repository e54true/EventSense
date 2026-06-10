"use client";

// Timeline (homepage). Lists events newest-first via TanStack Query.
//
// Infinite pagination instead of load-everything: the events table grows
// without bound, so we pull 20 at a time and let the user pull more. The
// filter bar (source / ticker / event type) maps straight onto the backend's
// /events query params — switching a filter resets the pagination.

import { useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { EventCard } from "@/components/EventCard";
import { AccuracyPill } from "@/components/AccuracyPill";
import { cn } from "@/lib/utils";
import type { EventFilters, EventSource } from "@/lib/types";

const PER_PAGE = 20;

const SOURCE_OPTIONS: { value: EventSource; label: string }[] = [
  { value: "FRED", label: "FRED" },
  { value: "SEC_EDGAR", label: "SEC" },
  { value: "FOMC", label: "FOMC" },
  { value: "EARNINGS", label: "Earnings" },
];

export default function Home() {
  const [filters, setFilters] = useState<EventFilters>({});

  const events = useInfiniteQuery({
    queryKey: ["events", filters],
    queryFn: ({ pageParam }) => api.listEvents(pageParam, PER_PAGE, filters),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => {
      const { page, per_page, total } = lastPage.meta;
      return page * per_page < total ? page + 1 : undefined;
    },
  });

  const allEvents = events.data?.pages.flatMap((p) => p.data) ?? [];
  const total = events.data?.pages[0]?.meta.total;

  return (
    <div className="space-y-8">
      <HeroSection />

      <div>
        <div className="mb-3 flex items-center justify-between border-b border-term-border pb-2">
          <h2 className="font-mono text-xs font-bold tracking-[0.2em] text-term-muted">
            <span className="text-term-amber">▮</span> LIVE FEED
          </h2>
          <span className="font-mono text-[11px] text-term-dim tabular-nums">
            {total !== undefined ? `${allEvents.length} / ${total}` : ""}
          </span>
        </div>

        <FilterBar filters={filters} onChange={setFilters} />

        {events.isLoading && <SkeletonTimeline />}

        {events.error && (
          <div className="border border-term-down/40 bg-term-down/10 p-4 font-mono text-sm text-term-down">
            FAILED TO LOAD EVENTS: {events.error.message}
          </div>
        )}

        {events.data && allEvents.length === 0 && (
          <div className="border border-term-border bg-term-panel p-10 text-center">
            <p className="text-sm text-term-muted">
              No events match these filters.
            </p>
          </div>
        )}

        {allEvents.length > 0 && (
          <>
            <ul className="space-y-2">
              {allEvents.map((event) => (
                <li key={event.id}>
                  <EventCard event={event} />
                </li>
              ))}
            </ul>

            {events.hasNextPage && (
              <button
                onClick={() => events.fetchNextPage()}
                disabled={events.isFetchingNextPage}
                className="mt-4 w-full border border-term-border bg-term-panel py-2.5 font-mono text-xs font-bold tracking-[0.2em] text-term-muted hover:border-term-amber/60 hover:text-term-amber transition-colors disabled:opacity-50"
              >
                {events.isFetchingNextPage
                  ? "LOADING…"
                  : `LOAD MORE (${total !== undefined ? total - allEvents.length : "…"} REMAINING)`}
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function FilterBar({
  filters,
  onChange,
}: {
  filters: EventFilters;
  onChange: (f: EventFilters) => void;
}) {
  // Distinct values actually present in the DB — a new ticker or event type
  // shows up here without a frontend change.
  const { data: options } = useQuery({
    queryKey: ["events.filters"],
    queryFn: () => api.getEventFilters(),
    staleTime: 5 * 60_000,
  });

  const hasActive =
    filters.source !== undefined ||
    filters.ticker !== undefined ||
    filters.event_type !== undefined;

  return (
    <div className="mb-4 space-y-2">
      <FilterRow label="SOURCE">
        {SOURCE_OPTIONS.map((s) => (
          <FilterChip
            key={s.value}
            label={s.label}
            active={filters.source === s.value}
            onClick={() =>
              onChange({
                ...filters,
                source: filters.source === s.value ? undefined : s.value,
              })
            }
          />
        ))}
      </FilterRow>

      {options && options.tickers.length > 0 && (
        <FilterRow label="TICKER">
          {options.tickers.map((t) => (
            <FilterChip
              key={t}
              label={t}
              active={filters.ticker === t}
              onClick={() =>
                onChange({
                  ...filters,
                  ticker: filters.ticker === t ? undefined : t,
                })
              }
            />
          ))}
        </FilterRow>
      )}

      {options && options.event_types.length > 0 && (
        <FilterRow label="TYPE">
          {options.event_types.map((et) => (
            <FilterChip
              key={et}
              label={et.replace(/_/g, " ")}
              active={filters.event_type === et}
              onClick={() =>
                onChange({
                  ...filters,
                  event_type: filters.event_type === et ? undefined : et,
                })
              }
            />
          ))}
        </FilterRow>
      )}

      {hasActive && (
        <button
          onClick={() => onChange({})}
          className="font-mono text-[10px] tracking-widest text-term-down hover:underline"
        >
          ✕ CLEAR FILTERS
        </button>
      )}
    </div>
  );
}

function FilterRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline gap-2 flex-wrap">
      <span className="font-mono text-[10px] tracking-widest text-term-dim w-14 shrink-0">
        {label}
      </span>
      {children}
    </div>
  );
}

function FilterChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "border px-2 py-0.5 font-mono text-[11px] font-semibold tracking-wider transition-colors",
        active
          ? "border-term-amber bg-term-amber/15 text-term-amber"
          : "border-term-border bg-term-panel text-term-muted hover:border-term-border2 hover:text-term-text",
      )}
    >
      {label}
    </button>
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
