"use client";

// Event detail UI: header with source / type / time, full title, predictions
// list, and collapsible raw payload.

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { format, formatDistanceToNow } from "date-fns";

import { api } from "@/lib/api";
import { EventDetailResponse, PredictionWithOutcomes } from "@/lib/types";
import { AttachedDocumentsPanel } from "@/components/AttachedDocumentsPanel";
import { LLMSummaryPanel } from "@/components/LLMSummaryPanel";
import { MacroContextPanel } from "@/components/MacroContextPanel";
import { PredictionLegend } from "@/components/PredictionLegend";
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

      <header className="border border-term-border bg-term-panel p-6">
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          <SourceBadge source={event.source} />
          <span className="font-mono text-[10px] tracking-widest text-term-dim uppercase">
            {event.event_type.replace(/_/g, " ")}
          </span>
          <StatusChip status={event.status} />
          <span
            className="font-mono text-[11px] text-term-dim ml-auto tabular-nums"
            title={event.published_at}
          >
            {format(new Date(event.published_at), "PPpp")} · {publishedAgo}
          </span>
        </div>

        <h1 className="text-xl font-bold text-term-text leading-snug">
          {event.title}
        </h1>

        <dl className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
          <div className="border border-term-border bg-term-panel2/60 p-3">
            <dt className="font-mono text-[10px] uppercase tracking-widest text-term-dim mb-0.5">
              External ID
            </dt>
            <dd className="font-mono text-term-muted text-xs break-all">
              {event.external_id}
            </dd>
          </div>
          <div className="border border-term-border bg-term-panel2/60 p-3">
            <dt className="font-mono text-[10px] uppercase tracking-widest text-term-dim mb-0.5">
              Affected tickers
            </dt>
            <dd className="text-term-text">
              {event.affected_tickers.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {event.affected_tickers.map((t) => (
                    <span
                      key={t}
                      className="font-mono text-xs font-bold text-term-amber"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              ) : (
                <span className="text-term-dim">none</span>
              )}
            </dd>
          </div>
          <div className="border border-term-border bg-term-panel2/60 p-3">
            <dt className="font-mono text-[10px] uppercase tracking-widest text-term-dim mb-0.5">
              Fetched
            </dt>
            <dd className="text-term-muted text-xs">
              {formatDistanceToNow(new Date(event.fetched_at), {
                addSuffix: true,
              })}
            </dd>
          </div>
        </dl>

        {event.failure_reason && (
          <div className="mt-4 border border-term-amber/40 bg-term-amber/10 p-3 text-xs text-term-amber">
            <strong className="font-semibold">Failure reason:</strong>{" "}
            {event.failure_reason}
          </div>
        )}

        <SourceLinks payload={event.payload} />
      </header>

      <LLMSummaryPanel summary={event.llm_summary} />

      {predictions.length > 0 && (
        <section className="space-y-3">
          <h2 className="font-mono text-xs font-bold tracking-[0.2em] text-term-muted uppercase">
            <span className="text-term-amber">▮</span> Price action
            <span className="ml-2 text-term-dim normal-case font-normal tracking-normal">
              — windowed on event time, rebased to 100
            </span>
          </h2>
          <PriceChart
            tickers={chartTickersForEvent(event)}
            publishedAt={event.published_at}
            predictedAt={predictions[0].predicted_at}
          />
        </section>
      )}

      <section>
        <PredictionsHeader
          predictions={predictions}
          totalCost={totalCost}
        />
        <div className="mb-3">
          <PredictionLegend />
        </div>
        {predictions.length === 0 ? (
          <div className="border border-term-border bg-term-panel p-6 text-center text-sm text-term-muted">
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

      <details className="border border-term-border bg-term-panel">
        <summary className="cursor-pointer p-4 font-mono text-xs font-bold tracking-[0.2em] text-term-muted uppercase select-none flex items-center justify-between">
          <span>Raw payload (JSON)</span>
          <span className="text-[10px] text-term-dim tracking-normal">
            {Object.keys(event.payload).length} fields
          </span>
        </summary>
        <div className="px-4 pb-4">
          <pre className="overflow-x-auto border border-term-border bg-[#070b10] p-4 text-xs text-term-text/90 leading-relaxed">
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
    <div className="mb-3 flex items-center justify-between border-b border-term-border pb-2">
      <h2 className="font-mono text-xs font-bold tracking-[0.2em] text-term-muted uppercase">
        <span className="text-term-amber">▮</span> LLM predictions
        <span className="ml-2 text-term-dim">({predictions.length})</span>
      </h2>
      {predictions.length > 0 && (
        <div className="font-mono text-[11px] text-term-dim tabular-nums">
          TOTAL COST ${totalCost.toFixed(5)}
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
      <h3 className="font-mono text-[11px] font-bold text-term-dim uppercase tracking-widest mb-2">
        {heading}
        <span className="ml-2 normal-case font-normal">
          ({predictions.length})
        </span>
      </h3>
      {predictions.length === 0 ? (
        emptyHint ? (
          <p className="text-xs text-term-dim italic px-1">{emptyHint}</p>
        ) : null
      ) : (
        <ul className="space-y-2">
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

// External links pulled out of the event's source payload. Different event
// types use different field names — we render whichever ones are present so
// adding a new source-link key backend-side doesn't require a frontend change
// (e.g. a future TRANSCRIPT_URL would just need to be added to this map).
type LinkSpec = { key: string; label: string; nested?: string };
const SOURCE_LINK_SPECS: LinkSpec[] = [
  // Earnings: SEC 8-K item 2.02 press release matched at ingest time
  { key: "sec_filing", label: "SEC 8-K (press release)", nested: "primary_doc_url" },
  // Earnings: Yahoo Finance quote page
  { key: "yahoo_finance_url", label: "Yahoo Finance" },
  // SEC 8-K events: cover document
  { key: "primary_doc_url", label: "SEC filing" },
  // FOMC statement: Fed press release URL
  { key: "link", label: "Federal Reserve press release" },
  // Dot plot: SEP projections page
  { key: "url", label: "SEP projections page" },
];

function getLink(payload: Record<string, unknown>, spec: LinkSpec): string | null {
  const value = payload[spec.key];
  if (value === undefined || value === null) return null;
  if (spec.nested) {
    if (typeof value !== "object") return null;
    const inner = (value as Record<string, unknown>)[spec.nested];
    return typeof inner === "string" ? inner : null;
  }
  return typeof value === "string" ? value : null;
}

function SourceLinks({ payload }: { payload: Record<string, unknown> }) {
  const links = SOURCE_LINK_SPECS.map((spec) => {
    const url = getLink(payload, spec);
    return url ? { ...spec, url } : null;
  }).filter((l): l is LinkSpec & { url: string } => l !== null);

  if (links.length === 0) return null;

  return (
    <div className="mt-4 flex flex-wrap items-center gap-2">
      <span className="font-mono text-[10px] uppercase tracking-widest text-term-dim">
        Source links
      </span>
      {links.map((l) => (
        <a
          key={l.key}
          href={l.url}
          target="_blank"
          rel="noreferrer noopener"
          className="inline-flex items-center gap-1 border border-term-amber/40 bg-term-amber/10 px-2 py-0.5 font-mono text-[11px] font-medium text-term-amber hover:bg-term-amber/20 transition-colors"
        >
          {l.label}
          <span aria-hidden>↗</span>
        </a>
      ))}
    </div>
  );
}

// Pick which tickers to plot on the price chart for a given event.
// Company events (8-K, earnings) get [company, SPY, QQQ] — the subject ticker
// plus both index baselines. Macro events (CPI/NFP/GDP/FOMC/dot plot) get
// just the index baselines since there's no per-company subject.
const COMPANY_EVENT_TYPES = new Set(["8K_FILING", "EARNINGS_REPORT"]);
const INDEX_BASELINES = ["SPY", "QQQ"];

function chartTickersForEvent(event: {
  event_type: string;
  affected_tickers: string[];
}): string[] {
  const isCompany = COMPANY_EVENT_TYPES.has(event.event_type);
  const company = event.affected_tickers[0];
  if (isCompany && company && !INDEX_BASELINES.includes(company)) {
    return [company, ...INDEX_BASELINES];
  }
  return INDEX_BASELINES;
}

function StatusChip({ status }: { status: string }) {
  const styles: Record<string, string> = {
    FETCHED: "text-term-muted border-term-muted/40 bg-term-muted/10",
    ANALYZED: "text-src-fred border-src-fred/40 bg-src-fred/10",
    FAILED: "text-term-down border-term-down/40 bg-term-down/10",
    IGNORED: "text-term-dim border-term-dim/40 bg-term-dim/10",
  };
  return (
    <span
      className={`inline-flex items-center border px-1.5 py-px font-mono text-[10px] font-bold tracking-widest ${
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
      className="inline-flex items-center gap-1 font-mono text-xs tracking-wider text-term-muted hover:text-term-amber transition-colors"
    >
      ← BACK TO TIMELINE
    </Link>
  );
}

function Skeleton() {
  return (
    <div className="space-y-4">
      <div className="h-4 w-32 bg-term-panel2 animate-pulse" />
      <div className="h-44 border border-term-border bg-term-panel animate-pulse" />
      <div className="h-32 border border-term-border bg-term-panel animate-pulse" />
    </div>
  );
}

function ErrorBlock({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="space-y-4">
      <BackLink />
      <div className="border border-term-down/40 bg-term-down/10 p-4 text-sm text-term-down">
        <p className="font-semibold">{title}</p>
        <p className="mt-1 opacity-80">{detail}</p>
      </div>
    </div>
  );
}
