import type { EventSource } from "@/lib/types";
import { cn } from "@/lib/utils";

// Per-source colour coding so the timeline is scannable. The mapping is
// arbitrary but consistent — same colour everywhere the source appears.
const STYLES: Record<EventSource, string> = {
  FRED: "bg-blue-100 text-blue-900 ring-blue-200",
  SEC_EDGAR: "bg-purple-100 text-purple-900 ring-purple-200",
  FOMC: "bg-amber-100 text-amber-900 ring-amber-200",
  EARNINGS: "bg-emerald-100 text-emerald-900 ring-emerald-200",
};

export function SourceBadge({ source }: { source: EventSource }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        STYLES[source],
      )}
    >
      {source}
    </span>
  );
}
