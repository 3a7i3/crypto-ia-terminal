import type {
  PplComparisonClass,
  PplComparisonGroup,
  PplComparisonRecord,
  PplComparisonRelation,
  PplComparisonSnapshot,
  PplComparisonSourceValue,
  PplShadowStatus,
} from "./pplComparisonTypes";

const CLASSES = new Set<PplComparisonClass>(["COMPARABLE", "PARTIAL", "UNRESOLVED"]);
const RELATIONS = new Set<PplComparisonRelation>([
  "EQUAL",
  "DIFFERENT",
  "LEGACY_ONLY",
  "PPL_ONLY",
  "NOT_COMPARABLE",
]);
const SHADOW = new Set<PplShadowStatus>([
  "OFF",
  "WAITING_CLEAN_BOUNDARY",
  "ACTIVE",
  "DEGRADED",
]);
const GROUP_RELATIONS = new Set(["BOTH", "LEGACY_ONLY", "PPL_ONLY", "NEITHER"]);

function obj(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

function finite(x: unknown): x is number {
  return typeof x === "number" && Number.isFinite(x);
}

function nonNegativeInt(x: unknown): x is number {
  return Number.isInteger(x) && typeof x === "number" && x >= 0;
}

function nullableString(x: unknown): x is string | null {
  return x === null || typeof x === "string";
}

function sourceValue(x: unknown): x is PplComparisonSourceValue {
  return (
    obj(x) &&
    typeof x.status === "string" &&
    x.status.length > 0 &&
    typeof x.provenance === "string" &&
    x.provenance.length > 0
  );
}

function comparison(x: unknown): x is PplComparisonRecord {
  if (!obj(x)) return false;
  if (typeof x.comparison_id !== "string" || !x.comparison_id.startsWith("web02-")) return false;
  if (typeof x.domain !== "string" || typeof x.field !== "string") return false;
  if (!nullableString(x.trade_id)) return false;
  if (!CLASSES.has(x.classification as PplComparisonClass)) return false;
  if (!RELATIONS.has(x.relation as PplComparisonRelation)) return false;
  if (!sourceValue(x.legacy) || !sourceValue(x.ppl)) return false;
  if (x.delta_ppl_minus_legacy !== null && !finite(x.delta_ppl_minus_legacy)) return false;
  if (x.classification !== "COMPARABLE" && x.delta_ppl_minus_legacy !== null) return false;
  if (typeof x.comparison_rule !== "string") return false;
  if (!nullableString(x.note)) return false;
  return true;
}

function group(x: unknown): x is PplComparisonGroup {
  return (
    obj(x) &&
    typeof x.trade_id === "string" &&
    GROUP_RELATIONS.has(String(x.relation)) &&
    typeof x.legacy_present === "boolean" &&
    typeof x.ppl_present === "boolean" &&
    Array.isArray(x.field_comparison_ids) &&
    x.field_comparison_ids.every((id) => typeof id === "string" && id.startsWith("web02-"))
  );
}

function event(x: unknown): boolean {
  return (
    obj(x) &&
    typeof x.event_id === "string" &&
    nonNegativeInt(x.sequence) &&
    x.sequence >= 1 &&
    typeof x.event_type === "string" &&
    nullableString(x.trade_id) &&
    nullableString(x.decision_id) &&
    finite(x.timestamp) &&
    obj(x.payload)
  );
}

export function validatePplComparisonSnapshot(x: unknown): x is PplComparisonSnapshot {
  if (!obj(x)) return false;
  if (x.schema_version !== "1.0.0") return false;
  if (x.product !== "PPLComparator" || x.domain !== "ppl_comparison") return false;
  if (x.authority !== "OBSERVATIONAL_TELEMETRY") return false;
  if (x.mode !== "SHADOW_COMPARISON" && x.mode !== "AUTHORITY_STATUS") return false;
  if (typeof x.generated_at_utc !== "string" || Number.isNaN(Date.parse(x.generated_at_utc))) return false;
  if (typeof x.process_instance_id !== "string" || !nonNegativeInt(x.cycle)) return false;
  if (!nullableString(x.source_sha) || !SHADOW.has(x.shadow_status as PplShadowStatus)) return false;
  if (!nullableString(x.paper_epoch_id) || typeof x.comparison_available !== "boolean") return false;
  if (!nullableString(x.comparison_unavailable_reason)) return false;
  if (x.comparison_available && x.shadow_status !== "ACTIVE") return false;
  if (x.mode === "AUTHORITY_STATUS" && x.comparison_available) return false;
  if (!obj(x.legacy_source) || !obj(x.ppl_source) || !obj(x.summary)) return false;
  const legacySource = x.legacy_source;
  const pplSource = x.ppl_source;
  const legacyKeys = Object.keys(legacySource).sort();
  const pplKeys = Object.keys(pplSource).sort();
  if (legacyKeys.join("|") !== ["authority", "scope", "source"].join("|")) return false;
  if (pplKeys.join("|") !== ["authority", "last_error", "scope", "source"].join("|")) return false;
  if (
    typeof legacySource.source !== "string" ||
    legacySource.source.length === 0 ||
    typeof legacySource.scope !== "string" ||
    legacySource.scope.length === 0
  ) return false;
  if (
    typeof pplSource.source !== "string" ||
    pplSource.source.length === 0 ||
    typeof pplSource.scope !== "string" ||
    pplSource.scope.length === 0 ||
    !nullableString(pplSource.last_error)
  ) return false;
  if (x.mode === "SHADOW_COMPARISON") {
    if (legacySource.authority !== "PAPER_AUTHORITY" || pplSource.authority !== "NONE") return false;
  } else {
    if (legacySource.authority !== "NONE" || pplSource.authority !== "PAPER_AUTHORITY") return false;
  }

  const summary = x.summary;

  const summaryKeys = [
    "total", "comparable", "partial", "unresolved", "equal", "different",
    "legacy_only", "ppl_only", "not_comparable",
  ];
  if (!summaryKeys.every((key) => nonNegativeInt(summary[key]))) return false;

  if (!Array.isArray(x.comparisons) || !x.comparisons.every(comparison)) return false;
  if (summary.total !== x.comparisons.length) return false;
  if (!Array.isArray(x.positions) || !x.positions.every(group)) return false;
  if (!Array.isArray(x.closed_session) || !x.closed_session.every(group)) return false;
  if (!Array.isArray(x.ppl_events) || !x.ppl_events.every(event)) return false;
  if (!finite(x.snapshot_age_s) || x.snapshot_age_s < 0) return false;
  if (x.freshness_classification !== "FRESH" && x.freshness_classification !== "STALE") return false;
  return true;
}
