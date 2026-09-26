import type {
  ResearchAttributionSection,
  ResearchCandidateEvaluationStatus,
  ResearchCandidateLifecycle,
  ResearchCandidateRow,
  ResearchEvidenceStatus,
  ResearchLabSnapshot,
  ResearchMetric,
  ResearchStatisticalStrength,
} from "./researchLabTypes";

const EVIDENCE = new Set<ResearchEvidenceStatus>([
  "COMPLETE",
  "PARTIAL",
  "NOT_AVAILABLE",
  "NOT_APPLICABLE",
  "UNRESOLVED",
]);
const STRENGTH = new Set<ResearchStatisticalStrength>([
  "DESCRIPTIVE_ONLY",
  "LOW_SAMPLE",
  "ADEQUATE_FOR_DECLARED_TEST",
  "NOT_EVALUATED",
]);
const CANDIDATE_CLASS = new Set(["CONFIG", "STRATEGY", "FEATURE", "HYBRID"]);
const CANDIDATE_STATE = new Set<ResearchCandidateLifecycle>([
  "CANDIDATE",
  "REPLAYED",
  "SHADOW_READY",
  "QUALIFIED",
  "PROMOTED_TO_NEW_EPOCH",
  "REJECTED",
  "DORMANT",
  "RETIRED",
]);
const CANDIDATE_EVAL = new Set<ResearchCandidateEvaluationStatus>([
  "NOT_EVALUATED",
  "EVALUATED",
  "BLOCKED",
]);
const TARGET_DOMAINS = new Set([
  "SIGNAL",
  "STRATEGY",
  "REGIME",
  "GATE",
  "RISK",
  "SIZING",
  "EXECUTION",
  "FEATURE_PIPELINE",
  "RESEARCH_ONLY",
]);

const TOP_KEYS = [
  "schema_version",
  "product",
  "domain",
  "authority",
  "generated_at_utc",
  "presentation_builder_source_sha",
  "research_state",
  "provenance",
  "population",
  "performance",
  "risk_stability",
  "costs",
  "attribution",
  "candidate_registry",
  "limitations",
] as const;

