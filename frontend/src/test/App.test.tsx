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

  // O-02W-D2-R1.1 case 16 — a malformed `status` and a malformed position
  // field must be rejected by the admission gate BEFORE React attempts to
  // render them: the app must never throw and must never show a success
  // panel for either body.
  it("never renders (and never throws) when portfolio.status is malformed", async () => {
    const snap = baseSnapshot();
    (snap.portfolio as unknown as Record<string, unknown>).status = { bad: true };
    fetchMock.mockResolvedValue(jsonResponse(snap));

    expect(() => render(<App />)).not.toThrow();
    await waitFor(() => expect(screen.getByTestId("snapshot-status-transport-error")).toBeInTheDocument());
    expect(screen.queryByTestId("overview-view")).toBeNull();
    expect(screen.getByTestId("no-snapshot")).toBeInTheDocument();
  });

  it("never renders (and never throws) when an open position field is malformed", async () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = {
      semantics: "PRESENT",
      value: [
        {
          position_id: "p1",
          symbol: "BTCUSDT",
          side: { bad: true },
          size_usd: 100,
          entry_price: 50000,
          current_price: { value: 51000, semantics: "PRESENT" },
          current_price_observed_at_utc: null,
          tp_price: null,
          sl_price: null,
          tp_sl_source: "original",
          unrealized_pnl_usd: { value: 20, semantics: "PRESENT" },
          unrealized_pnl_pct: { value: 2, semantics: "PRESENT" },
          opened_at: null,
          regime: { value: "TREND_BULL", semantics: "PRESENT" },
          restored_without_regime: false,
          personality: null,
          restored: false,
        },
      ],
    } as never;
    fetchMock.mockResolvedValue(jsonResponse(snap));

    expect(() => render(<App />)).not.toThrow();
    await waitFor(() => expect(screen.getByTestId("snapshot-status-transport-error")).toBeInTheDocument());
    expect(screen.queryByTestId("portfolio-view")).toBeNull();
    expect(screen.getByTestId("no-snapshot")).toBeInTheDocument();
  });

  // O-02W-D2-R1.2 render regression — a string `"false"` must never reach a
  // boolean render callback and must never be displayed as `true` via JS
  // truthiness. The typed admission gate rejects the whole snapshot before
  // SystemView/DecisionsView ever mount, so no "true" text for a supplied
  // "false" string can ever appear anywhere in the document.
  it('never displays a string "false" boot_alive as true — the typed gate rejects it before render', async () => {
    const snap = baseSnapshot();
    snap.system_health.boot_alive = { value: "false", semantics: "PRESENT" } as never;
    fetchMock.mockResolvedValue(jsonResponse(snap));

    expect(() => render(<App />)).not.toThrow();
    await waitFor(() => expect(screen.getByTestId("snapshot-status-transport-error")).toBeInTheDocument());
    expect(screen.queryByTestId("system-view")).toBeNull();
    expect(screen.getByTestId("no-snapshot")).toBeInTheDocument();
    // No "true" boolean-rendered boot_alive value anywhere in the document —
    // the malformed body never reached ObservedValueView's boolean callback.
    expect(document.body.textContent ?? "").not.toMatch(/\btrue\b/);
  });

  it('never displays a string "false" is_actionable as true — the typed gate rejects it before render', async () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.per_symbol_decisions = [
      {
        symbol: "ETHUSDT",
        packet_id: null,
        context_id: null,
        created_cycle_id: null,
        created_at: { value: null, semantics: "UNKNOWN" },
        latest_transition_at_utc: { value: null, semantics: "UNKNOWN" },
        side: { value: null, semantics: "UNKNOWN" },
        confidence_raw: { value: null, semantics: "UNKNOWN" },
        confidence_adjusted: { value: null, semantics: "UNKNOWN" },
        regime: { value: null, semantics: "UNKNOWN" },
        lifecycle_state: { value: null, semantics: "UNKNOWN" },
        is_actionable: { value: "false", semantics: "PRESENT", authority: "EXECUTION_AUTHORITY" },
        trade_allowed: { value: null, semantics: "UNKNOWN", authority: "OBSERVATIONAL_TELEMETRY" },
        first_blocker: { value: null, semantics: "UNKNOWN", authority: "OBSERVATIONAL_TELEMETRY" },
      },
    ] as never;
    fetchMock.mockResolvedValue(jsonResponse(snap));

    expect(() => render(<App />)).not.toThrow();
    await waitFor(() => expect(screen.getByTestId("snapshot-status-transport-error")).toBeInTheDocument());
    expect(screen.queryByTestId("decisions-view")).toBeNull();
    expect(screen.getByTestId("no-snapshot")).toBeInTheDocument();
    expect(document.body.textContent ?? "").not.toMatch(/\btrue\b/);
  });
});
