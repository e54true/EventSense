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
export type PredictionKind = "MARKET" | "COMPANY";

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
  llm_summary: string | null;
  created_at: string;
  updated_at: string;
}

export interface PredictionRead {
  id: string;
  event_id: string;
  ticker: string;
  kind: PredictionKind;
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

export interface OutcomeRead {
  id: string;
  prediction_id: string;
  window: OutcomeWindow;
  baseline_price: string; // Decimal arrives as string
  end_price: string;
  ticker_return: number;
  spy_return: number;
  excess_return: number;
  aligned: boolean;
  validated_at: string;
}

export interface PredictionWithOutcomes extends PredictionRead {
  outcomes: OutcomeRead[];
}

export interface PricePoint {
  snapshot_at: string;
  price: string; // Decimal as string
}

export interface PriceRangeResponse {
  ticker: string;
  points: PricePoint[];
  from_at: string;
  to_at: string;
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

export interface IndicatorSnapshotRead {
  indicator_key: string;
  value: number;
  observed_at: string; // ISO 8601
  delta_30d: number | null;
}

export interface RecentEventRead {
  published_at: string;
  source: string;
  event_type: string;
  title: string;
}

export interface EventContextRead {
  lookback_days: number;
  latest_indicators: IndicatorSnapshotRead[];
  recent_events: RecentEventRead[];
}

export type DocumentKind =
  | "FILING_COVER"
  | "PRESS_RELEASE"
  | "EXHIBIT"
  | "TRANSCRIPT";

export interface AttachedDocumentRead {
  doc_kind: DocumentKind;
  content_text: string;
  raw_url: string;
  byte_size: number;
  fetched_at: string; // ISO 8601
}

export interface EventDetailResponse {
  data: EventRead;
  predictions: PredictionWithOutcomes[];
  context: EventContextRead;
  attached_documents: AttachedDocumentRead[];
}

export interface IndicatorsLatestResponse {
  indicators: IndicatorSnapshotRead[];
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
    kind: PredictionKind | null;
  };
}
