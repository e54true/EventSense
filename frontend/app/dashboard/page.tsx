"use client";

// Accuracy dashboard — aggregate alignment rates sliced by kind, source,
// window, ticker, and model. Each slice is its own /accuracy?... query;
// recharts renders the breakdown bars.

import { useQueries, useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { MacroContextPanel } from "@/components/MacroContextPanel";
import { PnlPanel } from "@/components/PnlPanel";
import { api } from "@/lib/api";
import type { EventSource, OutcomeWindow, PredictionKind } from "@/lib/types";

const SOURCES: EventSource[] = ["FRED", "SEC_EDGAR", "FOMC", "EARNINGS"];
// 1h dropped — see OutcomesTable.tsx / validator.py for rationale.
const WINDOWS: OutcomeWindow[] = ["24h", "7d"];
const KINDS: PredictionKind[] = ["MARKET", "COMPANY"];
// Models the router has used in production. Bars with no validated outcomes
// drop out automatically, so listing retired/new models here is harmless —
// gpt-4o-era bars double as the prompt-v2 cohort vs the gpt-5/v3 cohort.
const MODELS = ["gpt-4o-mini", "gpt-4o", "gpt-5-mini", "gpt-5"];

export default function DashboardPage() {
  const overall = useQuery({
    queryKey: ["accuracy.overall"],
    queryFn: () => api.getAccuracy(),
  });
  const indicators = useQuery({
    queryKey: ["indicators.latest"],
    queryFn: () => api.getIndicatorsLatest(),
  });

  return (
    <div className="space-y-8">
      <HeroSection
        rate={overall.data?.alignment_rate}
        total={overall.data?.total_outcomes}
        baselines={overall.data?.baselines}
      />

      <section>
        <SectionHeading
          title="Simulated P&L"
          hint="— $100 on every directional call, from the first event onward"
        />
        <PnlPanel />
      </section>

      <MacroContextPanel
        title="Current macro state"
        subtitle="latest indicator values + 30d change"
        indicators={indicators.data?.indicators ?? []}
      />

      <section>
        <SectionHeading
          title="Accuracy by kind"
          hint="— does the v2 analyzer call the market or the company better?"
        />
        <AccuracyBarChart
          dimension="kind"
          labels={KINDS}
          query={(value) => api.getAccuracy({ kind: value as PredictionKind })}
        />
      </section>

      <section>
        <SectionHeading title="Accuracy by source" />
        <AccuracyBarChart
          dimension="source"
          labels={SOURCES}
          query={(value) => api.getAccuracy({ source: value as EventSource })}
        />
      </section>

      <section>
        <SectionHeading title="Accuracy by window" />
        <AccuracyBarChart
          dimension="window"
          labels={WINDOWS}
          query={(value) => api.getAccuracy({ window: value as OutcomeWindow })}
        />
      </section>

      <section>
        <SectionHeading
          title="Accuracy by ticker"
          hint="— which names does the analyzer read best?"
        />
        <TickerAccuracyChart />
      </section>

      <section>
        <SectionHeading
          title="Accuracy by model"
          hint="— gpt-4o era (prompt v2) vs gpt-5 era (prompt v3)"
        />
        <AccuracyBarChart
          dimension="model"
          labels={MODELS}
          query={(value) => api.getAccuracy({ model: value })}
        />
      </section>
    </div>
  );
}

function TickerAccuracyChart() {
  // Company tickers come from /events/filters (whatever actually has events,
  // so newly-added watchlist names appear without a frontend change); SPY/QQQ
  // are prepended because MARKET predictions target them even though no
  // event lists them in affected_tickers.
  const filters = useQuery({
    queryKey: ["events.filters"],
    queryFn: () => api.getEventFilters(),
    staleTime: 5 * 60_000,
  });
  const tickers = ["SPY", "QQQ", ...(filters.data?.tickers ?? [])];
  return (
    <AccuracyBarChart
      dimension="ticker"
      labels={tickers}
      query={(value) => api.getAccuracy({ ticker: value })}
    />
  );
}

function SectionHeading({ title, hint }: { title: string; hint?: string }) {
  return (
    <h2 className="font-mono text-xs font-bold tracking-[0.2em] text-term-muted uppercase mb-3 border-b border-term-border pb-2">
      <span className="text-term-amber">▮</span> {title}
      {hint && (
        <span className="ml-2 text-term-dim font-normal normal-case tracking-normal">
          {hint}
        </span>
      )}
    </h2>
  );
}

function HeroSection({
  rate,
  total,
  baselines,
}: {
  rate: number | null | undefined;
  total: number | undefined;
  baselines?: {
    always_bullish: number | null;
    always_bearish: number | null;
    always_neutral: number | null;
  };
}) {
  const pct =
    rate === null || rate === undefined
      ? null
      : (rate * 100).toFixed(1);
  const fmtBaseline = (v: number | null | undefined) =>
    v === null || v === undefined ? "—" : `${(v * 100).toFixed(0)}%`;
  return (
    <section className="border border-term-border border-l-2 border-l-term-amber bg-term-panel p-6">
      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.3em] text-term-amber">
        ▮ Aggregate accuracy
      </p>
      <div className="mt-2 flex items-baseline gap-3">
        <span className="font-mono text-5xl font-bold tabular-nums text-term-text">
          {pct === null ? "N/A" : `${pct}%`}
        </span>
        <span className="font-mono text-xs text-term-muted tabular-nums">
          {total !== undefined && total > 0
            ? `ACROSS ${total} VALIDATED PREDICTIONS`
            : "NO VALIDATED PREDICTIONS YET"}
        </span>
      </div>
      {baselines && total !== undefined && total > 0 && (
        <p className="mt-2 font-mono text-[11px] text-term-dim tabular-nums">
          BASELINES — ALWAYS-BULLISH {fmtBaseline(baselines.always_bullish)} ·
          ALWAYS-BEARISH {fmtBaseline(baselines.always_bearish)} ·
          ALWAYS-NEUTRAL {fmtBaseline(baselines.always_neutral)}
        </p>
      )}
      <p className="mt-3 text-sm text-term-muted max-w-2xl leading-relaxed">
        Predictions are aligned when the raw ticker return matches the
        predicted direction beyond the window&apos;s neutral band —{" "}
        <code className="font-mono text-term-text/80">±0.5%</code> at 24h,{" "}
        <code className="font-mono text-term-text/80">±1.5%</code> at 7d.
        NEUTRAL aligns when the move stays inside the band.
      </p>
    </section>
  );
}

