import type { Availability } from "./types";

export const AVAILABILITY_LABEL: Record<Availability, string> = {
  yes: "available",
  no: "unavailable",
  unknown: "unknown",
};

/** Formats an ISO timestamp in the viewer's locale and time zone. */
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString();
}
