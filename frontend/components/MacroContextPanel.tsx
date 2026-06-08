import type { IndicatorSnapshotRead } from "@/lib/types";
import { cn } from "@/lib/utils";

// Friendly display labels for indicator keys. Anything not in the map falls
// back to the raw key — adding a new indicator backend-side requires no
// frontend change to render correctly, just less prettily.
const INDICATOR_LABEL: Record<string, string> = {
  DGS10: "10Y Treasury",
  DGS2: "2Y Treasury",
  SP500_PE: "S&P 500 P/E",
  SP500_TTM_EPS: "S&P 500 TTM EPS",
};

// Suffix that goes after the value (e.g. "%" for yields). Empty when the
// value already speaks for itself (P/E, EPS dollars).
const INDICATOR_UNIT: Record<string, string> = {
  DGS10: "%",
  DGS2: "%",
};

function formatValue(key: string, value: number): string {
  const unit = INDICATOR_UNIT[key] ?? "";
  // 10Y/2Y print 2 decimal places (4.47%); P/E + EPS 2 decimal places too.
  return `${value.toFixed(2)}${unit}`;
}

function formatDelta(key: string, delta: number | null): {
  label: string;
  tone: "pos" | "neg" | "neutral";
} {
  if (delta === null) return { label: "—", tone: "neutral" };
  const unit = INDICATOR_UNIT[key] ?? "";
  const sign = delta >= 0 ? "+" : "";
  // Yields: show in bps (basis points). Everything else: show as the raw unit.
  if (unit === "%") {
    const bps = Math.round(delta * 100);
    const bpsSign = bps >= 0 ? "+" : "";
    return {
      label: `${bpsSign}${bps} bps`,
      tone: bps > 0 ? "pos" : bps < 0 ? "neg" : "neutral",
    };
  }
  return {
    label: `${sign}${delta.toFixed(2)}`,
    tone: delta > 0 ? "pos" : delta < 0 ? "neg" : "neutral",
  };
}

const DELTA_TONE: Record<"pos" | "neg" | "neutral", string> = {
  pos: "text-green-700",
  neg: "text-rose-700",
  neutral: "text-slate-500",
};

type Props = {
  title?: string;
  subtitle?: string;
  indicators: IndicatorSnapshotRead[];
};

export function MacroContextPanel({
  title = "Macro context",
  subtitle = "current values, 30-day change",
  indicators,
}: Props) {
  if (indicators.length === 0) {
    return (
      <section className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900 uppercase tracking-wide">
          {title}
        </h2>
        <p className="mt-2 text-sm text-slate-500">
          No indicator data yet — daily polls populate this panel once Beat runs.
        </p>
      </section>
    );
  }

  // Stable order: known keys in a hand-picked sequence, unknown keys appended.
  const ordered = [...indicators].sort((a, b) => {
    const order = ["DGS2", "DGS10", "SP500_PE", "SP500_TTM_EPS"];
    const ai = order.indexOf(a.indicator_key);
    const bi = order.indexOf(b.indicator_key);
    if (ai === -1 && bi === -1) return a.indicator_key.localeCompare(b.indicator_key);
    if (ai === -1) return 1;
    if (bi === -1) return -1;
    return ai - bi;
  });

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
      <div className="flex items-baseline justify-between mb-4">
        <h2 className="text-sm font-semibold text-slate-900 uppercase tracking-wide">
          {title}
        </h2>
        <span className="text-xs text-slate-500">{subtitle}</span>
      </div>
      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {ordered.map((ind) => {
          const delta = formatDelta(ind.indicator_key, ind.delta_30d);
          return (
            <div
              key={ind.indicator_key}
              className="rounded-lg bg-slate-50 p-3 flex flex-col gap-1"
            >
              <dt className="text-[11px] uppercase tracking-wider text-slate-500">
                {INDICATOR_LABEL[ind.indicator_key] ?? ind.indicator_key}
              </dt>
              <dd className="text-lg font-semibold text-slate-900 tabular-nums">
                {formatValue(ind.indicator_key, ind.value)}
              </dd>
              <dd className={cn("text-xs tabular-nums", DELTA_TONE[delta.tone])}>
                {delta.label}
              </dd>
            </div>
          );
        })}
      </dl>
    </section>
  );
}
