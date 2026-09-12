// ── Canonical operator snapshot types ────────────────────────────────────────
// Mirrors GET /api/operator/v1/snapshot (O-02W-D1 API, O-02W-C producer).
// The cockpit never recomputes, corrects, enriches, or infers any of this —
// it only renders producer-supplied values and their provenance.

import type { ObservedValue } from "./lib/observedValue";

export type InstanceRelation = "CURRENT_INSTANCE" | "PREVIOUS_INSTANCE" | "UNKNOWN";
export type RuntimeState = "CURRENT" | "LAST_KNOWN";
export type WorktreeState = "CLEAN" | "DIRTY" | "UNKNOWN";
export type DeploymentEvidenceStatus = "VERIFIED" | "CLAIMED_ONLY" | "UNKNOWN";
export type RuntimeShaEvidenceStatus = "VERIFIED" | "CLAIMED_ONLY" | "UNKNOWN";
export type PortfolioMode = "PAPER" | "REAL_API" | "TESTNET_API" | "UNKNOWN";
export type Authority = "EXECUTION_AUTHORITY" | "OBSERVATIONAL_TELEMETRY" | "DECISION_OUTCOME_EVIDENCE" | string;

export interface DeploymentEvidence {
  status: DeploymentEvidenceStatus;
  source: string | null;
  evidence_ref: string | null;
  observed_at_utc: string | null;
}

export interface OpenPosition {
  position_id: string;
  symbol: string;
  side: string | null;
  size_usd: number | null;
  entry_price: number | null;
  current_price: ObservedValue<number>;
  current_price_observed_at_utc: string | null;
  tp_price: number | null;
  sl_price: number | null;
  // REM-C R1.3: "restored_original" — position was restored from the
  // ledger AND its TP/SL were durably recorded evidence (schema v4), not
  // a reconstructed default. Distinct from "restored_default" (genuinely
  // reconstructed) and "original" (never restored at all).
  tp_sl_source: "original" | "restored_default" | "restored_original" | string;
  unrealized_pnl_usd: ObservedValue<number>;
  unrealized_pnl_pct: ObservedValue<number>;
  opened_at: number | null; // epoch seconds (MexcPosition.opened_ts) — never an ISO string, per contract §5/§19
  regime: ObservedValue<string>;
  restored_without_regime: boolean;
  personality: string | null;
  restored: boolean;
  restored_evidence_gaps?: string[];
}

export interface PortfolioDomain {
  domain: string;
  observed_at_utc: string;
  source: string;
  freshness: string;
  status: string;
  schema_version: string;
  source_version: string | null;
  evidence: Record<string, unknown>;
  source_updated_at_utc: ObservedValue<string>;
  authority: Authority;
  mode: PortfolioMode;
  paper_equity_usd: ObservedValue<number>;
  paper_open_positions_count: ObservedValue<number>;
  paper_unrealized_pnl_usd: ObservedValue<number>;
  paper_realized_pnl_usd: ObservedValue<number>;
  real_account_equity_usd: ObservedValue<number>;
  real_account_free_usd: ObservedValue<number>;
  real_account_stale: ObservedValue<boolean>;
  real_account_last_poll_utc: ObservedValue<string>;
  non_paper_wallet_balance_usd: ObservedValue<number>;
  capital_x_usd: ObservedValue<number>;
  open_positions: ObservedValue<OpenPosition[]>;
  portfolio_status?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface PerSymbolDecision {
  symbol: string;
  packet_id: string | null;
  context_id: string | null;
  created_cycle_id: string | null;
  created_at: ObservedValue<string>;
  latest_transition_at_utc: ObservedValue<string>;
  side: ObservedValue<string>;
  confidence_raw: ObservedValue<number>;
  confidence_adjusted: ObservedValue<number>;
  regime: ObservedValue<string>;
  lifecycle_state: ObservedValue<string>;
  is_actionable: ObservedValue<boolean> & { authority: Authority };
  trade_allowed: ObservedValue<boolean> & { authority: Authority };
  first_blocker: ObservedValue<string> & { authority: Authority };
}

export interface DecisionPipelineDomain {
  domain: string;
  observed_at_utc: string;
  source: string;
  freshness: string;
  status: string;
  schema_version: string;
  source_version: string | null;
  evidence: Record<string, unknown>;
  source_updated_at_utc: ObservedValue<string>;
  authority: Authority;
  stages: unknown[];
  trade_allowed: ObservedValue<boolean>;
  first_blocker: ObservedValue<string>;
  per_symbol_decisions: PerSymbolDecision[];
  [key: string]: unknown;
}

export interface SystemHealthDomain {
  domain: string;
  observed_at_utc: string;
  source: string;
  freshness: string;
  status: string;
  schema_version: string;
  source_version: string | null;
  evidence: Record<string, unknown>;
  source_updated_at_utc: ObservedValue<string>;
  authority: Authority;
  boot_alive: ObservedValue<boolean>;
  health_score: ObservedValue<number>;
  health_level: ObservedValue<string>;
  exchange_connectivity_healthy: ObservedValue<boolean>;
  exchange_latency_ms: ObservedValue<number>;
  module_statuses: Record<string, unknown>;
  [key: string]: unknown;
}

export interface OperatorSnapshot {
  schema_version: string;
  snapshot_id: string;
  cycle: number;
  process_instance_id: string;
  generated_at_utc: string;
  source_sha: string | null;
  worktree_state: WorktreeState;
  deployment_evidence: DeploymentEvidence;
  runtime_sha_evidence_status: RuntimeShaEvidenceStatus;
  portfolio: PortfolioDomain;
  decision_pipeline: DecisionPipelineDomain;
  system_health: SystemHealthDomain;
  // Reader-supplied evidence (never producer-authored), merged onto the
  // envelope by the API's /api/operator/v1/snapshot route:
  instance_relation: InstanceRelation;
  runtime_state: RuntimeState;
  stale_reason: string | null;
  snapshot_age_s: number | null;
  freshness_classification: string;
}

export interface ApiStructuredError {
  error_code?: string;
  error_message?: string;
  retries_used?: number;
}
