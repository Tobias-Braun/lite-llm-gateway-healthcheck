import type { AvailabilityPoint } from "../types";
import { AVAILABILITY_LABEL, formatDateTime } from "../format";

interface AvailabilityTimelineProps {
  points: AvailabilityPoint[];
  /** Renders at a smaller size, for per-model timelines inside the model table. */
  small?: boolean;
}

/** Time and status as today, plus latency (for `yes`) or error (for `no`) when the round has one. */
function pointTooltip(point: AvailabilityPoint): string {
  const base = `${formatDateTime(point.datetime)}: ${AVAILABILITY_LABEL[point.available]}`;
  if (point.available === "yes" && point.latencyMs != null) {
    return `${base}, ${point.latencyMs} ms`;
  }
  if (point.available === "no" && point.error) {
    return `${base}, ${point.error}`;
  }
  return base;
}

/** One colored segment per check (oldest left), with the datetime and state as native tooltip. */
export function AvailabilityTimeline({ points, small }: AvailabilityTimelineProps) {
  const className = `timeline${small ? " timeline-small" : ""}`;

  if (points.length === 0) {
    return (
      <div className={className} aria-label="No availability history yet">
        <span className="timeline-segment status-unknown timeline-empty" title="No checks yet" />
      </div>
    );
  }

  return (
    <div className={className} aria-label="Availability history">
      {points.map((point) => (
        <span
          key={point.datetime}
          className={`timeline-segment status-${point.available}`}
          title={pointTooltip(point)}
        />
      ))}
    </div>
  );
}
