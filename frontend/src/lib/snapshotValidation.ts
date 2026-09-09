// ── snapshotValidation — runtime boundary for the operator snapshot ────────
// O-02W-D2-R1 Correction B, hardened by O-02W-D2-R1.1 Corrections A-D.
// `looksLikeSnapshot()` originally checked only five key names; R1's
// `validateOperatorSnapshot()` closed most gaps but MASTER reproduced four
// residual admission holes on HEAD 29c1747 (`portfolio.status = {bad:
// true}`, `system_health.freshness = ["bad"]`, `open_positions[].side =
// {bad: true}`, a contradictory `confidence_raw`) — each returned `true`
// and let a value React cannot safely render reach a view. This module now
// validates every domain-spine field (domain id / status / freshness
// closed vocabularies), every OpenPosition field React renders or keys on,
// every PerSymbolDecision field DecisionsView renders, and every top-level
// primitive interpolated directly into JSX — before a response is ever
// assigned status="success". This is the client's own admission gate, not
// a second competing API contract, and it never infers, repairs, or
// normalizes a malformed value — only accepts or rejects it whole.

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

/** An ObservedValue that must be valid per Correction A, and — whenever its
 * semantics carries an actual list (PRESENT/STALE) — must carry an array. */
function isValidListObservedValue(x: unknown): boolean {
  if (!isObservedValue(x)) return false;
  if (x.semantics === "PRESENT" || x.semantics === "STALE") {
    return Array.isArray(x.value);
  }
  return true;
}

function isValidAuthorityObservedValue(x: unknown): boolean {
  // is_actionable/trade_allowed/first_blocker carry an extra `authority`
  // key alongside value/semantics — isObservedValue tolerates extra keys.
  if (!isObservedValue(x)) return false;
  const authority = (x as unknown as Record<string, unknown>).authority;
  return isNonBlankString(authority);
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
 * primitive, so only shape-checked), and the two R1-added envelope fields
 * (`source_updated_at_utc`, `authority`) must themselves be valid. */
function isValidDomainSpine(x: Record<string, unknown>, expectedDomain: string): boolean {
  if (x.domain !== expectedDomain) return false;
  if (!DOMAIN_STATUSES.has(x.status as string)) return false;
  if (!FRESHNESS_STATUSES.has(x.freshness as string)) return false;
  if (!isNonBlankString(x.schema_version)) return false;
  if (!isNonBlankString(x.source)) return false;
  if (!isNonBlankString(x.observed_at_utc)) return false;
  if (!isNullableString(x.source_version)) return false;
  if (!isPlainObject(x.evidence)) return false;
  if (!isObservedValue(x.source_updated_at_utc)) return false;
  if (!isNonBlankString(x.authority)) return false;
  return true;
}

/** O-02W-D2-R1.1 Correction B — every OpenPosition field React renders or
 * uses as list identity/key. An object or array in any directly-rendered
 * primitive field invalidates the whole snapshot. */
function isValidOpenPosition(x: unknown): boolean {
  if (!isPlainObject(x)) return false;
  if (!isNonBlankString(x.position_id)) return false;
  if (!isNonBlankString(x.symbol)) return false;
  if (!isNullableString(x.side)) return false;
  if (!isNullableFiniteNumber(x.size_usd)) return false;
  if (!isNullableFiniteNumber(x.entry_price)) return false;
  if (!isObservedValue(x.current_price)) return false;
  if (!isNullableString(x.current_price_observed_at_utc)) return false;
  if (!isNullableFiniteNumber(x.tp_price)) return false;
  if (!isNullableFiniteNumber(x.sl_price)) return false;
  if (!isNonBlankString(x.tp_sl_source)) return false;
  if (!isObservedValue(x.unrealized_pnl_usd)) return false;
  if (!isObservedValue(x.unrealized_pnl_pct)) return false;
  if (!isNullableString(x.opened_at)) return false;
  if (!isObservedValue(x.regime)) return false;
  if (!isBoolean(x.restored_without_regime)) return false;
  if (!isNullableString(x.personality)) return false;
  if (!isBoolean(x.restored)) return false;
  return true;
}

