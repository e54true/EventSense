import type { PredictionRead, PredictionWithOutcomes } from "@/lib/types";
import { cn } from "@/lib/utils";
import { DirectionBadge } from "./DirectionBadge";
import { OutcomesTable } from "./OutcomesTable";

const MAGNITUDE_STYLE: Record<PredictionRead["magnitude"], string> = {
  LOW: "text-slate-500",
  MEDIUM: "text-slate-700",
  HIGH: "text-slate-900 font-semibold",
};

const CONFIDENCE_BAR_COLOR: Record<PredictionRead["direction"], string> = {
  BULLISH: "bg-green-500",
  BEARISH: "bg-rose-500",
  NEUTRAL: "bg-slate-400",
};

// Accepts either PredictionRead (no outcomes) or PredictionWithOutcomes —
// the OutcomesTable section is conditional on having outcomes data.
type Props = {
  prediction: PredictionRead | PredictionWithOutcomes;
};

function hasOutcomes(p: Props["prediction"]): p is PredictionWithOutcomes {
  return "outcomes" in p && Array.isArray(p.outcomes);
}

export function PredictionRow({ prediction }: Props) {
  const confidencePct = prediction.confidence * 100;
  const outcomes = hasOutcomes(prediction) ? prediction.outcomes : null;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-3 mb-2">
        <span className="font-mono text-base font-bold text-slate-900 min-w-16">
          {prediction.ticker}
        </span>
        <DirectionBadge direction={prediction.direction} />
        <span className={cn("text-xs uppercase tracking-wider", MAGNITUDE_STYLE[prediction.magnitude])}>
          {prediction.magnitude}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <div className="w-16 h-1.5 rounded-full bg-slate-100 overflow-hidden">
            <div
              className={cn("h-full rounded-full", CONFIDENCE_BAR_COLOR[prediction.direction])}
              style={{ width: `${confidencePct}%` }}
            />
          </div>
          <span className="text-xs font-semibold text-slate-600 tabular-nums w-9 text-right">
            {confidencePct.toFixed(0)}%
          </span>
        </div>
      </div>

      <p className="text-sm text-slate-700 leading-relaxed pl-1">
        {prediction.reasoning}
      </p>

      <div className="mt-3 flex items-center gap-2 text-[11px] text-slate-400 font-mono">
        <span>{prediction.llm_model}</span>
        <span className="text-slate-300">·</span>
        <span>prompt {prediction.prompt_version}</span>
        {prediction.llm_cost_usd > 0 && (
          <>
            <span className="text-slate-300">·</span>
            <span className="tabular-nums">${prediction.llm_cost_usd.toFixed(5)}</span>
          </>
        )}
      </div>

      {outcomes !== null && outcomes.length > 0 && (
        <div className="mt-3">
          <OutcomesTable outcomes={outcomes} />
        </div>
      )}
    </div>
  );
}
