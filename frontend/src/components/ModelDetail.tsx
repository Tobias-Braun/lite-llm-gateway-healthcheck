import { useLatency } from "../useLatency";
import { AvailabilityTimeline } from "./AvailabilityTimeline";
import { LatencyPanel } from "./LatencyPanel";

interface ModelDetailProps {
  family: string;
  model: string;
}

/** Expanded model row: health over the family's full history window, plus the model's latency chart. */
export function ModelDetail({ family, model }: ModelDetailProps) {
  // The live latency series carries each round's availability, so it also drives the full-length bar.
  const { data, error } = useLatency({ span: "live", days: 1, family, model });

  return (
    <div className="model-detail">
      <h3 className="latency-title">Health history</h3>
      {error && (
        <p className="banner banner-error" role="alert">
          Could not load history: {error}
        </p>
      )}
      {!data && !error && <p className="muted">Loading history…</p>}
      {data && <AvailabilityTimeline points={data.series[0]?.points ?? []} />}
      <LatencyPanel title="Latency" family={family} model={model} />
    </div>
  );
}
