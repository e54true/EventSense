import type { EventSource } from "@/lib/types";
import { cn } from "@/lib/utils";

// Per-source colour coding so the timeline is scannable. The mapping is
// arbitrary but consistent — same colour everywhere the source appears.
const STYLES: Record<EventSource, string> = {
  FRED: "bg-blue-50 text-blue-700 ring-blue-600/20",
  SEC_EDGAR: "bg-purple-50 text-purple-700 ring-purple-600/20",
  FOMC: "bg-amber-50 text-amber-800 ring-amber-600/20",
  EARNINGS: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
};

const LABEL: Record<EventSource, string> = {
  FRED: "FRED",
  SEC_EDGAR: "SEC",
  FOMC: "FOMC",
  EARNINGS: "EARNINGS",
};

export function SourceBadge({ source }: { source: EventSource }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-semibold tracking-wide ring-1 ring-inset",
        STYLES[source],
      )}
    >
      {LABEL[source]}
    </span>
  );
}
