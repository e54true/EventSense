// Renders the 1h / 24h / 7d outcomes for one prediction.
//
// Three slots fixed in column order so users can scan rows of predictions
// and see the same time horizons line up. Empty slot = "not validated yet"
// (window hasn't elapsed or price data not available).

import type { OutcomeRead, OutcomeWindow } from "@/lib/types";
import { cn } from "@/lib/utils";

const WINDOWS: OutcomeWindow[] = ["1h", "24h", "7d"];

function formatPct(v: number): string {
  const sign = v > 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(2)}%`;
}

function returnColor(v: number): string {
  if (v > 0) return "text-green-700";
  if (v < 0) return "text-rose-700";
  return "text-slate-500";
}

export function OutcomesTable({ outcomes }: { outcomes: OutcomeRead[] }) {
  const byWindow = new Map(outcomes.map((o) => [o.window, o]));

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/50 overflow-hidden">
      <table className="w-full text-xs">
        <thead className="bg-slate-100/80">
          <tr className="text-left text-[10px] uppercase tracking-wider text-slate-500">
            <th className="px-3 py-2 font-medium">Window</th>
            <th className="px-3 py-2 font-medium text-right">Ticker</th>
            <th className="px-3 py-2 font-medium text-right">SPY</th>
            <th className="px-3 py-2 font-medium text-right">Excess</th>
            <th className="px-3 py-2 font-medium text-center">Aligned</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200/80">
          {WINDOWS.map((w) => {
            const o = byWindow.get(w);
            if (!o) {
              return (
                <tr key={w} className="text-slate-400">
                  <td className="px-3 py-2 font-mono font-semibold">{w}</td>
                  <td colSpan={4} className="px-3 py-2 italic">
                    pending validation
                  </td>
                </tr>
              );
            }
            return (
              <tr key={w} className="text-slate-700">
                <td className="px-3 py-2 font-mono font-semibold text-slate-900">
                  {w}
                </td>
                <td
                  className={cn(
                    "px-3 py-2 text-right tabular-nums",
                    returnColor(o.ticker_return),
                  )}
                >
                  {formatPct(o.ticker_return)}
                </td>
                <td
                  className={cn(
                    "px-3 py-2 text-right tabular-nums",
                    returnColor(o.spy_return),
                  )}
                >
                  {formatPct(o.spy_return)}
                </td>
                <td
                  className={cn(
                    "px-3 py-2 text-right tabular-nums font-semibold",
                    returnColor(o.excess_return),
                  )}
                >
                  {formatPct(o.excess_return)}
                </td>
                <td className="px-3 py-2 text-center">
                  {o.aligned ? (
                    <span className="text-green-600 font-bold">✓</span>
                  ) : (
                    <span className="text-rose-500 font-bold">✗</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
