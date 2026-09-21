export type FinancialReconciliationStatus =
  | "EXACT"
  | "WITHIN_TOLERANCE"
  | "DIVERGENT"
  | "UNRESOLVED";

export type FinancialComparability =
  | "COMPARABLE"
  | "NON_COMPARABLE"
  | "UNAVAILABLE"
  | "NOT_APPLICABLE";

export type FinancialFreshness =
  | "LIVE"
  | "STALE"
  | "UNAVAILABLE"
  | "NOT_APPLICABLE";

export type FinancialSourceKind =
  | "PPL"
  | "SIMULATOR"
  | "EXCHANGE_READ_ONLY";

export interface FinancialReconciliationRecord {
  record_id: string;
  source_kind: FinancialSourceKind;
  source_id: string;
  field: string;
  projected_value: string | null;
  observed_value: string | null;
  delta_observed_minus_projected: string | null;
  unreconciled_amount: string | null;
  status: FinancialReconciliationStatus;
  comparability: FinancialComparability;
  freshness: FinancialFreshness;
  observed_at: string;
  projected_provenance: string;
  observed_provenance: string;
  note: string | null;
}

export interface FinancialReconciliationSnapshot {
  schema_version: "1.0.0";
  product: "FIN02FinancialCockpit";
  domain: "financial_reconciliation";
  authority: "FINANCIAL_OBSERVATION";
  generated_at_utc: string;
  reconciliation_id: string;
  paper_epoch_id: string;
  financial_snapshot_id: string;
  source_stream_digest: string;
  last_source_sequence: number;
  fin_schema_version: number;
  fin_code_sha: string;
  source_code_sha: string;
  config_hash: string;
  financial_model: string;
  asset: string;
  financial: {
    initial_epoch_capital: string;
    cash_available: string;
    capital_reserved: string;
    capital_deployed: string;
    capital_unresolved: string;
    gross_realized_price_pnl: string;
    fees_paid: string;
    funding_net: string | null;
    funding_status: string;
    funding_evidence_ref: string | null;
    realized_pnl: string | null;
    known_unrealized_pnl: string;
    unrealized_pnl: string | null;
    certified_equity: string | null;
    evidence_status: string;
    reconciliation_status: FinancialReconciliationStatus;
    valuation_as_of: string;
    valuation_statuses: Array<"LIVE" | "STALE" | "UNAVAILABLE">;
    open_position_count: number;
    settled_position_count: number;
    unresolved_position_count: number;
  };
  reconciliation: {
    overall_status: FinancialReconciliationStatus;
    as_of: string;
    unresolved_capital: string;
    unreconciled_capital: string | null;
    policy: {
      absolute_tolerance: string;
      relative_tolerance: string;
      stale_after_s: string;
    };
    ppl_observation_digest: string;
    simulator_observation_digest: string | null;
    external_observation_digest: string | null;
  };
  sources: {
    ppl: Record<string, unknown>;
    simulator: Record<string, unknown> | null;
    external: Record<string, unknown> | null;
  };
  records: FinancialReconciliationRecord[];
  snapshot_age_s: number;
  freshness_classification: "FRESH" | "STALE";
}
