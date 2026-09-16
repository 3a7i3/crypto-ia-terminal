import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MarketView } from "../views/MarketView";

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

function marketSnapshot(freshness: "FRESH" | "STALE" = "FRESH") {
  return {
    schema_version: "1.0.0",
    product: "CryptoRadar",
    domain: "market",
    authority: "OBSERVATIONAL_TELEMETRY",
    mode: "OBSERVATION",
    generated_at_utc: "2026-09-14T20:00:00Z",
    source_updated_at_utc: "2026-09-14T19:59:00Z",
    window_hours: 24,
    min_confidence: 65,
    packets_observed: 5,
    market_regime: "bull_trend",
    universe_size: 2,
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
    snapshot_age_s: freshness === "FRESH" ? 20 : 120,
    freshness_classification: freshness,
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("MarketView", () => {
  it("renders the same CryptoRadar opportunity truth for desktop and mobile without execution levels", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(marketSnapshot())));
    render(<MarketView />);

    await waitFor(() => expect(screen.getByTestId("market-freshness")).toHaveTextContent("FRESH"));
    const view = screen.getByTestId("market-view");
    expect(view).toHaveTextContent("OBSERVATIONAL_TELEMETRY");
    expect(view).toHaveTextContent("rolling 24h observation window");
    expect(view).toHaveTextContent("display classification only");

    const row = screen.getByTestId("market-opportunity-row");
    const card = screen.getByTestId("market-opportunity-card");
    for (const expected of ["BTC/USDT", "75.0", "80.0", "LONG", "100%", "2", "bull_trend"]) {
      expect(row).toHaveTextContent(expected);
      expect(card).toHaveTextContent(expected);
    }

    expect(screen.getByTestId("market-opportunity-cards")).toBeInTheDocument();
    expect(view).not.toHaveTextContent("Entry");
    expect(view).not.toHaveTextContent("Stop Loss");
    expect(view).not.toHaveTextContent("Take Profit");
    expect(view).not.toHaveTextContent("trade_allowed");
  });

  it("renders stale evidence explicitly", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(marketSnapshot("STALE"))));
    render(<MarketView />);

    await waitFor(() => expect(screen.getByTestId("market-freshness")).toHaveTextContent("STALE"));
    expect(screen.getByTestId("market-view")).toHaveTextContent("120s");
  });

  it("keeps provenance inspectable without changing source values", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(marketSnapshot())));
    render(<MarketView />);

    await waitFor(() => expect(screen.getByText("Provenance & source timing")).toBeInTheDocument());
    const view = screen.getByTestId("market-view");
    expect(view).toHaveTextContent("2026-09-14 20:00:00Z");
    expect(view).toHaveTextContent("2026-09-14 19:59:00Z");
  });

  it("renders explicit API failure rather than an empty healthy market", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          { error_code: "MARKET_SNAPSHOT_MISSING", error_message: "missing" },
          503,
        ),
      ),
    );
    render(<MarketView />);

    await waitFor(() => expect(screen.getByTestId("market-error")).toBeInTheDocument());
    expect(screen.getByTestId("market-view")).toHaveTextContent("MARKET_SNAPSHOT_MISSING");
  });
});
