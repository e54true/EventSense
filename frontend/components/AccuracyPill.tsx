"use client";

// Small stat tile — fetches /accuracy?source=X and shows the LLM alignment rate.
// Each tile is its own query so they parallel-fetch and one failure doesn't
// take the rest down.

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { EventSource } from "@/lib/types";

const ACCENT: Record<EventSource, string> = {
  FRED: "border-l-src-fred text-src-fred",
  SEC_EDGAR: "border-l-src-sec text-src-sec",
  FOMC: "border-l-src-fomc text-src-fomc",
  EARNINGS: "border-l-src-earn text-src-earn",
};

export function AccuracyPill({
  source,
  label,
}: {
  source: EventSource;
  label: string;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["accuracy", { source }],
    queryFn: () => api.getAccuracy({ source }),
  });

  const rate = data?.alignment_rate;
  const total = data?.total_outcomes ?? 0;

  return (
    <div
      className={`border border-term-border border-l-2 bg-term-panel p-3 ${ACCENT[source]}`}
    >
      <div className="font-mono text-[10px] font-bold tracking-widest uppercase">
        {label}
      </div>
      <div className="mt-1 flex items-baseline gap-1.5">
        {isLoading ? (
          <span className="font-mono text-lg font-bold tabular-nums text-term-dim">
            ——
          </span>
        ) : rate === null || rate === undefined ? (
          <>
            <span className="font-mono text-lg font-bold tabular-nums text-term-muted">
              N/A
            </span>
            <span className="font-mono text-[10px] text-term-dim">NO DATA</span>
          </>
        ) : (
          <>
            <span className="font-mono text-2xl font-bold tabular-nums text-term-text">
              {(rate * 100).toFixed(0)}%
            </span>
            <span className="font-mono text-[10px] text-term-dim tabular-nums">
              n={total}
            </span>
          </>
        )}
      </div>
    </div>
  );
}
