import type { MicrostructureDetail } from "./marketMicrostructureDetail";
export type MicrostructureFreshness = "FRESH" | "STALE" | "UNKNOWN" | "NOT_AVAILABLE";
export interface MicrostructureRow {
  detail?: MicrostructureDetail | null;
  symbol: string;
  stream_requested: boolean;
  availability: "OBSERVED" | "UNAVAILABLE";
  unavailable_reason: "SOURCE_UNAVAILABLE" | "NO_OBSERVATION" | null;
  observed_at_utc: string | null;
  state: string | null;
  state_confidence: number | null;
  price: number | null;
  price_change_bps: number | null;
  buy_pressure_pct: number | null;
  sell_pressure_pct: number | null;
  buy_flow_usd: number | null;
  sell_flow_usd: number | null;
  total_flow_usd: number | null;
  resistance: number | null;
  fragility: number | null;
  flow_window_ms: number | null;
  notable: boolean | null;
  observation_age_s: number | null;
  freshness_classification: MicrostructureFreshness;
}
export interface MarketMicrostructureSnapshot {
  schema_version: "1.0.0" | "1.1.0";
  product: "MarketMicrostructureSnapshot";
  domain: "market_microstructure";
  authority: "OBSERVATIONAL_TELEMETRY";
  mode: "READ_ONLY";
  generated_at_utc: string;
  source_updated_at_utc: string;
  source_artifact_sha256: string;
  exchange: "mexc" | "binance";
  unit_contract_source: "api" | "fallback" | "mixed" | "unknown";
  unit_contract_degraded: boolean | null;
  pressure_field_count: number | null;
  coverage: { requested: number; streamable: number; observed: number; unavailable: number };
  rows: MicrostructureRow[];
  read_at_utc: string;
  source_age_s: number;
  freshness_classification: "FRESH" | "STALE";
}
