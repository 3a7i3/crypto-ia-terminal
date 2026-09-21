import type {
  FinancialComparability,
  FinancialFreshness,
  FinancialReconciliationRecord,
  FinancialReconciliationSnapshot,
  FinancialReconciliationStatus,
  FinancialSourceKind,
} from "./financialReconciliationTypes";

const RECON = new Set<FinancialReconciliationStatus>([
  "EXACT",
  "WITHIN_TOLERANCE",
  "DIVERGENT",
  "UNRESOLVED",
]);
const COMP = new Set<FinancialComparability>([
  "COMPARABLE",
  "NON_COMPARABLE",
  "UNAVAILABLE",
  "NOT_APPLICABLE",
]);
const FRESH = new Set<FinancialFreshness>([
  "LIVE",
  "STALE",
  "UNAVAILABLE",
  "NOT_APPLICABLE",
]);
const SOURCE = new Set<FinancialSourceKind>([
  "PPL",
  "SIMULATOR",
  "EXCHANGE_READ_ONLY",
]);

function obj(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

function nonEmpty(x: unknown): x is string {
  return typeof x === "string" && x.length > 0;
}

function decimalText(x: unknown, nullable = false): x is string | null {
  if (x === null) return nullable;
  if (typeof x !== "string" || x.length === 0) return false;
  const value = Number(x);
  return Number.isFinite(value);
}

function nonNegativeInt(x: unknown): x is number {
  return typeof x === "number" && Number.isInteger(x) && x >= 0;
}

function record(x: unknown): x is FinancialReconciliationRecord {
  if (!obj(x)) return false;
  if (!nonEmpty(x.record_id) || !nonEmpty(x.source_id) || !nonEmpty(x.field)) return false;
  if (!SOURCE.has(x.source_kind as FinancialSourceKind)) return false;
  if (!RECON.has(x.status as FinancialReconciliationStatus)) return false;
  if (!COMP.has(x.comparability as FinancialComparability)) return false;
  if (!FRESH.has(x.freshness as FinancialFreshness)) return false;
  if (!decimalText(x.projected_value, true)) return false;
  if (!decimalText(x.observed_value, true)) return false;
  if (!decimalText(x.delta_observed_minus_projected, true)) return false;
  if (!decimalText(x.unreconciled_amount, true)) return false;
  if (!decimalText(x.observed_at)) return false;
  if (!nonEmpty(x.projected_provenance) || !nonEmpty(x.observed_provenance)) return false;
  if (x.note !== null && typeof x.note !== "string") return false;
  return true;
}

export function validateFinancialReconciliationSnapshot(
  x: unknown,
): x is FinancialReconciliationSnapshot {
  if (!obj(x)) return false;
  if (x.schema_version !== "1.0.0") return false;
  if (x.product !== "FIN02FinancialCockpit") return false;
  if (x.domain !== "financial_reconciliation") return false;
  if (x.authority !== "FINANCIAL_OBSERVATION") return false;
  if (!nonEmpty(x.generated_at_utc) || Number.isNaN(Date.parse(x.generated_at_utc))) return false;

  for (const key of [
    "reconciliation_id",
    "paper_epoch_id",
    "financial_snapshot_id",
    "reconciliation_code_sha",
    "source_stream_digest",
    "fin_code_sha",
    "source_code_sha",
    "config_hash",
    "financial_model",
    "asset",
  ] as const) {
    if (!nonEmpty(x[key])) return false;
  }

  if (!nonNegativeInt(x.last_source_sequence) || x.last_source_sequence < 1) return false;
  if (!nonNegativeInt(x.fin_schema_version) || x.fin_schema_version < 1) return false;
  if (!obj(x.financial) || !obj(x.reconciliation) || !obj(x.sources)) return false;

  const financial = x.financial;
  for (const key of [
    "initial_epoch_capital",
    "cash_available",
    "capital_reserved",
    "capital_deployed",
    "capital_unresolved",
    "gross_realized_price_pnl",
    "fees_paid",
    "known_unrealized_pnl",
    "valuation_as_of",
  ]) {
    if (!decimalText(financial[key])) return false;
  }
  for (const key of ["funding_net", "realized_pnl", "unrealized_pnl", "certified_equity"]) {
    if (!decimalText(financial[key], true)) return false;
  }
  if (!nonNegativeInt(financial.open_position_count)) return false;
  if (!nonNegativeInt(financial.settled_position_count)) return false;
  if (!nonNegativeInt(financial.unresolved_position_count)) return false;
  if (!RECON.has(financial.reconciliation_status as FinancialReconciliationStatus)) return false;
  if (!Array.isArray(financial.valuation_statuses)) return false;

  const reconciliation = x.reconciliation;
  if (!RECON.has(reconciliation.overall_status as FinancialReconciliationStatus)) return false;
  if (!decimalText(reconciliation.as_of)) return false;
  if (!decimalText(reconciliation.unresolved_capital)) return false;
  if (!decimalText(reconciliation.unreconciled_capital, true)) return false;
  if (!obj(reconciliation.policy)) return false;
  for (const key of ["absolute_tolerance", "relative_tolerance", "stale_after_s"]) {
    if (!decimalText(reconciliation.policy[key])) return false;
  }

  if (!Array.isArray(x.records) || !x.records.every(record)) return false;
  const ids = x.records.map((row) => row.record_id);
  if (new Set(ids).size !== ids.length) return false;

  if (typeof x.snapshot_age_s !== "number" || !Number.isFinite(x.snapshot_age_s) || x.snapshot_age_s < 0) return false;
  if (x.freshness_classification !== "FRESH" && x.freshness_classification !== "STALE") return false;

  return true;
}