function obj(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

function exactKeys(x: Record<string, unknown>, keys: readonly string[]): boolean {
  const actual = Object.keys(x).sort();
  const expected = [...keys].sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

function nonempty(x: unknown): x is string {
  return typeof x === "string" && x.trim().length > 0;
}

function nonNegativeInt(x: unknown): x is number {
  return typeof x === "number" && Number.isSafeInteger(x) && x >= 0;
}

function finiteNumber(x: unknown): x is number {
  return typeof x === "number" && Number.isFinite(x);
}

function sha40(x: unknown): x is string {
  return typeof x === "string" && /^[0-9a-f]{40}$/.test(x);
}

function sha256(x: unknown): x is string {
  return typeof x === "string" && /^[0-9a-f]{64}$/.test(x);
}

function metric(x: unknown, refs: Set<string>, maxN: number): x is ResearchMetric {
  if (!obj(x)) return false;
  if (!exactKeys(x, [
    "metric_name",
    "value",
    "unit",
    "evidence_status",
    "statistical_strength",
    "population_n",
    "derivation",
    "source_ref",
    "reason",
  ])) return false;
  if (!nonempty(x.metric_name) || !nonempty(x.unit)) return false;
  if (!EVIDENCE.has(x.evidence_status as ResearchEvidenceStatus)) return false;
  if (!STRENGTH.has(x.statistical_strength as ResearchStatisticalStrength)) return false;
  if (!nonNegativeInt(x.population_n) || x.population_n > maxN) return false;
  if (!nonempty(x.derivation) || !nonempty(x.source_ref) || !refs.has(x.source_ref)) return false;
  if (x.reason !== null && !nonempty(x.reason)) return false;

  if (x.evidence_status === "NOT_AVAILABLE" || x.evidence_status === "NOT_APPLICABLE" || x.evidence_status === "UNRESOLVED") {
    return x.value === null && nonempty(x.reason);
  }

  if (x.value === null || typeof x.value === "boolean") return false;
  if (typeof x.value === "number") return finiteNumber(x.value);
  return nonempty(x.value);
}

function metricList(x: unknown, refs: Set<string>, maxN: number): x is ResearchMetric[] {
  if (!Array.isArray(x)) return false;
  const names = new Set<string>();
  for (const item of x) {
    if (!metric(item, refs, maxN)) return false;
    if (names.has(item.metric_name)) return false;
    names.add(item.metric_name);
  }
  return true;
}

function attribution(x: unknown, refs: Set<string>, maxN: number): x is ResearchAttributionSection[] {
  if (!Array.isArray(x)) return false;
  const dimensions = new Set<string>();
  for (const section of x) {
    if (!obj(section) || !exactKeys(section, ["dimension", "evidence_status", "statistical_strength", "rows"])) return false;
    if (!nonempty(section.dimension) || dimensions.has(section.dimension)) return false;
    dimensions.add(section.dimension);
    if (!EVIDENCE.has(section.evidence_status as ResearchEvidenceStatus)) return false;
    if (!STRENGTH.has(section.statistical_strength as ResearchStatisticalStrength)) return false;
    if (!Array.isArray(section.rows)) return false;
    const labels = new Set<string>();
    for (const row of section.rows) {
      if (!obj(row) || !exactKeys(row, ["label", "population_n", "metrics"])) return false;
      if (!nonempty(row.label) || labels.has(row.label)) return false;
      labels.add(row.label);
      if (!nonNegativeInt(row.population_n) || row.population_n > maxN) return false;
      if (!metricList(row.metrics, refs, row.population_n)) return false;
    }
  }
  return true;
}

function candidateRow(x: unknown, refs: Set<string>): x is ResearchCandidateRow {
  if (!obj(x)) return false;
  if (!exactKeys(x, [
    "candidate_id",
    "candidate_class",
    "target_domains",
    "lifecycle_state",
    "parent_evidence_refs",
    "source_code_sha",
    "config_hash",
    "hypothesis_summary",
    "evaluation_status",
    "known_limitations",
  ])) return false;
  if (!sha256(x.candidate_id)) return false;
  if (!CANDIDATE_CLASS.has(String(x.candidate_class))) return false;
  if (!CANDIDATE_STATE.has(x.lifecycle_state as ResearchCandidateLifecycle)) return false;
  if (!Array.isArray(x.target_domains) || x.target_domains.length === 0) return false;
  if (!x.target_domains.every((value) => typeof value === "string" && TARGET_DOMAINS.has(value))) return false;
  if (new Set(x.target_domains).size !== x.target_domains.length) return false;
  if (x.target_domains.includes("RESEARCH_ONLY") && x.target_domains.length !== 1) return false;
  if (!Array.isArray(x.parent_evidence_refs) || x.parent_evidence_refs.length === 0) return false;
  if (!x.parent_evidence_refs.every((value) => typeof value === "string" && refs.has(value))) return false;
  if (new Set(x.parent_evidence_refs).size !== x.parent_evidence_refs.length) return false;
  if (x.source_code_sha !== "NOT_IMPLEMENTED" && !sha40(x.source_code_sha)) return false;
  if (x.config_hash !== "NOT_AVAILABLE" && !sha256(x.config_hash)) return false;
  if (!nonempty(x.hypothesis_summary)) return false;
  if (!CANDIDATE_EVAL.has(x.evaluation_status as ResearchCandidateEvaluationStatus)) return false;
  if (!Array.isArray(x.known_limitations) || x.known_limitations.length === 0 || !x.known_limitations.every(nonempty)) return false;
  return true;
}

export function validateResearchLabSnapshot(x: unknown): x is ResearchLabSnapshot {
  if (!obj(x) || !exactKeys(x, TOP_KEYS)) return false;
  if (x.schema_version !== "1.0.0") return false;
  if (x.product !== "ResearchLabSnapshot") return false;
  if (x.domain !== "research_lab") return false;
  if (x.authority !== "RESEARCH_NON_AUTHORITATIVE") return false;
  if (!nonempty(x.generated_at_utc) || Number.isNaN(Date.parse(x.generated_at_utc))) return false;
  if (!sha40(x.presentation_builder_source_sha)) return false;
  if (x.research_state !== "AVAILABLE" && x.research_state !== "EMPTY") return false;

  if (!obj(x.provenance) || !exactKeys(x.provenance, ["primary_context", "source_artifacts"])) return false;
  const context = x.provenance.primary_context;
  if (!obj(context) || !exactKeys(context, [
    "dataset_id",
    "source_boundary_id",
    "paper_epoch_id",
    "research_run_id",
    "diagnostic_run_id",
    "research_source_code_sha",
    "research_config_hash",
    "presentation_builder_source_sha",
    "population_definition",
    "n",
    "evidence_status",
    "statistical_strength",
  ])) return false;
  if (!sha256(context.dataset_id) || !sha256(context.source_boundary_id)) return false;
  if (context.paper_epoch_id !== null && !nonempty(context.paper_epoch_id)) return false;
  if (!sha256(context.research_run_id)) return false;
  if (context.diagnostic_run_id !== null && !sha256(context.diagnostic_run_id)) return false;
  if (!sha40(context.research_source_code_sha)) return false;
  if (context.research_config_hash !== null && !sha256(context.research_config_hash)) return false;
  if (context.presentation_builder_source_sha !== x.presentation_builder_source_sha) return false;
  if (!nonempty(context.population_definition) || !nonNegativeInt(context.n)) return false;
  if (!EVIDENCE.has(context.evidence_status as ResearchEvidenceStatus)) return false;
  if (!STRENGTH.has(context.statistical_strength as ResearchStatisticalStrength)) return false;

  if (!Array.isArray(x.provenance.source_artifacts) || x.provenance.source_artifacts.length === 0) return false;
  const refs = new Set<string>();
  for (const artifact of x.provenance.source_artifacts) {
    if (!obj(artifact) || !exactKeys(artifact, ["artifact_ref", "artifact_type", "sha256"])) return false;
    if (!nonempty(artifact.artifact_ref) || refs.has(artifact.artifact_ref)) return false;
    refs.add(artifact.artifact_ref);
    if (!nonempty(artifact.artifact_type) || !sha256(artifact.sha256)) return false;
  }

  if (!obj(x.population) || !exactKeys(x.population, ["population_definition", "n", "evidence_status", "statistical_strength"])) return false;
  if (x.population.population_definition !== context.population_definition || x.population.n !== context.n) return false;
  if (!EVIDENCE.has(x.population.evidence_status as ResearchEvidenceStatus)) return false;
  if (!STRENGTH.has(x.population.statistical_strength as ResearchStatisticalStrength)) return false;

  if (!metricList(x.performance, refs, context.n)) return false;
  if (!metricList(x.risk_stability, refs, context.n)) return false;
  if (!metricList(x.costs, refs, context.n)) return false;
  if (!attribution(x.attribution, refs, context.n)) return false;

  if (!obj(x.candidate_registry) || !exactKeys(x.candidate_registry, ["candidate_count", "rows"])) return false;
  if (!nonNegativeInt(x.candidate_registry.candidate_count) || !Array.isArray(x.candidate_registry.rows)) return false;
  if (x.candidate_registry.candidate_count !== x.candidate_registry.rows.length) return false;
  if (!x.candidate_registry.rows.every((row) => candidateRow(row, refs))) return false;
  const candidateIds = x.candidate_registry.rows.map((row) => row.candidate_id);
  if (new Set(candidateIds).size !== candidateIds.length) return false;

  if (!Array.isArray(x.limitations) || x.limitations.length === 0 || !x.limitations.every(nonempty)) return false;

  if (x.research_state === "EMPTY") {
    if (context.n !== 0) return false;
    if (x.performance.length || x.risk_stability.length || x.costs.length || x.attribution.length) return false;
    if (x.candidate_registry.candidate_count !== 0) return false;
  }
  return true;
}
