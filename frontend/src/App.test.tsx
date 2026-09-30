import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { Accordion } from "./components/Accordion";
import { families, latencyResponse } from "./test/fixtures";

describe("Accordion", () => {
  beforeEach(() => {
    stubFetch();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders one panel per family with timeline visible while collapsed", () => {
    const { container } = render(<Accordion families={families} />);

    const heads = screen.getAllByRole("button");
    expect(heads).toHaveLength(3);
    expect(heads[0]).toHaveTextContent("Claude");
    expect(heads[0]).toHaveAttribute("aria-expanded", "false");

    // Scoped to each panel's own family-level timeline, not the nested per-model ones.
    const segments = container.querySelectorAll(".panel > .timeline .timeline-segment");
    // 3 points for Claude, the grey placeholder for GPT, 1 point for Partial.
    expect(segments).toHaveLength(5);
    expect(segments[0]).toHaveClass("status-no");
    expect(segments[2]).toHaveClass("status-yes");
    expect(segments[3]).toHaveClass("status-unknown");
    expect(segments[2].getAttribute("data-tooltip")).toMatch(/available$/);
    expect(segments[4]).toHaveClass("status-partial");

    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("opens multiple panels independently and shows the model columns", () => {
    render(<Accordion families={families} />);
    const [claude, gpt] = screen.getAllByRole("button");

    fireEvent.click(claude);
    fireEvent.click(gpt);
    const tables = screen.getAllByRole("table");
    expect(tables).toHaveLength(2);

    const rows = within(tables[0]).getAllByRole("row");
    expect(rows[0]).toHaveTextContent("NameCompanyLatencyUptimeHistory");
    // The History header carries a note that its window differs from the family timeline above.
    expect(within(rows[0]).getByText("History")).toHaveAttribute("title", expect.stringMatching(/window/));
    expect(rows[1]).toHaveTextContent("claude-sonnet-5Anthropic812 ms100%");
    expect(rows[2]).toHaveTextContent("claude-opus-5Anthropic—0%");
    expect(within(rows[2]).getByRole("img")).toHaveAttribute("data-tooltip", "Timeout after 30s");

    // Each model row also gets its own small timeline, driven by that model's own history.
    const modelSegments = rows[2].querySelectorAll(".timeline-segment");
    expect(modelSegments).toHaveLength(2);
    expect(modelSegments[0]).toHaveClass("timeline-segment", "status-no");
    // History-cell tooltips are enriched with latency (yes) or error (no); family ones are not.
    expect(modelSegments[0].getAttribute("data-tooltip")).toContain("Timeout after 30s");
    const successSegments = rows[1].querySelectorAll(".timeline-segment");
    expect(successSegments[0].getAttribute("data-tooltip")).toMatch(/790 ms$/);
  });

  it("shows the family latency chart only while the panel is open, and switches spans", async () => {
    const fetchMock = stubFetch();
    render(<Accordion families={families} />);
    expect(fetchMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getAllByRole("button")[0]);
    expect(await screen.findByRole("img", { name: "Family latency, Live" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenLastCalledWith(expect.stringMatching(/span=live.*family=Claude/), expect.anything());
    expect(screen.queryByRole("combobox", { name: "Lookback" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Hour of day" }));
    expect(await screen.findByRole("img", { name: "Family latency, Hour of day" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenLastCalledWith(expect.stringMatching(/span=hour&days=30/), expect.anything());

    fireEvent.change(screen.getByRole("combobox", { name: "Lookback" }), { target: { value: "90" } });
    expect(fetchMock).toHaveBeenLastCalledWith(expect.stringMatching(/span=hour&days=90/), expect.anything());
  });

  it("expands a model row into its full-length health bar and latency chart", async () => {
    const fetchMock = stubFetch();
    const { container } = render(<Accordion families={families} />);
    fireEvent.click(screen.getAllByRole("button")[0]);

    const toggle = screen.getByRole("button", { name: "claude-sonnet-5" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    expect(await screen.findByRole("img", { name: "Latency, Live" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringMatching(/model=claude-sonnet-5/), expect.anything());
    // Four live rounds from the latency API, more than the row's own two-round model history.
    const detailSegments = container.querySelectorAll(".model-detail .timeline-segment");
    expect(detailSegments).toHaveLength(4);
    expect(detailSegments[1]).toHaveClass("status-no");
    expect(detailSegments[1].getAttribute("data-tooltip")).toContain("down");

    fireEvent.click(toggle);
    expect(container.querySelector(".model-detail")).not.toBeInTheDocument();
  });
});

function stubFetch(config: { ok: boolean; title?: string } = { ok: true, title: "Gateway Health Check" }) {
  const fetchMock = vi.fn((url: string) => {
    if (url.startsWith("/api/latency")) {
      return Promise.resolve(new Response(JSON.stringify(latencyResponse(url)), { status: 200 }));
    }
    if (url === "/api/config") {
      return Promise.resolve(
        config.ok
          ? new Response(JSON.stringify({ title: config.title }), { status: 200 })
          : new Response("", { status: 500, statusText: "Server Error" }),
      );
    }
    return Promise.resolve(new Response(JSON.stringify(families), { status: 200 }));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("App", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads families from the API", async () => {
    const fetchMock = stubFetch();

    render(<App />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
    expect(await screen.findByText("Claude")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/families", expect.anything());
  });

  it("shows the cross-family latency overview with one stats row per family", async () => {
    stubFetch();

    render(<App />);
    expect(await screen.findByRole("img", { name: "Latency overview, Live" })).toBeInTheDocument();
    const stats = screen.getByRole("table");
    const rows = within(stats).getAllByRole("row");
    expect(rows[0]).toHaveTextContent("FamilyAvgp95Checks");
    expect(rows.slice(1).map((row) => row.textContent)).toEqual([
      "Claude120 ms130 ms3",
      "GPT120 ms130 ms3",
      "Partial120 ms130 ms3",
    ]);
  });

  it("shows an error when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) =>
        Promise.resolve(
          url === "/api/config"
            ? new Response(JSON.stringify({ title: "Gateway Health Check" }), { status: 200 })
            : new Response("", { status: 500, statusText: "Server Error" }),
        ),
      ),
    );

    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("500");
  });

  it("shows the default title before the config fetch resolves and updates once it does", async () => {
    stubFetch({ ok: true, title: "Acme Gateway" });

    render(<App />);
    expect(screen.getByRole("heading", { name: "Gateway Health Check" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Acme Gateway" })).toBeInTheDocument();
    expect(document.title).toBe("Acme Gateway");
  });

  it("toggles the theme from the header and remembers the choice", async () => {
    stubFetch();
    localStorage.removeItem("theme");

    render(<App />);
    // jsdom has no matchMedia, so the system theme resolves to light.
    fireEvent.click(screen.getByRole("button", { name: "Switch to dark theme" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("theme")).toBe("dark");

    fireEvent.click(screen.getByRole("button", { name: "Switch to light theme" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem("theme")).toBe("light");
    await screen.findByText("Claude");
  });

  it("falls back to the default title when the config fetch fails", async () => {
    stubFetch({ ok: false });

    render(<App />);
    await screen.findByText("Claude");
    expect(screen.getByRole("heading", { name: "Gateway Health Check" })).toBeInTheDocument();
  });
});
