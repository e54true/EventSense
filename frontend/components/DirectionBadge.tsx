import type { PredictionDirection } from "@/lib/types";
import { cn } from "@/lib/utils";

const STYLES: Record<PredictionDirection, { label: string; classes: string }> = {
  BULLISH: { label: "▲ BULLISH", classes: "bg-green-100 text-green-900 ring-green-200" },
  BEARISH: { label: "▼ BEARISH", classes: "bg-red-100 text-red-900 ring-red-200" },
  NEUTRAL: { label: "● NEUTRAL", classes: "bg-gray-100 text-gray-900 ring-gray-200" },
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
