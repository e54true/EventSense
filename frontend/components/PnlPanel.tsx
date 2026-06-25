"use client";

// Simulated trading P&L — "if I had put $100 on every directional call the
// system made, from the first event onward, where would I be?"
//
// Backend does all the math (GET /api/v1/pnl, computed live from validated
// outcomes); this panel renders: a headline P&L hero, the cumulative equity
// curve vs an always-long-SPY benchmark, per-window/best-worst stat cards,
// and P&L breakdown tables by model / ticker / confidence.

import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
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
import type { EquityPoint, GroupPnl, PnlTrade } from "@/lib/types";

const STAKE_USD = 100;

function money(v: number): string {
  const sign = v > 0 ? "+" : v < 0 ? "-" : "";
  return `${sign}$${Math.abs(v).toFixed(2)}`;
}

function pct(v: number | null): string {
  if (v === null) return "—";
  const scaled = v * 100;
  return `${scaled > 0 ? "+" : ""}${scaled.toFixed(2)}%`;
}

function pnlColor(v: number): string {
  if (v > 0) return "text-term-up";
  if (v < 0) return "text-term-down";
  return "text-term-muted";
}

interface CurvePoint {
  ts: number;
  strategy: number;
  spy: number;
  ticker: string;
  window: string;
  direction: string;
  tradePnl: number;
}

