/** Mirrors the shared `GET /api/families` contract served by the FastAPI backend. */

export type Availability = "yes" | "no" | "unknown";

export interface AvailabilityPoint {
  /** ISO 8601 timestamp (UTC). */
  datetime: string;
  available: Availability;
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
}

export interface ModelFamily {
  title: string;
  status: Availability;
  history: ModelHistory;
  models: ModelDef[];
}
