// CryptoRadar Flux — deep validation of MarketFlowArtifact 1.0.0 (lot 3A).
//
// A line-by-line port of the FORM and INTERNAL-CONSISTENCY rules owned by
// contract.py and artifact.validate_artifact of the Python Flux package. The
// Python module remains the oracle: nothing here is looser, and no business
// invariant is added that the oracle does not make. Every structure is closed
// (exact keys at every node); UNKNOWN is never 0; nothing is recomputed,
// normalised or mutated, and no value is promoted (a FUTURE_TIMESTAMP or STALE
// book stays that, whatever the browser clock says).
//
// Passing says the document is well formed and self-consistent. It says
// nothing about whether the trades or the book are true, fresh or admitted.
// Run it on a document obtained through readStrictJson: a predicate over an
// already parsed value cannot see duplicate keys or the lexeme 1.0.

import {
  BOOK_STATUS_RE, CODE_RE, HEX64_RE, decAdd, decCompare, decDivModPositive, decEquals, decIsPositive,
  decIsZero, decSub, isContractText, isSafeCounter, parseDecimal, parseNs, type ExactDecimal,
} from "./marketFlowExact";
import {
  MARKET_FLOW_AGE_STATUSES, MARKET_FLOW_BAR_STATUSES, MARKET_FLOW_BOOK_STATES, MARKET_FLOW_CALC_VERSION,
  MARKET_FLOW_CHANNEL, MARKET_FLOW_FRESHNESS, MARKET_FLOW_INSTRUMENTS, MARKET_FLOW_L2_REFUSALS,
  MARKET_FLOW_LEVEL_TIME_STATES, MARKET_FLOW_PRODUCT, MARKET_FLOW_SCHEMA_VERSION, MARKET_FLOW_SEND_STATES,
  MARKET_FLOW_SILENCE_STATUSES, MARKET_FLOW_VENUE, type MarketFlowArtifact, type MarketFlowPublication,
} from "./marketFlowTypes";

export const MAX_BARS = 100_000;
export const MAX_COLUMNS = 10_000;
export const MAX_ROWS = 100_000;
export const MAX_ITEMS = 1_000;
export const MAX_LIST = 256;
export const MAX_TEXT = 512;
/** Depth guard of the walk over an arbitrary value (a valid document is 7 deep). */
const MAX_WALK_DEPTH = 64;

export const MARKET_FLOW_INVALID_REASONS: readonly string[] = [
  "SEQUENCE_DUPLICATE_OR_REORDERED", "SEQUENCE_GAP", "CROSSED_OR_LOCKED_BOOK",
  ...MARKET_FLOW_L2_REFUSALS.map(r => "MALFORMED_MESSAGE:" + r),
  ...MARKET_FLOW_L2_REFUSALS.map(r => "APPLY_REFUSED:" + r),
];

export const MARKET_FLOW_ARTIFACT_KEYS = [
  "schema_version", "product", "calc_version", "evidence_kind", "synthetic", "state_label", "flow",
  "as_of_receipt_ns", "anchor_ns", "bar_ns", "inputs", "trades", "bars", "rolling_delta", "book", "heatmap",
  "level_events", "assumptions", "limits", "economic_metrics", "score", "recommendation",
] as const;

export interface MarketFlowViolation {
  /** Same vocabulary as the Python oracle (CLOSED_KEYS_REQUIRED, ENUM_REFUSED, ...). */
  readonly code: string;
  readonly path: string;
}
export type MarketFlowCheck = { readonly ok: true } | ({ readonly ok: false } & MarketFlowViolation);

class Violation extends Error {
  constructor(readonly code: string, readonly path: string) {
    super(code + ":" + path);
  }
}

function bad(path: string, code = "CONTRACT_VIOLATION"): never {
  throw new Violation(code, path);
}

type Rec = Record<string, unknown>;

const isRecord = (x: unknown): x is Rec => typeof x === "object" && x !== null && !Array.isArray(x);
const has = (o: object, k: string): boolean => Object.prototype.hasOwnProperty.call(o, k);

function obj(x: unknown, keys: readonly string[], path: string): Rec {
  if (!isRecord(x)) return bad(path, "CLOSED_KEYS_REQUIRED");
  const own = Object.keys(x);
  if (own.length !== keys.length || !keys.every(k => has(x, k))) return bad(path, "CLOSED_KEYS_REQUIRED");
  return x;
}

function int(x: unknown, path: string, lo = 0, hi = Number.MAX_SAFE_INTEGER): number {
  if (!isSafeCounter(x, lo, hi)) return bad(path, "INTEGER_REQUIRED");
  return x;
}

