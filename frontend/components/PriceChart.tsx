"use client";

// Price chart showing N tickers around the event's published_at, each
// rebased to 100 at the start of the window so the lines share an axis
// regardless of absolute price.
//
// Caller decides which tickers — typically:
//   - company event (8-K, earnings):  [companyTicker, SPY, QQQ]
//   - macro event (CPI/NFP/GDP/FOMC): [SPY, QQQ]
//
// publishedAt is the primary anchor (event time → market reaction window).
// predictedAt is marked separately only when it differs from publishedAt
// by more than a day (historical backfill case where the analyzer ran
// long after the event).

import { useQueries } from "@tanstack/react-query";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { format } from "date-fns";

import { api } from "@/lib/api";
import type { PricePoint } from "@/lib/types";

interface Props {
  tickers: string[];
  publishedAt: string;
  predictedAt: string;
}

const BEFORE_HOURS = 24;
const AFTER_HOURS = 24 * 7;
const PREDICTED_LINE_GAP_THRESHOLD_HOURS = 24;

// Stable colour per ticker so the same line means the same thing across
// different event pages. SPY/QQQ stay muted (baselines); company tickers
// get a vivid colour.
const LINE_STYLE: Record<string, { stroke: string; strokeWidth: number; strokeDasharray?: string }> =
  {
    SPY: { stroke: "#94a3b8", strokeWidth: 1.5, strokeDasharray: "4 2" },
    QQQ: { stroke: "#f59e0b", strokeWidth: 1.5, strokeDasharray: "6 3" },
  };
const COMPANY_STYLE = { stroke: "#0f172a", strokeWidth: 2 };

function styleFor(ticker: string) {
  return LINE_STYLE[ticker] ?? COMPANY_STYLE;
}

function isoOffset(from: Date, hours: number): string {
  return new Date(from.getTime() + hours * 3600_000).toISOString();
}

function resampleDaily(points: PricePoint[]): PricePoint[] {
  if (points.length === 0) return points;
  const byDay = new Map<string, PricePoint>();
  for (const p of points) {
    byDay.set(p.snapshot_at.slice(0, 10), p);
  }
  return Array.from(byDay.values()).sort(
    (a, b) => new Date(a.snapshot_at).getTime() - new Date(b.snapshot_at).getTime(),
  );
}

function rebase(points: PricePoint[]): Map<number, number> {
  if (points.length === 0) return new Map();
  const base = Number(points[0].price);
  const out = new Map<number, number>();
  for (const p of points) {
    out.set(new Date(p.snapshot_at).getTime(), (Number(p.price) / base) * 100);
  }
  return out;
}

interface MergedPoint {
  ts: number;
  [tickerKey: string]: number | undefined;
}

export function PriceChart({ tickers, publishedAt, predictedAt }: Props) {
  const publishedDate = new Date(publishedAt);
  const predictedDate = new Date(predictedAt);
  const fromAt = isoOffset(publishedDate, -BEFORE_HOURS);
  const toAt = isoOffset(publishedDate, AFTER_HOURS);
  const predictedDriftHours =
    (predictedDate.getTime() - publishedDate.getTime()) / 3600_000;
  const showPredictedLine =
    Math.abs(predictedDriftHours) > PREDICTED_LINE_GAP_THRESHOLD_HOURS;

  // De-dupe in case caller passes overlapping tickers (e.g. company == SPY edge case).
  const uniqueTickers = Array.from(new Set(tickers));

  const queries = useQueries({
    queries: uniqueTickers.map((ticker) => ({
      queryKey: ["prices.range", ticker, fromAt, toAt],
      queryFn: () => api.getPriceRange(ticker, fromAt, toAt),
      staleTime: 5 * 60_000,
    })),
  });

  const anyLoading = queries.some((q) => q.isLoading);
  if (anyLoading) {
    return <div className="h-72 rounded-xl border border-slate-200 bg-white animate-pulse" />;
  }

  // Per-ticker daily resample + rebase to 100 at first sample.
  const perTickerMap = new Map<string, Map<number, number>>();
  for (let i = 0; i < uniqueTickers.length; i++) {
    const ticker = uniqueTickers[i];
    const points = resampleDaily(queries[i].data?.points ?? []);
    perTickerMap.set(ticker, rebase(points));
  }

  // Union of all timestamps across all tickers.
  const allTs = new Set<number>();
  for (const m of perTickerMap.values()) {
    for (const ts of m.keys()) allTs.add(ts);
  }

  if (allTs.size === 0) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-center text-sm text-slate-600">
        No price data for {format(publishedDate, "PP")} ± {AFTER_HOURS / 24}d.
        <br />
        <span className="text-xs text-slate-500">
          This usually means the event predates the system&apos;s price-snapshot
          history. Running the price backfill against this window would fill
          the chart.
        </span>
      </div>
    );
  }

  const data: MergedPoint[] = Array.from(allTs)
    .sort((a, b) => a - b)
    .map((ts) => {
      const row: MergedPoint = { ts };
      for (const [ticker, m] of perTickerMap) {
        row[ticker] = m.get(ts);
      }
      return row;
    });

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-900">
          {uniqueTickers.join(" / ")} · daily closes, rebased to 100 at event
        </h3>
        <span className="text-xs text-slate-500 tabular-nums">
          {data.length} days
        </span>
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis
            dataKey="ts"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            tickFormatter={(ts: number) => format(new Date(ts), "MMM d")}
            tick={{ fontSize: 11, fill: "#64748b" }}
            stroke="#94a3b8"
            minTickGap={30}
          />
          <YAxis
            domain={["dataMin - 0.5", "dataMax + 0.5"]}
            tick={{ fontSize: 11, fill: "#64748b" }}
            stroke="#94a3b8"
            tickFormatter={(v: number) => v.toFixed(1)}
          />
          <Tooltip
            labelFormatter={(ts) => format(new Date(Number(ts)), "PPpp")}
            formatter={(value, name) => {
              const num = typeof value === "number" ? value : Number(value);
              return [num.toFixed(2), name];
            }}
            contentStyle={{
              fontSize: 12,
              border: "1px solid #e2e8f0",
              borderRadius: 8,
            }}
          />
          <Legend
            iconType="line"
            wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
          />
          <ReferenceLine
            x={publishedDate.getTime()}
            stroke="#6366f1"
            strokeDasharray="4 4"
            label={{
              value: "event",
              position: "top",
              fill: "#6366f1",
              fontSize: 11,
            }}
          />
          {showPredictedLine && (
            <ReferenceLine
              x={predictedDate.getTime()}
              stroke="#94a3b8"
              strokeDasharray="2 4"
              label={{
                value: "analyzed",
                position: "top",
                fill: "#64748b",
                fontSize: 10,
              }}
            />
          )}
          {uniqueTickers.map((ticker) => {
            const s = styleFor(ticker);
            return (
              <Line
                key={ticker}
                type="monotone"
                dataKey={ticker}
                name={ticker}
                stroke={s.stroke}
                strokeWidth={s.strokeWidth}
                strokeDasharray={s.strokeDasharray}
                dot={{ r: 2, fill: s.stroke }}
                activeDot={{ r: 5 }}
                connectNulls
                isAnimationActive={false}
              />
            );
          })}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
