import type { PredictionRead, PredictionWithOutcomes } from "@/lib/types";
import { cn } from "@/lib/utils";
import { DirectionBadge } from "./DirectionBadge";
import { KindBadge } from "./KindBadge";
import { OutcomesTable } from "./OutcomesTable";

const MAGNITUDE_STYLE: Record<PredictionRead["magnitude"], string> = {
  LOW: "text-term-dim",
  MEDIUM: "text-term-muted",
  HIGH: "text-term-text font-bold",
};

const CONFIDENCE_BAR_COLOR: Record<PredictionRead["direction"], string> = {
  BULLISH: "bg-term-up",
  BEARISH: "bg-term-down",
  NEUTRAL: "bg-term-muted",
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
    <div className="border border-term-border bg-term-panel p-4">
      <div className="flex items-center gap-3 mb-2 flex-wrap">
        <span className="font-mono text-base font-bold text-term-amber min-w-16">
          {prediction.ticker}
        </span>
        <KindBadge kind={prediction.kind} />
        <DirectionBadge direction={prediction.direction} />
        <span
          className={cn(
            "font-mono text-[10px] uppercase tracking-widest",
            MAGNITUDE_STYLE[prediction.magnitude],
          )}
        >
          {prediction.magnitude}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <div className="w-16 h-1 bg-term-panel2 overflow-hidden">
            <div
              className={cn("h-full", CONFIDENCE_BAR_COLOR[prediction.direction])}
              style={{ width: `${confidencePct}%` }}
            />
          </div>
          <span className="font-mono text-xs font-bold text-term-muted tabular-nums w-9 text-right">
            {confidencePct.toFixed(0)}%
          </span>
        </div>
      </div>

      <p className="text-sm text-term-text/90 leading-relaxed">
        {prediction.reasoning}
      </p>

      <div className="mt-3 flex items-center gap-2 font-mono text-[10px] text-term-dim">
        <span>{prediction.llm_model}</span>
        <span>·</span>
        <span>prompt {prediction.prompt_version}</span>
        {prediction.llm_cost_usd > 0 && (
          <>
            <span>·</span>
            <span className="tabular-nums">
              ${prediction.llm_cost_usd.toFixed(5)}
            </span>
          </>
        )}
      </div>

      {outcomes !== null && (
        <div className="mt-3">
          <OutcomesTable outcomes={outcomes} predictedAt={prediction.predicted_at} />
        </div>
      )}
    </div>
  );
}
