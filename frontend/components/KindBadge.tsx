import type { PredictionKind } from "@/lib/types";
import { cn } from "@/lib/utils";

const STYLES: Record<PredictionKind, { label: string; classes: string }> = {
  MARKET: {
    label: "MARKET",
    classes: "bg-indigo-50 text-indigo-700 ring-indigo-600/20",
  },
  COMPANY: {
    label: "COMPANY",
    classes: "bg-amber-50 text-amber-800 ring-amber-600/20",
  },
};

export function KindBadge({ kind }: { kind: PredictionKind }) {
  const { label, classes } = STYLES[kind];
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wide ring-1 ring-inset",
        classes,
      )}
    >
      {label}
    </span>
  );
}
