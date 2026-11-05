// CryptoRadar Flux — cross-stack differential corpus (lot 3A).
//
// The corpus is generated at run time by the Flux generator under tests/cross_stack through the
// REAL offline chain (synthetic_session -> artifact.replay -> file -> MarketFlowReader -> FastAPI GET).
// With CROSS_STACK_FIXTURES_DIR defined, a missing manifest, case or file FAILS; it is never skipped.
// Without the variable (a plain local `npm test`) the whole suite is skipped and says so by name.
// A finite corpus is not a proof for every JSON text or every Unicode version.
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { fetchMarketFlow } from "../lib/marketFlowClient";
import { readStrictJson } from "../lib/marketFlowJson";
import {
  MARKET_FLOW_AGE_STATUSES, MARKET_FLOW_BAR_STATUSES, MARKET_FLOW_BOOK_STATES, MARKET_FLOW_CALC_VERSION,
  MARKET_FLOW_CHANNEL, MARKET_FLOW_FRESHNESS, MARKET_FLOW_INSTRUMENTS, MARKET_FLOW_L2_REFUSALS,
  MARKET_FLOW_LEVEL_TIME_STATES, MARKET_FLOW_SCHEMA_VERSION, MARKET_FLOW_SEND_STATES,
  MARKET_FLOW_SILENCE_STATUSES, MARKET_FLOW_VENUE, type MarketFlowPublication,
} from "../lib/marketFlowTypes";
import {
  MARKET_FLOW_ARTIFACT_KEYS, MARKET_FLOW_INVALID_REASONS, MAX_BARS, MAX_COLUMNS, MAX_ITEMS, MAX_LIST, MAX_ROWS,
  MAX_TEXT, checkMarketFlowArtifact, checkMarketFlowPublication,
} from "../lib/marketFlowValidation";
import { ORACLE_PYTHON_TARGET, ORACLE_UNICODE_VERSION, PYTHON_NONPRINTABLE_RANGES, codePointLength } from "../lib/marketFlowExact";

const dir = process.env.CROSS_STACK_FIXTURES_DIR;
const suite = dir ? describe : describe.skip;
const root = () => path.join(dir!, "F_flux_corpus");

interface FileRef { file: string; sha256: string; bytes: number }
interface Verdict { valid: boolean; error: string | null }
interface Case {
  id: string; group: string; description: string; http_status: number; expect: string; python: Verdict;
  body: FileRef; artifact?: FileRef; error_code?: string | null; events_sha256?: string;
}
interface Manifest {
  kind: string; oracle: Record<string, unknown>; cases: Case[]; required_native_cases: string[];
  mutation_files: Record<string, { file: string; count: number; valid: number }>;
  generator_problems: string[]; oracle_non_value_errors: number; reader_sampled_mutations: number;
}
interface Mutation {
  id: string; path: (string | number)[]; op: "set" | "delete" | "add_key" | "append" | "pop";
  value?: unknown; key?: string; python: Verdict;
}

// Declared here on purpose: a manifest that silently drops a case must fail, not shrink the gate.
const REQUIRED_NATIVE = [
  "native_base", "native_ns_above_2_53", "native_ns_30_digits", "native_eth_unicode_text", "native_as_of_straddle",
  "native_book_invalid_gap", "native_no_snapshot", "native_malformed_message", "native_event_times",
  "native_silence_exceeded", "native_depth_limited", "native_no_trades",
];
const REQUIRED_OTHER = [
  "variant_historical", "variant_future_timestamp", "variant_stale_age", "variant_qualified_within_assumptions",
  "variant_qualified_with_unresolved", "variant_placeholder_with_time", "variant_open_heatmap_status",
  "file_synthetic_false", "file_float_counter", "file_duplicate_key", "file_bom", "file_invalid_utf8", "file_oversize",
  "http_not_configured", "http_route_missing",
  "raw_float_counter", "raw_duplicate_escaped_key", "raw_nan", "raw_bom", "raw_invalid_utf8", "raw_serving_wrong_class",
  "raw_pretty_printed", "raw_negative_zero_counter", "raw_surrogate_pair_escape",
];
const REQUIRED_MUTATION_FILES = ["base", "ns30", "eth", "straddle", "events", "silence", "unicode"];

