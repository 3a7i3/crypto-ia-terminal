import { describe, expect, it } from "vitest";
import { validateMarketRadarSnapshot } from "../lib/marketValidation";

function marketSnapshot() {
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
    snapshot_age_s: 20,
    freshness_classification: "FRESH",
  };
}

describe("validateMarketRadarSnapshot", () => {
  it("accepts the certified observational MARKET shape", () => {
    expect(validateMarketRadarSnapshot(marketSnapshot())).toBe(true);
  });

  it("rejects execution authority", () => {
    const bad = marketSnapshot();
    bad.authority = "EXECUTION_AUTHORITY";
    expect(validateMarketRadarSnapshot(bad)).toBe(false);
  });

  it("rejects Entry/SL/TP-shaped opportunity enrichment", () => {
    const bad = marketSnapshot();
    (bad.top_opportunities[0] as unknown as Record<string, unknown>).entry = 100;
    expect(validateMarketRadarSnapshot(bad)).toBe(false);
  });

  it("rejects an invented freshness state", () => {
    const bad = marketSnapshot();
    bad.freshness_classification = "CURRENT";
    expect(validateMarketRadarSnapshot(bad)).toBe(false);
  });
});
