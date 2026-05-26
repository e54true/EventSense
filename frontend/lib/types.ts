// Frontend mirror of the backend Pydantic schemas.
//
// Kept hand-written rather than generated from FastAPI's OpenAPI spec so the
// types are easy to read in PR review. The trade-off: if the backend schema
// changes, we have to update this file manually (M8 will add openapi-typescript
// codegen to a CI check, but not yet — it's nice to see the contracts side by
// side for now).

export type EventSource = "FRED" | "SEC_EDGAR" | "FOMC" | "EARNINGS";
export type EventStatus = "FETCHED" | "ANALYZED" | "FAILED" | "IGNORED";

export type PredictionDirection = "BULLISH" | "BEARISH" | "NEUTRAL";
export type PredictionMagnitude = "LOW" | "MEDIUM" | "HIGH";

export type OutcomeWindow = "1h" | "24h" | "7d";

export interface EventRead {
  id: string;
  source: EventSource;
  event_type: string;
  external_id: string;
  title: string;
  payload: Record<string, unknown>;
  affected_tickers: string[];
  published_at: string; // ISO 8601
  fetched_at: string;
  status: EventStatus;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface PredictionRead {
  id: string;
  event_id: string;
  ticker: string;
  direction: PredictionDirection;
  magnitude: PredictionMagnitude;
  confidence: number;
  reasoning: string;
  llm_provider: string;
  llm_model: string;
  prompt_version: string;
  llm_cost_usd: number;
  predicted_at: string;
  created_at: string;
}

export interface PaginationMeta {
  page: number;
  per_page: number;
  total: number;
}

export interface EventListResponse {
  data: EventRead[];
  meta: PaginationMeta;
}

export interface EventDetailResponse {
  data: EventRead;
  predictions: PredictionRead[];
}

export interface AccuracyResponse {
  total_outcomes: number;
  aligned_count: number;
  alignment_rate: number | null;
  filters: {
    source: EventSource | null;
    ticker: string | null;
    window: OutcomeWindow | null;
    model: string | null;
  };
}
