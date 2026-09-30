import type { AppConfig, LatencyResponse, LatencySpan, ModelFamily } from "./types";

/** Relative URL so it works both behind the Vite dev proxy and when served by the backend. */
export const FAMILIES_URL = "/api/families";
export const CONFIG_URL = "/api/config";
export const LATENCY_URL = "/api/latency";

/** How often live data (families and live latency) is refetched. */
export const REFRESH_INTERVAL_MS = 30_000;

export async function fetchFamilies(signal?: AbortSignal): Promise<ModelFamily[]> {
  const response = await fetch(FAMILIES_URL, { signal });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as ModelFamily[];
}

export interface LatencyQuery {
  span: LatencySpan;
  days: number;
  family?: string;
  model?: string;
}

/** Aggregates are bucketed in the viewer's own time zone, so busy hours read in local time. */
export async function fetchLatency(query: LatencyQuery, signal?: AbortSignal): Promise<LatencyResponse> {
  const params = new URLSearchParams({
    span: query.span,
    days: String(query.days),
    tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
  });
  if (query.family) params.set("family", query.family);
  if (query.model) params.set("model", query.model);
  const response = await fetch(`${LATENCY_URL}?${params}`, { signal });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as LatencyResponse;
}

export async function fetchConfig(signal?: AbortSignal): Promise<AppConfig> {
  const response = await fetch(CONFIG_URL, { signal });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} ${response.statusText}`);
  }
  return (await response.json()) as AppConfig;
}
