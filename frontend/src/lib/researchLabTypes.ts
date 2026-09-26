export type ResearchEvidenceStatus =
  | "COMPLETE"
  | "PARTIAL"
  | "NOT_AVAILABLE"
  | "NOT_APPLICABLE"
  | "UNRESOLVED";

export type ResearchStatisticalStrength =
  | "DESCRIPTIVE_ONLY"
  | "LOW_SAMPLE"
  | "ADEQUATE_FOR_DECLARED_TEST"
  | "NOT_EVALUATED";

export interface ResearchArtifactRef {
  artifact_ref: string;
  artifact_type: string;
  sha256: string;
}

export interface ResearchPrimaryContext {
  dataset_id: string;
  source_boundary_id: string;
  paper_epoch_id: string | null;
  research_run_id: string;
  diagnostic_run_id: string | null;
  research_source_code_sha: string;
  research_config_hash: string | null;
  presentation_builder_source_sha: string;
  population_definition: string;
  n: number;
  evidence_status: ResearchEvidenceStatus;
  statistical_strength: ResearchStatisticalStrength;
}

export interface ResearchMetric {
  metric_name: string;
  value: number | string | null;
  unit: string;
  evidence_status: ResearchEvidenceStatus;
  statistical_strength: ResearchStatisticalStrength;
  population_n: number;
  derivation: string;
  source_ref: string;
  reason: string | null;
}

export interface ResearchAttributionRow {
  label: string;
  population_n: number;
  metrics: ResearchMetric[];
}

export interface ResearchAttributionSection {
  dimension: string;
  evidence_status: ResearchEvidenceStatus;
  statistical_strength: ResearchStatisticalStrength;
  rows: ResearchAttributionRow[];
}

export type ResearchCandidateClass = "CONFIG" | "STRATEGY" | "FEATURE" | "HYBRID";

export type ResearchCandidateLifecycle =
  | "CANDIDATE"
  | "REPLAYED"
  | "SHADOW_READY"
  | "QUALIFIED"
  | "PROMOTED_TO_NEW_EPOCH"
  | "REJECTED"
  | "DORMANT"
  | "RETIRED";

export type ResearchCandidateEvaluationStatus =
  | "NOT_EVALUATED"
  | "EVALUATED"
  | "BLOCKED";

export interface ResearchCandidateRow {
  candidate_id: string;
  candidate_class: ResearchCandidateClass;
  target_domains: string[];
  lifecycle_state: ResearchCandidateLifecycle;
  parent_evidence_refs: string[];
  source_code_sha: string;
  config_hash: string;
  hypothesis_summary: string;
  evaluation_status: ResearchCandidateEvaluationStatus;
  known_limitations: string[];
}

export interface ResearchLabSnapshot {
  schema_version: "1.0.0";
  product: "ResearchLabSnapshot";
  domain: "research_lab";
  authority: "RESEARCH_NON_AUTHORITATIVE";
  generated_at_utc: string;
  presentation_builder_source_sha: string;
  research_state: "AVAILABLE" | "EMPTY";
  provenance: {
    primary_context: ResearchPrimaryContext;
    source_artifacts: ResearchArtifactRef[];
  };
  population: {
    population_definition: string;
    n: number;
    evidence_status: ResearchEvidenceStatus;
    statistical_strength: ResearchStatisticalStrength;
  };
  performance: ResearchMetric[];
  risk_stability: ResearchMetric[];
  costs: ResearchMetric[];
  attribution: ResearchAttributionSection[];
  candidate_registry: {
    candidate_count: number;
    rows: ResearchCandidateRow[];
  };
  limitations: string[];
}