function boolean(x: unknown, path: string): boolean {
  if (typeof x !== "boolean") return bad(path, "BOOLEAN_REQUIRED");
  return x;
}

function text(x: unknown, path: string, maxLen = MAX_TEXT): string {
  if (!isContractText(x, maxLen)) return bad(path, "TEXT_REQUIRED");
  return x;
}

function code(x: unknown, path: string): string {
  if (typeof x !== "string" || !CODE_RE.test(x)) return bad(path, "CODE_REQUIRED");
  return x;
}

function oneOf<T extends string>(x: unknown, allowed: readonly T[], path: string): T {
  if (typeof x !== "string" || !(allowed as readonly string[]).includes(x)) return bad(path, "ENUM_REFUSED");
  return x as T;
}

function ns(x: unknown, path: string, signed = false): bigint {
  const v = parseNs(x, signed);
  if (v === null) return bad(path, "NS_MUST_BE_DECIMAL_STRING");
  return v;
}

function dec(x: unknown, path: string, signed = false, positive = false): ExactDecimal {
  const v = parseDecimal(x, signed);
  if (v === null) return bad(path, "DECIMAL_TEXT_REQUIRED");
  if (positive && !decIsPositive(v)) return bad(path, "POSITIVE_DECIMAL_REQUIRED");
  return v;
}

function mustBeNone(x: unknown, path: string): void {
  if (x !== null) bad(path, "NULL_REQUIRED");
}

function strList(x: unknown, path: string): void {
  if (!Array.isArray(x) || x.length > MAX_LIST) return bad(path, "LIST_REQUIRED");
  x.forEach((v, i) => text(v, path + "[" + i + "]"));
}

function span(x: unknown, path: string, signed = false): [bigint, bigint] {
  if (!Array.isArray(x) || x.length !== 2) return bad(path, "PAIR_REQUIRED");
  const lo = ns(x[0], path + "[0]", signed);
  const hi = ns(x[1], path + "[1]", signed);
  if (lo > hi) return bad(path, "INTERVAL_ORDER");
  return [lo, hi];
}

function decBounds(x: unknown, path: string): [ExactDecimal, ExactDecimal] {
  if (!Array.isArray(x) || x.length !== 2) return bad(path, "PAIR_REQUIRED");
  const lo = dec(x[0], path + "[0]", true);
  const hi = dec(x[1], path + "[1]", true);
  if (decCompare(lo, hi) > 0) return bad(path, "INTERVAL_ORDER");
  return [lo, hi];
}

// ---------------------------------------------------------------- flow

const FLOW_KEYS = ["venue", "instrument", "base", "quote", "market_kind", "id_domain", "side_convention"] as const;

function checkFlow(f: unknown): Rec {
  const flow = obj(f, FLOW_KEYS, "flow");
  for (const k of ["venue", "instrument", "base", "quote"]) text(flow[k], "flow." + k, 64);
  oneOf(flow.market_kind, ["SPOT"], "flow.market_kind");
  oneOf(flow.id_domain, ["SESSION", "INSTRUMENT"], "flow.id_domain");
  const sc = obj(flow.side_convention, ["attested", "evidence_ref"], "flow.side_convention");
  boolean(sc.attested, "flow.side_convention.attested");
  text(sc.evidence_ref, "flow.side_convention.evidence_ref");
  // The book layer is the Coinbase Advanced L2 candidate: no other venue / product label.
  if (flow.venue !== MARKET_FLOW_VENUE) bad("flow.venue", "FLOW_BOOK_IDENTITY_MISMATCH");
  const pair = typeof flow.instrument === "string" && has(MARKET_FLOW_INSTRUMENTS, flow.instrument)
    ? MARKET_FLOW_INSTRUMENTS[flow.instrument as keyof typeof MARKET_FLOW_INSTRUMENTS]
    : null;
  if (pair === null || flow.base !== pair[0] || flow.quote !== pair[1]) bad("flow.instrument", "FLOW_BOOK_IDENTITY_MISMATCH");
  return flow;
}

// ---------------------------------------------------------------- inputs / trades

function checkInputs(x: unknown): void {
  const o = obj(x, ["events_sha256", "event_count", "events_after_as_of_not_read",
    "events_straddling_as_of_not_read", "l2_events_not_read_after_straddle"], "inputs");
  if (typeof o.events_sha256 !== "string" || !HEX64_RE.test(o.events_sha256)) bad("inputs.events_sha256", "SHA256_REQUIRED");
  for (const k of ["event_count", "events_after_as_of_not_read", "events_straddling_as_of_not_read",
    "l2_events_not_read_after_straddle"]) int(o[k], "inputs." + k);
}

