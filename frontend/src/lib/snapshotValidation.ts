// ── snapshotValidation — runtime boundary for the operator snapshot ────────
// O-02W-D2-R1 Correction B, hardened by O-02W-D2-R1.1 Corrections A-E and
// O-02W-D2-R1.2 Corrections A-C.
//
// `looksLikeSnapshot()` originally checked only five key names. Later
// rounds closed structural holes (domain id/status/freshness vocabularies,
// full OpenPosition/PerSymbolDecision field coverage, deployment-evidence
// closed vocabulary) but `isObservedValue()` validates only the generic
// null-semantics matrix, not the generic type `T` — so MASTER reproduced a
// further hole on HEAD c03dbee: `boot_alive = {value: "false", semantics:
// "PRESENT"}` (and the equivalent for `is_actionable`, a numeric field
// carrying a string, and `open_positions = {value: "", semantics:
// "EMPTY"}`) all returned `true`. React then renders a string `"false"`
// through a boolean render callback using JS truthiness, showing `true`
// for a value that means false — a false-liveness / false-execution-
// authority presentation. R1.2 adds typed ObservedValue validators
// (numeric/boolean/string/list) applied to every field the cockpit
// renders, plus a closed, per-field-mapped authority vocabulary.
//
// This module validates every field the cockpit renders before a response
// is ever assigned status="success" — the client's own admission gate, not
// a second competing API contract. It never infers, repairs, coerces, or
// normalizes a malformed value — only accepts or rejects the whole
// snapshot.

import type { OperatorSnapshot } from "../types";
import { isObservedValue } from "./observedValue";

