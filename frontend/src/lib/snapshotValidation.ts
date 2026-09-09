// ── snapshotValidation — runtime boundary for the operator snapshot ────────
// O-02W-D2-R1 Correction B. `looksLikeSnapshot()` previously checked only
// five key names; a structurally malformed HTTP 200 body (null domains,
// wrong-typed collections, contradictory ObservedValue fields) could reach
// the views and crash them. This validates every field the cockpit actually
// renders before the client is allowed to report status="success" — it is
// not a second competing API contract, just the client's own admission gate.

import type { OperatorSnapshot } from "../types";
import { isObservedValue } from "./observedValue";

function isPlainObject(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

const WORKTREE_STATES = new Set(["CLEAN", "DIRTY", "UNKNOWN"]);
const EVIDENCE_STATUSES = new Set(["VERIFIED", "CLAIMED_ONLY", "UNKNOWN"]);
const PORTFOLIO_MODES = new Set(["PAPER", "REAL_API", "TESTNET_API", "UNKNOWN"]);
const INSTANCE_RELATIONS = new Set(["CURRENT_INSTANCE", "PREVIOUS_INSTANCE", "UNKNOWN"]);
const RUNTIME_STATES = new Set(["CURRENT", "LAST_KNOWN"]);

function isNullableString(x: unknown): boolean {
  return x === null || typeof x === "string";
}

/** An ObservedValue that must be valid per Correction A, and — whenever its
 * semantics carries an actual list (PRESENT/STALE) — must carry an array. */
function isValidListObservedValue(x: unknown): boolean {
  if (!isObservedValue(x)) return false;
  if (x.semantics === "PRESENT" || x.semantics === "STALE") {
    return Array.isArray(x.value);
  }
  return true;
}

function isValidDeploymentEvidence(x: unknown): boolean {
  if (!isPlainObject(x)) return false;
  if (!EVIDENCE_STATUSES.has(x.status as string)) return false;
  if (x.source !== null && typeof x.source !== "string") return false;
  if (x.evidence_ref !== null && typeof x.evidence_ref !== "string") return false;
  if (!isNullableString(x.observed_at_utc)) return false;
  return true;
}

function isValidOpenPosition(x: unknown): boolean {
  if (!isPlainObject(x)) return false;
  if (typeof x.position_id !== "string") return false;
  if (typeof x.symbol !== "string") return false;
  if (!isObservedValue(x.current_price)) return false;
  if (!isObservedValue(x.unrealized_pnl_usd)) return false;
  if (!isObservedValue(x.unrealized_pnl_pct)) return false;
  if (!isObservedValue(x.regime)) return false;
  return true;
}

function isValidPortfolio(x: unknown): boolean {
  if (!isPlainObject(x)) return false;
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

function isValidAuthorityObservedValue(x: unknown): boolean {
  // is_actionable/trade_allowed/first_blocker carry an extra `authority`
  // key alongside value/semantics — isObservedValue tolerates extra keys.
  if (!isObservedValue(x)) return false;
  const authority = (x as unknown as Record<string, unknown>).authority;
  return typeof authority === "string" && authority.length > 0;
}

function isValidPerSymbolDecision(x: unknown): boolean {
  if (!isPlainObject(x)) return false;
  if (typeof x.symbol !== "string") return false;
  if (!isValidAuthorityObservedValue(x.is_actionable)) return false;
  if (!isValidAuthorityObservedValue(x.trade_allowed)) return false;
  if (!isValidAuthorityObservedValue(x.first_blocker)) return false;
  if (!isObservedValue(x.side)) return false;
  if (!isObservedValue(x.regime)) return false;
  if (!isObservedValue(x.lifecycle_state)) return false;
  return true;
}

function isValidDecisionPipeline(x: unknown): boolean {
  if (!isPlainObject(x)) return false;
  if (!Array.isArray(x.stages)) return false;
  if (!isObservedValue(x.trade_allowed)) return false;
  if (!isObservedValue(x.first_blocker)) return false;
  if (!Array.isArray(x.per_symbol_decisions)) return false;
  if (!x.per_symbol_decisions.every(isValidPerSymbolDecision)) return false;
  return true;
}

function isValidSystemHealth(x: unknown): boolean {
  if (!isPlainObject(x)) return false;
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
 * client error state — never a partially-healthy render. */
export function validateOperatorSnapshot(x: unknown): x is OperatorSnapshot {
  if (!isPlainObject(x)) return false;

  if (typeof x.schema_version !== "string") return false;
  if (typeof x.snapshot_id !== "string" || x.snapshot_id.length === 0) return false;
  if (typeof x.cycle !== "number") return false;
  if (typeof x.process_instance_id !== "string" || x.process_instance_id.length === 0) return false;
  if (typeof x.generated_at_utc !== "string") return false;
  if (!isNullableString(x.source_sha)) return false;
  if (!WORKTREE_STATES.has(x.worktree_state as string)) return false;
  if (!isValidDeploymentEvidence(x.deployment_evidence)) return false;
  if (!EVIDENCE_STATUSES.has(x.runtime_sha_evidence_status as string)) return false;

  if (!isValidPortfolio(x.portfolio)) return false;
  if (!isValidDecisionPipeline(x.decision_pipeline)) return false;
  if (!isValidSystemHealth(x.system_health)) return false;

  if (!INSTANCE_RELATIONS.has(x.instance_relation as string)) return false;
  if (!RUNTIME_STATES.has(x.runtime_state as string)) return false;
  if (!isNullableString(x.stale_reason)) return false;
  if (x.snapshot_age_s !== null && typeof x.snapshot_age_s !== "number") return false;
  if (typeof x.freshness_classification !== "string") return false;

  return true;
}
