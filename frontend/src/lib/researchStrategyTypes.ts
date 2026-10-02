export const STRATEGY_CRITERIA = [
  "PERFORMANCE",
  "POPULATION",
  "VALIDATION",
  "STABILITY",
  "COSTS",
  "DRAWDOWN",
] as const;
export type CriterionKey = (typeof STRATEGY_CRITERIA)[number];
export type CriterionStatus = "PASS" | "FAIL" | "PARTIAL" | "NOT_AVAILABLE";
export interface StrategyMetric {
  metric_name: string;
  metric_semantics_version: string;
  n: number;
  value: number | string | null;
  evidence_status: string;
  statistical_strength: string;
  baseline_value: number | string | null;
  candidate_value: number | string | null;
  delta: number | string | null;
  derivation: string;
}
export interface StrategyEvaluation {
  evaluation_run_id: string;
  dataset_id: string;
  source_boundary_id: string;
  role: string;
  method: string;
  metric_semantics_version: string;
  config_hash: string;
  baseline_id: string;
  source_code_sha: string;
  run_status: string;
  population_definition: string;
  metrics: StrategyMetric[];
  generated_at_utc: string;
}
export interface StrategyCriterion {
  criterion_id: CriterionKey;
  status: CriterionStatus;
  reason: string;
  metric_refs: string[];
}
export interface StrategyRanking {
  group_id: string;
  position: number;
  group_size: number;
  metric_name: string;
  ordering: "ASC" | "DESC";
  reason: string;
}
export interface ResearchStrategyRow {
  candidate_id: string;
  candidate_class: string;
  label: string;
  hypothesis: string;
  rationale: string;
  target_domains: string[];
  source_code_sha: string;
  config_hash: string;
  evaluation: StrategyEvaluation | null;
  criteria: StrategyCriterion[];
  ranking: StrategyRanking | null;
  assessment_policy_id: string | null;
  assessment_policy_ref: string | null;
  limitations: string[];
}
export interface ResearchStrategyBoard {
  schema_version: "1.0.0";
  product: "ResearchStrategyBoardSnapshot";
  domain: "research_strategy_board";
  authority: "RESEARCH_NON_AUTHORITATIVE";
  generated_at_utc: string;
  builder_source_sha: string;
  admission_ref: string;
  catalog_state: "AVAILABLE" | "EMPTY";
  rows: ResearchStrategyRow[];
  source_artifacts: {
    artifact_ref: string;
    artifact_type: string;
    sha256: string;
  }[];
  limitations: string[];
}
