import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { Accordion } from "./components/Accordion";
import { families } from "./test/fixtures";

describe("Accordion", () => {
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
    expect(segments[2].getAttribute("title")).toMatch(/available$/);
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
    expect(rows[0]).toHaveTextContent("NameProviderCompanyHistory");
    expect(rows[1]).toHaveTextContent("claude-sonnet-5GoogleAnthropic");
    expect(within(rows[2]).getByRole("img")).toHaveAttribute("title", "Timeout after 30s");

    // Each model row also gets its own small timeline, driven by that model's own history.
    const modelSegments = within(rows[2]).getAllByTitle(/unavailable$/);
    expect(modelSegments).toHaveLength(2);
    expect(modelSegments[0]).toHaveClass("timeline-segment", "status-no");
  });
});

describe("App", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads families from the API", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(families), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
    expect(await screen.findByText("Claude")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/families", expect.anything());
  });

  it("shows an error when the request fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 500, statusText: "Server Error" })));

    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("500");
  });
});
