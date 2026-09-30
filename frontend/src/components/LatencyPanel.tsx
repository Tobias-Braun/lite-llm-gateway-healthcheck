import { useMemo, useState } from "react";
import { formatMs } from "../format";
import type { LatencyResponse, LatencySpan } from "../types";
import { useLatency } from "../useLatency";
import { type ChartSeries, LatencyChart } from "./LatencyChart";

interface LatencyPanelProps {
  title: string;
  /** Without a family, one series per family is shown (the cross-family overview). */
  family?: string;
  model?: string;
}

const SPANS: { value: LatencySpan; label: string }[] = [
  { value: "live", label: "Live" },
  { value: "hour", label: "Hour of day" },
  { value: "weekday", label: "Day of week" },
  { value: "monthday", label: "Day of month" },
];
const LOOKBACK_DAYS = [7, 30, 90];
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

// Module-level so the chart's d3 effect doesn't redraw on every render.
const FORMAT_X: Record<LatencySpan, (x: number) => string> = {
  live: (x) => new Date(x).toLocaleString(),
  hour: (x) => `${String(x).padStart(2, "0")}:00`,
  weekday: (x) => WEEKDAYS[x] ?? "",
  monthday: (x) => `Day ${x}`,
};

const LATENCY_COLOR = "var(--latency)";
const SERIES_COLORS = 6;

function toChartSeries(response: LatencyResponse, overview: boolean): ChartSeries[] {
  return response.series.map((s, i) => ({
    label: s.model ?? s.family,
    color: overview ? `var(--series-${(i % SERIES_COLORS) + 1})` : LATENCY_COLOR,
    values: s.points
      ? s.points.map((p) => ({ x: Date.parse(p.datetime), y: p.latencyMs }))
      : (s.buckets ?? []).map((b) => ({
          x: b.bucket,
          y: b.avgMs,
          detail: `avg ${formatMs(b.avgMs)} · p95 ${formatMs(b.p95Ms)} · ${b.count} checks`,
        })),
  }));
}

/** A latency chart with its span (live or aggregated) and lookback selectors, plus summary figures. */
export function LatencyPanel({ title, family, model }: LatencyPanelProps) {
  const [span, setSpan] = useState<LatencySpan>("live");
  const [days, setDays] = useState(LOOKBACK_DAYS[1]);
  const { data, error } = useLatency({ span, days, family, model });
  const overview = family === undefined;
  const series = useMemo(
    () => (data && data.span === span ? toChartSeries(data, overview) : null),
    [data, span, overview],
  );
  const spanLabel = SPANS.find((s) => s.value === span)?.label;

  return (
    <div className="latency">
      <div className="latency-head">
        <h3 className="latency-title">{title}</h3>
        <div className="segmented" role="group" aria-label="Latency span">
          {SPANS.map((s) => (
            <button key={s.value} type="button" aria-pressed={span === s.value} onClick={() => setSpan(s.value)}>
              {s.label}
            </button>
          ))}
        </div>
        {span !== "live" && (
          <select aria-label="Lookback" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {LOOKBACK_DAYS.map((d) => (
              <option key={d} value={d}>
                Last {d} days
              </option>
            ))}
          </select>
        )}
      </div>
      {error && (
        <p className="banner banner-error" role="alert">
          Could not load latency: {error}
        </p>
      )}
      {!series && !error && <p className="muted">Loading latency…</p>}
      {series && data && (
        <>
          <LatencyChart series={series} xKind={span === "live" ? "time" : "bucket"} formatX={FORMAT_X[span]} label={`${title}, ${spanLabel}`} />
          {overview ? (
            <table className="latency-stats">
              <thead>
                <tr>
                  <th>Family</th>
                  <th>Avg</th>
                  <th>p95</th>
                  <th>Checks</th>
                </tr>
              </thead>
              <tbody>
                {data.series.map((s, i) => (
                  <tr key={s.family}>
                    <td>
                      <span className="chart-swatch" style={{ background: series[i].color }} />
                      {s.family}
                    </td>
                    <td>{formatMs(s.summary.avgMs)}</td>
                    <td>{formatMs(s.summary.p95Ms)}</td>
                    <td>{s.summary.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="muted latency-summary">
              avg {formatMs(data.series[0]?.summary.avgMs ?? null)} · p95 {formatMs(data.series[0]?.summary.p95Ms ?? null)} ·{" "}
              {data.series[0]?.summary.count ?? 0} checks
            </p>
          )}
        </>
      )}
    </div>
  );
}