function checkTrades(x: unknown): void {
  const t = obj(x, ["accepted", "duplicates", "conflicts", "refused", "sessions", "excluded"], "trades");
  int(t.accepted, "trades.accepted");
  int(t.duplicates, "trades.duplicates");
  if (!Array.isArray(t.conflicts) || t.conflicts.length > MAX_ITEMS * 10) bad("trades.conflicts", "LIST_REQUIRED");
  (t.conflicts as unknown[]).forEach((c, i) => {
    const p = "trades.conflicts[" + i + "]";
    const o = obj(c, ["trade_id", "session_id"], p);
    text(o.trade_id, p + ".trade_id");
    text(o.session_id, p + ".session_id");
  });
  if (!isRecord(t.refused) || Object.keys(t.refused).length > MAX_LIST) bad("trades.refused", "OBJECT_REQUIRED");
  for (const [k, v] of Object.entries(t.refused as Rec)) {
    code(k, "trades.refused.key");
    int(v, "trades.refused." + k, 1);
  }
  strList(t.sessions, "trades.sessions");
  const ex = obj(t.excluded, ["no_event_time", "future_event_time", "outside_range"], "trades.excluded");
  for (const [k, v] of Object.entries(ex)) int(v, "trades.excluded." + k);
}

// ---------------------------------------------------------------- bars / rolling

const BAR_OBSERVED_KEYS = [
  "index", "start_ns", "end_ns", "status", "trade_count", "quote",
  "buy_volume", "sell_volume", "unknown_volume", "buy_notional", "sell_notional", "unknown_notional",
  "open", "close", "high", "low",
  "delta_status", "delta_base", "delta_base_bounds", "segment", "cvd_base", "cvd_base_bounds",
] as const;
const BAR_NOT_COVERED_KEYS = [
  "index", "start_ns", "end_ns", "status", "trade_count",
  "delta_status", "delta_base", "delta_base_bounds", "segment", "cvd_base", "cvd_base_bounds",
] as const;

/** Segment of the bar, or null when the bar carries none. */
function checkBar(b: unknown, i: number, anchor: bigint, barNs: bigint, quote: string): number | null {
  const p = "bars[" + i + "]";
  if (!isRecord(b)) return bad(p, "OBJECT_REQUIRED");
  const status = oneOf(b.status, MARKET_FLOW_BAR_STATUSES, p + ".status");
  obj(b, status === "NOT_COVERED" ? BAR_NOT_COVERED_KEYS : BAR_OBSERVED_KEYS, p);
  if (int(b.index, p + ".index") !== i) bad(p + ".index", "BAR_INDEX_ORDER");
  const lo = ns(b.start_ns, p + ".start_ns");
  const hi = ns(b.end_ns, p + ".end_ns");
  if (lo !== anchor + BigInt(i) * barNs || hi !== lo + barNs) bad(p, "BAR_GEOMETRY");
  if (status === "NOT_COVERED") {
    for (const k of ["trade_count", "delta_base", "delta_base_bounds", "segment", "cvd_base", "cvd_base_bounds"]) {
      mustBeNone(b[k], p + "." + k); // UNKNOWN is never 0
    }
    if (b.delta_status !== "NOT_COVERED") bad(p + ".delta_status", "STATUS_INCONSISTENT");
    return null;
  }
  const count = int(b.trade_count, p + ".trade_count");
  if (b.quote !== quote) bad(p + ".quote", "QUOTE_MISMATCH"); // USD is not USDT is not USDC
  const buy = dec(b.buy_volume, p + ".buy_volume");
  const sell = dec(b.sell_volume, p + ".sell_volume");
  const unknown = dec(b.unknown_volume, p + ".unknown_volume");
  for (const k of ["buy_notional", "sell_notional", "unknown_notional"]) dec(b[k], p + "." + k);
  if ((count === 0) !== (status === "OBSERVED_ZERO") && status !== "SESSION_BREAK_UNRESOLVED") {
    bad(p + ".trade_count", "STATUS_INCONSISTENT");
  }
  let nulls = 0;
  for (const k of ["open", "close", "high", "low"]) {
    if (b[k] === null) nulls += 1;
    else dec(b[k], p + "." + k);
  }
  if ((count === 0) !== (nulls === 4) || (count > 0 && nulls > 0)) bad(p, "PRICES_INCONSISTENT");
  if (count === 0 && !(decIsZero(buy) && decIsZero(sell) && decIsZero(unknown))) bad(p, "ZERO_BAR_WITH_VOLUME");
  if (status === "SESSION_BREAK_UNRESOLVED") {
    if (b.delta_status !== status) bad(p + ".delta_status", "STATUS_INCONSISTENT");
    for (const k of ["delta_base", "delta_base_bounds", "segment", "cvd_base", "cvd_base_bounds"]) mustBeNone(b[k], p + "." + k);
    return null;
  }
  const ds = oneOf(b.delta_status, ["EXACT", "PARTIAL_UNKNOWN_SIDE"] as const, p + ".delta_status");
  const [blo, bhi] = decBounds(b.delta_base_bounds, p + ".delta_base_bounds");
  const d = decSub(buy, sell);
  if (!decEquals(blo, decSub(d, unknown)) || !decEquals(bhi, decAdd(d, unknown))) bad(p + ".delta_base_bounds", "BOUNDS_INCONSISTENT");
  if (ds === "EXACT") {
    if (!decIsZero(unknown) || b.delta_base === null || !decEquals(dec(b.delta_base, p + ".delta_base", true), d)) {
      bad(p + ".delta_base", "STATUS_INCONSISTENT");
    }
  } else if (decIsZero(unknown) || b.delta_base !== null) {
    bad(p + ".delta_base", "STATUS_INCONSISTENT");
  }
  const segment = int(b.segment, p + ".segment");
  const [clo, chi] = decBounds(b.cvd_base_bounds, p + ".cvd_base_bounds");
  if (b.cvd_base === null) {
    if (decEquals(clo, chi)) bad(p + ".cvd_base", "STATUS_INCONSISTENT");
  } else {
    const c = dec(b.cvd_base, p + ".cvd_base", true);
    if (!(decEquals(c, clo) && decEquals(clo, chi))) bad(p + ".cvd_base", "STATUS_INCONSISTENT");
  }
  return segment;
}

