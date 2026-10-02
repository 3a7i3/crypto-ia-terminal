import {
  STRATEGY_CRITERIA,
  type ResearchStrategyBoard,
  type ResearchStrategyRow,
  type StrategyEvaluation,
} from "./researchStrategyTypes";
type Obj = Record<string, any>;
const object = (v: unknown): v is Obj =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const exact = (v: unknown, fields: string): v is Obj =>
  object(v) &&
  Object.keys(v).sort().join(" ") === fields.split(" ").sort().join(" ");
const text = (v: unknown, max = 2048): v is string =>
  typeof v === "string" && v.trim().length > 0 && v.length <= max;
const hash = (v: unknown, len = 64): v is string =>
  typeof v === "string" && new RegExp(`^[0-9a-f]{${len}}$`).test(v);
const member = (v: unknown, values: readonly string[]) =>
  typeof v === "string" && values.includes(v);
const integer = (v: unknown, max = Number.MAX_SAFE_INTEGER): v is number =>
  typeof v === "number" && Number.isSafeInteger(v) && v >= 0 && v <= max;
const strings = (v: unknown, max = 32): v is string[] =>
  Array.isArray(v) &&
  v.length <= max &&
  v.every((x) => text(x)) &&
  new Set(v).size === v.length;
const scalar = (v: unknown) =>
  v === null || text(v, 256) || (typeof v === "number" && Number.isFinite(v));
const utc = (v: unknown) =>
  text(v, 40) &&
  /(?:Z|[+-]\d{2}:\d{2})$/.test(v) &&
  Number.isFinite(Date.parse(v));