interface BarRow {
  label: string;
  rate: number;
  total: number;
}

// Above/below coin-flip gets its own colour so the bars read at a glance.
function barColor(rate: number): string {
  if (rate >= 50) return "#2fd980";
  return "#ff5c6c";
}

function AccuracyBarChart({
  dimension,
  labels,
  query,
}: {
  dimension: "source" | "window" | "kind" | "ticker" | "model";
  labels: string[];
  query: (
    value: string,
  ) => Promise<{ alignment_rate: number | null; total_outcomes: number }>;
}) {
  // One query per slice — they fan out in parallel, fail independently.
  // useQueries (not useQuery-in-a-loop) keeps the Rules of Hooks intact.
  const results = useQueries({
    queries: labels.map((label) => ({
      queryKey: ["accuracy", dimension, label],
      queryFn: () => query(label),
    })),
  });

  const data: BarRow[] = labels
    .map((label, i) => {
      const d = results[i].data;
      if (!d || d.alignment_rate === null) return null;
      return { label, rate: d.alignment_rate * 100, total: d.total_outcomes };
    })
    .filter((r): r is BarRow => r !== null);

  if (data.length === 0) {
    return (
      <div className="border border-term-border bg-term-panel p-6 text-center text-sm text-term-muted">
        Not enough validated predictions for this breakdown yet.
      </div>
    );
  }

  return (
    <div className="border border-term-border bg-term-panel p-4">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1d2938" />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 12, fill: "#7d8fa5", fontFamily: "var(--font-geist-mono)" }}
            stroke="#2b3b50"
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fontSize: 11, fill: "#7d8fa5", fontFamily: "var(--font-geist-mono)" }}
            stroke="#2b3b50"
            tickFormatter={(v: number) => `${v}%`}
          />
          <Tooltip
            cursor={{ fill: "rgba(255, 176, 46, 0.06)" }}
            // Recharts' Formatter typing is loose; ValueType can be number/string/array,
            // but we know our dataKey="rate" is always a number. Cast accordingly.
            formatter={(value, _name, item) => {
              const num = typeof value === "number" ? value : Number(value);
              const total = (item?.payload as BarRow)?.total ?? 0;
              return [`${num.toFixed(1)}% (n=${total})`, "Alignment rate"];
            }}
            contentStyle={{
              fontSize: 12,
              fontFamily: "var(--font-geist-mono)",
              background: "#0d141d",
              border: "1px solid #2b3b50",
              borderRadius: 0,
              color: "#d6e0ec",
            }}
            labelStyle={{ color: "#7d8fa5" }}
            // Bars get their colour from <Cell>, so recharts can't derive an
            // item text colour and falls back to black — unreadable on dark.
            itemStyle={{ color: "#d6e0ec" }}
          />
          <Bar dataKey="rate" isAnimationActive={false}>
            {data.map((row) => (
              <Cell key={row.label} fill={barColor(row.rate)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
