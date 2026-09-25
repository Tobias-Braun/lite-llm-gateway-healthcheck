import type { AvailabilityPoint } from "../types";
import { AVAILABILITY_LABEL, formatDateTime } from "../format";

interface AvailabilityTimelineProps {
  points: AvailabilityPoint[];
}

/** One colored segment per check (oldest left), with the datetime and state as native tooltip. */
export function AvailabilityTimeline({ points }: AvailabilityTimelineProps) {
  if (points.length === 0) {
    return (
      <div className="timeline" aria-label="No availability history yet">
        <span className="timeline-segment status-unknown timeline-empty" title="No checks yet" />
      </div>
    );
  }

  return (
    <div className="timeline" aria-label="Availability history">
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
