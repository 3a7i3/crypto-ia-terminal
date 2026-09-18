export type PplComparisonClass = "COMPARABLE" | "PARTIAL" | "UNRESOLVED";
export type PplComparisonRelation =
  | "EQUAL"
  | "DIFFERENT"
  | "LEGACY_ONLY"
  | "PPL_ONLY"
  | "NOT_COMPARABLE";
export type PplShadowStatus =
  | "OFF"
  | "WAITING_CLEAN_BOUNDARY"
  | "ACTIVE"
  | "DEGRADED";

export interface PplComparisonSourceValue {
  value: unknown;
  status: string;
  provenance: string;
}

export interface PplComparisonRecord {
  comparison_id: string;
  domain: string;
  field: string;
  trade_id: string | null;
  classification: PplComparisonClass;
  relation: PplComparisonRelation;
  legacy: PplComparisonSourceValue;
  ppl: PplComparisonSourceValue;
  delta_ppl_minus_legacy: number | null;
  comparison_rule: string;
  note: string | null;
}

export interface PplComparisonGroup {
  trade_id: string;
  relation: "BOTH" | "LEGACY_ONLY" | "PPL_ONLY" | "NEITHER";
  legacy_present: boolean;
  ppl_present: boolean;
  field_comparison_ids: string[];
}

export interface PplComparisonEvent {
  event_id: string;
  sequence: number;
  event_type: string;
  trade_id: string | null;
  decision_id: string | null;
  timestamp: number;
  payload: Record<string, unknown>;
}

export interface PplLegacySourceMeta {
  source: string;
  authority: "PAPER_AUTHORITY";
  scope: string;
}

export interface PplShadowSourceMeta {
  source: string;
  authority: "NONE";
  scope: string;
  last_error: string | null;
}

export interface PplComparisonSummary {
  total: number;
  comparable: number;
  partial: number;
  unresolved: number;
  equal: number;
  different: number;
  legacy_only: number;
  ppl_only: number;
  not_comparable: number;
}

export interface PplComparisonSnapshot {
  schema_version: "1.0.0";
  product: "PPLComparator";
  domain: "ppl_comparison";
  authority: "OBSERVATIONAL_TELEMETRY";
  mode: "SHADOW_COMPARISON";
  generated_at_utc: string;
  process_instance_id: string;
  cycle: number;
  source_sha: string | null;
  shadow_status: PplShadowStatus;
  paper_epoch_id: string | null;
  comparison_available: boolean;
  comparison_unavailable_reason: string | null;
  legacy_source: PplLegacySourceMeta;
  ppl_source: PplShadowSourceMeta;
  summary: PplComparisonSummary;
  comparisons: PplComparisonRecord[];
  positions: PplComparisonGroup[];
  closed_session: PplComparisonGroup[];
  ppl_events: PplComparisonEvent[];
  snapshot_age_s: number;
  freshness_classification: "FRESH" | "STALE";
}
