import { useEffect, useState } from "react";
import { type LatencyQuery, REFRESH_INTERVAL_MS, fetchLatency } from "./api";
import type { LatencyResponse } from "./types";

/** Fetches `GET /api/latency` for `query`; the live span is refetched on the dashboard's refresh interval. */
export function useLatency({ span, days, family, model }: LatencyQuery) {
  const [data, setData] = useState<LatencyResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    // Drop the previous query's data, whose shape (points vs. buckets) may not match the new span.
    setData(null);
    setError(null);

    async function load() {
      try {
        setData(await fetchLatency({ span, days, family, model }, controller.signal));
        setError(null);
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : String(err));
        }
      }
    }

    void load();
    const timer = span === "live" ? window.setInterval(load, REFRESH_INTERVAL_MS) : undefined;
    return () => {
      window.clearInterval(timer);
      controller.abort();
    };
  }, [span, days, family, model]);

  return { data, error };
}
