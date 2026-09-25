import type { ModelFamily } from "../types";

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
      },
      {
        modelname: "claude-opus-5",
        provider: "Google",
        company: "Anthropic",
        status: "no",
        lastChecked: "2026-09-25T15:00:00Z",
        latencyMs: null,
        error: "Timeout after 30s",
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
      },
    ],
  },
];
