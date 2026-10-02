export type BurnInDeadlineState =
  | "BEFORE_TIMEOUT"
  | "RECOVERY_WINDOW"
  | "RECOVERY_EXPIRED"
  | "NOT_AVAILABLE";

export type BurnInLifecycleStatus = "OPEN" | "CLOSED" | "UNRESOLVED";

export interface BurnInScientificT0 {
  status: "PRESENT" | "NOT_AVAILABLE";
  value_utc: string | null;
  source: string | null;
}

export interface BurnInEventCounts {
  EPOCH_CREATED: number;
  POSITION_OPENED: number;
  POSITION_CLOSED: number;
  POSITION_UNRESOLVED: number;
  RECOVERY_COMPLETED: number;
}

export interface BurnInLifecycleCounts {
  open: number;
  closed: number;
  unresolved: number;
  total: number;
}

export interface BurnInLastEvent {
  sequence: number;
  event_type:
    | "EPOCH_CREATED"
    | "POSITION_OPENED"
    | "POSITION_CLOSED"
    | "POSITION_UNRESOLVED"
    | "RECOVERY_COMPLETED";
  timestamp_utc: string;
  trade_id: string | null;
  decision_id: string | null;
}

export interface BurnInOpenLifecycle {
  trade_id: string;
  decision_id: string | null;
  symbol: string;
  side: "LONG" | "SHORT";
  principal_usd: number;
  entry_price: number;
  entry_fee_usd: number;
  opened_sequence: number;
  opened_at_utc: string;
  age_seconds: number;
  tp_price: number | null;
  sl_price: number | null;
  timeout_at_utc: string | null;
  recovery_eligible_until_utc: string | null;
  deadline_state: BurnInDeadlineState;
}

export interface BurnInHistoryRow {
  trade_id: string;
  open_decision_id: string | null;
  terminal_decision_id: string | null;
  symbol: string;
  side: "LONG" | "SHORT";
  principal_usd: number;
  entry_price: number;
  entry_fee_usd: number;
  opened_sequence: number;
  opened_at_utc: string;
  status: BurnInLifecycleStatus;
  terminal_sequence: number | null;
  terminal_at_utc: string | null;
  exit_price: number | null;
  exit_fee_usd: number | null;
  gross_pnl_usd: number | null;
  net_realized_pnl_usd: number | null;
  unresolved_reason: string | null;
  duration_seconds: number | null;
}

export interface BurnInFrozenConfig {
  snapshot_schema: "BURN_IN_EXPERIMENT_CONFIG_V1";
  snapshot_sha256: string;
  runtime_source_sha: string;
  pb_max_positions: string;
  paper_portfolio_brain_level: string;
  mexc_sim_max_position_usd: string;
  mexc_sim_max_age_h: string;
  paper_lifecycle_authority: string;
}

export interface BurnInStatusSnapshot {
  schema_version: "1.0.0";
  product: "BurnInStatusSnapshot";
  domain: "burn_in";
  authority: "PPL_AUTHORITY_PRESENTATION";
  mode: "READ_ONLY";
  generated_at_utc: string;
  source_updated_at_utc: string;
  paper_epoch_id: string;
  epoch_created_at_utc: string;
  source_code_sha: string;
  config_snapshot_hash: string;
  ppl_stream_sha256: string;
  scientific_t0: BurnInScientificT0;
  event_count: number;
  last_sequence: number;
  event_counts: BurnInEventCounts;
  lifecycle_counts: BurnInLifecycleCounts;
  last_event: BurnInLastEvent;
  open_lifecycles: BurnInOpenLifecycle[];
  lifecycle_history: BurnInHistoryRow[];
  history_order: "OPEN_SEQUENCE_DESC";
  frozen_config: BurnInFrozenConfig;
  finalization: {
    state: "NOT_AVAILABLE";
    reason: string;
  };
  snapshot_age_s: number;
  freshness_classification: "FRESH" | "STALE";
}