function isPlainObject(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

function isNonBlankString(x: unknown): x is string {
  return typeof x === "string" && x.trim().length > 0;
}

function isNullableString(x: unknown): boolean {
  return x === null || typeof x === "string";
}

function isNullableNonBlankString(x: unknown): boolean {
  return x === null || isNonBlankString(x);
}

function isFiniteNumber(x: unknown): x is number {
  return typeof x === "number" && Number.isFinite(x);
}

function isNullableFiniteNumber(x: unknown): boolean {
  return x === null || isFiniteNumber(x);
}

function isBoolean(x: unknown): x is boolean {
  return typeof x === "boolean";
}

const WORKTREE_STATES = new Set(["CLEAN", "DIRTY", "UNKNOWN"]);
const EVIDENCE_STATUSES = new Set(["VERIFIED", "CLAIMED_ONLY", "UNKNOWN"]);
// O-02W-D2-R1.1 Correction E — `deployment_evidence.source` is a closed
// producer-identity vocabulary (contract §15), never free-form text. A
// VERIFIED status is never treated as proof of runtime memory here — this
// is a shape check only, not a semantic upgrade of the evidence itself.
const DEPLOYMENT_EVIDENCE_SOURCES = new Set(["deploy_tag", "deploy_audit", "post_deploy_verification"]);
const PORTFOLIO_MODES = new Set(["PAPER", "REAL_API", "TESTNET_API", "UNKNOWN"]);
const INSTANCE_RELATIONS = new Set(["CURRENT_INSTANCE", "PREVIOUS_INSTANCE", "UNKNOWN"]);
const RUNTIME_STATES = new Set(["CURRENT", "LAST_KNOWN"]);

// O-02W-D2-R1.1 Correction A — canonical closed vocabularies for the
// domain-spine `status`/`freshness` fields (contracts.py DOMAIN_STATUSES /
// FreshnessStatus). Arrays, objects, numbers, booleans, nulls, and invented
// strings are all rejected — never coerced or defaulted.
const DOMAIN_STATUSES = new Set(["OK", "DEGRADED", "ATTENTION_REQUIRED", "UNAVAILABLE"]);
const FRESHNESS_STATUSES = new Set(["FRESH", "DEGRADED", "STALE", "UNKNOWN", "NOT_APPLICABLE"]);
const DOMAIN_IDS = new Set(["portfolio", "decision_pipeline", "system_health"]);

// O-02W-D2-R1.2 Correction C — the canonical authority vocabulary
// (§4/§8 of the contract) is closed. Never normalized, relabeled, or
// upgraded — a value outside this set rejects the whole snapshot.
const AUTHORITY_VOCAB = new Set(["EXECUTION_AUTHORITY", "OBSERVATIONAL_TELEMETRY", "DECISION_OUTCOME_EVIDENCE"]);
const AUTHORITY_EXECUTION = "EXECUTION_AUTHORITY";
const AUTHORITY_OBSERVATIONAL = "OBSERVATIONAL_TELEMETRY";

function isValidAuthorityValue(x: unknown): boolean {
  return typeof x === "string" && AUTHORITY_VOCAB.has(x);
}

// ── O-02W-D2-R1.2 Correction A — typed ObservedValue validators ────────────
//
// `isObservedValue()` remains the generic semantic-matrix validator (value/
// semantics internal consistency only). Each typed helper below first
// requires a valid generic ObservedValue, then — for every semantics whose
// generic invariant already allows a non-null value (PRESENT/ZERO/FALSE/
// EMPTY/STALE) — additionally requires that non-null value to be the
// declared JS type. UNKNOWN/UNAVAILABLE/NOT_APPLICABLE always carry
// `value: null`, which the generic matrix already enforces, so nothing
// further to type-check there. Never coerces; a mismatch is a straight
// rejection.

/** Numeric ObservedValue: any non-null value must be a genuine finite
 * JS number — never a string, boolean, array, or object. */
function isNumericObservedValue(x: unknown): boolean {
  if (!isObservedValue(x)) return false;
  if (x.value === null) return true;
  return typeof x.value === "number" && Number.isFinite(x.value);
}

/** Boolean ObservedValue: any non-null value must be an actual boolean —
 * never `"true"`/`"false"`/0/1/arrays/objects, and never judged by JS
 * truthiness. */
function isBooleanObservedValue(x: unknown): boolean {
  if (!isObservedValue(x)) return false;
  if (x.value === null) return true;
  return typeof x.value === "boolean";
}

/** String ObservedValue: any non-null value must be a genuine string —
 * never a number, boolean, array, or object. */
function isStringObservedValue(x: unknown): boolean {
  if (!isObservedValue(x)) return false;
  if (x.value === null) return true;
  return typeof x.value === "string";
}

/** List ObservedValue: ANY non-null value (including under EMPTY) must be
 * an actual array — an empty string or empty object can never stand in for
 * an empty list (this closes the exact `open_positions = {value: "",
 * semantics: "EMPTY"}` hole MASTER reproduced). PRESENT/STALE additionally
 * require every element to pass `isValidItem`. */
function isListObservedValue(x: unknown, isValidItem: (item: unknown) => boolean): boolean {
  if (!isObservedValue(x)) return false;
  if (x.value === null) return true;
  if (!Array.isArray(x.value)) return false;
  if (x.semantics === "PRESENT" || x.semantics === "STALE") {
    return x.value.every(isValidItem);
  }
  return true;
}

/** O-02W-D2-R1.2 Correction C — an authority-bearing ObservedValue whose
 * non-null value must additionally pass `isValidNonNullValue` (its declared
 * type), and whose `authority` tag must be EXACTLY `expectedAuthority` —
 * the certified per-field mapping is enforced, never normalized. */
function isValidMappedAuthorityObservedValue(
  x: unknown,
  isValidNonNullValue: (v: unknown) => boolean,
  expectedAuthority: string,
): boolean {
  if (!isObservedValue(x)) return false;
  if (x.value !== null && !isValidNonNullValue(x.value)) return false;
  const authority = (x as unknown as Record<string, unknown>).authority;
  return authority === expectedAuthority;
}

/** O-02W-D2-R1.1 Correction E — the canonical `deployment_evidence` schema:
 * `status` closed to VERIFIED/CLAIMED_ONLY/UNKNOWN, `source` closed to
 * deploy_tag/deploy_audit/post_deploy_verification/null (an invented,
 * case-mismatched, or padded value is rejected — never coerced),
 * `evidence_ref` a non-blank string or null, `observed_at_utc` a string or
 * null. `runtime_sha_evidence_status` is never upgraded by any of this. */
function isValidDeploymentEvidence(x: unknown): boolean {
  if (!isPlainObject(x)) return false;
  if (!EVIDENCE_STATUSES.has(x.status as string)) return false;
  if (x.source !== null && !DEPLOYMENT_EVIDENCE_SOURCES.has(x.source as string)) return false;
  if (!isNullableNonBlankString(x.evidence_ref)) return false;
  if (!isNullableString(x.observed_at_utc)) return false;
  return true;
}

/** O-02W-D2-R1.1 Correction A — the O-01 DomainSnapshot spine every domain
 * payload extends: `domain` must equal the expected id, `status`/
 * `freshness` must be members of their closed vocabularies (never an
 * array/object/number/boolean/null/invented string), `schema_version`/
 * `source`/`observed_at_utc` must be usable strings, `source_version` is
 * nullable-string, `evidence` must be a plain object (never rendered as a
 * primitive, so only shape-checked), `source_updated_at_utc` must be a
 * valid string-typed ObservedValue (R1.2 Correction B), and `authority`
 * (R1.2 Correction C) must belong to the closed authority vocabulary. */
function isValidDomainSpine(x: Record<string, unknown>, expectedDomain: string): boolean {
  if (x.domain !== expectedDomain) return false;
  if (!DOMAIN_STATUSES.has(x.status as string)) return false;
  if (!FRESHNESS_STATUSES.has(x.freshness as string)) return false;
  if (!isNonBlankString(x.schema_version)) return false;
  if (!isNonBlankString(x.source)) return false;
  if (!isNonBlankString(x.observed_at_utc)) return false;
  if (!isNullableString(x.source_version)) return false;
  if (!isPlainObject(x.evidence)) return false;
  if (!isStringObservedValue(x.source_updated_at_utc)) return false;
  if (!isValidAuthorityValue(x.authority)) return false;
  return true;
}

/** O-02W-D2-R1.1 Correction B, typed by O-02W-D2-R1.2 Correction B — every
 * OpenPosition field React renders or uses as list identity/key. An object,
 * array, or wrong-typed primitive in any directly-rendered field invalidates
 * the whole snapshot. */
function isValidOpenPosition(x: unknown): boolean {
  if (!isPlainObject(x)) return false;
  if (!isNonBlankString(x.position_id)) return false;
  if (!isNonBlankString(x.symbol)) return false;
  if (!isNullableString(x.side)) return false;
  if (!isNullableFiniteNumber(x.size_usd)) return false;
  if (!isNullableFiniteNumber(x.entry_price)) return false;
  if (!isNumericObservedValue(x.current_price)) return false;
  if (!isNullableString(x.current_price_observed_at_utc)) return false;
  if (!isNullableFiniteNumber(x.tp_price)) return false;
  if (!isNullableFiniteNumber(x.sl_price)) return false;
  if (!isNonBlankString(x.tp_sl_source)) return false;
  if (!isNumericObservedValue(x.unrealized_pnl_usd)) return false;
  if (!isNumericObservedValue(x.unrealized_pnl_pct)) return false;
  if (!isNullableString(x.opened_at)) return false;
  if (!isStringObservedValue(x.regime)) return false;
  if (!isBoolean(x.restored_without_regime)) return false;
  if (!isNullableString(x.personality)) return false;
  if (!isBoolean(x.restored)) return false;
  return true;
}

function isValidPortfolio(x: unknown): boolean {
  if (!isPlainObject(x)) return false;
  if (!isValidDomainSpine(x, "portfolio")) return false;
  if (!PORTFOLIO_MODES.has(x.mode as string)) return false;

  // O-02W-D2-R1.2 Correction B — numeric-typed portfolio fields.
  const requiredNumericFields = [
    "paper_equity_usd",
    "paper_open_positions_count",
    "paper_unrealized_pnl_usd",
    "paper_realized_pnl_usd",
    "real_account_equity_usd",
    "real_account_free_usd",
    "non_paper_wallet_balance_usd",
    "capital_x_usd",
  ];
  for (const key of requiredNumericFields) {
    if (!isNumericObservedValue(x[key])) return false;
  }

  if (!isBooleanObservedValue(x.real_account_stale)) return false;
  if (!isStringObservedValue(x.real_account_last_poll_utc)) return false;

  if (!isListObservedValue(x.open_positions, isValidOpenPosition)) return false;

  return true;
}

/** O-02W-D2-R1.1 Correction C, typed by O-02W-D2-R1.2 Corrections B/C —
 * every field DecisionsView renders or keys on, plus the remaining declared
 * PerSymbolDecision fields. `is_actionable`/`trade_allowed`/`first_blocker`
 * each require both their declared JS type AND their exact certified
 * authority mapping. */
function isValidPerSymbolDecision(x: unknown): boolean {
  if (!isPlainObject(x)) return false;
  if (!isNonBlankString(x.symbol)) return false;
  if (!isNullableString(x.packet_id)) return false;
  if (!isNullableString(x.context_id)) return false;
  if (!isNullableString(x.created_cycle_id)) return false;
  if (!isStringObservedValue(x.created_at)) return false;
  if (!isStringObservedValue(x.latest_transition_at_utc)) return false;
  if (!isStringObservedValue(x.side)) return false;
  if (!isNumericObservedValue(x.confidence_raw)) return false;
  if (!isNumericObservedValue(x.confidence_adjusted)) return false;
  if (!isStringObservedValue(x.regime)) return false;
  if (!isStringObservedValue(x.lifecycle_state)) return false;

  if (!isValidMappedAuthorityObservedValue(x.is_actionable, isBoolean, AUTHORITY_EXECUTION)) return false;
  if (!isValidMappedAuthorityObservedValue(x.trade_allowed, isBoolean, AUTHORITY_OBSERVATIONAL)) return false;
  if (!isValidMappedAuthorityObservedValue(x.first_blocker, (v) => typeof v === "string", AUTHORITY_OBSERVATIONAL)) {
    return false;
  }
  return true;
}

function isValidDecisionPipeline(x: unknown): boolean {
  if (!isPlainObject(x)) return false;
  if (!isValidDomainSpine(x, "decision_pipeline")) return false;
  if (!Array.isArray(x.stages)) return false;
  // O-02W-D2-R1.2 Correction B — the domain-level aggregate is boolean-
  // typed; its aggregate first_blocker is string-typed.
  if (!isBooleanObservedValue(x.trade_allowed)) return false;
  if (!isStringObservedValue(x.first_blocker)) return false;
  if (!Array.isArray(x.per_symbol_decisions)) return false;
  if (!x.per_symbol_decisions.every(isValidPerSymbolDecision)) return false;
  return true;
}

function isValidSystemHealth(x: unknown): boolean {
  if (!isPlainObject(x)) return false;
  if (!isValidDomainSpine(x, "system_health")) return false;
  // O-02W-D2-R1.2 Correction B — boot_alive/exchange_connectivity_healthy
  // are boolean-typed; a string `"false"` can never satisfy either and
  // therefore can never reach a boolean render callback via truthiness.
  if (!isBooleanObservedValue(x.boot_alive)) return false;
  if (!isNumericObservedValue(x.health_score)) return false;
  if (!isStringObservedValue(x.health_level)) return false;
  if (!isBooleanObservedValue(x.exchange_connectivity_healthy)) return false;
  if (!isNumericObservedValue(x.exchange_latency_ms)) return false;
  if (!isPlainObject(x.module_statuses)) return false;
  return true;
}

/** The single admission gate: only a body that passes this may ever be
 * assigned to `status: "success"`. Anything else must surface an explicit
 * client error state — never a partially-healthy render. Tightens every
 * top-level value directly interpolated into JSX (identifiers, `cycle`,
 * `snapshot_age_s`, timestamps, etc.) so an object/array can never occupy a
 * primitive presentation field. */
export function validateOperatorSnapshot(x: unknown): x is OperatorSnapshot {
  if (!isPlainObject(x)) return false;

  if (!isNonBlankString(x.schema_version)) return false;
  if (!isNonBlankString(x.snapshot_id)) return false;
  if (!Number.isSafeInteger(x.cycle) || (x.cycle as number) < 0) return false;
  if (!isNonBlankString(x.process_instance_id)) return false;
  if (!isNonBlankString(x.generated_at_utc)) return false;
  if (!isNullableNonBlankString(x.source_sha)) return false;
  if (!WORKTREE_STATES.has(x.worktree_state as string)) return false;
  if (!isValidDeploymentEvidence(x.deployment_evidence)) return false;
  if (!EVIDENCE_STATUSES.has(x.runtime_sha_evidence_status as string)) return false;

  if (!isValidPortfolio(x.portfolio)) return false;
  if (!isValidDecisionPipeline(x.decision_pipeline)) return false;
  if (!isValidSystemHealth(x.system_health)) return false;

  if (!INSTANCE_RELATIONS.has(x.instance_relation as string)) return false;
  if (!RUNTIME_STATES.has(x.runtime_state as string)) return false;
  if (!isNullableString(x.stale_reason)) return false;
  if (x.snapshot_age_s !== null && !(isFiniteNumber(x.snapshot_age_s) && (x.snapshot_age_s as number) >= 0)) {
    return false;
  }
  if (!isNonBlankString(x.freshness_classification)) return false;

  return true;
}

// Exported for reuse by tests/other modules without duplicating the
// vocabulary — not part of the validation logic itself.
export { DOMAIN_IDS, DOMAIN_STATUSES, FRESHNESS_STATUSES, AUTHORITY_VOCAB };
