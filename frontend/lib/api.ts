// Thin typed wrapper around fetch — no axios, no codegen, just functions.
//
// All requests use the API base URL from NEXT_PUBLIC_API_URL. The NEXT_PUBLIC_
// prefix is the Next.js convention for env vars that need to ship to the
// browser bundle (the rest are server-only).

import type {
  AccuracyResponse,
  EventDetailResponse,
  EventListResponse,
  EventSource,
  IndicatorsLatestResponse,
  OutcomeWindow,
  PredictionKind,
  PriceRangeResponse,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

class APIError extends Error {
  constructor(public status: number, public detail: string) {
    super(`API ${status}: ${detail}`);
  }
}

async function request<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Accept: "application/json" },
    // Server Components can cache GETs; explicit no-store keeps timeline fresh
    // (we want every page load to see the latest events).
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // Body wasn't JSON; fall back to statusText.
    }
    throw new APIError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listEvents: (page = 1, perPage = 20): Promise<EventListResponse> =>
    request(`/api/v1/events?page=${page}&per_page=${perPage}`),

  getEvent: (id: string): Promise<EventDetailResponse> =>
    request(`/api/v1/events/${id}`),

  getPriceRange: (
    ticker: string,
    fromAt: string,
    toAt: string,
  ): Promise<PriceRangeResponse> => {
    const qs = new URLSearchParams({ from_at: fromAt, to_at: toAt });
    return request(`/api/v1/prices/${ticker}/range?${qs}`);
  },

  getAccuracy: (filters?: {
    source?: EventSource;
    ticker?: string;
    window?: OutcomeWindow;
    model?: string;
    kind?: PredictionKind;
  }): Promise<AccuracyResponse> => {
    const params = new URLSearchParams();
    if (filters?.source) params.set("source", filters.source);
    if (filters?.ticker) params.set("ticker", filters.ticker);
    if (filters?.window) params.set("window", filters.window);
    if (filters?.model) params.set("model", filters.model);
    if (filters?.kind) params.set("kind", filters.kind);
    const qs = params.toString();
    return request(`/api/v1/accuracy${qs ? `?${qs}` : ""}`);
  },

  getIndicatorsLatest: (): Promise<IndicatorsLatestResponse> =>
    request(`/api/v1/indicators/latest`),
};

export { APIError };