function isValidPortfolio(x: unknown): boolean {
  if (!isPlainObject(x)) return false;
  if (!isValidDomainSpine(x, "portfolio")) return false;
  if (!PORTFOLIO_MODES.has(x.mode as string)) return false;

  const requiredObservedValues = [
    "paper_equity_usd",
    "paper_open_positions_count",
    "paper_unrealized_pnl_usd",
    "paper_realized_pnl_usd",
    "real_account_equity_usd",
    "real_account_free_usd",
    "real_account_stale",
    "real_account_last_poll_utc",
    "non_paper_wallet_balance_usd",
    "capital_x_usd",
  ];
  for (const key of requiredObservedValues) {
    if (!isObservedValue(x[key])) return false;
  }

  if (!isValidListObservedValue(x.open_positions)) return false;
  const opv = x.open_positions as { semantics: string; value: unknown };
  if ((opv.semantics === "PRESENT" || opv.semantics === "STALE") && Array.isArray(opv.value)) {
    if (!opv.value.every(isValidOpenPosition)) return false;
  }

  return true;
}

/** O-02W-D2-R1.1 Correction C — every field DecisionsView renders or keys
 * on, plus the remaining declared PerSymbolDecision fields. */
function isValidPerSymbolDecision(x: unknown): boolean {
  if (!isPlainObject(x)) return false;
  if (!isNonBlankString(x.symbol)) return false;
  if (!isNullableString(x.packet_id)) return false;
  if (!isNullableString(x.context_id)) return false;
  if (!isNullableString(x.created_cycle_id)) return false;
  if (!isObservedValue(x.created_at)) return false;
  if (!isObservedValue(x.latest_transition_at_utc)) return false;
  if (!isObservedValue(x.side)) return false;
  if (!isObservedValue(x.confidence_raw)) return false;
  if (!isObservedValue(x.confidence_adjusted)) return false;
  if (!isObservedValue(x.regime)) return false;
  if (!isObservedValue(x.lifecycle_state)) return false;
  if (!isValidAuthorityObservedValue(x.is_actionable)) return false;
  if (!isValidAuthorityObservedValue(x.trade_allowed)) return false;
  if (!isValidAuthorityObservedValue(x.first_blocker)) return false;
  return true;
}

function isValidDecisionPipeline(x: unknown): boolean {
  if (!isPlainObject(x)) return false;
  if (!isValidDomainSpine(x, "decision_pipeline")) return false;
  if (!Array.isArray(x.stages)) return false;
  if (!isObservedValue(x.trade_allowed)) return false;
  if (!isObservedValue(x.first_blocker)) return false;
  if (!Array.isArray(x.per_symbol_decisions)) return false;
  if (!x.per_symbol_decisions.every(isValidPerSymbolDecision)) return false;
  return true;
}

function isValidSystemHealth(x: unknown): boolean {
  if (!isPlainObject(x)) return false;
  if (!isValidDomainSpine(x, "system_health")) return false;
  if (!isObservedValue(x.boot_alive)) return false;
  if (!isObservedValue(x.health_score)) return false;
  if (!isObservedValue(x.health_level)) return false;
  if (!isObservedValue(x.exchange_connectivity_healthy)) return false;
  if (!isObservedValue(x.exchange_latency_ms)) return false;
  if (!isPlainObject(x.module_statuses)) return false;
  return true;
}

/** The single admission gate: only a body that passes this may ever be
 * assigned to `status: "success"`. Anything else must surface an explicit
 * client error state — never a partially-healthy render. O-02W-D2-R1.1
 * Correction D tightens every top-level value directly interpolated into
 * JSX (identifiers, `cycle`, `snapshot_age_s`, timestamps, etc.) so an
 * object/array can never occupy a primitive presentation field. */
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

// Exported for DOMAIN_IDS reuse by tests/other modules without duplicating
// the vocabulary — not part of the validation logic itself.
export { DOMAIN_IDS, DOMAIN_STATUSES, FRESHNESS_STATUSES };
