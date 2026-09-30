import type { AvailabilityPoint } from "../types";
import { AVAILABILITY_LABEL, formatDateTime } from "../format";

interface AvailabilityTimelineProps {
  points: AvailabilityPoint[];
  /** Renders at a smaller size, for per-model timelines inside the model table. */
  small?: boolean;
}

/** Gateway errors can be whole JSON dumps; longer ones are cut so the tooltip stays compact. */
const MAX_ERROR_LENGTH = 160;

/** Time and status as today, plus latency (for `yes`) or error (for `no`) when the round has one. */
function pointTooltip(point: AvailabilityPoint): string {
  const base = `${formatDateTime(point.datetime)}: ${AVAILABILITY_LABEL[point.available]}`;
  if (point.available === "yes" && point.latencyMs != null) {
    return `${base}, ${point.latencyMs} ms`;
  }
  if (point.available === "no" && point.error) {
    const error =
      point.error.length > MAX_ERROR_LENGTH ? `${point.error.slice(0, MAX_ERROR_LENGTH)}…` : point.error;
    return `${base}, ${error}`;
  }
  return base;
}

/** One colored segment per check (oldest left), with the datetime and state as a styled tooltip. */
export function AvailabilityTimeline({ points, small }: AvailabilityTimelineProps) {
  const className = `timeline${small ? " timeline-small" : ""}`;

  if (points.length === 0) {
    return (
      <div className={className} aria-label="No availability history yet">
        <span className="timeline-segment status-unknown timeline-empty" data-tooltip="No checks yet" />
      </div>
    );
  }

  return (
    <div className={className} aria-label="Availability history">
      {points.map((point, index) => (
        <span
          key={point.datetime}
          // Tooltips open towards the timeline's middle, so they never stick out past its ends.
          className={`timeline-segment status-${point.available} ${
            index < points.length / 2 ? "tooltip-start" : "tooltip-end"
          }`}
          data-tooltip={pointTooltip(point)}
        />
      ))}
    </div>
  );
}
