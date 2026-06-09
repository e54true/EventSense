"use client";

// Accuracy dashboard — aggregate alignment rates sliced by source, window,
// and model. Each slice is its own /accuracy?... query; recharts renders the
// breakdown bars.

import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { MacroContextPanel } from "@/components/MacroContextPanel";
import { api } from "@/lib/api";
import type { EventSource, OutcomeWindow, PredictionKind } from "@/lib/types";

const SOURCES: EventSource[] = ["FRED", "SEC_EDGAR", "FOMC", "EARNINGS"];
// 1h dropped — see OutcomesTable.tsx / validator.py for rationale.
const WINDOWS: OutcomeWindow[] = ["24h", "7d"];
const KINDS: PredictionKind[] = ["MARKET", "COMPANY"];

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
      <HeroSection rate={overall.data?.alignment_rate} total={overall.data?.total_outcomes} />

      <MacroContextPanel
        title="Current macro state"
        subtitle="latest indicator values + 30d change"
        indicators={indicators.data?.indicators ?? []}
      />

      <section>
        <h2 className="text-sm font-semibold text-slate-900 uppercase tracking-wide mb-3">
          Accuracy by kind
          <span className="ml-2 text-slate-400 font-normal normal-case">
            — does the v2 analyzer call the market or the company better?
          </span>
        </h2>
        <AccuracyBarChart
          dimension="kind"
          labels={KINDS}
          query={(value) => api.getAccuracy({ kind: value as PredictionKind })}
        />
      </section>

      <section>
        <h2 className="text-sm font-semibold text-slate-900 uppercase tracking-wide mb-3">
          Accuracy by source
        </h2>
        <AccuracyBarChart
          dimension="source"
          labels={SOURCES}
          query={(value) => api.getAccuracy({ source: value as EventSource })}
        />
      </section>

      <section>
        <h2 className="text-sm font-semibold text-slate-900 uppercase tracking-wide mb-3">
          Accuracy by window
        </h2>
        <AccuracyBarChart
          dimension="window"
          labels={WINDOWS}
          query={(value) => api.getAccuracy({ window: value as OutcomeWindow })}
        />
      </section>
    </div>
  );
}

function HeroSection({
  rate,
  total,
}: {
  rate: number | null | undefined;
  total: number | undefined;
}) {
  const pct =
    rate === null || rate === undefined
      ? null
      : (rate * 100).toFixed(1);
  return (
    <section className="rounded-2xl border border-slate-200/80 bg-gradient-to-br from-indigo-50 via-white to-pink-50 p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-wider text-indigo-700">
        Aggregate accuracy
      </p>
      <div className="mt-2 flex items-baseline gap-3">
        <span className="text-5xl font-bold tabular-nums text-slate-900">
          {pct === null ? "N/A" : `${pct}%`}
        </span>
        <span className="text-sm text-slate-600 tabular-nums">
          {total !== undefined && total > 0
            ? `across ${total} validated predictions`
            : "no validated predictions yet"}
        </span>
      </div>
      <p className="mt-3 text-sm text-slate-600 max-w-2xl">
        Predictions are aligned when the sign of <code className="font-mono">excess_return</code>{" "}
        (ticker minus SPY) matches the predicted direction. NEUTRAL aligns when{" "}
        <code className="font-mono">|excess|</code> stays under 0.5%.
      </p>
    </section>
  );
}

interface BarRow {
  label: string;
  rate: number;
  total: number;
}

function AccuracyBarChart({
  dimension,
  labels,
  query,
}: {
  dimension: "source" | "window" | "kind";
  labels: string[];
  query: (
    value: string,
  ) => Promise<{ alignment_rate: number | null; total_outcomes: number }>;
}) {
  // One useQuery per slice — they fan out in parallel, fail independently.
  const results = labels.map((label) =>
    // eslint-disable-next-line react-hooks/rules-of-hooks
    useQuery({
      queryKey: ["accuracy", dimension, label],
      queryFn: () => query(label),
    }),
  );

  const data: BarRow[] = labels
    .map((label, i) => {
      const d = results[i].data;
      if (!d || d.alignment_rate === null) return null;
      return { label, rate: d.alignment_rate * 100, total: d.total_outcomes };
    })
    .filter((r): r is BarRow => r !== null);

  if (data.length === 0) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-center text-sm text-slate-500">
        Not enough validated predictions for this breakdown yet.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 12, fill: "#475569" }}
            stroke="#94a3b8"
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fontSize: 11, fill: "#64748b" }}
            stroke="#94a3b8"
            tickFormatter={(v: number) => `${v}%`}
          />
          <Tooltip
            // Recharts' Formatter typing is loose; ValueType can be number/string/array,
            // but we know our dataKey="rate" is always a number. Cast accordingly.
            formatter={(value, _name, item) => {
              const num = typeof value === "number" ? value : Number(value);
              const total = (item?.payload as BarRow)?.total ?? 0;
              return [`${num.toFixed(1)}% (n=${total})`, "Alignment rate"];
            }}
            contentStyle={{
              fontSize: 12,
              border: "1px solid #e2e8f0",
              borderRadius: 8,
            }}
          />
          <Bar
            dataKey="rate"
            fill="#6366f1"
            radius={[4, 4, 0, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
