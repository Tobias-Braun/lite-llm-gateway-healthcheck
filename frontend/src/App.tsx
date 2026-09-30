import { useEffect, useState } from "react";
import { REFRESH_INTERVAL_MS, fetchConfig, fetchFamilies } from "./api";
import logo from "./assets/logo.svg";
import { Accordion } from "./components/Accordion";
import { LatencyPanel } from "./components/LatencyPanel";
import { ThemeToggle } from "./components/ThemeToggle";
import type { ModelFamily } from "./types";

export const DEFAULT_TITLE = "Gateway Health Check";

export function App() {
  const [families, setFamilies] = useState<ModelFamily[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [title, setTitle] = useState(DEFAULT_TITLE);

  useEffect(() => {
    const controller = new AbortController();

    fetchConfig(controller.signal)
      .then((config) => {
        setTitle(config.title);
        document.title = config.title;
      })
      .catch(() => {
        // Keep the default title; no blank header, no crash.
      });

    return () => controller.abort();
  }, []);

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
        <h1>
          <img className="logo" src={logo} alt="" />
          {title}
        </h1>
        <div className="header-meta">
          {updatedAt && (
            <span className="muted">
              <span className="live-dot" aria-hidden="true" />
              Updated {updatedAt.toLocaleTimeString()}
            </span>
          )}
          <ThemeToggle />
        </div>
      </header>
      {error && (
        <p className="banner banner-error" role="alert">
          Could not load status: {error}
        </p>
      )}
      {families === null && !error && <p className="muted">Loading…</p>}
      {families !== null && families.length === 0 && <p className="muted">No model families configured.</p>}
      {families !== null && families.length > 0 && (
        <>
          <section className="card">
            <LatencyPanel title="Latency overview" />
          </section>
          <Accordion families={families} />
        </>
      )}
    </main>
  );
}
