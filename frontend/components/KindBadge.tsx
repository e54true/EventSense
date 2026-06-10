import type { PredictionKind } from "@/lib/types";
import { cn } from "@/lib/utils";

const STYLES: Record<PredictionKind, { label: string; classes: string }> = {
  MARKET: {
    label: "MARKET",
    classes: "text-src-fred border-src-fred/40 bg-src-fred/10",
  },
  COMPANY: {
    label: "COMPANY",
    classes: "text-term-amber border-term-amber/40 bg-term-amber/10",
  },
};

export function KindBadge({ kind }: { kind: PredictionKind }) {
  const { label, classes } = STYLES[kind];
  return (
    <span
      className={cn(
        "inline-flex items-center border px-1.5 py-px font-mono text-[10px] font-bold tracking-widest",
        classes,
      )}
    >
      {label}
    </span>
  );
}