function checkBars(bars: unknown, anchor: bigint, barNs: bigint, asOf: bigint, quote: string): void {
  if (!Array.isArray(bars) || bars.length > MAX_BARS) return bad("bars", "LIST_REQUIRED");
  if (bars.length > 0 && anchor + BigInt(bars.length) * barNs > asOf) bad("bars", "BAR_AFTER_AS_OF");
  let lastSegment = -1;
  bars.forEach((b, i) => {
    const seg = checkBar(b, i, anchor, barNs, quote);
    if (seg !== null) {
      if (seg < lastSegment) bad("bars[" + i + "].segment", "SEGMENT_ORDER");
      lastSegment = seg;
    }
  });
}

function checkRolling(r: unknown, barNs: bigint): void {
  if (!isRecord(r) || Object.keys(r).length > MAX_LIST) return bad("rolling_delta", "OBJECT_REQUIRED");
  for (const [key, v] of Object.entries(r)) {
    const p = "rolling_delta." + key;
    const w = ns(key, p + ".key");
    if (w <= 0n || w % barNs !== 0n) bad(p, "WINDOW_MUST_BE_BAR_MULTIPLE");
    if (!isRecord(v)) return bad(p, "OBJECT_REQUIRED");
    if (v.status === "NOT_AVAILABLE") {
      obj(v, ["status", "reason"], p);
      oneOf(v.reason, ["WINDOW_BEFORE_ANCHOR", "COVERAGE_INCOMPLETE_OR_UNRESOLVED"] as const, p + ".reason");
    } else {
      obj(v, ["status", "delta_base", "delta_base_bounds"], p);
      const st = oneOf(v.status, ["EXACT", "PARTIAL_UNKNOWN_SIDE"] as const, p + ".status");
      const [lo, hi] = decBounds(v.delta_base_bounds, p + ".delta_base_bounds");
      if (st === "EXACT") {
        if (!decEquals(lo, hi) || v.delta_base === null || !decEquals(dec(v.delta_base, p + ".delta_base", true), lo)) {
          bad(p, "STATUS_INCONSISTENT");
        }
      } else if (decEquals(lo, hi) || v.delta_base !== null) {
        bad(p, "STATUS_INCONSISTENT");
      }
    }
  }
}

// ---------------------------------------------------------------- book

const BBO_KEYS = ["connection_id", "product", "base", "quote", "market_kind", "status", "reason", "bid", "ask",
  "mid", "spread", "economic_metrics", "qualification", "unattested_assumptions"] as const;
const LEVEL_KEYS = ["price", "size", "level_event_time_ns", "level_event_time_state", "level_last_change_seq"] as const;
const FRESH_KEYS = ["product", "book_state", "reason", "connection_silence_ns", "connection_silence_status",
  "connection_last_channel", "frontier", "state_age_ns", "state_age_status", "unresolved",
  "freshness", "unattested_assumptions"] as const;

