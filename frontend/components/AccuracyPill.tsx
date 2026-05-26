"use client";

// Small stat pill — fetches /accuracy?source=X and shows the LLM alignment rate.
// Each pill is its own query so they parallel-fetch and one failure doesn't
// take the rest down.

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { EventSource } from "@/lib/types";

const ACCENT: Record<EventSource, string> = {
  FRED: "from-blue-500/10 to-blue-500/0 text-blue-700",
  SEC_EDGAR: "from-purple-500/10 to-purple-500/0 text-purple-700",
  FOMC: "from-amber-500/10 to-amber-500/0 text-amber-700",
  EARNINGS: "from-emerald-500/10 to-emerald-500/0 text-emerald-700",
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
      className={`relative overflow-hidden rounded-xl bg-gradient-to-br ${ACCENT[source]} p-3 ring-1 ring-inset ring-black/5`}
    >
      <div className="text-xs font-medium uppercase tracking-wide opacity-80">
        {label}
      </div>
      <div className="mt-1 flex items-baseline gap-1.5">
        {isLoading ? (
          <span className="text-lg font-bold tabular-nums opacity-50">—</span>
        ) : rate === null || rate === undefined ? (
          <>
            <span className="text-lg font-bold tabular-nums">N/A</span>
            <span className="text-xs text-slate-500">no data</span>
          </>
        ) : (
          <>
            <span className="text-2xl font-bold tabular-nums">
              {(rate * 100).toFixed(0)}%
            </span>
            <span className="text-xs text-slate-500 tabular-nums">
              · {total} validated
            </span>
          </>
        )}
      </div>
    </div>
  );
}
