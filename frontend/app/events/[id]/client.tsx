"use client";

// Event detail UI: header with source / type / time, full title, predictions
// list, and collapsible raw payload.

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { format, formatDistanceToNow } from "date-fns";

import { api } from "@/lib/api";
import { EventDetailResponse, PredictionWithOutcomes } from "@/lib/types";
import { AttachedDocumentsPanel } from "@/components/AttachedDocumentsPanel";
import { MacroContextPanel } from "@/components/MacroContextPanel";
import { PredictionRow } from "@/components/PredictionRow";
import { PriceChart } from "@/components/PriceChart";
import { RecentEventsTimeline } from "@/components/RecentEventsTimeline";
import { SourceBadge } from "@/components/SourceBadge";

export function EventDetailClient({ id }: { id: string }) {
  const { data, isLoading, error } = useQuery<EventDetailResponse>({
    queryKey: ["event", id],
    queryFn: () => api.getEvent(id),
  });

  if (isLoading) {
    return <Skeleton />;
  }

  if (error) {
    return <ErrorBlock title="Failed to load event" detail={error.message} />;
  }

  if (!data) {
    return <ErrorBlock title="Not found" detail="No event with this ID." />;
  }

  const { data: event, predictions, context } = data;
  const totalCost = predictions.reduce((acc, p) => acc + p.llm_cost_usd, 0);
  const marketPredictions = predictions.filter((p) => p.kind === "MARKET");
  const companyPredictions = predictions.filter((p) => p.kind === "COMPANY");
  const publishedAgo = formatDistanceToNow(new Date(event.published_at), {
    addSuffix: true,
  });

  return (
    <div className="space-y-6">
      <BackLink />

      <header className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          <SourceBadge source={event.source} />
          <span className="text-xs font-medium text-slate-500 tracking-wide">
            {event.event_type.replace(/_/g, " ")}
          </span>
          <StatusChip status={event.status} />
          <span
            className="text-xs text-slate-500 ml-auto"
            title={event.published_at}
          >
            {format(new Date(event.published_at), "PPpp")} · {publishedAgo}
          </span>
        </div>

        <h1 className="text-xl font-bold text-slate-900 leading-snug">
          {event.title}
        </h1>

        <dl className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
          <div className="rounded-lg bg-slate-50 p-3">
            <dt className="text-[11px] uppercase tracking-wider text-slate-500 mb-0.5">
              External ID
            </dt>
            <dd className="font-mono text-slate-800 text-xs break-all">
              {event.external_id}
            </dd>
          </div>
          <div className="rounded-lg bg-slate-50 p-3">
            <dt className="text-[11px] uppercase tracking-wider text-slate-500 mb-0.5">
              Affected tickers
            </dt>
            <dd className="text-slate-800">
              {event.affected_tickers.length > 0 ? (
                <div className="flex flex-wrap gap-1">
                  {event.affected_tickers.map((t) => (
                    <span
                      key={t}
                      className="font-mono text-xs font-semibold text-slate-900"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              ) : (
                <span className="text-slate-500">none</span>
              )}
            </dd>
          </div>
          <div className="rounded-lg bg-slate-50 p-3">
            <dt className="text-[11px] uppercase tracking-wider text-slate-500 mb-0.5">
              Fetched
            </dt>
            <dd className="text-slate-800 text-xs">
              {formatDistanceToNow(new Date(event.fetched_at), {
                addSuffix: true,
              })}
            </dd>
          </div>
        </dl>

        {event.failure_reason && (
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
            <strong className="font-semibold">Failure reason:</strong>{" "}
            {event.failure_reason}
          </div>
        )}
      </header>

      {predictions.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-slate-900 uppercase tracking-wide">
            Price action
            <span className="ml-2 text-slate-400 normal-case">
              — predicted_at marked, lines rebased to 100
            </span>
          </h2>
          {predictions.slice(0, 1).map((p) => (
            <PriceChart
              key={p.id}
              ticker={p.ticker}
              predictedAt={p.predicted_at}
            />
          ))}
        </section>
      )}

      <section>
        <PredictionsHeader
          predictions={predictions}
          totalCost={totalCost}
        />
        {predictions.length === 0 ? (
          <div className="rounded-xl border border-slate-200 bg-white p-6 text-center text-sm text-slate-600">
            No predictions yet — the analyzer worker runs every minute, so a
            FETCHED event should pick up an analysis shortly.
          </div>
        ) : (
          <div className="space-y-5">
            <PredictionGroup
              heading="Market reaction (SPY / QQQ)"
              predictions={marketPredictions}
              emptyHint="No MARKET impacts on this event — the analyzer thought the macro stage was neutral."
            />
            {companyPredictions.length > 0 && (
              <PredictionGroup
                heading="Company reaction"
                predictions={companyPredictions}
              />
            )}
          </div>
        )}
      </section>

      <AttachedDocumentsPanel documents={data.attached_documents} />

      <MacroContextPanel
        title={`Macro context (at ${format(new Date(event.published_at), "PP")})`}
        subtitle={`indicator values, 30d change`}
        indicators={context.latest_indicators}
      />

      <RecentEventsTimeline
        events={context.recent_events}
        lookbackDays={context.lookback_days}
      />

      <details className="rounded-2xl border border-slate-200/80 bg-white shadow-sm">
        <summary className="cursor-pointer p-4 text-sm font-medium text-slate-700 select-none flex items-center justify-between">
          <span>Raw payload (JSON)</span>
          <span className="text-xs text-slate-400">
            {Object.keys(event.payload).length} fields
          </span>
        </summary>
        <div className="px-4 pb-4">
          <pre className="overflow-x-auto rounded-lg bg-slate-900 p-4 text-xs text-slate-100 leading-relaxed">
            {JSON.stringify(event.payload, null, 2)}
          </pre>
        </div>
      </details>
    </div>
  );
}

function PredictionsHeader({
  predictions,
  totalCost,
}: {
  predictions: PredictionWithOutcomes[];
  totalCost: number;
}) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h2 className="text-sm font-semibold text-slate-900 uppercase tracking-wide">
        LLM predictions
        <span className="ml-2 text-slate-400">({predictions.length})</span>
      </h2>
      {predictions.length > 0 && (
        <div className="text-xs text-slate-500 font-mono tabular-nums">
          Total cost ${totalCost.toFixed(5)}
        </div>
      )}
    </div>
  );
}