export function PnlPanel() {
  const pnl = useQuery({
    queryKey: ["pnl", STAKE_USD],
    queryFn: () => api.getPnl({ stake_usd: STAKE_USD }),
    // New outcomes appear whenever the validator scores a fresh event; keep
    // the simulation live while the dashboard is open.
    refetchInterval: 60_000,
  });

  if (pnl.isLoading) {
    return <div className="h-96 border border-term-border bg-term-panel animate-pulse" />;
  }
  if (pnl.isError || !pnl.data) {
    return (
      <div className="border border-term-border bg-term-panel p-6 text-center text-sm text-term-muted">
        Failed to load the P&L simulation.
      </div>
    );
  }

  const d = pnl.data;
  if (d.total.trades === 0) {
    return (
      <div className="border border-term-border bg-term-panel p-6 text-center text-sm text-term-muted">
        No validated directional calls to simulate yet.
      </div>
    );
  }

  const total = d.total;
  const edge = total.pnl_usd - total.spy_pnl_usd;
  const accent = total.pnl_usd >= 0 ? "border-l-term-up" : "border-l-term-down";
  const windows = new Map(d.by_window.map((g) => [g.label, g]));

  const curve: CurvePoint[] = d.equity_curve.map((p: EquityPoint) => ({
    ts: new Date(p.t).getTime(),
    strategy: p.pnl_usd,
    spy: p.spy_pnl_usd,
    ticker: p.ticker,
    window: p.window,
    direction: p.direction,
    tradePnl: p.trade_pnl_usd,
  }));

  return (
    <div className="space-y-4">
      {/* Headline */}
      <div className={`border border-term-border border-l-2 ${accent} bg-term-panel p-6`}>
        <p className="font-mono text-[10px] font-bold uppercase tracking-[0.3em] text-term-amber">
          ▮ Following every call · ${STAKE_USD} per trade
        </p>
        <div className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span className={`font-mono text-5xl font-bold tabular-nums ${pnlColor(total.pnl_usd)}`}>
            {money(total.pnl_usd)}
          </span>
          <span className={`font-mono text-2xl font-bold tabular-nums ${pnlColor(total.pnl_usd)}`}>
            {pct(total.return_pct)}
          </span>
          <span className="font-mono text-xs text-term-muted tabular-nums">
            ON ${total.invested_usd.toLocaleString()} DEPLOYED · {total.trades} TRADES ·{" "}
            {total.neutral_skipped} NEUTRAL SKIPPED
          </span>
        </div>
        <p className="mt-2 font-mono text-[11px] text-term-dim tabular-nums">
          VS ALWAYS-LONG-SPY SAME STAKES{" "}
          <span className={pnlColor(total.spy_pnl_usd)}>
            {money(total.spy_pnl_usd)} ({pct(total.spy_return_pct)})
          </span>{" "}
          · MODEL EDGE{" "}
          <span className={pnlColor(edge)}>{money(edge)}</span> · CONFIDENCE-WEIGHTED STAKES{" "}
          <span className={pnlColor(d.weighted.pnl_usd)}>
            {money(d.weighted.pnl_usd)} ({pct(d.weighted.return_pct)})
          </span>
        </p>
        {d.period_start && d.period_end && (
          <p className="mt-1 font-mono text-[11px] text-term-dim tabular-nums">
            {format(new Date(d.period_start), "PP")} → {format(new Date(d.period_end), "PP")} ·
            UPDATES AS NEW OUTCOMES VALIDATE
          </p>
        )}
      </div>

      {/* Equity curve */}
      <div className="border border-term-border bg-term-panel p-4">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="font-mono text-xs font-bold tracking-wider text-term-text">
            CUMULATIVE P&L
            <span className="ml-2 text-term-dim font-normal">
              STRATEGY VS ALWAYS-LONG-SPY · ONE STEP PER CLOSED TRADE
            </span>
          </h3>
          <span className="font-mono text-[11px] text-term-dim tabular-nums">
            {curve.length} trades
          </span>
        </div>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={curve} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1d2938" />
            <XAxis
              dataKey="ts"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              tickFormatter={(ts: number) => format(new Date(ts), "MMM d")}
              tick={{ fontSize: 11, fill: "#7d8fa5", fontFamily: "var(--font-geist-mono)" }}
              stroke="#2b3b50"
              minTickGap={30}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#7d8fa5", fontFamily: "var(--font-geist-mono)" }}
              stroke="#2b3b50"
              tickFormatter={(v: number) => `$${v.toFixed(0)}`}
            />
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const p = payload[0].payload as CurvePoint;
                const arrow = p.direction === "BULLISH" ? "▲ LONG" : "▼ SHORT";
                return (
                  <div
                    className="border border-term-border2 bg-term-panel p-2 font-mono text-xs"
                    style={{ background: "#0d141d" }}
                  >
                    <div className="text-term-muted">{format(new Date(p.ts), "PPp")}</div>
                    <div className="mt-1 text-term-text">
                      {p.ticker} {p.window} {arrow}{" "}
                      <span className={pnlColor(p.tradePnl)}>{money(p.tradePnl)}</span>
                    </div>
                    <div className="mt-1 tabular-nums">
                      <span className="text-term-amber">STRATEGY {money(p.strategy)}</span>
                      <span className="ml-3 text-term-muted">SPY {money(p.spy)}</span>
                    </div>
                  </div>
                );
              }}
            />
            <ReferenceLine y={0} stroke="#2b3b50" />
            <Line
              type="monotone"
              dataKey="strategy"
              name="STRATEGY"
              stroke="#ffb02e"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="spy"
              name="ALWAYS-LONG SPY"
              stroke="#7d8fa5"
              strokeWidth={1.5}
              strokeDasharray="4 2"
              dot={false}
              activeDot={{ r: 4 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
        <p className="mt-1 font-mono text-[10px] text-term-dim">
          <span className="text-term-amber">━ STRATEGY</span>
          <span className="ml-3">┄ ALWAYS-LONG SPY (same stakes)</span>
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <WindowCard label="24H STRATEGY" group={windows.get("24h")} />
        <WindowCard label="7D STRATEGY" group={windows.get("7d")} />
        <div className="border border-term-border border-l-2 border-l-term-amber bg-term-panel p-3">
          <div className="font-mono text-[10px] font-bold tracking-widest uppercase text-term-amber">
            Win rate
          </div>
          <div className="mt-1 flex items-baseline gap-1.5">
            <span className="font-mono text-2xl font-bold tabular-nums text-term-text">
              {total.win_rate === null ? "—" : `${(total.win_rate * 100).toFixed(0)}%`}
            </span>
            <span className="font-mono text-[10px] text-term-dim tabular-nums">
              {total.wins}W / {total.losses}L
            </span>
          </div>
        </div>
        <TradeCard best={d.best_trade} worst={d.worst_trade} />
      </div>

      {/* Risk metrics */}
      <div className="grid grid-cols-2 gap-3">
        <div className={`border border-term-border border-l-2 bg-term-panel p-3 ${
          (total.sharpe_annualized ?? total.sharpe_ratio ?? 0) > 0 ? "border-l-term-up" : "border-l-term-down"
        }`}>
          <div className="font-mono text-[10px] font-bold tracking-widest uppercase text-term-amber">
            Sharpe ratio (per-trade)
          </div>
          <div className="mt-1 flex items-baseline gap-1.5">
            <span className={`font-mono text-2xl font-bold tabular-nums ${
              total.sharpe_ratio === null ? "text-term-muted"
              : total.sharpe_ratio > 0 ? "text-term-up" : "text-term-down"
            }`}>
              {total.sharpe_ratio !== null ? total.sharpe_ratio.toFixed(2) : "—"}
            </span>
            <span className="font-mono text-[10px] text-term-dim tabular-nums">
              per-trade · annualized {total.sharpe_annualized !== null ? total.sharpe_annualized.toFixed(1) : "—"}
            </span>
          </div>
        </div>
        <div className="border border-term-border border-l-2 border-l-term-down bg-term-panel p-3">
          <div className="font-mono text-[10px] font-bold tracking-widest uppercase text-term-dim">
            Max drawdown
          </div>
          <div className="mt-1 flex items-baseline gap-1.5">
            <span className={`font-mono text-2xl font-bold tabular-nums ${total.mdd_pct ? "text-term-down" : "text-term-muted"}`}>
              {total.mdd_pct !== null ? `${(total.mdd_pct * 100).toFixed(1)}%` : "0.0%"}
            </span>
            <span className="font-mono text-[10px] text-term-dim tabular-nums">
              {total.mdd_usd > 0 ? `-$${total.mdd_usd.toFixed(2)} of peak` : "no drawdown"}
            </span>
          </div>
        </div>
      </div>

      {/* Breakdown tables */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <PnlTable title="P&L BY MODEL" rows={d.by_model} />
        <PnlTable title="P&L BY TICKER" rows={d.by_ticker} />
        <PnlTable
          title="P&L BY CONFIDENCE"
          rows={d.by_confidence.filter((g) => g.trades > 0)}
        />
        <div className="border border-term-border bg-term-panel p-4">
          <div className="font-mono text-[10px] font-bold tracking-widest uppercase text-term-dim">
            How this is computed
          </div>
          <p className="mt-2 text-xs leading-relaxed text-term-muted">
            Every BULLISH call goes long ${STAKE_USD}, every BEARISH call goes short ${STAKE_USD}{" "}
            (pure notional inversion — no borrow fees, slippage, or commissions), NEUTRAL stands
            aside. Entry is the prediction&apos;s anchor price, exit is the validated 24h / 7d
            window price, so each trade&apos;s P&L is ±${STAKE_USD} × the stored window return;
            7d trades follow the dedicated 7d call. Trades overlap, so return % is total P&L ÷
            total deployed capital rather than a compounding bankroll. The SPY line answers
            &quot;what if I&apos;d bought the index with the same stakes instead?&quot;
          </p>
        </div>
      </div>
    </div>
  );
}

function WindowCard({ label, group }: { label: string; group?: GroupPnl }) {
  if (!group || group.trades === 0) {
    return (
      <div className="border border-term-border bg-term-panel p-3">
        <div className="font-mono text-[10px] font-bold tracking-widest uppercase text-term-dim">
          {label}
        </div>
        <div className="mt-1 font-mono text-2xl font-bold text-term-muted">—</div>
      </div>
    );
  }
  return (
    <div
      className={`border border-term-border border-l-2 bg-term-panel p-3 ${
        group.pnl_usd >= 0 ? "border-l-term-up" : "border-l-term-down"
      }`}
    >
      <div className="font-mono text-[10px] font-bold tracking-widest uppercase text-term-dim">
        {label}
      </div>
      <div className="mt-1 flex items-baseline gap-1.5">
        <span className={`font-mono text-2xl font-bold tabular-nums ${pnlColor(group.pnl_usd)}`}>
          {money(group.pnl_usd)}
        </span>
        <span className="font-mono text-[10px] text-term-dim tabular-nums">
          {pct(group.return_pct)} · n={group.trades}
        </span>
      </div>
    </div>
  );
}

function TradeCard({ best, worst }: { best: PnlTrade | null; worst: PnlTrade | null }) {
  return (
    <div className="border border-term-border bg-term-panel p-3">
      <div className="font-mono text-[10px] font-bold tracking-widest uppercase text-term-dim">
        Best / worst trade
      </div>
      <div className="mt-1 space-y-0.5 font-mono text-[11px] tabular-nums">
        {best && (
          <div className="text-term-text">
            <span className="text-term-up">{money(best.pnl_usd)}</span> {best.ticker}{" "}
            {best.window} {best.direction === "BULLISH" ? "▲" : "▼"}{" "}
            <span className="text-term-dim">{format(new Date(best.entered_at), "MMM d")}</span>
          </div>
        )}
        {worst && (
          <div className="text-term-text">
            <span className="text-term-down">{money(worst.pnl_usd)}</span> {worst.ticker}{" "}
            {worst.window} {worst.direction === "BULLISH" ? "▲" : "▼"}{" "}
            <span className="text-term-dim">{format(new Date(worst.entered_at), "MMM d")}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function PnlTable({ title, rows }: { title: string; rows: GroupPnl[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="border border-term-border bg-term-panel p-4">
      <div className="font-mono text-[10px] font-bold tracking-widest uppercase text-term-dim">
        {title}
      </div>
      <table className="mt-2 w-full font-mono text-xs tabular-nums">
        <thead>
          <tr className="border-b border-term-border text-left text-[10px] tracking-widest text-term-dim">
            <th className="py-1 pr-2 font-normal">LABEL</th>
            <th className="py-1 pr-2 text-right font-normal">TRADES</th>
            <th className="py-1 pr-2 text-right font-normal">P&L</th>
            <th className="py-1 pr-2 text-right font-normal">RET</th>
            <th className="py-1 text-right font-normal">WIN</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((g) => (
            <tr key={g.label} className="border-b border-term-border/40 last:border-0">
              <td className="py-1 pr-2 text-term-text">{g.label}</td>
              <td className="py-1 pr-2 text-right text-term-muted">{g.trades}</td>
              <td className={`py-1 pr-2 text-right ${pnlColor(g.pnl_usd)}`}>{money(g.pnl_usd)}</td>
              <td className={`py-1 pr-2 text-right ${pnlColor(g.pnl_usd)}`}>
                {pct(g.return_pct)}
              </td>
              <td className="py-1 text-right text-term-muted">
                {g.win_rate === null ? "—" : `${(g.win_rate * 100).toFixed(0)}%`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