let manifest: Manifest;
const byId = new Map<string, Case>();

function read(ref: FileRef, sub: string): Buffer {
  const file = path.join(root(), sub, ref.file);
  if (!existsSync(file)) throw new Error("corpus file missing: " + file);
  const data = readFileSync(file);
  if (data.length !== ref.bytes || createHash("sha256").update(data).digest("hex") !== ref.sha256) {
    throw new Error("corpus file hash/size mismatch: " + file);
  }
  return data;
}
const bytesOf = (b: Buffer): Uint8Array => new Uint8Array(b.buffer, b.byteOffset, b.length);
const body = (c: Case) => bytesOf(read(c.body, "bodies"));
const need = (id: string): Case => {
  const c = byId.get(id);
  if (!c) throw new Error("required corpus case absent: " + id);
  return c;
};

function strictPublication(c: Case): boolean {
  const parsed = readStrictJson(body(c));
  return parsed.ok && checkMarketFlowPublication(parsed.value).ok;
}
function strictArtifact(raw: Uint8Array): boolean {
  const parsed = readStrictJson(raw);
  return parsed.ok && checkMarketFlowArtifact(parsed.value).ok;
}
const publicationOf = (id: string): MarketFlowPublication => JSON.parse(Buffer.from(body(need(id))).toString("utf8"));
const artifactOf = (id: string): Record<string, unknown> => {
  const { serving: _serving, ...artifact } = publicationOf(id) as unknown as Record<string, unknown>;
  void _serving;
  return artifact;
};

function applyMutation(doc: unknown, m: Mutation): unknown {
  const out = structuredClone(doc) as Record<string | number, unknown>;
  if (m.path.length === 0 && m.op === "set") return structuredClone(m.value);
  let parent: Record<string | number, unknown> = out;
  for (const step of m.path.slice(0, -1)) parent = parent[step] as Record<string | number, unknown>;
  const last = m.path.length === 0 ? null : m.path[m.path.length - 1];
  if (m.op === "set") parent[last as string | number] = structuredClone(m.value);
  else if (m.op === "delete") delete parent[last as string | number];
  else {
    const target = (last === null ? out : parent[last]) as unknown;
    if (m.op === "add_key") (target as Record<string, unknown>)[m.key as string] = 0;
    else if (m.op === "append") (target as unknown[]).push(structuredClone(m.value));
    else if (m.op === "pop") (target as unknown[]).pop();
  }
  return out;
}

function stubFetch(status: number, data: Uint8Array) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(data as BodyInit, { status })));
}
afterEach(() => vi.unstubAllGlobals());

