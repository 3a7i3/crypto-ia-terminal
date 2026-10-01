import type {
  BurnInHistoryRow,
  BurnInOpenLifecycle,
  BurnInStatusSnapshot,
} from "./burnInStatusTypes";

function plain(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}
function exact(x: Record<string, unknown>, expected: readonly string[]): boolean {
  const actual = Object.keys(x).sort();
  const wanted = [...expected].sort();
  return actual.length === wanted.length && actual.every((key, i) => key === wanted[i]);
}
function str(x: unknown): x is string {
  return typeof x === "string" && x.trim().length > 0;
}
function nullableStr(x: unknown): boolean {
  return x === null || str(x);
}
function finite(x: unknown): x is number {
  return typeof x === "number" && Number.isFinite(x);
}
function nnInt(x: unknown): x is number {
  return Number.isSafeInteger(x) && (x as number) >= 0;
}
function utc(x: unknown): boolean {
  return str(x) && Number.isFinite(Date.parse(x));
}
function nullableUtc(x: unknown): boolean {
  return x === null || utc(x);
}
function hash(x: unknown, n: number): boolean {
  return typeof x === "string" && x.length === n && /^[0-9a-f]+$/.test(x.toLowerCase());
}

const TOP = [
  "schema_version", "product", "domain", "authority", "mode",
  "generated_at_utc", "source_updated_at_utc", "paper_epoch_id",
  "epoch_created_at_utc", "source_code_sha", "config_snapshot_hash",
  "ppl_stream_sha256", "scientific_t0", "event_count", "last_sequence",
  "event_counts", "lifecycle_counts", "last_event", "open_lifecycles",
  "lifecycle_history", "history_order", "frozen_config", "finalization",
  "snapshot_age_s", "freshness_classification",
] as const;
const OPEN = [
  "trade_id", "decision_id", "symbol", "side", "principal_usd", "entry_price",
  "entry_fee_usd", "opened_sequence", "opened_at_utc", "age_seconds", "tp_price",
  "sl_price", "timeout_at_utc", "recovery_eligible_until_utc", "deadline_state",
] as const;
const HISTORY = [
  "trade_id", "open_decision_id", "terminal_decision_id", "symbol", "side",
  "principal_usd", "entry_price", "entry_fee_usd", "opened_sequence",
  "opened_at_utc", "status", "terminal_sequence", "terminal_at_utc",
  "exit_price", "exit_fee_usd", "gross_pnl_usd", "net_realized_pnl_usd",
  "unresolved_reason", "duration_seconds",
] as const;
const EVENT_KEYS = [
  "EPOCH_CREATED", "POSITION_OPENED", "POSITION_CLOSED",
  "POSITION_UNRESOLVED", "RECOVERY_COMPLETED",
] as const;
const DEADLINES = new Set(["BEFORE_TIMEOUT", "RECOVERY_WINDOW", "RECOVERY_EXPIRED", "NOT_AVAILABLE"]);
const STATUSES = new Set(["OPEN", "CLOSED", "UNRESOLVED"]);
const EVENTS: ReadonlySet<string> = new Set(EVENT_KEYS);

function validOpen(x: unknown): x is BurnInOpenLifecycle {
  if (!plain(x) || !exact(x, OPEN)) return false;
  if (!str(x.trade_id) || !nullableStr(x.decision_id) || !str(x.symbol)) return false;
  if (x.side !== "LONG" && x.side !== "SHORT") return false;
  for (const key of ["principal_usd", "entry_price", "entry_fee_usd", "age_seconds"] as const) {
    if (!finite(x[key]) || x[key] < 0) return false;
  }
  if (!nnInt(x.opened_sequence) || x.opened_sequence < 1 || !utc(x.opened_at_utc)) return false;
  for (const key of ["tp_price", "sl_price"] as const) {
    if (x[key] !== null && !finite(x[key])) return false;
  }
  return nullableUtc(x.timeout_at_utc) &&
    nullableUtc(x.recovery_eligible_until_utc) &&
    typeof x.deadline_state === "string" &&
    DEADLINES.has(x.deadline_state);
}

function validHistory(x: unknown): x is BurnInHistoryRow {
  if (!plain(x) || !exact(x, HISTORY)) return false;
  if (!str(x.trade_id) || !nullableStr(x.open_decision_id) || !nullableStr(x.terminal_decision_id)) return false;
  if (!str(x.symbol) || (x.side !== "LONG" && x.side !== "SHORT")) return false;
  for (const key of ["principal_usd", "entry_price", "entry_fee_usd"] as const) {
    if (!finite(x[key])) return false;
  }
  if (!nnInt(x.opened_sequence) || x.opened_sequence < 1 || !utc(x.opened_at_utc)) return false;
  if (typeof x.status !== "string" || !STATUSES.has(x.status)) return false;
  if (x.terminal_sequence !== null && (!nnInt(x.terminal_sequence) || x.terminal_sequence < 1)) return false;
  if (!nullableUtc(x.terminal_at_utc)) return false;
  for (const key of ["exit_price", "exit_fee_usd", "gross_pnl_usd", "net_realized_pnl_usd"] as const) {
    if (x[key] !== null && !finite(x[key])) return false;
  }
  const durationSeconds = x.duration_seconds;
  if (durationSeconds !== null && (!finite(durationSeconds) || durationSeconds < 0)) return false;
  if (!nullableStr(x.unresolved_reason)) return false;

  if (x.status === "OPEN") {
    return [
      x.terminal_sequence, x.terminal_at_utc, x.exit_price, x.exit_fee_usd,
      x.gross_pnl_usd, x.net_realized_pnl_usd, x.unresolved_reason, x.duration_seconds,
    ].every((value) => value === null);
  }
  if (x.status === "CLOSED") {
    return x.terminal_sequence !== null && x.terminal_at_utc !== null &&
      x.exit_price !== null && x.exit_fee_usd !== null &&
      x.gross_pnl_usd !== null && x.net_realized_pnl_usd !== null &&
      x.unresolved_reason === null && x.duration_seconds !== null;
  }
  return x.terminal_sequence !== null && x.terminal_at_utc !== null &&
    x.exit_price === null && x.exit_fee_usd === null &&
    x.gross_pnl_usd === null && x.net_realized_pnl_usd === null &&
    str(x.unresolved_reason) && x.duration_seconds !== null;
}

