import * as d3 from "d3";
import { useEffect, useRef, useState } from "react";

export interface ChartValue {
  /** A timestamp in ms (`time` charts) or a bucket number (`bucket` charts). */
  x: number;
  /** Latency in ms; `null` leaves a gap in the line. */
  y: number | null;
  /** Tooltip text replacing the plain `<y> ms`. */
  detail?: string;
}

export interface ChartSeries {
  label: string;
  /** Any CSS color, including `var(--…)` tokens. */
  color: string;
  values: ChartValue[];
}

interface LatencyChartProps {
  series: ChartSeries[];
  xKind: "time" | "bucket";
  /** Formats an x value for the tooltip (and the axis of `bucket` charts); must be referentially stable. */
  formatX: (x: number) => string;
  label: string;
}

interface Hover {
  left: number;
  x: number;
  rows: { label: string; color: string; text: string }[];
}

const HEIGHT = 200;
// The left margin fits y labels up to "10000 ms" plus their padding from the plot area.
const MARGIN = { top: 16, right: 20, bottom: 32, left: 72 };
const FALLBACK_WIDTH = 640;

/** Line chart drawn with d3 into a React-owned SVG; the hover rule and tooltip stay in React. */
export function LatencyChart({ series, xKind, formatX, label }: LatencyChartProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const plotRef = useRef<SVGGElement>(null);
  const [width, setWidth] = useState(FALLBACK_WIDTH);
  const [hover, setHover] = useState<Hover | null>(null);
  const hasData = series.some((s) => s.values.some((v) => v.y != null));

  useEffect(() => {
    const wrap = wrapRef.current;
    // jsdom (tests) has no ResizeObserver; the fallback width is fine there.
    if (!wrap || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width || FALLBACK_WIDTH));
    observer.observe(wrap);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!plotRef.current) return;
    const plot = d3.select(plotRef.current);
    plot.selectAll("*").remove();
    setHover(null);
    if (!hasData) return;

    const innerWidth = Math.max(width - MARGIN.left - MARGIN.right, 10);
    const innerHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
    const xs = [...new Set(series.flatMap((s) => s.values.map((v) => v.x)))].sort((a, b) => a - b);
    const domain: [number, number] = [xs[0], xs[xs.length - 1] === xs[0] ? xs[0] + 1 : xs[xs.length - 1]];
    const x = d3.scaleLinear().domain(domain).range([0, innerWidth]);
    const yMax = d3.max(series, (s) => d3.max(s.values, (v) => v.y ?? 0)) ?? 0;
    const y = d3
      .scaleLinear()
      .domain([0, yMax || 1])
      .nice()
      .range([innerHeight, 0]);
    const maxTicks = Math.max(2, Math.floor(innerWidth / 70));

    // Time axes get d3's multi-scale labels ("09 PM", "Sep 30"); bucket axes a thinned-out integer set.
    const timeScale = d3.scaleTime().domain(domain.map((d) => new Date(d)));
    const xAxis = d3.axisBottom(x).tickSizeOuter(0).tickPadding(10);
    if (xKind === "time") {
      const tickFormat = timeScale.tickFormat();
      xAxis.tickValues(timeScale.ticks(maxTicks).map(Number)).tickFormat((d) => tickFormat(new Date(+d)));
    } else {
      const step = Math.ceil(xs.length / maxTicks);
      xAxis.tickValues(xs.filter((_, i) => i % step === 0)).tickFormat((d) => formatX(+d));
    }

    plot
      .append("g")
      .attr("class", "chart-grid")
      .call(
        d3
          .axisLeft(y)
          .ticks(4)
          .tickSize(-innerWidth)
          .tickPadding(12)
          .tickFormat((d) => `${d} ms`),
      );
    plot.append("g").attr("class", "chart-axis").attr("transform", `translate(0,${innerHeight})`).call(xAxis);

    const line = d3
      .line<ChartValue>()
      .defined((v) => v.y != null)
      .x((v) => x(v.x))
      .y((v) => y(v.y ?? 0))
      .curve(d3.curveMonotoneX);
    for (const s of series) {
      // Line and dots read their color (and glow) from `--line`, see index.css.
      const group = plot.append("g").style("--line", s.color);
      group.append("path").datum(s.values).attr("class", "chart-line").attr("d", line);
      group
        .selectAll("circle")
        .data(s.values.filter((v) => v.y != null))
        .join("circle")
        .attr("class", "chart-dot")
        .attr("r", 2.5)
        .attr("cx", (v) => x(v.x))
        .attr("cy", (v) => y(v.y ?? 0));
    }

    plot
      .append("rect")
      .attr("class", "chart-overlay")
      .attr("width", innerWidth)
      .attr("height", innerHeight)
      .on("pointermove", (event: PointerEvent) => {
        const nearest = xs[d3.bisectCenter(xs, x.invert(d3.pointer(event)[0]))];
        setHover({
          left: MARGIN.left + x(nearest),
          x: nearest,
          rows: series.map((s) => {
            const value = s.values.find((v) => v.x === nearest);
            const text = value?.y != null ? (value.detail ?? `${value.y} ms`) : "no data";
            return { label: s.label, color: s.color, text };
          }),
        });
      })
      .on("pointerleave", () => setHover(null));
  }, [series, xKind, formatX, width, hasData]);

  // The wrapper always renders, so the ResizeObserver is attached even while there is no data yet.
  return (
    <div className="chart" ref={wrapRef}>
      {hasData ? (
        <svg width={width} height={HEIGHT} role="img" aria-label={label}>
          <g ref={plotRef} transform={`translate(${MARGIN.left},${MARGIN.top})`} />
          {hover && (
            <line className="chart-rule" x1={hover.left} x2={hover.left} y1={MARGIN.top} y2={HEIGHT - MARGIN.bottom} />
          )}
        </svg>
      ) : (
        <p className="muted">No latency data for this period yet.</p>
      )}
      {hover && (
        <div
          className="chart-tooltip"
          style={{
            left: hover.left,
            // Flip to the left of the rule on the right half, so the bubble never leaves the chart.
            transform: hover.left > width / 2 ? "translateX(calc(-100% - 10px))" : "translateX(10px)",
          }}
        >
          <strong>{formatX(hover.x)}</strong>
          {hover.rows.map((row) => (
            <div key={row.label}>
              <span className="chart-swatch" style={{ background: row.color }} />
              {series.length > 1 && `${row.label}: `}
              {row.text}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
