import type { AvailabilityPoint } from "../types";
import { AVAILABILITY_LABEL, formatDateTime } from "../format";

interface AvailabilityTimelineProps {
  points: AvailabilityPoint[];
  /** Renders at a smaller size, for per-model timelines inside the model table. */
  small?: boolean;
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
          title={`${formatDateTime(point.datetime)}: ${AVAILABILITY_LABEL[point.available]}`}
        />
      ))}
    </div>
  );
}
