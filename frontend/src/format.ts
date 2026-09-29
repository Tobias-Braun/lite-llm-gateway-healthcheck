import type { Availability, AvailabilityPoint, ModelDef } from "./types";

export const AVAILABILITY_LABEL: Record<Availability, string> = {
  yes: "available",
  no: "unavailable",
  partial: "partially available",
  unknown: "unknown",
};

/** Formats an ISO timestamp in the viewer's locale and time zone. */
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString();
}

/** The model's latest check latency, or `—` if it has no check yet or its latest check failed. */
export function formatLatency(model: ModelDef): string {
  return model.status === "yes" && model.latencyMs != null ? `${model.latencyMs} ms` : "—";
}

/** Success rate over the shown history window (`yes / (yes + no)`), or `—` if none has a result. */
export function formatUptime(points: AvailabilityPoint[]): string {
  const yes = points.filter((p) => p.available === "yes").length;
  const no = points.filter((p) => p.available === "no").length;
  const total = yes + no;
  return total === 0 ? "—" : `${Math.round((yes / total) * 100)}%`;
}
