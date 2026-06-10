import type { EventSource } from "@/lib/types";
import { cn } from "@/lib/utils";

// Per-source colour coding so the timeline is scannable. The mapping is
// arbitrary but consistent — same colour everywhere the source appears.
const STYLES: Record<EventSource, string> = {
  FRED: "text-src-fred border-src-fred/40 bg-src-fred/10",
  SEC_EDGAR: "text-src-sec border-src-sec/40 bg-src-sec/10",
  FOMC: "text-src-fomc border-src-fomc/40 bg-src-fomc/10",
  EARNINGS: "text-src-earn border-src-earn/40 bg-src-earn/10",
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
        "inline-flex items-center border px-1.5 py-px font-mono text-[10px] font-bold tracking-widest",
        STYLES[source],
      )}
    >
      {LABEL[source]}
    </span>
  );
}
