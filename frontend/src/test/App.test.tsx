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

function basePplComparisonSnapshot() {
  return {
    schema_version: "1.0.0",
    product: "PPLComparator",
    domain: "ppl_comparison",
    authority: "OBSERVATIONAL_TELEMETRY",
    mode: "SHADOW_COMPARISON",
    generated_at_utc: "2026-09-18T01:00:00Z",
    process_instance_id: "proc-1",
    cycle: 42,
    source_sha: "a".repeat(40),
    shadow_status: "ACTIVE",
    paper_epoch_id: "epoch-1",
    comparison_available: true,
    comparison_unavailable_reason: null,
    legacy_source: { source: "MEXC_SIM", authority: "PAPER_AUTHORITY", scope: "live_process_state" },
    ppl_source: { source: "PPL", authority: "NONE", scope: "configured_shadow_epoch", last_error: null },
    summary: {
      total: 1, comparable: 1, partial: 0, unresolved: 0,
      equal: 0, different: 1, legacy_only: 0, ppl_only: 0, not_comparable: 0,
    },
    comparisons: [
      {
        comparison_id: "web02-cash",
        domain: "accounting",
        field: "free_cash",
        trade_id: null,
        classification: "COMPARABLE",
        relation: "DIFFERENT",
        legacy: { value: 678.46, status: "PRESENT", provenance: "MEXC_SIM._capital" },
        ppl: { value: 678.4625, status: "PRESENT", provenance: "PPL.projection.available_cash" },
        delta_ppl_minus_legacy: 0.0025,
        comparison_rule: "numeric_abs_tol_1e-9",
        note: "raw divergence",
      },
    ],
    positions: [],
    closed_session: [],
    ppl_events: [],
    snapshot_age_s: 10,
    freshness_classification: "FRESH",
  };
}

describe("App", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/operator/v1/market") return Promise.resolve(jsonResponse(baseMarketSnapshot()));
      if (url === "/api/operator/v1/ppl-comparison") return Promise.resolve(jsonResponse(basePplComparisonSnapshot()));
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

    // None of these canonical advisor panels triggers an independent-domain
    // request. MARKET and WEB-02 PPL fetch only when their tabs mount.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("renders WEB-02 as an independent observational domain", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("overview-view")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("tab-ppl"));
    await waitFor(() => expect(screen.getByTestId("ppl-comparison-view")).toHaveTextContent("Legacy PAPER"));
    expect(screen.getByTestId("ppl-domain-badge")).toHaveTextContent("PPL SHADOW");
    expect(screen.queryByTestId("mode-badge")).toBeNull();
    expect(screen.getByTestId("ppl-comparison-view")).toHaveTextContent("678.46");
    expect(fetchMock).toHaveBeenCalledWith("/api/operator/v1/ppl-comparison", { method: "GET" });
  });

  it("renders real MARKET telemetry while Scores remains NOT_EXPOSED", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByTestId("overview-view")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("tab-market"));
    await waitFor(() => expect(screen.getByTestId("market-freshness")).toHaveTextContent("FRESH"));
    expect(screen.getByTestId("market-domain-badge")).toHaveTextContent("MARKET");
    expect(screen.queryByTestId("mode-badge")).toBeNull();
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

  it("keeps MARKET independently healthy when the canonical snapshot is explicitly missing", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/operator/v1/market") return Promise.resolve(jsonResponse(baseMarketSnapshot()));
      return Promise.resolve(jsonResponse({ error_code: "SNAPSHOT_MISSING", error_message: "canonical artifact absent" }, 503));
    });

    render(<App />);
    await waitFor(() => expect(screen.getByTestId("snapshot-status-api-error")).toHaveTextContent("SNAPSHOT_MISSING"));
    expect(screen.getByTestId("no-snapshot")).toHaveTextContent("UNRESOLVED");

    fireEvent.click(screen.getByTestId("tab-market"));
    await waitFor(() => expect(screen.getByTestId("market-freshness")).toHaveTextContent("FRESH"));
    expect(screen.queryByTestId("snapshot-status-api-error")).toBeNull();
    expect(screen.getByTestId("market-canonical-context")).toHaveTextContent("SNAPSHOT_MISSING");
    expect(screen.getByTestId("market-canonical-context")).toHaveTextContent("separate observational domain");
    expect(screen.getByTestId("market-view")).toHaveTextContent("OBSERVATIONAL_TELEMETRY");
    expect(screen.queryByTestId("overview-view")).toBeNull();

    // The canonical truth is not hidden; it returns with the canonical domain.
    fireEvent.click(screen.getByTestId("tab-overview"));
    expect(screen.getByTestId("snapshot-status-api-error")).toHaveTextContent("SNAPSHOT_MISSING");
    expect(screen.getByTestId("no-snapshot")).toHaveTextContent("UNRESOLVED");
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