export function validateBurnInStatusSnapshot(x: unknown): x is BurnInStatusSnapshot {
  if (!plain(x) || !exact(x, TOP)) return false;
  if (x.schema_version !== "1.0.0" || x.product !== "BurnInStatusSnapshot") return false;
  if (x.domain !== "burn_in" || x.authority !== "PPL_AUTHORITY_PRESENTATION" || x.mode !== "READ_ONLY") return false;
  if (!utc(x.generated_at_utc) || !utc(x.source_updated_at_utc) || !str(x.paper_epoch_id) || !utc(x.epoch_created_at_utc)) return false;
  if (!hash(x.source_code_sha, 40) || !hash(x.config_snapshot_hash, 64) || !hash(x.ppl_stream_sha256, 64)) return false;

  if (!plain(x.scientific_t0) || !exact(x.scientific_t0, ["status", "value_utc", "source"])) return false;
  if (x.scientific_t0.status === "PRESENT") {
    if (!utc(x.scientific_t0.value_utc) || !str(x.scientific_t0.source)) return false;
  } else if (x.scientific_t0.status === "NOT_AVAILABLE") {
    if (x.scientific_t0.value_utc !== null || x.scientific_t0.source !== null) return false;
  } else return false;

  if (!nnInt(x.event_count) || x.event_count < 1 || !nnInt(x.last_sequence) || x.last_sequence < 1) return false;
  if (!plain(x.event_counts) || !exact(x.event_counts, EVENT_KEYS)) return false;
  let sum = 0;
  for (const key of EVENT_KEYS) {
    if (!nnInt(x.event_counts[key])) return false;
    sum += x.event_counts[key] as number;
  }
  if (sum !== x.event_count) return false;

  if (!plain(x.lifecycle_counts) || !exact(x.lifecycle_counts, ["open", "closed", "unresolved", "total"])) return false;
  const lc = x.lifecycle_counts;
  for (const key of ["open", "closed", "unresolved", "total"] as const) {
    if (!nnInt(lc[key])) return false;
  }
  if (Number(lc.open) + Number(lc.closed) + Number(lc.unresolved) !== Number(lc.total)) return false;
  if (lc.total !== x.event_counts.POSITION_OPENED) return false;

  if (!plain(x.last_event) || !exact(x.last_event, ["sequence", "event_type", "timestamp_utc", "trade_id", "decision_id"])) return false;
  if (x.last_event.sequence !== x.last_sequence || !nnInt(x.last_event.sequence)) return false;
  if (typeof x.last_event.event_type !== "string" || !EVENTS.has(x.last_event.event_type)) return false;
  if (!utc(x.last_event.timestamp_utc) || !nullableStr(x.last_event.trade_id) || !nullableStr(x.last_event.decision_id)) return false;

  if (!Array.isArray(x.open_lifecycles) || !x.open_lifecycles.every(validOpen)) return false;
  if (x.open_lifecycles.length !== lc.open) return false;
  if (!Array.isArray(x.lifecycle_history) || !x.lifecycle_history.every(validHistory)) return false;
  if (x.lifecycle_history.length !== lc.total) return false;
  if (new Set(x.lifecycle_history.map((row) => row.trade_id)).size !== x.lifecycle_history.length) return false;
  if (x.history_order !== "OPEN_SEQUENCE_DESC") return false;

  if (!plain(x.frozen_config) || !exact(x.frozen_config, [
    "snapshot_schema", "snapshot_sha256", "runtime_source_sha", "pb_max_positions",
    "paper_portfolio_brain_level", "mexc_sim_max_position_usd", "mexc_sim_max_age_h",
    "paper_lifecycle_authority",
  ])) return false;
  if (x.frozen_config.snapshot_schema !== "BURN_IN_EXPERIMENT_CONFIG_V1") return false;
  if (!hash(x.frozen_config.snapshot_sha256, 64) || !hash(x.frozen_config.runtime_source_sha, 40)) return false;
  for (const key of ["pb_max_positions", "paper_portfolio_brain_level", "mexc_sim_max_position_usd", "mexc_sim_max_age_h", "paper_lifecycle_authority"] as const) {
    if (!str(x.frozen_config[key])) return false;
  }
  if (x.frozen_config.snapshot_sha256 !== x.config_snapshot_hash || x.frozen_config.runtime_source_sha !== x.source_code_sha) return false;

  if (!plain(x.finalization) || !exact(x.finalization, ["state", "reason"])) return false;
  if (x.finalization.state !== "NOT_AVAILABLE" || !str(x.finalization.reason)) return false;
  if (!finite(x.snapshot_age_s) || x.snapshot_age_s < 0) return false;
  return x.freshness_classification === "FRESH" || x.freshness_classification === "STALE";
}