suite("MarketFlow: Python oracle vs TypeScript contract over the real offline chain", () => {
  beforeAll(() => {
    const file = path.join(root(), "manifest.json");
    if (!existsSync(file)) throw new Error("market-flow corpus manifest missing: " + file);
    manifest = JSON.parse(readFileSync(file, "utf8")) as Manifest;
    for (const c of manifest.cases) byId.set(c.id, c);
  });

  it("is complete, hashed and free of generator problems", () => {
    expect(manifest.kind).toBe("MarketFlowCorpus");
    expect(manifest.generator_problems).toEqual([]);
    expect([...manifest.required_native_cases].sort()).toEqual([...REQUIRED_NATIVE].sort());
    for (const id of [...REQUIRED_NATIVE, ...REQUIRED_OTHER]) need(id);
    for (const c of manifest.cases) {
      body(c);
      if (c.artifact) read(c.artifact, "artifacts");
    }
    expect(Object.keys(manifest.mutation_files).sort()).toEqual([...REQUIRED_MUTATION_FILES].sort());
    for (const key of REQUIRED_MUTATION_FILES) {
      const rows = JSON.parse(readFileSync(path.join(root(), manifest.mutation_files[key].file), "utf8")).cases as Mutation[];
      expect(rows.length).toBe(manifest.mutation_files[key].count);
      expect(rows.length).toBeGreaterThan(2000);
    }
    expect(manifest.oracle_non_value_errors).toBe(0);
    expect(manifest.reader_sampled_mutations).toBeGreaterThan(100);
  });

  it("mirrors the Python constants (no silent drift of an enum, limit or key set)", () => {
    const o = manifest.oracle as Record<string, any>;
    expect(o.contract_version).toBe(MARKET_FLOW_SCHEMA_VERSION);
    expect(o.calc_version).toBe(MARKET_FLOW_CALC_VERSION);
    expect(o.venue).toBe(MARKET_FLOW_VENUE);
    expect(o.channel).toBe(MARKET_FLOW_CHANNEL);
    expect(o.instruments).toEqual(MARKET_FLOW_INSTRUMENTS);
    expect(o.top_keys).toEqual([...MARKET_FLOW_ARTIFACT_KEYS].sort());
    expect(o.bar_statuses).toEqual([...MARKET_FLOW_BAR_STATUSES]);
    expect(o.book_states).toEqual([...MARKET_FLOW_BOOK_STATES]);
    expect(o.l2_refusals).toEqual([...MARKET_FLOW_L2_REFUSALS]);
    expect(o.invalid_reasons).toEqual([...MARKET_FLOW_INVALID_REASONS]);
    expect(o.silence_statuses).toEqual([...MARKET_FLOW_SILENCE_STATUSES]);
    expect(o.age_statuses).toEqual([...MARKET_FLOW_AGE_STATUSES]);
    expect(o.freshness).toEqual([...MARKET_FLOW_FRESHNESS]);
    expect(o.send_states).toEqual([...MARKET_FLOW_SEND_STATES]);
    expect(o.level_time_states).toEqual([...MARKET_FLOW_LEVEL_TIME_STATES]);
    expect(o.limits).toMatchObject({
      MAX_BARS, MAX_COLUMNS, MAX_ROWS, MAX_ITEMS, MAX_LIST, MAX_TEXT, READER_MAX_BYTES: 4_000_000,
    });
  });

  it("uses the Unicode table of the targeted oracle runtime, or fails visibly", () => {
    const o = manifest.oracle as Record<string, any>;
    // A different Python/Unicode version is a divergence to resolve, never to hide.
    expect(String(o.python_version).startsWith(ORACLE_PYTHON_TARGET + ".")).toBe(true);
    expect(o.unicode_version).toBe(ORACLE_UNICODE_VERSION);
    expect((o.nonprintable_ranges as number[][]).flat()).toEqual([...PYTHON_NONPRINTABLE_RANGES]);
  });

  it.each(REQUIRED_NATIVE)("accepts the real HTTP 200 body of %s unchanged, through reader and client", async id => {
    const c = need(id);
    expect(c.http_status).toBe(200);
    const raw = body(c);
    const parsed = readStrictJson(raw);
    expect(parsed.ok).toBe(true);
    const before = structuredClone((parsed as { value: unknown }).value);
    expect(checkMarketFlowPublication((parsed as { value: unknown }).value)).toEqual({ ok: true });
    expect((parsed as { value: unknown }).value).toEqual(before); // not mutated
    stubFetch(200, raw);
    const result = await fetchMarketFlow();
    expect(result.status).toBe("success");
    if (result.status === "success") {
      expect(result.publication).toEqual(JSON.parse(Buffer.from(raw).toString("utf8")));
      expect(result.publication.serving.freshness_classification).toBe("NOT_ASSESSED_" + result.publication.state_label);
    }
  });

  it("keeps nanoseconds beyond 2**53 and 30-digit texts exactly", () => {
    const hi = publicationOf("native_ns_above_2_53");
    expect(BigInt(hi.anchor_ns)).toBeGreaterThan(2n ** 53n);
    expect(Number(BigInt(hi.anchor_ns) + 1n)).toBe(Number(BigInt(hi.anchor_ns))); // a Number could not tell them apart
    expect(hi.anchor_ns).toMatch(/^[1-9][0-9]{18}$/);
    const thirty = publicationOf("native_ns_30_digits");
    expect(thirty.as_of_receipt_ns).toMatch(/^[1-9][0-9]{28,29}$/);
    expect(thirty.as_of_receipt_ns.length).toBeGreaterThanOrEqual(29);
    for (const id of ["native_ns_above_2_53", "native_ns_30_digits"]) {
      const text = Buffer.from(body(need(id))).toString("utf8");
      const doc = publicationOf(id);
      expect(text).toContain('"as_of_receipt_ns":"' + doc.as_of_receipt_ns + '"');
      expect(doc.bars[0].start_ns).toBe(doc.anchor_ns);
    }
  });

  it("keeps non-BMP text, refusal codes and native book reasons exactly", () => {
    const eth = publicationOf("native_eth_unicode_text");
    expect(eth.flow.instrument).toBe("ETH-USD");
    expect(eth.flow.side_convention.evidence_ref).toContain("\u{1F600}");
    expect(eth.trades.sessions.some(s => s.includes("\u{1F600}"))).toBe(true);
    expect(codePointLength(eth.flow.side_convention.evidence_ref)).toBeLessThan(eth.flow.side_convention.evidence_ref.length);
    const gap = publicationOf("native_book_invalid_gap");
    expect(gap.book.state).toEqual(["INVALID", "SEQUENCE_GAP"]);
    expect(gap.book.freshness?.freshness).toBe("NOT_USABLE");
    expect(gap.book.bbo.status).toBe("NOT_AVAILABLE");
    expect(gap.book.bbo.reason).toBe("SEQUENCE_GAP");
    const none = publicationOf("native_no_snapshot");
    expect(none.book.state).toEqual(["NO_SNAPSHOT", null]);
    expect(none.book.freshness).toBeNull();
    const cut = publicationOf("native_as_of_straddle");
    expect(cut.book.state).toEqual(["UNRESOLVED", "MESSAGE_STRADDLES_AS_OF"]);
    expect(cut.inputs.events_straddling_as_of_not_read).toBeGreaterThan(0);
    expect(cut.inputs.l2_events_not_read_after_straddle).toBeGreaterThan(0);
    expect(cut.inputs.events_after_as_of_not_read).toBeGreaterThan(0);
    const bad = publicationOf("native_malformed_message");
    expect(bad.heatmap.columns.some(c => c.status === "BOOK_INVALID")).toBe(true);
    const stale = publicationOf("native_silence_exceeded");
    expect(stale.book.freshness?.freshness).toBe("STALE");
    expect(stale.heatmap.columns.some(c => c.status === "BOOK_STALE_BY_SILENCE")).toBe(true);
  });

  it("keeps UNKNOWN distinct from zero, session breaks, NOT_COVERED and sparse heatmap cells", () => {
    const base = publicationOf("native_base");
    expect(base.bars.map(b => b.status)).toEqual(["OBSERVED", "OBSERVED_ZERO", "OBSERVED", "NOT_COVERED", "SESSION_BREAK_UNRESOLVED"]);
    const notCovered = base.bars[3];
    expect(notCovered).toMatchObject({ trade_count: null, delta_base: null, cvd_base: null, segment: null });
    expect(base.bars[4]).toMatchObject({ delta_status: "SESSION_BREAK_UNRESOLVED", cvd_base_bounds: null });
    expect(base.bars.some(b => b.status !== "NOT_COVERED" && b.status !== "SESSION_BREAK_UNRESOLVED" && b.delta_status === "PARTIAL_UNKNOWN_SIDE")).toBe(true);
    const live = base.heatmap.columns.find(c => c.status === "LIVE");
    expect(live && live.status === "LIVE" && live.bids.every(([row]) => Number.isInteger(row))).toBe(true);
    const times = publicationOf("native_event_times").book.bbo;
    expect(times.status).toBe("OBSERVED_UNQUALIFIED");
    if (times.status === "OBSERVED_UNQUALIFIED") {
      expect(times.bid.level_event_time_state).toBe("NATIVE_UNQUALIFIED");
      expect(times.ask).toMatchObject({ level_event_time_state: "PLACEHOLDER_EPOCH_NOT_A_DATE", level_event_time_ns: null });
    }
  });

  it.each(manifest0("derived_variant"))("agrees with Python on %s (artifact level)", id => {
    const c = need(id);
    expect(strictArtifact(bytesOf(read(c.artifact!, "artifacts")))).toBe(c.python.valid);
    // The reader serves a valid variant (200) and refuses an invalid one (503 INVALID_SCHEMA).
    expect(c.http_status).toBe(c.python.valid ? 200 : 503);
  });

  it.each(manifest0("artifact_corruption"))("refuses the corrupted artifact %s and surfaces the native error code", async id => {
    const c = need(id);
    expect(strictArtifact(bytesOf(read(c.artifact!, "artifacts")))).toBe(false);
    expect(c.http_status).toBe(503);
    stubFetch(503, body(c));
    const result = await fetchMarketFlow();
    expect(result).toEqual({ status: "api_error", httpStatus: 503, errorCode: c.error_code });
    expect(String(c.error_code).startsWith("MARKET_FLOW_")).toBe(true);
  });

  it.each(["http_not_configured", "http_route_missing"])("maps the native body of %s to api_error", async id => {
    const c = need(id);
    stubFetch(c.http_status, body(c));
    const result = await fetchMarketFlow();
    expect(result).toEqual({ status: "api_error", httpStatus: c.http_status, errorCode: c.error_code ?? null });
  });

  it.each(manifest0("response_mutation"))("matches Python on the response mutation %s", async id => {
    const c = need(id);
    expect(strictPublication(c)).toBe(c.python.valid);
    stubFetch(200, body(c));
    const result = await fetchMarketFlow();
    if (c.python.valid) expect(result.status).toBe("success");
    else expect(result.status).toBe("transport_error"); // an HTTP 200 never becomes api_error
  });

  it.each(REQUIRED_MUTATION_FILES)("agrees with the Python oracle on every mutation of corpus %s", key => {
    const file = JSON.parse(readFileSync(path.join(root(), manifest.mutation_files[key].file), "utf8")) as { base: string; cases: Mutation[] };
    const base = artifactOf(file.base);
    expect(checkMarketFlowArtifact(base).ok).toBe(true);
    const mismatches: string[] = [];
    let accepted = 0;
    for (const m of file.cases) {
      const ok = checkMarketFlowArtifact(applyMutation(base, m)).ok;
      if (ok) accepted += 1;
      if (ok !== m.python.valid) mismatches.push(m.id + " " + JSON.stringify(m.path) + " " + m.op + " python=" + String(m.python.error));
    }
    expect(mismatches.slice(0, 20)).toEqual([]);
    expect(accepted).toBe(manifest.mutation_files[key].valid);
  });
});

/** Case ids of a group, read at collection time (it.each needs them before beforeAll runs). */
function manifest0(group: string): string[] {
  if (!dir) return ["(corpus not generated)"];
  const file = path.join(root(), "manifest.json");
  if (!existsSync(file)) return ["(MANIFEST MISSING)"];
  return (JSON.parse(readFileSync(file, "utf8")) as Manifest).cases.filter(c => c.group === group).map(c => c.id);
}
