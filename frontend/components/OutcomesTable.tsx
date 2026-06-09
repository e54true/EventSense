// Renders the 1h / 24h / 7d outcomes for one prediction.
//
// Three slots fixed in column order so users can scan rows of predictions
// and see the same time horizons line up. Three possible row states:
//
//   1. filled — outcome row exists, show return + aligned tick
//   2. maturing — window hasn't elapsed yet from predicted_at, show "Xh left"
//   3. unavailable — window matured but validator couldn't fill (most often:
//      1h tolerance can't reach the nearest daily price snapshot for events
//      whose predicted_at is at 00:00 UTC). Communicates "structural miss"
//      rather than implying the value is still coming.

import type { OutcomeRead, OutcomeWindow } from "@/lib/types";
import { cn } from "@/lib/utils";

// 1h dropped — for events whose predicted_at sits at 00:00 UTC (off-hours),
// the validator's 1h price-tolerance window never overlaps with our daily
// price snapshots, so H1 outcomes never write. See validator.py rationale.
// Old H1 outcomes from prior deploys, if any, are simply not rendered.
const WINDOWS: OutcomeWindow[] = ["24h", "7d"];
const WINDOW_DURATION_HOURS: Record<OutcomeWindow, number> = {
  "1h": 1, // kept for type completeness; not iterated.
  "24h": 24,
  "7d": 7 * 24,
};

function formatPct(v: number): string {
  const sign = v > 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(2)}%`;
}

function returnColor(v: number): string {
  if (v > 0) return "text-green-700";
  if (v < 0) return "text-rose-700";
  return "text-slate-500";
}

function formatTimeLeft(hours: number): string {
  if (hours < 24) return `${Math.ceil(hours)}h left`;
  return `${Math.ceil(hours / 24)}d left`;
}

type RowState =
  | { kind: "filled"; outcome: OutcomeRead }
  | { kind: "maturing"; hoursLeft: number }
  | { kind: "unavailable" };

function rowStateFor(
  window: OutcomeWindow,
  predictedAt: string,
  outcome: OutcomeRead | undefined,
): RowState {
  if (outcome) return { kind: "filled", outcome };
  const maturesMs =
    new Date(predictedAt).getTime() +
    WINDOW_DURATION_HOURS[window] * 3600_000;
  const nowMs = Date.now();
  if (maturesMs > nowMs) {
    return { kind: "maturing", hoursLeft: (maturesMs - nowMs) / 3600_000 };
  }
  return { kind: "unavailable" };
}

export function OutcomesTable({
  outcomes,
  predictedAt,
}: {
  outcomes: OutcomeRead[];
  predictedAt: string;
}) {
  const byWindow = new Map(outcomes.map((o) => [o.window, o]));

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/50 overflow-hidden">
      <table className="w-full text-xs">
        <thead className="bg-slate-100/80">
          <tr className="text-left text-[10px] uppercase tracking-wider text-slate-500">
            <th className="px-3 py-2 font-medium w-20">Window</th>
            <th className="px-3 py-2 font-medium text-right">Ticker return</th>
            <th className="px-3 py-2 font-medium text-center w-24">Aligned</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200/80">
          {WINDOWS.map((w) => {
            const state = rowStateFor(w, predictedAt, byWindow.get(w));
            return (
              <tr key={w}>
                <td className="px-3 py-2 font-mono font-semibold text-slate-900 w-20">
                  {w}
                </td>
                {state.kind === "filled" ? (
                  <>
                    <td
                      className={cn(
                        "px-3 py-2 text-right tabular-nums font-semibold",
                        returnColor(state.outcome.ticker_return),
                      )}
                    >
                      {formatPct(state.outcome.ticker_return)}
                    </td>
                    <td className="px-3 py-2 text-center w-24">
                      {state.outcome.aligned ? (
                        <span className="text-green-600 font-bold">✓</span>
                      ) : (
                        <span className="text-rose-500 font-bold">✗</span>
                      )}
                    </td>
                  </>
                ) : state.kind === "maturing" ? (
                  <>
                    <td className="px-3 py-2 text-right text-slate-400 italic tabular-nums">
                      maturing · {formatTimeLeft(state.hoursLeft)}
                    </td>
                    <td className="px-3 py-2 text-center text-slate-300 w-24">
                      —
                    </td>
                  </>
                ) : (
                  <>
                    <td
                      className="px-3 py-2 text-right text-slate-400 italic"
                      title={
                        w === "1h"
                          ? "1h window can't be filled when only daily price snapshots are available — needs intraday data captured around predicted_at"
                          : "window matured but the validator couldn't find prices within tolerance"
                      }
                    >
                      no data
                    </td>
                    <td className="px-3 py-2 text-center text-slate-300 w-24">
                      —
                    </td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
