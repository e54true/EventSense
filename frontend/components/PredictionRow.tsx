import type { PredictionRead } from "@/lib/types";
import { cn } from "@/lib/utils";
import { DirectionBadge } from "./DirectionBadge";

const MAGNITUDE_STYLE: Record<PredictionRead["magnitude"], string> = {
  LOW: "text-gray-500",
  MEDIUM: "text-gray-700",
  HIGH: "text-gray-900 font-semibold",
};

export function PredictionRow({ prediction }: { prediction: PredictionRead }) {
  const confidencePct = (prediction.confidence * 100).toFixed(0);

  return (
    <div className="rounded-md border border-gray-200 bg-white p-3">
      <div className="flex items-center gap-3 mb-2">
        <span className="font-mono text-sm font-semibold text-gray-900 w-16">
          {prediction.ticker}
        </span>
        <DirectionBadge direction={prediction.direction} />
        <span className={cn("text-xs", MAGNITUDE_STYLE[prediction.magnitude])}>
          {prediction.magnitude}
        </span>
        <span className="ml-auto text-xs text-gray-500 tabular-nums">
          conf {confidencePct}%
        </span>
      </div>
      <p className="text-sm text-gray-700 leading-relaxed">
        {prediction.reasoning}
      </p>
      <div className="mt-2 flex items-center gap-2 text-xs text-gray-400">
        <span>{prediction.llm_model}</span>
        <span>·</span>
        <span>prompt {prediction.prompt_version}</span>
        {prediction.llm_cost_usd > 0 && (
          <>
            <span>·</span>
            <span className="tabular-nums">${prediction.llm_cost_usd.toFixed(5)}</span>
          </>
        )}
      </div>
    </div>
  );
}
