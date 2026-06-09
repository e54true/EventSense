"use client";

// Price chart showing ticker vs SPY around the event's published_at.
//
// We anchor the chart on `publishedAt` (when the market actually saw the
// event) rather than `predictedAt` (when the analyzer happened to run). For
// freshly-ingested events these are within seconds of each other, but for
// historical backfill (earnings reports from N months ago surfaced by today's
// adapter run) they can differ by weeks — and the market reaction happened
// around publishedAt, not predictedAt.
//
// Both series are *normalized to 100 at the first data point* so they share
// an axis regardless of absolute price. publishedAt is marked with the primary
// vertical ReferenceLine; predictedAt is marked separately when it differs
// from publishedAt by more than a day.

import { useQuery } from "@tanstack/react-query";
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
  ticker: string;
  publishedAt: string; // ISO 8601 — event time, primary anchor
  predictedAt: string; // ISO 8601 — analyzer run time, secondary marker
}

// Pull a window centered on the event: 1 day before through 7 days after.
// 30-day cap on the backend means we have room to expand later.
const BEFORE_HOURS = 24;
const AFTER_HOURS = 24 * 7;
// If predicted_at lags published_at by more than this, draw a second
// reference line so the user can see "the analyzer was late to this event".
const PREDICTED_LINE_GAP_THRESHOLD_HOURS = 24;

function isoOffset(from: Date, hours: number): string {
  return new Date(from.getTime() + hours * 3600_000).toISOString();
}

interface MergedPoint {
  ts: number; // ms epoch — Recharts handles ints better than strings on the x-axis
  tickerNormalized?: number;
  spyNormalized?: number;
}

// Resample to one point per calendar day (UTC). The backfill mixes daily
// closes (1pt/day for old data) with intraday minute bars (1pt/min for last
// 5 days) — plotting both together makes the line look smooth then suddenly
// jagged. For an 8-day window the daily-close resolution is what the user
// actually wants to see ("what was each day's close worth?").
function resampleDaily(points: PricePoint[]): PricePoint[] {
  if (points.length === 0) return points;
  // Keep the last sample of each UTC date. We iterate in order, overwriting
  // earlier samples for the same day so the final map holds end-of-day prices.
  const byDay = new Map<string, PricePoint>();
  for (const p of points) {
    const day = p.snapshot_at.slice(0, 10); // YYYY-MM-DD
    byDay.set(day, p);
  }
  return Array.from(byDay.values()).sort(
    (a, b) =>
      new Date(a.snapshot_at).getTime() - new Date(b.snapshot_at).getTime(),
  );
}

function rebase(points: PricePoint[]): Map<number, number> {
  // Find the price closest to (but not after) the first sample, then divide
  // every later price by it × 100 so the series starts at 100.
  if (points.length === 0) return new Map();
  const base = Number(points[0].price);
  const out = new Map<number, number>();
  for (const p of points) {
    out.set(new Date(p.snapshot_at).getTime(), (Number(p.price) / base) * 100);
  }
  return out;
}

export function PriceChart({ ticker, publishedAt, predictedAt }: Props) {
  const publishedDate = new Date(publishedAt);
  const predictedDate = new Date(predictedAt);
  const fromAt = isoOffset(publishedDate, -BEFORE_HOURS);
  const toAt = isoOffset(publishedDate, AFTER_HOURS);
  const predictedDriftHours =
    (predictedDate.getTime() - publishedDate.getTime()) / 3600_000;
  const showPredictedLine =
    Math.abs(predictedDriftHours) > PREDICTED_LINE_GAP_THRESHOLD_HOURS;

  // Two parallel queries — Recharts is happy with whichever arrives first
  // (we render dots/lines incrementally as each finishes).
  const tickerQuery = useQuery({
    queryKey: ["prices.range", ticker, fromAt, toAt],
    queryFn: () => api.getPriceRange(ticker, fromAt, toAt),
  });

  const spyQuery = useQuery({
    queryKey: ["prices.range", "SPY", fromAt, toAt],
    queryFn: () => api.getPriceRange("SPY", fromAt, toAt),
    // SPY is shared across most predictions — bump cache time so opening
    // multiple event detail pages doesn't re-fetch the same window.
    staleTime: 5 * 60_000,
  });

  if (tickerQuery.isLoading || spyQuery.isLoading) {
    return (
      <div className="h-72 rounded-xl border border-slate-200 bg-white animate-pulse" />
    );
  }

  const tickerPoints = resampleDaily(tickerQuery.data?.points ?? []);
  const spyPoints = resampleDaily(spyQuery.data?.points ?? []);

  if (tickerPoints.length === 0 && spyPoints.length === 0) {
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

  // Merge by timestamp into a single array (Recharts wants one row per x-tick).
  const tickerMap = rebase(tickerPoints);
  const spyMap = rebase(spyPoints);
  const allTs = new Set<number>([...tickerMap.keys(), ...spyMap.keys()]);
  const data: MergedPoint[] = Array.from(allTs)
    .sort((a, b) => a - b)
    .map((ts) => ({
      ts,
      tickerNormalized: tickerMap.get(ts),
      spyNormalized: spyMap.get(ts),
    }));

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-900">
          {ticker} vs SPY · daily closes, rebased to 100 at event
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
              return [num.toFixed(2), name === "tickerNormalized" ? ticker : "SPY"];
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
            formatter={(value: string) =>
              value === "tickerNormalized" ? ticker : "SPY"
            }
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
          <Line
            type="monotone"
            dataKey="tickerNormalized"
            stroke="#0f172a"
            strokeWidth={2}
            dot={{ r: 3, fill: "#0f172a" }}
            activeDot={{ r: 5 }}
            connectNulls
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="spyNormalized"
            stroke="#94a3b8"
            strokeWidth={1.5}
            dot={{ r: 2, fill: "#94a3b8" }}
            strokeDasharray="4 2"
            connectNulls
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
