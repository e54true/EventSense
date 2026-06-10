import type { PredictionDirection } from "@/lib/types";
import { cn } from "@/lib/utils";

const STYLES: Record<PredictionDirection, { label: string; classes: string }> = {
  BULLISH: {
    label: "▲ BULLISH",
    classes: "text-term-up border-term-up/40 bg-term-up/10",
  },
  BEARISH: {
    label: "▼ BEARISH",
    classes: "text-term-down border-term-down/40 bg-term-down/10",
  },
  NEUTRAL: {
    label: "● NEUTRAL",
    classes: "text-term-muted border-term-muted/40 bg-term-muted/10",
  },
};

export function DirectionBadge({ direction }: { direction: PredictionDirection }) {
  const { label, classes } = STYLES[direction];
  return (
    <span
      className={cn(
        "inline-flex items-center border px-2 py-px font-mono text-[11px] font-bold tracking-wider tabular-nums",
        classes,
      )}
    >
      {label}
    </span>
  );
}
