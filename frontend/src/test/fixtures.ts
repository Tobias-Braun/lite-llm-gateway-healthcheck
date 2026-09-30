import type { LatencyResponse, LatencySeries, LatencySpan, ModelFamily } from "../types";

const LIVE_TIMES = ["2026-09-25T13:30:00Z", "2026-09-25T14:00:00Z", "2026-09-25T14:30:00Z", "2026-09-25T15:00:00Z"];

/** A `/api/latency` payload for the given request URL, following the shared contract. */
export function latencyResponse(url: string): LatencyResponse {
  const params = new URL(url, "http://localhost").searchParams;
  const span = (params.get("span") ?? "live") as LatencySpan;
  const family = params.get("family");
  const model = params.get("model");
  const titles = family ? [family] : families.map((f) => f.title);
  const buckets = { live: 0, hour: 24, weekday: 7, monthday: 31 }[span];
  const series: LatencySeries[] = titles.map((title) => ({
    family: title,
    model,
    points:
      span === "live"
        ? LIVE_TIMES.map((datetime, i) => ({
            datetime,
            available: i === 1 ? "no" : "yes",
            latencyMs: i === 1 ? null : 100 + i * 10,
            error: i === 1 ? "down" : null,
          }))
        : null,
    buckets:
      span === "live"
        ? null
        : Array.from({ length: buckets }, (_, i) => ({
            bucket: span === "monthday" ? i + 1 : i,
            avgMs: i % 2 ? null : 200 + i,
            p95Ms: i % 2 ? null : 300 + i,
            count: i % 2 ? 0 : 3,
          })),
    summary: { avgMs: 120, p95Ms: 130, count: 3 },
  }));
  return { span, series };
}

/** Sample `/api/families` payload following the shared contract, used by the tests. */
export const families: ModelFamily[] = [
  {
    title: "Claude",
    status: "yes",
    history: {
      availabilityPoints: [
        { datetime: "2026-09-25T14:00:00Z", available: "no" },
        { datetime: "2026-09-25T14:30:00Z", available: "unknown" },
        { datetime: "2026-09-25T15:00:00Z", available: "yes" },
      ],
    },
    models: [
      {
        modelname: "claude-sonnet-5",
        provider: "Google",
        company: "Anthropic",
        status: "yes",
        lastChecked: "2026-09-25T15:00:00Z",
        latencyMs: 812,
        error: null,
        history: {
          availabilityPoints: [
            { datetime: "2026-09-25T14:30:00Z", available: "yes", latencyMs: 790, error: null },
            { datetime: "2026-09-25T15:00:00Z", available: "yes", latencyMs: 812, error: null },
          ],
        },
      },
      {
        modelname: "claude-opus-5",
        provider: "Google",
        company: "Anthropic",
        status: "no",
        lastChecked: "2026-09-25T15:00:00Z",
        latencyMs: null,
        error: "Timeout after 30s",
        history: {
          availabilityPoints: [
            { datetime: "2026-09-25T14:30:00Z", available: "no", latencyMs: null, error: "Timeout after 30s" },
            { datetime: "2026-09-25T15:00:00Z", available: "no", latencyMs: null, error: "Timeout after 30s" },
          ],
        },
      },
    ],
  },
  {
    title: "GPT",
    status: "unknown",
    history: { availabilityPoints: [] },
    models: [
      {
        modelname: "gpt-5",
        provider: "Azure",
        company: "OpenAI",
        status: "unknown",
        lastChecked: null,
        latencyMs: null,
        error: null,
        history: { availabilityPoints: [] },
      },
    ],
  },
  {
    title: "Partial",
    status: "partial",
    history: {
      availabilityPoints: [{ datetime: "2026-09-25T15:00:00Z", available: "partial" }],
    },
    models: [
      {
        modelname: "model-a",
        provider: "Azure",
        company: "OpenAI",
        status: "yes",
        lastChecked: "2026-09-25T15:00:00Z",
        latencyMs: 120,
        error: null,
        history: {
          availabilityPoints: [{ datetime: "2026-09-25T15:00:00Z", available: "yes", latencyMs: 120, error: null }],
        },
      },
      {
        modelname: "model-b",
        provider: "Azure",
        company: "OpenAI",
        status: "no",
        lastChecked: "2026-09-25T15:00:00Z",
        latencyMs: null,
        error: "down",
        history: {
          availabilityPoints: [{ datetime: "2026-09-25T15:00:00Z", available: "no", latencyMs: null, error: "down" }],
        },
      },
    ],
  },
];
