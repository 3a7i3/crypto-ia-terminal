import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import App from "../App";
import { baseSnapshot } from "./fixtures";

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

describe("App", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue(jsonResponse(baseSnapshot()));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("feeds every panel from a single canonical snapshot fetch", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("overview-view")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("tab-portfolio"));
    expect(screen.getByTestId("portfolio-view")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("tab-decisions"));
    expect(screen.getByTestId("decisions-view")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("tab-system"));
    expect(screen.getByTestId("system-view")).toBeInTheDocument();

    // Only one fetch was ever made — switching tabs never triggers a
    // second, per-panel request.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("presents Market and Scores as NOT_EXPOSED, with no demo/fabricated data", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("overview-view")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("tab-market"));
    expect(screen.getByTestId("not-exposed-label")).toHaveTextContent("NOT_EXPOSED");

    fireEvent.click(screen.getByTestId("tab-scores"));
    expect(screen.getByTestId("not-exposed-label")).toHaveTextContent("NOT_EXPOSED");
    const text = screen.getByTestId("not-exposed-view").textContent ?? "";
    expect(text).not.toMatch(/\d+%\s*win/i);
    expect(text).not.toMatch(/expectancy|equity_curve/i);
  });

  it("renders the canonical portfolio mode without a PAPER fallback for UNKNOWN", async () => {
    fetchMock.mockResolvedValue(jsonResponse(baseSnapshot({ portfolio: { ...baseSnapshot().portfolio, mode: "UNKNOWN" } })));
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("mode-badge")).toHaveAttribute("data-mode", "UNKNOWN"));
  });
});