function stateReason(st: unknown, path: string): [string, unknown] {
  if (!Array.isArray(st) || st.length !== 2) return bad(path, "PAIR_REQUIRED");
  const state = oneOf(st[0], MARKET_FLOW_BOOK_STATES, path + "[0]");
  const reason = st[1];
  if (state === "INVALID") oneOf(reason, MARKET_FLOW_INVALID_REASONS, path + "[1]");
  else if (state === "UNRESOLVED") oneOf(reason, ["MESSAGE_STRADDLES_AS_OF"] as const, path + "[1]");
  else mustBeNone(reason, path + "[1]");
  return [state, reason];
}

/** The derived overall classification (l2._overall); it is never a free field. */
function overallFreshness(silence: string, age: string): string {
  if (age === "FUTURE") return "FUTURE_TIMESTAMP";
  if (silence === "STALE_BY_SILENCE" || age === "STALE") return "STALE";
  if (age === "FUTURE_NOT_EXCLUDED") return "FUTURE_NOT_EXCLUDED";
  if (age === "STALE_NOT_EXCLUDED" || silence === "SILENCE_BUDGET_NOT_EXCLUDED") return "STALE_NOT_EXCLUDED";
  if (silence === "UNRESOLVED") return "UNRESOLVED";
  if (age === "WITHIN_ASSUMPTIONS") return "QUALIFIED_WITHIN_ASSUMPTIONS";
  return "LIVE_UNQUALIFIED";
}

function checkBook(book: unknown, flow: Rec): void {
  const bk = obj(book, ["state", "bbo", "freshness"], "book");
  const [state, reason] = stateReason(bk.state, "book.state");
  const b = obj(bk.bbo, BBO_KEYS, "book.bbo");
  text(b.connection_id, "book.bbo.connection_id", 128);
  if (b.product !== flow.instrument || b.base !== flow.base || b.quote !== flow.quote || b.market_kind !== flow.market_kind) {
    bad("book.bbo", "FLOW_BOOK_IDENTITY_MISMATCH"); // one instrument, one identity
  }
  oneOf(b.status, ["NOT_AVAILABLE", "OBSERVED_UNQUALIFIED"] as const, "book.bbo.status");
  for (const k of ["mid", "spread", "economic_metrics"]) mustBeNone(b[k], "book.bbo." + k);
  oneOf(b.qualification, ["UNQUALIFIED"] as const, "book.bbo.qualification");
  strList(b.unattested_assumptions, "book.bbo.unattested_assumptions");
  if (b.status === "OBSERVED_UNQUALIFIED") {
    if (state !== "LIVE") bad("book.bbo.status", "STATUS_INCONSISTENT");
    mustBeNone(b.reason, "book.bbo.reason");
    for (const side of ["bid", "ask"] as const) {
      const sp = "book.bbo." + side;
      const lv = obj(b[side], LEVEL_KEYS, sp);
      dec(lv.price, sp + ".price", false, true);
      dec(lv.size, sp + ".size", false, true);
      if (lv.level_event_time_ns !== null) ns(lv.level_event_time_ns, sp + ".level_event_time_ns");
      const lts = oneOf(lv.level_event_time_state, MARKET_FLOW_LEVEL_TIME_STATES, sp + ".level_event_time_state");
      // A placeholder epoch is not a date: no time value may stand behind it.
      if ((lv.level_event_time_ns !== null) !== (lts === "NATIVE_UNQUALIFIED")) bad(sp + ".level_event_time_ns", "STATUS_INCONSISTENT");
      int(lv.level_last_change_seq, sp + ".level_last_change_seq");
    }
  } else {
    mustBeNone(b.bid, "book.bbo.bid");
    mustBeNone(b.ask, "book.bbo.ask");
    const want = state === "LIVE" ? "EMPTY_SIDE" : (reason !== null && reason !== "" ? reason : state);
    if (b.reason !== want) bad("book.bbo.reason", "STATUS_INCONSISTENT");
  }
  const f = bk.freshness;
  if (f === null) return;
  const fr = obj(f, FRESH_KEYS, "book.freshness");
  if (fr.product !== flow.instrument) bad("book.freshness.product", "FLOW_BOOK_IDENTITY_MISMATCH");
  if (fr.book_state !== state || fr.reason !== reason) bad("book.freshness.book_state", "STATUS_INCONSISTENT");
  const silenceStatus = oneOf(fr.connection_silence_status, MARKET_FLOW_SILENCE_STATUSES, "book.freshness.connection_silence_status");
  const ageStatus = oneOf(fr.state_age_status, MARKET_FLOW_AGE_STATUSES, "book.freshness.state_age_status");
  const silence = fr.connection_silence_ns === null ? null : span(fr.connection_silence_ns, "book.freshness.connection_silence_ns");
  const age = fr.state_age_ns === null ? null : span(fr.state_age_ns, "book.freshness.state_age_ns", true);
  if ((silence === null) !== (silenceStatus === "UNRESOLVED") || (age === null) !== (ageStatus === "UNRESOLVED")) {
    bad("book.freshness", "STATUS_INCONSISTENT"); // a status never claims a value that is absent
  }
  if (fr.connection_last_channel !== null) text(fr.connection_last_channel, "book.freshness.connection_last_channel");
  if (!Array.isArray(fr.unresolved) || fr.unresolved.length > MAX_LIST) bad("book.freshness.unresolved", "LIST_REQUIRED");
  (fr.unresolved as unknown[]).forEach((v, i) => code(v, "book.freshness.unresolved[" + i + "]"));
  strList(fr.unattested_assumptions, "book.freshness.unattested_assumptions");
  oneOf(fr.freshness, MARKET_FLOW_FRESHNESS, "book.freshness.freshness");
  if (state !== "LIVE") {
    if (fr.freshness !== "NOT_USABLE" || silenceStatus !== "UNRESOLVED" || ageStatus !== "UNRESOLVED" || fr.frontier !== null) {
      bad("book.freshness", "STATUS_INCONSISTENT");
    }
    return;
  }
  const fo = obj(fr.frontier, ["channel", "sequence_num", "send_state"], "book.freshness.frontier");
  if (fo.channel !== MARKET_FLOW_CHANNEL) bad("book.freshness.frontier.channel", "FLOW_BOOK_IDENTITY_MISMATCH");
  int(fo.sequence_num, "book.freshness.frontier.sequence_num");
  oneOf(fo.send_state, MARKET_FLOW_SEND_STATES, "book.freshness.frontier.send_state");
  // No qualification may exist while the age or the provenance behind it is unresolved.
  if (fr.freshness !== overallFreshness(silenceStatus, ageStatus)) bad("book.freshness.freshness", "STATUS_INCONSISTENT");
  const unresolved = fr.unresolved as unknown[];
  if (ageStatus === "UNRESOLVED" && unresolved.length === 0) bad("book.freshness.unresolved", "STATUS_INCONSISTENT");
  if (fr.freshness === "QUALIFIED_WITHIN_ASSUMPTIONS" && (unresolved.length > 0 || age === null)) {
    bad("book.freshness.freshness", "STATUS_INCONSISTENT");
  }
}

