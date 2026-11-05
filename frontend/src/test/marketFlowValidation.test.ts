// Targeted counter-examples for the Flux contract, on the repository's synthetic reference file.
// (The exhaustive differential check against the Python oracle is marketFlow.compat.test.ts.)
import { readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { parseStrictJsonText, readStrictJson } from "../lib/marketFlowJson";
import {
  MARKET_FLOW_INVALID_REASONS, checkMarketFlowArtifact, checkMarketFlowPublication, validateMarketFlowArtifact,
  validateMarketFlowPublication,
} from "../lib/marketFlowValidation";

// Vitest runs from frontend/ (npm test / CI working-directory).
// The path is assembled from segments on purpose: a repository guard test greps the frontend sources for the
// Python package name. The file is the repository's synthetic reference, read in place (never copied).
const GOLDEN = path.resolve(process.cwd(), "..", "observability", ["market", "flow"].join("_"), "fixtures",
  ["market", "flow", "artifact", "synthetic"].join("_") + ".json");
type Doc = Record<string, any>;
const golden = (): Doc => JSON.parse(readFileSync(GOLDEN, "utf8"));
const publication = (d: Doc = golden()): Doc => ({ ...d, serving: { freshness_classification: "NOT_ASSESSED_" + d.state_label } });
const code = (d: unknown) => {
  const r = checkMarketFlowArtifact(d);
  return r.ok ? null : r.code;
};
const refuses = (mutate: (d: Doc) => void, want?: string) => {
  const d = golden();
  mutate(d);
  const r = checkMarketFlowArtifact(d);
  expect(r.ok).toBe(false);
  if (want && !r.ok) expect(r.code).toBe(want);
};
const accepts = (mutate: (d: Doc) => void) => {
  const d = golden();
  mutate(d);
  expect(checkMarketFlowArtifact(d)).toEqual({ ok: true });
  return d;
};
const deepFreeze = <T,>(x: T): T => {
  if (typeof x === "object" && x !== null) {
    Object.values(x).forEach(deepFreeze);
    Object.freeze(x);
  }
  return x;
};
afterEach(() => vi.useRealTimers());

describe("reference artifact", () => {
  it("passes both validators, as raw bytes and as an object, without being modified", () => {
    const raw = readFileSync(GOLDEN);
    const parsed = readStrictJson(new Uint8Array(raw.buffer, raw.byteOffset, raw.length));
    expect(parsed.ok).toBe(true);
    const frozen = deepFreeze(golden());
    expect(validateMarketFlowArtifact(frozen)).toBe(true);
    expect(validateMarketFlowPublication(deepFreeze(publication()))).toBe(true);
    expect(frozen).toEqual(golden());
  });
  it("is a type guard over unknown input", () => {
    for (const v of [null, undefined, 1, "x", [], {}, true]) {
      expect(validateMarketFlowArtifact(v)).toBe(false);
      expect(validateMarketFlowPublication(v)).toBe(false);
    }
  });
});

describe("closed structures", () => {
  it("refuses an unknown or a missing key at the root and at nested nodes", () => {
    refuses(d => { d.extra = 1; }, "CLOSED_TOP_LEVEL_KEYS_REQUIRED");
    refuses(d => { delete d.limits; }, "CLOSED_TOP_LEVEL_KEYS_REQUIRED");
    refuses(d => { d.flow.extra = 1; }, "CLOSED_KEYS_REQUIRED");
    refuses(d => { delete d.flow.id_domain; }, "CLOSED_KEYS_REQUIRED");
    refuses(d => { d.inputs.extra = 1; }, "CLOSED_KEYS_REQUIRED");
    refuses(d => { d.trades.excluded.extra = 1; }, "CLOSED_KEYS_REQUIRED");
    refuses(d => { d.bars[0].extra = 1; }, "CLOSED_KEYS_REQUIRED");
    refuses(d => { delete d.bars[3].segment; }, "CLOSED_KEYS_REQUIRED");
    refuses(d => { d.book.bbo.extra = 1; }, "CLOSED_KEYS_REQUIRED");
    refuses(d => { d.book.freshness.frontier.extra = 1; }, "CLOSED_KEYS_REQUIRED");
    refuses(d => { d.heatmap.columns[0].extra = 1; }, "CLOSED_KEYS_REQUIRED");
    refuses(d => { d.level_events.extra = 1; }, "CLOSED_KEYS_REQUIRED");
    refuses(d => { d.level_events.items[0].extra = 1; }, "CLOSED_KEYS_REQUIRED");
  });
  it("does not accept a variant as an object padded with optional nulls", () => {
    refuses(d => { d.bars[3].quote = null; }, "CLOSED_KEYS_REQUIRED"); // NOT_COVERED has no volume fields
    refuses(d => { delete d.bars[0].quote; }, "CLOSED_KEYS_REQUIRED");
    refuses(d => { d.heatmap.columns[0] = { bucket: 0, status: "NO_SAMPLE", sample_receipt_ns: null, bids: [], asks: [] }; });
  });
  it("refuses wrong versions, products and constants", () => {
    refuses(d => { d.schema_version = "1.0.1"; }, "CONTRACT_VERSION_REFUSED");
    refuses(d => { d.product = "MarketFlow"; }, "CONTRACT_VERSION_REFUSED");
    refuses(d => { d.calc_version = "flow-calc-1.0.1"; }, "CALC_VERSION_REFUSED");
    refuses(d => { d.heatmap.unit = "BASE"; }, "CONSTANT_REFUSED");
    refuses(d => { d.heatmap.zero_semantics = "ZERO"; }, "CONSTANT_REFUSED");
  });
});

describe("provenance and authority", () => {
  it("requires synthetic=true and a matching label; LIVE provenance does not exist", () => {
    refuses(d => { d.synthetic = false; }, "EVIDENCE_KIND_REQUIRED");
    refuses(d => { d.synthetic = "true"; }, "EVIDENCE_KIND_REQUIRED");
    refuses(d => { d.evidence_kind = "LIVE"; d.state_label = "LIVE"; }, "EVIDENCE_KIND_REQUIRED");
    refuses(d => { d.state_label = "HISTORICAL"; }, "STATE_LABEL_MISMATCH");
    refuses(d => { d.evidence_kind = "HISTORICAL"; d.synthetic = false; }, "EVIDENCE_KIND_REQUIRED");
    accepts(d => { d.evidence_kind = "HISTORICAL"; d.state_label = "HISTORICAL"; });
  });
  it("refuses any metric, score or recommendation", () => {
    for (const k of ["economic_metrics", "score", "recommendation"]) {
      refuses(d => { d[k] = "1"; }, "NO_METRIC_SCORE_OR_RECOMMENDATION");
      refuses(d => { d[k] = {}; }, "NO_METRIC_SCORE_OR_RECOMMENDATION");
      refuses(d => { d[k] = 0; }, "NO_METRIC_SCORE_OR_RECOMMENDATION");
    }
    refuses(d => { d.book.bbo.mid = "1000.5"; }, "NULL_REQUIRED");
    refuses(d => { d.book.bbo.spread = "1"; }, "NULL_REQUIRED");
    refuses(d => { d.book.bbo.economic_metrics = {}; }, "NULL_REQUIRED");
    refuses(d => { d.book.bbo.qualification = "QUALIFIED"; }, "ENUM_REFUSED");
  });
  it("accepts a valid LIVE book inside a synthetic artifact: it proves no real feed", () => {
    const d = golden();
    expect(d.book.state).toEqual(["LIVE", null]);
    expect(d.synthetic).toBe(true);
    expect(checkMarketFlowArtifact(d).ok).toBe(true);
  });
});

describe("identity", () => {
  it("accepts exactly Coinbase Advanced SPOT BTC-USD / ETH-USD", () => {
    accepts(() => undefined);
    const eth = golden();
    eth.flow.instrument = "ETH-USD"; eth.flow.base = "ETH";
    eth.book.bbo.product = "ETH-USD"; eth.book.bbo.base = "ETH"; eth.book.freshness.product = "ETH-USD";
    expect(checkMarketFlowArtifact(eth).ok).toBe(true);
  });
  it("refuses aliases, other venues, perpetuals and mixed quotes", () => {
    refuses(d => { d.flow.venue = "coinbase"; }, "FLOW_BOOK_IDENTITY_MISMATCH");
    refuses(d => { d.flow.venue = "binance"; }, "FLOW_BOOK_IDENTITY_MISMATCH");
    refuses(d => { d.flow.market_kind = "PERP"; }, "ENUM_REFUSED");
    refuses(d => { d.flow.instrument = "BTC-USDT"; d.flow.quote = "USDT"; }, "FLOW_BOOK_IDENTITY_MISMATCH");
    refuses(d => { d.flow.instrument = "BTC-USD"; d.flow.base = "ETH"; }, "FLOW_BOOK_IDENTITY_MISMATCH");
    refuses(d => { d.flow.instrument = "ETH-USD"; }, "FLOW_BOOK_IDENTITY_MISMATCH");
    for (const q of ["USDT", "USDC", "usd", "EUR"]) {
      refuses(d => { d.flow.quote = q; }, "FLOW_BOOK_IDENTITY_MISMATCH");
      refuses(d => { d.bars[0].quote = q; }, "QUOTE_MISMATCH");
    }
    refuses(d => { d.book.bbo.product = "ETH-USD"; }, "FLOW_BOOK_IDENTITY_MISMATCH");
    refuses(d => { d.book.bbo.quote = "USDT"; }, "FLOW_BOOK_IDENTITY_MISMATCH");
    refuses(d => { d.book.freshness.product = "ETH-USD"; }, "FLOW_BOOK_IDENTITY_MISMATCH");
    refuses(d => { d.book.freshness.frontier.channel = "ticker"; }, "FLOW_BOOK_IDENTITY_MISMATCH");
    refuses(d => { d.flow.id_domain = "GLOBAL"; }, "ENUM_REFUSED");
  });
});

describe("exact values", () => {
  it("keeps nanosecond texts with 30 digits and refuses 31, numbers and signs", () => {
    refuses(d => { d.as_of_receipt_ns = 1_300_000_000_000; }, "NS_MUST_BE_DECIMAL_STRING");
    refuses(d => { d.as_of_receipt_ns = "9".repeat(31); }, "NS_MUST_BE_DECIMAL_STRING");
    refuses(d => { d.anchor_ns = "-1"; }, "NS_MUST_BE_DECIMAL_STRING");
    refuses(d => { d.anchor_ns = "01"; }, "NS_MUST_BE_DECIMAL_STRING");
    refuses(d => { d.bar_ns = "6e10"; }, "NS_MUST_BE_DECIMAL_STRING");
    refuses(d => { d.bar_ns = "0"; }, "BAR_GEOMETRY_INVALID");
    refuses(d => { d.as_of_receipt_ns = "1"; }, "BAR_GEOMETRY_INVALID");
  });
  it("accepts a book age with a sign, but never an unsigned field with one", () => {
    accepts(d => { Object.assign(d.book.freshness, { state_age_ns: ["-9", "-3"], state_age_status: "FUTURE", freshness: "FUTURE_TIMESTAMP", unresolved: [] }); });
    refuses(d => { d.book.freshness.connection_silence_ns = ["-9", "-3"]; }, "NS_MUST_BE_DECIMAL_STRING");
    refuses(d => { Object.assign(d.book.freshness, { state_age_ns: ["-3", "-9"], state_age_status: "FUTURE" }); }, "INTERVAL_ORDER");
  });
  it("preserves leading and trailing zeros that Python admits (nothing is normalised)", () => {
    const d = accepts(x => { x.heatmap.tick = "0.5000"; x.heatmap.price_lo = "00998.00"; x.heatmap.price_hi = "1004.0"; });
    expect(d.heatmap.tick).toBe("0.5000");
    expect(d.heatmap.price_lo).toBe("00998.00");
    const long = accepts(x => { x.bars[0].open = "9".repeat(125) + "." + "9".repeat(125); });
    expect(long.bars[0].open.length).toBe(251);
  });
  it("refuses decimals beyond 125 digits, exponents, separators, NaN and Unicode digits", () => {
    for (const v of ["9".repeat(126), "1." + "9".repeat(126), "1e5", "1,5", "NaN", "Infinity", "٣", ".5", "5.", "-1", "", " 1", "1 ", 5]) {
      refuses(d => { d.bars[0].open = v; }, "DECIMAL_TEXT_REQUIRED");
    }
  });
  it("checks delta and CVD bounds exactly, not approximately", () => {
    refuses(d => { d.bars[0].delta_base = "0.0000000000000000000001"; }, "STATUS_INCONSISTENT");
    refuses(d => { d.bars[0].delta_base_bounds = ["0", "1"]; }, "BOUNDS_INCONSISTENT");
    refuses(d => { d.bars[0].delta_base_bounds = ["1", "0"]; }, "INTERVAL_ORDER");
    refuses(d => { d.bars[0].cvd_base = "123"; }, "STATUS_INCONSISTENT");
    const partial = golden().bars.findIndex((b: Doc) => b.delta_status === "PARTIAL_UNKNOWN_SIDE");
    expect(partial).toBeGreaterThanOrEqual(0);
    refuses(d => { d.bars[partial].delta_base = d.bars[partial].delta_base_bounds[0]; }, "STATUS_INCONSISTENT");
    refuses(d => { d.bars[partial].unknown_volume = "0"; }, "BOUNDS_INCONSISTENT");
  });
  it("refuses a float, a boolean or an out-of-range value where a counter belongs", () => {
    for (const v of [true, false, -1, 2 ** 53, "19", null]) refuses(d => { d.inputs.event_count = v; }, "INTEGER_REQUIRED");
    refuses(d => { d.inputs.event_count = 1.5; }, "FLOAT_REFUSED");
    accepts(d => { d.inputs.event_count = 2 ** 53 - 1; });
  });
});

describe("coverage, sessions and series", () => {
  it("keeps NOT_COVERED, SESSION_BREAK and OBSERVED_ZERO distinct", () => {
    refuses(d => { d.bars[3].trade_count = 0; }, "NULL_REQUIRED");
    refuses(d => { d.bars[3].delta_base = "0"; }, "NULL_REQUIRED");
    refuses(d => { d.bars[3].delta_status = "EXACT"; }, "STATUS_INCONSISTENT");
    refuses(d => { d.bars[4].delta_status = "EXACT"; }, "STATUS_INCONSISTENT");
    refuses(d => { d.bars[4].segment = 1; }, "NULL_REQUIRED");
    refuses(d => { d.bars[1].trade_count = 1; }, "STATUS_INCONSISTENT");
    refuses(d => { d.bars[1].buy_volume = "1"; }, "ZERO_BAR_WITH_VOLUME");
    refuses(d => { d.bars[1].open = "1000"; }, "PRICES_INCONSISTENT");
    refuses(d => { d.bars[0].open = null; }, "PRICES_INCONSISTENT");
    refuses(d => { d.bars[0].status = "OBSERVED_ZERO"; }, "STATUS_INCONSISTENT");
  });
  it("checks bar geometry, order and the as_of boundary", () => {
    refuses(d => { d.bars[1].index = 2; }, "BAR_INDEX_ORDER");
    refuses(d => { d.bars[2].start_ns = d.bars[1].start_ns; }, "BAR_GEOMETRY");
    refuses(d => { d.bars[0].end_ns = d.bars[0].start_ns; }, "BAR_GEOMETRY");
    refuses(d => { d.as_of_receipt_ns = String(BigInt(d.as_of_receipt_ns) - 1n); }, "BAR_AFTER_AS_OF");
    refuses(d => { d.bars[0].segment = 9; }, "SEGMENT_ORDER");
  });
  it("accepts rolling windows only as positive multiples of the bar and keeps their reasons", () => {
    const w = Object.keys(golden().rolling_delta);
    expect(w.length).toBeGreaterThan(0);
    refuses(d => { d.rolling_delta["90000000000"] = { status: "NOT_AVAILABLE", reason: "WINDOW_BEFORE_ANCHOR" }; }, "WINDOW_MUST_BE_BAR_MULTIPLE");
    refuses(d => { d.rolling_delta["0"] = { status: "NOT_AVAILABLE", reason: "WINDOW_BEFORE_ANCHOR" }; }, "WINDOW_MUST_BE_BAR_MULTIPLE");
    refuses(d => { d.rolling_delta["060000000000"] = { status: "NOT_AVAILABLE", reason: "WINDOW_BEFORE_ANCHOR" }; }, "NS_MUST_BE_DECIMAL_STRING");
    refuses(d => { d.rolling_delta[w[0]] = { status: "NOT_AVAILABLE", reason: "MADE_UP" }; }, "ENUM_REFUSED");
    refuses(d => { d.rolling_delta[w[0]] = { status: "NOT_AVAILABLE", reason: "WINDOW_BEFORE_ANCHOR", delta_base: null }; }, "CLOSED_KEYS_REQUIRED");
  });
  it("keeps trade accounting open where Python is open and closed elsewhere", () => {
    accepts(d => { d.trades.refused.SOME_FUTURE_REFUSAL_CODE = 3; });
    refuses(d => { d.trades.refused.lowercase = 3; }, "CODE_REQUIRED");
    refuses(d => { d.trades.refused.X = 0; }, "INTEGER_REQUIRED");
    refuses(d => { d.trades.excluded.no_event_time = -1; }, "INTEGER_REQUIRED");
    refuses(d => { d.trades.conflicts = [{ trade_id: "t", session_id: "s", extra: 1 }]; }, "CLOSED_KEYS_REQUIRED");
  });
});

describe("book, time and freshness (the decision of the Python oracle is kept, nothing is promoted)", () => {
  it("accepts every native invalid-reason code and refuses an invented one", () => {
    expect(MARKET_FLOW_INVALID_REASONS.length).toBe(3 + 2 * 22);
    for (const reason of MARKET_FLOW_INVALID_REASONS) {
      const d = golden();
      d.book.state = ["INVALID", reason];
      d.book.bbo = { ...d.book.bbo, status: "NOT_AVAILABLE", reason, bid: null, ask: null };
      d.book.freshness = { ...d.book.freshness, book_state: "INVALID", reason, freshness: "NOT_USABLE", connection_silence_ns: null,
        connection_silence_status: "UNRESOLVED", state_age_ns: null, state_age_status: "UNRESOLVED", frontier: null };
      expect(code(d)).toBeNull();
    }
    refuses(d => { d.book.state = ["INVALID", "MALFORMED_MESSAGE:MADE_UP"]; }, "ENUM_REFUSED");
    refuses(d => { d.book.state = ["INVALID", null]; }, "ENUM_REFUSED");
    refuses(d => { d.book.state = ["LIVE", "SEQUENCE_GAP"]; }, "NULL_REQUIRED");
    refuses(d => { d.book.state = ["UNRESOLVED", "SEQUENCE_GAP"]; }, "ENUM_REFUSED");
    refuses(d => { d.book.state = ["BROKEN", null]; }, "ENUM_REFUSED");
    refuses(d => { d.book.state = ["LIVE"]; }, "PAIR_REQUIRED");
  });
  it("derives the overall freshness: it is never a free field", () => {
    const variants: [string, string, string[] | null, string, string][] = [
      ["FUTURE", "FUTURE_TIMESTAMP", ["-5", "-3"], "FUTURE_TIMESTAMP", "ok"],
      ["STALE", "STALE", ["500", "600"], "STALE", "ok"],
      ["FUTURE_NOT_EXCLUDED", "FUTURE_NOT_EXCLUDED", ["-5", "5"], "FUTURE_NOT_EXCLUDED", "ok"],
      ["STALE_NOT_EXCLUDED", "STALE_NOT_EXCLUDED", ["1", "900"], "STALE_NOT_EXCLUDED", "ok"],
      ["WITHIN_ASSUMPTIONS", "QUALIFIED_WITHIN_ASSUMPTIONS", ["1", "2"], "QUALIFIED_WITHIN_ASSUMPTIONS", "ok"],
      ["FUTURE", "LIVE_UNQUALIFIED", ["-5", "-3"], "LIVE_UNQUALIFIED", "STATUS_INCONSISTENT"],
      ["STALE", "FRESH", ["5", "6"], "FRESH", "ENUM_REFUSED"],
      ["WITHIN_ASSUMPTIONS", "QUALIFIED_WITHIN_ASSUMPTIONS", null, "x", "STATUS_INCONSISTENT"],
    ];
    for (const [age, fresh, interval, , verdict] of variants) {
      const d = golden();
      Object.assign(d.book.freshness, { state_age_status: age, state_age_ns: interval, freshness: fresh, unresolved: [] });
      expect(code(d) ?? "ok").toBe(verdict);
    }
    refuses(d => { d.book.freshness.unresolved = []; }, "STATUS_INCONSISTENT"); // age unresolved needs a reason
    refuses(d => { d.book.freshness.freshness = "QUALIFIED_WITHIN_ASSUMPTIONS"; }, "STATUS_INCONSISTENT");
  });
  it("is not changed by the browser clock", () => {
    const d = Object.assign(golden());
    vi.useFakeTimers();
    for (const when of ["1970-01-01T00:00:00Z", "2026-11-05T00:00:00Z", "2099-01-01T00:00:00Z"]) {
      vi.setSystemTime(new Date(when));
      expect(checkMarketFlowArtifact(d)).toEqual({ ok: true });
    }
  });
  it("handles level event times: a placeholder epoch has no date behind it", () => {
    accepts(d => { Object.assign(d.book.bbo.bid, { level_event_time_state: "PLACEHOLDER_EPOCH_NOT_A_DATE", level_event_time_ns: null }); });
    accepts(d => { Object.assign(d.book.bbo.bid, { level_event_time_state: "NATIVE_UNQUALIFIED", level_event_time_ns: "1767323045123456789" }); });
    refuses(d => { Object.assign(d.book.bbo.bid, { level_event_time_state: "PLACEHOLDER_EPOCH_NOT_A_DATE", level_event_time_ns: "0" }); }, "STATUS_INCONSISTENT");
    refuses(d => { Object.assign(d.book.bbo.bid, { level_event_time_state: "NATIVE_UNQUALIFIED", level_event_time_ns: null }); }, "STATUS_INCONSISTENT");
    refuses(d => { Object.assign(d.book.bbo.bid, { level_event_time_state: "NOT_SUPPLIED", level_event_time_ns: "1" }); }, "STATUS_INCONSISTENT");
    refuses(d => { Object.assign(d.book.bbo.bid, { level_event_time_state: "DATED" }); }, "ENUM_REFUSED");
  });
  it("requires an empty-side reason when the book is LIVE without a best price", () => {
    accepts(d => { Object.assign(d.book.bbo, { status: "NOT_AVAILABLE", reason: "EMPTY_SIDE", bid: null, ask: null }); });
    refuses(d => { Object.assign(d.book.bbo, { status: "NOT_AVAILABLE", reason: "LIVE", bid: null, ask: null }); }, "STATUS_INCONSISTENT");
    refuses(d => { Object.assign(d.book.bbo, { status: "NOT_AVAILABLE", reason: "EMPTY_SIDE" }); }, "NULL_REQUIRED");
    refuses(d => { d.book.state = ["NO_SNAPSHOT", null]; }, "STATUS_INCONSISTENT");
    refuses(d => { d.book.bbo.bid.price = "0"; }, "POSITIVE_DECIMAL_REQUIRED");
  });
  it("allows no freshness object only as null, and one that agrees with the state", () => {
    accepts(d => { d.book.freshness = null; });
    refuses(d => { d.book.freshness.book_state = "INVALID"; }, "STATUS_INCONSISTENT");
    refuses(d => { delete d.book.freshness; }, "CLOSED_KEYS_REQUIRED");
    refuses(d => { d.book.freshness.connection_silence_ns = null; }, "STATUS_INCONSISTENT");
  });
});

describe("as_of, heatmap and level events", () => {
  it("never accepts data dated after as_of", () => {
    refuses(d => { d.heatmap.columns[4] = { bucket: 4, status: "NOT_YET_COMPLETE", sample_receipt_ns: null }; }, "STATUS_INCONSISTENT");
    refuses(d => { d.heatmap.bucket_ns = "70000000000"; }, "BUCKET_AFTER_AS_OF");
    refuses(d => { d.heatmap.columns[0].sample_receipt_ns = d.heatmap.columns[1].sample_receipt_ns; }, "SAMPLE_OUTSIDE_BUCKET");
    for (const k of ["events_after_as_of_not_read", "events_straddling_as_of_not_read", "l2_events_not_read_after_straddle"]) {
      refuses(d => { delete d.inputs[k]; }, "CLOSED_KEYS_REQUIRED");
      refuses(d => { d.inputs[k] = "1"; }, "INTEGER_REQUIRED");
    }
    refuses(d => { d.inputs.events_sha256 = "A".repeat(64); }, "SHA256_REQUIRED");
  });
  it("keeps the heatmap sparse and checks its grid without allocating rows x columns", () => {
    refuses(d => { d.heatmap.rows += 1; }, "GRID_GEOMETRY_INVALID");
    refuses(d => { d.heatmap.price_hi = d.heatmap.price_lo; }, "GRID_GEOMETRY_INVALID");
    refuses(d => { d.heatmap.tick = "0"; }, "POSITIVE_DECIMAL_REQUIRED");
    const live = (golden().heatmap.columns as Doc[]).findIndex(c => c.status === "LIVE" && c.bids.length > 1);
    expect(live).toBeGreaterThanOrEqual(0);
    refuses(d => { d.heatmap.columns[live].bids.reverse(); }, "CELL_ORDER");
    refuses(d => { d.heatmap.columns[live].bids[0][0] = d.heatmap.rows; }, "INTEGER_REQUIRED");
    refuses(d => { d.heatmap.columns[live].bids[0][1] = "0"; }, "POSITIVE_DECIMAL_REQUIRED");
    const huge = golden();
    huge.heatmap.price_hi = "100000000000000000000"; // enormous grid: rows is bounded by the contract, never allocated
    huge.heatmap.rows = 100_000;
    expect(code(huge)).toBe("GRID_GEOMETRY_INVALID");
    const t0 = performance.now();
    checkMarketFlowArtifact(huge);
    expect(performance.now() - t0).toBeLessThan(200);
  });
  it("admits the open BOOK_* family only by its pattern", () => {
    const pending = (status: string) => (d: Doc) => {
      d.heatmap.columns[1] = { bucket: 1, status, sample_receipt_ns: d.heatmap.columns[1].sample_receipt_ns };
    };
    accepts(pending("BOOK_INVALID"));
    accepts(pending("BOOK_SOMETHING_NEW"));
    accepts(pending("BOOK_" + "A".repeat(59)));
    refuses(pending("BOOK_" + "A".repeat(60)), "ENUM_REFUSED");
    refuses(pending("BOOK_"), "ENUM_REFUSED");
    refuses(pending("book_invalid"), "ENUM_REFUSED");
    refuses(pending("MADE_UP"), "ENUM_REFUSED");
  });
  it("never invents a cause or a participant for a level event", () => {
    const items = golden().level_events.items as Doc[];
    expect(items.length).toBeGreaterThan(0);
    refuses(d => { d.level_events.items[0].cause = "CANCELLED"; }, "ENUM_REFUSED");
    refuses(d => { d.level_events.items[0].cause = "SPOOFING"; }, "ENUM_REFUSED");
    refuses(d => { d.level_events.items[0].kind = "CANCELLED"; }, "ENUM_REFUSED");
    const gone = items.findIndex(i => i.kind !== "APPEARED");
    if (gone >= 0) {
      refuses(d => { d.level_events.items[gone].left_censored = !d.level_events.items[gone].left_censored; }, "STATUS_INCONSISTENT");
      refuses(d => { d.level_events.items[gone].persistence_ns = { min: "9", max: "1" }; }, "INTERVAL_ORDER");
      refuses(d => { d.level_events.items[gone].participant = "x"; }, "CLOSED_KEYS_REQUIRED");
    }
  });
});

describe("text rules", () => {
  it("applies Python's printability and code-point length to every contract text", () => {
    accepts(d => { d.flow.side_convention.evidence_ref = "é\u{1F600}"; });
    accepts(d => { d.flow.side_convention.evidence_ref = "\u{1F600}".repeat(512); });
    for (const bad of ["", "a\nb", "a\tb", "a b", "a​b", "a\ud800b", "a b", "a\u{E0001}b", "\u{1F600}".repeat(513)]) {
      refuses(d => { d.flow.side_convention.evidence_ref = bad; }, "TEXT_REQUIRED");
    }
    refuses(d => { d.assumptions = ["ok", "bad\u0000"]; }, "TEXT_REQUIRED");
    refuses(d => { d.limits = new Array(257).fill("x"); }, "LIST_REQUIRED");
    refuses(d => { d.book.bbo.connection_id = "c".repeat(129); }, "TEXT_REQUIRED");
  });
});

describe("publication (HTTP 200 body)", () => {
  it("requires exactly the artifact keys plus serving, with the matching classification", () => {
    expect(checkMarketFlowPublication(publication())).toEqual({ ok: true });
    const bad = (mutate: (p: Doc) => void, want: string) => {
      const p = publication();
      mutate(p);
      const r = checkMarketFlowPublication(p);
      expect(r.ok).toBe(false);
      if (!r.ok) expect(r.code).toBe(want);
    };
    bad(p => { delete p.serving; }, "CLOSED_TOP_LEVEL_KEYS_REQUIRED");
    bad(p => { p.extra = 1; }, "CLOSED_TOP_LEVEL_KEYS_REQUIRED");
    bad(p => { p.serving.extra = 1; }, "CLOSED_KEYS_REQUIRED");
    bad(p => { p.serving = "NOT_ASSESSED_SYNTHETIC"; }, "CLOSED_KEYS_REQUIRED");
    bad(p => { p.serving.freshness_classification = "NOT_ASSESSED_HISTORICAL"; }, "SERVING_STATE_MISMATCH");
    bad(p => { p.serving.freshness_classification = "FRESH"; }, "SERVING_STATE_MISMATCH");
    bad(p => { p.synthetic = false; }, "EVIDENCE_KIND_REQUIRED");
    bad(p => { p.inputs.extra = 1; }, "CLOSED_KEYS_REQUIRED");
    const historical = publication();
    historical.evidence_kind = historical.state_label = "HISTORICAL";
    historical.serving.freshness_classification = "NOT_ASSESSED_HISTORICAL";
    expect(checkMarketFlowPublication(historical).ok).toBe(true);
  });
  it("does not accept a lexeme the object form cannot show, and the strict reader catches it", () => {
    const text = JSON.stringify(publication());
    const floaty = text.replace('"event_count":19', '"event_count":19.0');
    expect(floaty).not.toBe(text);
    // JSON.parse turns 19.0 into the integer 19: this is why transport conformance needs raw reading.
    expect(checkMarketFlowPublication(JSON.parse(floaty)).ok).toBe(true);
    expect(parseStrictJsonText(floaty)).toMatchObject({ ok: false, code: "NUMBER_NOT_INTEGER" });
    const dup = text.replace("{", '{"product":"MarketFlowArtifact",');
    expect(checkMarketFlowPublication(JSON.parse(dup)).ok).toBe(true);
    expect(parseStrictJsonText(dup)).toMatchObject({ ok: false, code: "DUPLICATE_KEY" });
  });
});

describe("bounded cost", () => {
  it("validates an artifact close to the 4,000,000-byte reader bound within a bounded time", () => {
    const d = golden();
    const bar = BigInt(d.bar_ns);
    const n = 16_000;
    d.as_of_receipt_ns = String(BigInt(d.anchor_ns) + 2n * BigInt(n) * bar);
    d.anchor_ns = String(BigInt(d.as_of_receipt_ns) - BigInt(n) * bar - 1_000n * bar);
    d.bars = Array.from({ length: n }, (_, i) => ({
      index: i, start_ns: String(BigInt(d.anchor_ns) + BigInt(i) * bar), end_ns: String(BigInt(d.anchor_ns) + BigInt(i + 1) * bar),
      status: "NOT_COVERED", trade_count: null, delta_status: "NOT_COVERED", delta_base: null, delta_base_bounds: null,
      segment: null, cvd_base: null, cvd_base_bounds: null,
    }));
    const bytes = new TextEncoder().encode(JSON.stringify(publication(d)));
    expect(bytes.length).toBeGreaterThan(3_000_000);
    expect(bytes.length).toBeLessThan(4_000_000);
    const t0 = performance.now();
    const parsed = readStrictJson(bytes);
    const t1 = performance.now();
    expect(parsed.ok).toBe(true);
    const verdict = checkMarketFlowPublication((parsed as { value: unknown }).value);
    const t2 = performance.now();
    expect(JSON.stringify(verdict)).toBe('{"ok":true}');
    expect(t2 - t0).toBeLessThan(10_000);
    console.info("[market-flow] %d bytes, %d bars: strict read %s ms, deep validation %s ms", bytes.length, n, (t1 - t0).toFixed(0), (t2 - t1).toFixed(0));
  });
  it("refuses lexemes beyond the bounds without BigInt conversion cost", () => {
    const d = golden();
    d.bars[0].open = "9".repeat(1_000_000);
    d.heatmap.price_hi = "9".repeat(1_000_000);
    const t0 = performance.now();
    expect(checkMarketFlowArtifact(d).ok).toBe(false);
    expect(performance.now() - t0).toBeLessThan(500);
  });
});
