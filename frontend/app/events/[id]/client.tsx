"use client";

// Event detail UI: header with source / type / time, full title, raw payload
// preview (collapsed JSON), and the list of LLM predictions for this event.

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { format } from "date-fns";

import { api } from "@/lib/api";
import { EventDetailResponse } from "@/lib/types";
import { SourceBadge } from "@/components/SourceBadge";
import { PredictionRow } from "@/components/PredictionRow";

export function EventDetailClient({ id }: { id: string }) {
  const { data, isLoading, error } = useQuery<EventDetailResponse>({
    queryKey: ["event", id],
    queryFn: () => api.getEvent(id),
  });

  if (isLoading) {
    return <Skeleton />;
  }

  if (error) {
    return (
      <ErrorBlock title="Failed to load event" detail={error.message} />
    );
  }

  if (!data) {
    return <ErrorBlock title="Not found" detail="No event with this ID." />;
  }

  const { data: event, predictions } = data;

  return (
    <div className="space-y-6">
      <BackLink />

      <header className="rounded-lg border border-gray-200 bg-white p-5">
        <div className="flex items-center gap-2 mb-3">
          <SourceBadge source={event.source} />
          <span className="text-xs text-gray-500">{event.event_type}</span>
          <span className="text-xs text-gray-400 ml-auto" title={event.published_at}>
            {format(new Date(event.published_at), "PPpp")}
          </span>
        </div>
        <h1 className="text-lg font-semibold text-gray-900 mb-1">
          {event.title}
        </h1>
        <div className="text-xs text-gray-500 mt-2 flex gap-3">
          <span>Status: {event.status}</span>
          <span>·</span>
          <span>External ID: <code>{event.external_id}</code></span>
        </div>
        {event.affected_tickers.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1">
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
        {event.failure_reason && (
          <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
            <strong>Failure reason:</strong> {event.failure_reason}
          </div>
        )}
      </header>

      <section>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-900">
            LLM predictions ({predictions.length})
          </h2>
          {predictions.length > 0 && (
            <span className="text-xs text-gray-500">
              Total cost ${" "}
              {predictions
                .reduce((acc, p) => acc + p.llm_cost_usd, 0)
                .toFixed(5)}
            </span>
          )}
        </div>
        {predictions.length === 0 ? (
          <div className="rounded-md border border-gray-200 bg-white p-4 text-sm text-gray-600">
            No predictions yet — the analyzer worker runs every minute, so a
            FETCHED event should pick up an analysis shortly.
          </div>
        ) : (
          <ul className="space-y-2">
            {predictions.map((p) => (
              <li key={p.id}>
                <PredictionRow prediction={p} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <details className="rounded-lg border border-gray-200 bg-white p-4">
        <summary className="cursor-pointer text-sm font-medium text-gray-700">
          Raw payload
        </summary>
        <pre className="mt-3 overflow-x-auto rounded bg-gray-50 p-3 text-xs text-gray-800">
          {JSON.stringify(event.payload, null, 2)}
        </pre>
      </details>
    </div>
  );
}

function BackLink() {
  return (
    <Link
      href="/"
      className="inline-flex items-center text-sm text-gray-600 hover:text-gray-900"
    >
      ← Back to timeline
    </Link>
  );
}

function Skeleton() {
  return (
    <div className="space-y-4">
      <div className="h-4 w-32 rounded bg-gray-200 animate-pulse" />
      <div className="h-40 rounded-lg border border-gray-200 bg-white animate-pulse" />
      <div className="h-32 rounded-lg border border-gray-200 bg-white animate-pulse" />
    </div>
  );
}

function ErrorBlock({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="space-y-4">
      <BackLink />
      <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800">
        <p className="font-medium">{title}</p>
        <p className="mt-1 text-red-700">{detail}</p>
      </div>
    </div>
  );
}