// ---------------------------------------------------------------- heatmap / events

const HEAT_KEYS = ["unit", "aggregation", "tick", "price_lo", "price_hi", "rows", "t0_ns", "bucket_ns", "columns",
  "zero_semantics"] as const;
const HEAT_CONST: Readonly<Record<string, string>> = {
  unit: "DISPLAYED_BASE_QUANTITY",
  aggregation: "LAST_LIVE_SAMPLE_IN_BUCKET",
  zero_semantics: "ABSENT_CELL_IN_LIVE_COLUMN_WITHIN_COVER_IS_OBSERVED_ZERO",
};

function checkCells(cells: unknown, rows: number, path: string): void {
  if (!Array.isArray(cells) || cells.length > rows) return bad(path, "LIST_REQUIRED");
  let last = -1;
  cells.forEach((c, i) => {
    if (!Array.isArray(c) || c.length !== 2) return bad(path + "[" + i + "]", "PAIR_REQUIRED");
    const j = int(c[0], path + "[" + i + "][0]", 0, rows - 1);
    if (j <= last) bad(path, "CELL_ORDER");
    last = j;
    dec(c[1], path + "[" + i + "][1]", false, true);
  });
}

function checkHeatmap(h: unknown, asOf: bigint): void {
  const hm = obj(h, HEAT_KEYS, "heatmap");
  for (const [k, v] of Object.entries(HEAT_CONST)) if (hm[k] !== v) bad("heatmap." + k, "CONSTANT_REFUSED");
  const tick = dec(hm.tick, "heatmap.tick", false, true);
  const lo = dec(hm.price_lo, "heatmap.price_lo");
  const hi = dec(hm.price_hi, "heatmap.price_hi");
  if (decCompare(hi, lo) <= 0) bad("heatmap", "GRID_GEOMETRY_INVALID");
  const { whole, hasRest } = decDivModPositive(decSub(hi, lo), tick);
  const rows = int(hm.rows, "heatmap.rows", 1, MAX_ROWS);
  if (BigInt(rows) !== whole + (hasRest ? 1n : 0n)) bad("heatmap.rows", "GRID_GEOMETRY_INVALID");
  const t0 = ns(hm.t0_ns, "heatmap.t0_ns");
  const width = ns(hm.bucket_ns, "heatmap.bucket_ns");
  if (width <= 0n) bad("heatmap.bucket_ns", "GRID_GEOMETRY_INVALID");
  const cols = hm.columns;
  if (!Array.isArray(cols) || cols.length < 1 || cols.length > MAX_COLUMNS) return bad("heatmap.columns", "LIST_REQUIRED");
  cols.forEach((c, i) => {
    const p = "heatmap.columns[" + i + "]";
    if (!isRecord(c)) return bad(p, "OBJECT_REQUIRED");
    const status = c.status;
    if (status === "LIVE") {
      obj(c, ["bucket", "status", "sample_receipt_ns", "bid_cover_floor", "ask_cover_ceiling", "bids", "asks"], p);
    } else {
      obj(c, ["bucket", "status", "sample_receipt_ns"], p);
    }
    if (int(c.bucket, p + ".bucket") !== i) bad(p + ".bucket", "BUCKET_ORDER");
    const end = t0 + BigInt(i + 1) * width;
    if (status === "NOT_YET_COMPLETE" || status === "NO_SAMPLE") {
      mustBeNone(c.sample_receipt_ns, p + ".sample_receipt_ns");
      if (status === "NOT_YET_COMPLETE" && end <= asOf) bad(p + ".status", "STATUS_INCONSISTENT");
      return;
    }
    if (end > asOf) bad(p + ".status", "BUCKET_AFTER_AS_OF");
    if (status !== "LIVE" && (typeof status !== "string" || !BOOK_STATUS_RE.test(status))) bad(p + ".status", "ENUM_REFUSED");
    const t = ns(c.sample_receipt_ns, p + ".sample_receipt_ns");
    if (!(t0 + BigInt(i) * width <= t && t < end)) bad(p + ".sample_receipt_ns", "SAMPLE_OUTSIDE_BUCKET");
    if (status === "LIVE") {
      if (c.bid_cover_floor !== null) dec(c.bid_cover_floor, p + ".bid_cover_floor");
      if (c.ask_cover_ceiling !== null) dec(c.ask_cover_ceiling, p + ".ask_cover_ceiling");
      checkCells(c.bids, rows, p + ".bids");
      checkCells(c.asks, rows, p + ".asks");
    }
  });
}

