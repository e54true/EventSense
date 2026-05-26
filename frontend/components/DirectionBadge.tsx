import type { PredictionDirection } from "@/lib/types";
import { cn } from "@/lib/utils";

const STYLES: Record<PredictionDirection, { label: string; classes: string }> = {
  BULLISH: {
    label: "▲ BULLISH",
    classes: "bg-green-50 text-green-700 ring-green-600/20",
  },
  BEARISH: {
    label: "▼ BEARISH",
    classes: "bg-rose-50 text-rose-700 ring-rose-600/20",
  },
  NEUTRAL: {
    label: "● NEUTRAL",
    classes: "bg-slate-100 text-slate-700 ring-slate-500/20",
  },
};

export function DirectionBadge({ direction }: { direction: PredictionDirection }) {
  const { label, classes } = STYLES[direction];
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ring-1 ring-inset tabular-nums",
        classes,
      )}
    >
      {label}
    </span>
  );
}
