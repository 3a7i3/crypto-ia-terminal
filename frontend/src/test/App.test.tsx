import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import App from "../App";
import { baseSnapshot } from "./fixtures";

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

function baseMarketSnapshot() {
  return {
    schema_version: "1.0.0",
    product: "CryptoRadar",
    domain: "market",
    authority: "OBSERVATIONAL_TELEMETRY",
    mode: "OBSERVATION",
    generated_at_utc: "2026-09-14T20:00:00Z",
    source_updated_at_utc: "2026-09-14T19:59:30Z",
    window_hours: 24,
    min_confidence: 65,
    packets_observed: 12,
    market_regime: "bull_trend",
    universe_size: 3,
    actionable_count: 1,
    watchlist_count: 1,
    top_opportunities: [
      {
        symbol: "BTC/USDT",
        avg_confidence: 75,
        max_confidence: 80,
        n_signals: 2,
        dominant_side: "LONG",
        dominance_pct: 100,
        regime: "bull_trend",
      },
    ],
    snapshot_age_s: 20,
    freshness_classification: "FRESH",
  };
}

describe("App", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/operator/v1/market") return Promise.resolve(jsonResponse(baseMarketSnapshot()));
      return Promise.resolve(jsonResponse(baseSnapshot()));
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("feeds the canonical advisor panels from a single snapshot fetch", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("overview-view")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("tab-portfolio"));
    expect(screen.getByTestId("portfolio-view")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("tab-decisions"));
    expect(screen.getByTestId("decisions-view")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("tab-system"));
    expect(screen.getByTestId("system-view")).toBeInTheDocument();

    // WEB-01-MARKET is the only explicit cross-process exception. None of
    // these canonical advisor panels triggers any second per-panel request.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("renders real MARKET telemetry while Scores remains NOT_EXPOSED", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("overview-view")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("tab-market"));
    await waitFor(() => expect(screen.getByTestId("market-freshness")).toHaveTextContent("FRESH"));
    expect(screen.getByTestId("market-view")).toHaveTextContent("CryptoRadar");
    expect(screen.getByTestId("market-view")).toHaveTextContent("BTC/USDT");
    expect(screen.queryByTestId("not-exposed-label")).toBeNull();

    // Canonical snapshot + MARKET subrouter fetch.
    expect(fetchMock).toHaveBeenCalledTimes(2);

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

  it('never displays a string "false" boot_alive as true — the typed gate rejects it before render', async () => {
    const snap = baseSnapshot();
    snap.system_health.boot_alive = { value: "false", semantics: "PRESENT" } as never;
    fetchMock.mockResolvedValue(jsonResponse(snap));

    expect(() => render(<App />)).not.toThrow();
    await waitFor(() => expect(screen.getByTestId("snapshot-status-transport-error")).toBeInTheDocument());
    expect(screen.queryByTestId("system-view")).toBeNull();
    expect(screen.getByTestId("no-snapshot")).toBeInTheDocument();
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