const EV_COMMON = ["cause", "interval_ns", "kind", "price", "side"] as const;
const EV_GONE = [...EV_COMMON, "last_qty", "left_censored", "persistence_ns", "trades_at_price_in_interval"] as const;
const EV_KEYS: Readonly<Record<string, readonly string[]>> = {
  APPEARED: [...EV_COMMON, "qty"],
  DISAPPEARED: EV_GONE,
  LEFT_COVERED_DEPTH: EV_GONE,
};

function checkLevelEvents(le: unknown): void {
  const o = obj(le, ["items", "truncated"], "level_events");
  boolean(o.truncated, "level_events.truncated");
  if (!Array.isArray(o.items) || o.items.length > MAX_ITEMS) return bad("level_events.items", "LIST_REQUIRED");
  o.items.forEach((e: unknown, i: number) => {
    const p = "level_events.items[" + i + "]";
    if (!isRecord(e)) return bad(p, "OBJECT_REQUIRED");
    const kind = oneOf(e.kind, Object.keys(EV_KEYS), p + ".kind");
    obj(e, EV_KEYS[kind], p);
    oneOf(e.side, ["bid", "ask"] as const, p + ".side");
    dec(e.price, p + ".price", false, true);
    span(e.interval_ns, p + ".interval_ns");
    // The cause of a level change is never claimed.
    oneOf(e.cause, kind === "LEFT_COVERED_DEPTH" ? ["NOT_A_DISAPPEARANCE"] as const : ["CAUSE_UNDETERMINED"] as const, p + ".cause");
    if (kind === "APPEARED") {
      dec(e.qty, p + ".qty", false, true);
      return;
    }
    dec(e.last_qty, p + ".last_qty", false, true);
    boolean(e.left_censored, p + ".left_censored");
    const pr = obj(e.persistence_ns, ["min", "max"], p + ".persistence_ns");
    const mn = ns(pr.min, p + ".persistence_ns.min");
    const mx = pr.max === null ? null : ns(pr.max, p + ".persistence_ns.max");
    if (mx !== null && mx < mn) bad(p + ".persistence_ns", "INTERVAL_ORDER");
    if (e.left_censored !== (pr.max === null)) bad(p + ".left_censored", "STATUS_INCONSISTENT");
    int(e.trades_at_price_in_interval, p + ".trades_at_price_in_interval");
  });
}

// ---------------------------------------------------------------- root

