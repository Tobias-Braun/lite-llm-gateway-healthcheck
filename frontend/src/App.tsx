import { useEffect, useState } from "react";
import { fetchFamilies } from "./api";
import { Accordion } from "./components/Accordion";
import type { ModelFamily } from "./types";

export const REFRESH_INTERVAL_MS = 30_000;

export function App() {
  const [families, setFamilies] = useState<ModelFamily[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      try {
        const data = await fetchFamilies(controller.signal);
        setFamilies(data);
        setError(null);
        setUpdatedAt(new Date());
      } catch (err) {
        if (controller.signal.aborted) {
          return;
        }
        // Keep showing the last successful data; only the error banner changes.
        setError(err instanceof Error ? err.message : String(err));
      }
    }

    void load();
    const timer = window.setInterval(load, REFRESH_INTERVAL_MS);
    return () => {
      window.clearInterval(timer);
      controller.abort();
    };
  }, []);

  return (
    <main className="app">
      <header className="app-header">
        <h1>Gateway Health Check</h1>
        {updatedAt && <span className="muted">Updated {updatedAt.toLocaleTimeString()}</span>}
      </header>
      {error && (
        <p className="banner banner-error" role="alert">
          Could not load status: {error}
        </p>
      )}
      {families === null && !error && <p className="muted">Loading…</p>}
      {families !== null && families.length === 0 && <p className="muted">No model families configured.</p>}
      {families !== null && families.length > 0 && <Accordion families={families} />}
    </main>
  );
}