function PredictionGroup({
  heading,
  predictions,
  emptyHint,
}: {
  heading: string;
  predictions: PredictionWithOutcomes[];
  emptyHint?: string;
}) {
  return (
    <div>
      <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
        {heading}
        <span className="ml-2 text-slate-400 normal-case font-normal">
          ({predictions.length})
        </span>
      </h3>
      {predictions.length === 0 ? (
        emptyHint ? (
          <p className="text-xs text-slate-500 italic px-1">{emptyHint}</p>
        ) : null
      ) : (
        <ul className="space-y-2.5">
          {predictions.map((p) => (
            <li key={p.id}>
              <PredictionRow prediction={p} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function StatusChip({ status }: { status: string }) {
  const styles: Record<string, string> = {
    FETCHED: "bg-slate-100 text-slate-700",
    ANALYZED: "bg-indigo-100 text-indigo-700",
    FAILED: "bg-rose-100 text-rose-700",
    IGNORED: "bg-slate-100 text-slate-500",
  };
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wide ${
        styles[status] ?? styles.FETCHED
      }`}
    >
      {status}
    </span>
  );
}

function BackLink() {
  return (
    <Link
      href="/"
      className="inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900 transition-colors"
    >
      ← Back to timeline
    </Link>
  );
}

function Skeleton() {
  return (
    <div className="space-y-4">
      <div className="h-4 w-32 rounded bg-slate-200 animate-pulse" />
      <div className="h-44 rounded-2xl border border-slate-200 bg-white animate-pulse" />
      <div className="h-32 rounded-2xl border border-slate-200 bg-white animate-pulse" />
    </div>
  );
}

function ErrorBlock({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="space-y-4">
      <BackLink />
      <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
        <p className="font-semibold">{title}</p>
        <p className="mt-1 text-rose-700">{detail}</p>
      </div>
    </div>
  );
}
