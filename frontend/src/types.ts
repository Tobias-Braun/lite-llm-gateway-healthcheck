/** Mirrors the shared `GET /api/families` contract served by the FastAPI backend. */

export type Availability = "yes" | "no" | "partial" | "unknown";

export interface AvailabilityPoint {
  /** ISO 8601 timestamp (UTC). */
  datetime: string;
  available: Availability;
  /** Model-level points only: that round's latency (for `yes`) or error (for `no`). */
  latencyMs?: number | null;
  error?: string | null;
}

export interface ModelHistory {
  /** Ordered oldest first. */
  availabilityPoints: AvailabilityPoint[];
}

export interface ModelDef {
  modelname: string;
  provider: string;
  company: string;
  status: Availability;
  lastChecked: string | null;
  latencyMs: number | null;
  error: string | null;
  history: ModelHistory;
}

export interface ModelFamily {
  title: string;
  status: Availability;
  history: ModelHistory;
  models: ModelDef[];
}

/** `GET /api/latency` span: live rounds, or an aggregate by local hour of day, weekday or day of month. */
export type LatencySpan = "live" | "hour" | "weekday" | "monthday";

export interface LatencyPoint extends AvailabilityPoint {
  latencyMs: number | null;
}

export interface LatencyBucket {
  /** Hour 0–23, weekday 0–6 (Monday = 0) or day of month 1–31. */
  bucket: number;
  avgMs: number | null;
  p95Ms: number | null;
  count: number;
}

export interface LatencySummary {
  avgMs: number | null;
  p95Ms: number | null;
  count: number;
}

export interface LatencySeries {
  family: string;
  model: string | null;
  /** Set for the live span, oldest first. */
  points: LatencyPoint[] | null;
  /** Set for aggregate spans, one per bucket of the span. */
  buckets: LatencyBucket[] | null;
  summary: LatencySummary;
}

/** Mirrors the `GET /api/latency` contract. */
export interface LatencyResponse {
  span: LatencySpan;
  series: LatencySeries[];
}

/** Mirrors the `GET /api/config` contract. */
export interface AppConfig {
  title: string;
}
