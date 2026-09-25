import type { Availability } from "../types";
import { AVAILABILITY_LABEL } from "../format";

interface StatusDotProps {
  status: Availability;
  /** Tooltip text; defaults to the readable status label. */
  title?: string;
}

export function StatusDot({ status, title }: StatusDotProps) {
  const label = title ?? AVAILABILITY_LABEL[status];
  return <span className={`status-dot status-${status}`} title={label} role="img" aria-label={label} />;
}
