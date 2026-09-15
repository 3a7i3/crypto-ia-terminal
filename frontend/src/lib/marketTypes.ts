export type MarketFreshness = "FRESH" | "STALE";

export interface MarketOpportunity {
  symbol: string;
  avg_confidence: number;
  max_confidence: number;
  n_signals: number;
  dominant_side: "LONG" | "SHORT" | "MIXED";
  dominance_pct: number;
  regime: string;
}

export interface MarketRadarSnapshot {
  schema_version: "1.0.0";
  product: "CryptoRadar";
  domain: "market";
  authority: "OBSERVATIONAL_TELEMETRY";
  mode: "OBSERVATION";
  generated_at_utc: string;
  source_updated_at_utc: string | null;
  window_hours: number;
  min_confidence: number;
  packets_observed: number;
  market_regime: string | null;
  universe_size: number;
  actionable_count: number;
  watchlist_count: number;
  top_opportunities: MarketOpportunity[];
  snapshot_age_s: number;
  freshness_classification: MarketFreshness;
}