const evidence = [
  "COMPLETE",
  "PARTIAL",
  "NOT_AVAILABLE",
  "NOT_APPLICABLE",
  "UNRESOLVED",
];
const strength = [
  "DESCRIPTIVE_ONLY",
  "LOW_SAMPLE",
  "ADEQUATE_FOR_DECLARED_TEST",
  "NOT_EVALUATED",
];
function evaluation(e: unknown): e is StrategyEvaluation | null {
  if (e === null) return true;
  if (
    !exact(
      e,
      "evaluation_run_id dataset_id source_boundary_id role method metric_semantics_version config_hash baseline_id source_code_sha run_status population_definition metrics generated_at_utc",
    )
  )
    return false;
  if (
    ![
      "evaluation_run_id",
      "dataset_id",
      "source_boundary_id",
      "config_hash",
      "baseline_id",
    ].every((k) => hash(e[k])) ||
    !hash(e.source_code_sha, 40) ||
    !member(e.role, ["DISCOVERY", "EVALUATION", "VALIDATION"]) ||
    !member(e.run_status, ["COMPLETE", "PARTIAL", "BLOCKED", "FAILED"]) ||
    !["method", "population_definition", "metric_semantics_version"].every(
      (k) => text(e[k], 256),
    ) ||
    !utc(e.generated_at_utc)
  )
    return false;
  if (
    !Array.isArray(e.metrics) ||
    e.metrics.length === 0 ||
    e.metrics.length > 32
  )
    return false;
  const names = new Set<string>();
  for (const m of e.metrics) {
    if (
      !exact(
        m,
        "metric_name metric_semantics_version n value evidence_status statistical_strength baseline_value candidate_value delta derivation",
      ) ||
      !text(m.metric_name, 128) ||
      !text(m.metric_semantics_version, 128) ||
      !integer(m.n) ||
      !member(m.evidence_status, evidence) ||
      !member(m.statistical_strength, strength) ||
      !["value", "baseline_value", "candidate_value", "delta"].every((k) =>
        scalar(m[k]),
      ) ||
      !text(m.derivation) ||
      names.has(m.metric_name)
    )
      return false;
    if (
      m.metric_semantics_version !== e.metric_semantics_version ||
      (!["COMPLETE", "PARTIAL"].includes(m.evidence_status) &&
        typeof m.value === "number")
    )
      return false;
    names.add(m.metric_name);
  }
  return true;
}
function row(r: unknown): r is ResearchStrategyRow {
  if (
    !exact(
      r,
      "candidate_id candidate_class label hypothesis rationale target_domains source_code_sha config_hash evaluation criteria ranking assessment_policy_id assessment_policy_ref limitations",
    )
  )
    return false;
  if (
    !hash(r.candidate_id) ||
    !member(r.candidate_class, ["STRATEGY", "FEATURE", "CONFIG", "HYBRID"]) ||
    !text(r.label, 128) ||
    !text(r.hypothesis) ||
    !text(r.rationale) ||
    !strings(r.limitations) ||
    !r.limitations.length ||
    !strings(r.target_domains) ||
    !r.target_domains.length ||
    !r.target_domains.every((d: string) =>
      member(d, [
        "SIGNAL",
        "STRATEGY",
        "REGIME",
        "GATE",
        "RISK",
        "SIZING",
        "EXECUTION",
        "FEATURE_PIPELINE",
        "RESEARCH_ONLY",
      ]),
    ) ||
    (r.source_code_sha !== "NOT_IMPLEMENTED" && !hash(r.source_code_sha, 40)) ||
    (r.config_hash !== "NOT_AVAILABLE" && !hash(r.config_hash)) ||
    !evaluation(r.evaluation)
  )
    return false;
  if (
    (r.assessment_policy_id === null) !== (r.assessment_policy_ref === null) ||
    (r.assessment_policy_id !== null &&
      (!hash(r.assessment_policy_id) || !text(r.assessment_policy_ref, 512)))
  )
    return false;
  if (
    !Array.isArray(r.criteria) ||
    r.criteria.length !== STRATEGY_CRITERIA.length
  )
    return false;
  const criteria = new Set<string>();
  const metrics = new Map(r.evaluation?.metrics.map((m) => [m.metric_name, m]));
  for (const c of r.criteria) {
    if (
      !exact(c, "criterion_id status reason metric_refs") ||
      !member(c.criterion_id, STRATEGY_CRITERIA) ||
      criteria.has(c.criterion_id) ||
      !member(c.status, ["PASS", "FAIL", "PARTIAL", "NOT_AVAILABLE"]) ||
      !text(c.reason) ||
      !strings(c.metric_refs) ||
      !c.metric_refs.every((ref: string) => metrics.has(ref))
    )
      return false;
    if (
      c.status !== "NOT_AVAILABLE" &&
      (r.evaluation === null || r.assessment_policy_id === null)
    )
      return false;
    if (
      ["PASS", "FAIL"].includes(c.status) &&
      (c.metric_refs.length === 0 ||
        r.evaluation?.run_status !== "COMPLETE" ||
        c.metric_refs.some(
          (ref: string) =>
            metrics.get(ref)?.evidence_status !== "COMPLETE" ||
            metrics.get(ref)?.n === 0,
        ))
    )
      return false;
    criteria.add(c.criterion_id);
  }
  const rank = r.ranking;
  if (rank !== null) {
    if (
      !exact(
        rank,
        "group_id position group_size metric_name ordering reason",
      ) ||
      !hash(rank.group_id) ||
      !integer(rank.position, 100) ||
      !integer(rank.group_size, 100) ||
      rank.position === 0 ||
      rank.position > rank.group_size ||
      !text(rank.metric_name, 128) ||
      !member(rank.ordering, ["ASC", "DESC"]) ||
      !text(rank.reason) ||
      r.evaluation?.run_status !== "COMPLETE" ||
      r.assessment_policy_id === null
    )
      return false;
    const metric = metrics.get(rank.metric_name);
    if (
      !metric ||
      metric.evidence_status !== "COMPLETE" ||
      typeof metric.value !== "number" ||
      metric.n === 0
    )
      return false;
  }
  return true;
}
export function validateResearchStrategyBoard(
  v: unknown,
): v is ResearchStrategyBoard {
  if (
    !exact(
      v,
      "schema_version product domain authority generated_at_utc builder_source_sha admission_ref catalog_state rows source_artifacts limitations",
    )
  )
    return false;
  if (
    v.schema_version !== "1.0.0" ||
    v.product !== "ResearchStrategyBoardSnapshot" ||
    v.domain !== "research_strategy_board" ||
    v.authority !== "RESEARCH_NON_AUTHORITATIVE" ||
    !utc(v.generated_at_utc) ||
    !hash(v.builder_source_sha, 40) ||
    !text(v.admission_ref, 512) ||
    !member(v.catalog_state, ["AVAILABLE", "EMPTY"]) ||
    !strings(v.limitations) ||
    !v.limitations.length
  )
    return false;
  if (
    !Array.isArray(v.rows) ||
    v.rows.length > 100 ||
    !v.rows.every(row) ||
    new Set(v.rows.map((r) => r.candidate_id)).size !== v.rows.length ||
    (v.catalog_state === "EMPTY") !== (v.rows.length === 0)
  )
    return false;
  if (
    !Array.isArray(v.source_artifacts) ||
    !v.source_artifacts.length ||
    v.source_artifacts.length > 301
  )
    return false;
  const refs = new Set<string>();
  const artifactTypes = new Map<string, string>();
  for (const a of v.source_artifacts) {
    if (
      !exact(a, "artifact_ref artifact_type sha256") ||
      !text(a.artifact_ref, 128) ||
      !text(a.artifact_type, 128) ||
      !hash(a.sha256) ||
      refs.has(a.artifact_ref)
    )
      return false;
    refs.add(a.artifact_ref);
    artifactTypes.set(a.artifact_ref, a.artifact_type);
  }
  if (artifactTypes.get("selection") !== "RESEARCH_CERTIFIED_SELECTION")
    return false;
  const groups = new Map<
    string,
    { identity: string; size: number; ranks: Set<number> }
  >();
  for (const r of v.rows as ResearchStrategyRow[]) {
    if (
      artifactTypes.get(`candidate:${r.candidate_id}`) !== "RL_CANDIDATE" ||
      (r.evaluation &&
        artifactTypes.get(`evaluation:${r.evaluation.evaluation_run_id}`) !==
          "RL_CANDIDATE_EVALUATION") ||
      (r.assessment_policy_id &&
        artifactTypes.get(`assessment:${r.candidate_id}`) !==
          "RESEARCH_STRATEGY_ASSESSMENT")
    )
      return false;
    if (r.ranking && r.evaluation) {
      const e = r.evaluation,
        rank = r.ranking;
      const identity = JSON.stringify([
        e.dataset_id,
        e.source_boundary_id,
        e.role,
        e.method,
        e.metric_semantics_version,
        e.config_hash,
        e.baseline_id,
        e.source_code_sha,
        e.population_definition,
        r.assessment_policy_id,
        rank.metric_name,
        rank.ordering,
      ]);
      const group = groups.get(rank.group_id) ?? {
        identity,
        size: rank.group_size,
        ranks: new Set<number>(),
      };
      if (
        group.identity !== identity ||
        group.size !== rank.group_size ||
        group.ranks.has(rank.position)
      )
        return false;
      group.ranks.add(rank.position);
      if (group.ranks.size > group.size) return false;
      groups.set(rank.group_id, group);
    }
  }
  return true;
}