/** Python refuses a float anywhere. A parsed value can only show it as a non-integer number. */
function walkNoFloat(x: unknown, path: string, depth: number): void {
  if (depth > MAX_WALK_DEPTH) bad(path, "DEPTH_EXCEEDED");
  if (typeof x === "number") {
    if (!Number.isInteger(x)) bad(path, "FLOAT_REFUSED");
  } else if (Array.isArray(x)) {
    x.forEach((v, i) => walkNoFloat(v, path + "[" + i + "]", depth + 1));
  } else if (isRecord(x)) {
    for (const [k, v] of Object.entries(x)) walkNoFloat(v, path + "." + k, depth + 1);
  }
}

function runArtifact(doc: unknown): void {
  if (!isRecord(doc) || Object.keys(doc).length !== MARKET_FLOW_ARTIFACT_KEYS.length || !MARKET_FLOW_ARTIFACT_KEYS.every(k => has(doc, k))) {
    bad("$", "CLOSED_TOP_LEVEL_KEYS_REQUIRED");
  }
  const d = doc as Rec;
  walkNoFloat(d, "$", 0);
  if (d.schema_version !== MARKET_FLOW_SCHEMA_VERSION || d.product !== MARKET_FLOW_PRODUCT) bad("schema_version", "CONTRACT_VERSION_REFUSED");
  if (d.calc_version !== MARKET_FLOW_CALC_VERSION) bad("calc_version", "CALC_VERSION_REFUSED");
  if (d.synthetic !== true || (d.evidence_kind !== "SYNTHETIC" && d.evidence_kind !== "HISTORICAL")) bad("evidence_kind", "EVIDENCE_KIND_REQUIRED");
  if (d.state_label !== d.evidence_kind) bad("state_label", "STATE_LABEL_MISMATCH");
  for (const k of ["economic_metrics", "score", "recommendation"]) {
    if (d[k] !== null) bad(k, "NO_METRIC_SCORE_OR_RECOMMENDATION");
  }
  const asOf = ns(d.as_of_receipt_ns, "as_of_receipt_ns");
  const anchor = ns(d.anchor_ns, "anchor_ns");
  const barNs = ns(d.bar_ns, "bar_ns");
  if (barNs <= 0n || asOf < anchor) bad("bar_ns", "BAR_GEOMETRY_INVALID");
  const flow = checkFlow(d.flow);
  checkInputs(d.inputs);
  checkTrades(d.trades);
  checkBars(d.bars, anchor, barNs, asOf, flow.quote as string);
  checkRolling(d.rolling_delta, barNs);
  checkBook(d.book, flow);
  checkHeatmap(d.heatmap, asOf);
  checkLevelEvents(d.level_events);
  for (const k of ["assumptions", "limits"]) strList(d[k], k);
}

function guarded(run: () => void): MarketFlowCheck {
  try {
    run();
    return { ok: true };
  } catch (error) {
    if (error instanceof Violation) return { ok: false, code: error.code, path: error.path };
    // Fail closed: an unexpected failure is a refusal, never a pass.
    return { ok: false, code: "VALIDATION_ERROR", path: "$" };
  }
}

/** Form + consistency check of an artifact (no `serving`). Returns the first violation. */
export function checkMarketFlowArtifact(x: unknown): MarketFlowCheck {
  return guarded(() => runArtifact(x));
}

export function validateMarketFlowArtifact(x: unknown): x is MarketFlowArtifact {
  return checkMarketFlowArtifact(x).ok;
}

/**
 * Check of the whole HTTP 200 publication: the artifact keys exactly plus
 * `serving`. Unknown keys are never dropped before validation.
 */
export function checkMarketFlowPublication(x: unknown): MarketFlowCheck {
  return guarded(() => {
    if (!isRecord(x)) return bad("$", "CLOSED_TOP_LEVEL_KEYS_REQUIRED");
    const keys = Object.keys(x);
    if (keys.length !== MARKET_FLOW_ARTIFACT_KEYS.length + 1 || !has(x, "serving")
      || !MARKET_FLOW_ARTIFACT_KEYS.every(k => has(x, k))) bad("$", "CLOSED_TOP_LEVEL_KEYS_REQUIRED");
    const serving = obj(x.serving, ["freshness_classification"], "serving");
    const artifact: Rec = {};
    for (const k of MARKET_FLOW_ARTIFACT_KEYS) artifact[k] = x[k]; // a view; x itself is untouched
    runArtifact(artifact);
    if (serving.freshness_classification !== "NOT_ASSESSED_" + String(x.state_label)) {
      bad("serving.freshness_classification", "SERVING_STATE_MISMATCH");
    }
  });
}

export function validateMarketFlowPublication(x: unknown): x is MarketFlowPublication {
  return checkMarketFlowPublication(x).ok;
}
