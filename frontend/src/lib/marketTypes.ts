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

export interface MarketCatalogueCoverage {
  start_at_utc: string;
  end_at_utc: string;
  input_packets: number;
  included_packets: number;
  outside_window_packets: number;
  future_packets: number;
  unresolved_timestamp_packets: number;
}

export interface MarketCatalogue {
  population: "ALL_OBSERVED_PACKETS";
  rows: MarketOpportunity[];
  qualified_rows: MarketOpportunity[];
  coverage: MarketCatalogueCoverage;
}

export interface MarketRadarSnapshot {
  schema_version: "1.0.0" | "1.1.0";
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
  catalogue?: MarketCatalogue;
  snapshot_age_s: number;
  freshness_classification: MarketFreshness;
}
