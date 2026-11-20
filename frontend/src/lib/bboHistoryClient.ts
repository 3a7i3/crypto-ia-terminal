/** Historical BBO composite (MEXC + Kraken Spot) read through the GET-only Operator API.
 *  The publication is built offline from sealed evidence; this client validates it
 *  and returns it unchanged. No value is recomputed here, nothing is LIVE. */
import { parseIntradayJson, decimalCompare } from "./intradayClient";

export const BBO_HISTORY_ENDPOINT = "/api/operator/v1/bbo-composite-history";
export const BBO_HISTORY_MAX_BYTES = 200_000;
export const BBO_HISTORY_LABEL = "Composite de milieux de carnet · Spot · Historique";
export const BBO_VENUES = ["mexc", "kraken"] as const;
export type BboVenue = typeof BBO_VENUES[number];
export const BBO_CATEGORIES = ["COMPOSITE", "SINGLE_SOURCE", "SOURCE_EXCLUDED", "EXCESSIVE_GAP", "NOT_EVALUATED"] as const;
export const BBO_SOURCE_STATES = ["VALID", "UNCHANGED_VERIFIED", "FRESHNESS_UNKNOWN", "CONTINUITY_LOST", "BOOK_INVALID", "NOT_INITIALIZED", "SOURCE_UNAVAILABLE"] as const;
export const BBO_SENS_L = [1, 2, 5, 10] as const;
export const BBO_SENS_G = [10, 25, 50, 100] as const;
export const BBO_SENS_KEYS = BBO_SENS_L.flatMap(l => BBO_SENS_G.map(g => `L${l}s_G${g}bps`));

export interface BboCandle { open: string | null; high: string | null; low: string | null; close: string | null; points: number; status: "COMPLETE" | "INCOMPLETE" }
export interface BboWindow {
  index: number; start_ms: number; end_ms: number; planned: number; evaluated: number; composite: number;
  by_category: Record<typeof BBO_CATEGORIES[number], number>;
  by_source_state: Record<BboVenue, Record<typeof BBO_SOURCE_STATES[number], number>>;
  candle: BboCandle; venue_candles: Record<BboVenue, BboCandle>; sensitivity_composite: Record<string, number>;
}
export interface BboFlux { eligible: number; unchanged_verified: number; evaluated: number; unresolved_breaks: number; verdict: string }
export interface BboPair {
  pair: string; display_symbol: string; market_type: "SPOT"; evidence_kind: "OBSERVATION" | "SYNTHETIC";
  venues: { venue: BboVenue; native_symbol: string; feed: string }[];
  thresholds: { liveness_max_ms: number; gap_max_bps: string; gap_boundary: string; step_ms: number; points_per_window: number; weights: string; reference_venue: string };
  window_utc: { start_ms: number; end_ms: number };
  coverage: { planned: number; evaluated: number; composite: number; complete_composite_candles: number; candles: number; verdict_pre_registered: string };
  windows: BboWindow[]; sensitivity_composite_totals: Record<string, number>; flux: Record<BboVenue, BboFlux>;
  hypotheses: { A_ORDER: { statement: string; majority_unchanged_verified: boolean } };
  kraken_checksums: { match: number; mismatch: number };
  provenance: {
    pilot: string; collection_commit: string; host: string; run_status: string; exit_code: number;
    started_utc_ms: number; ended_utc_ms: number; rest_used: Record<string, number>;
    reconnects: Record<BboVenue, number>; resyncs: Record<BboVenue, number>; frames: number; events: number;
    events_sha256: string; frames_sha256: string; summary_sha256: string; window_sha256: string[];
    archive_name: string; archive_sha256: string; replay: string;
  };
}
export interface BboHistory {
  schema_version: "bbo-composite-history/1.0.0"; label: string; scope: "HISTORICAL_PREVIEW_READ_ONLY";
  evidence_kind: "OBSERVATION" | "SYNTHETIC" | "MIXED"; generated_at_utc: string; report: string;
  pairs: BboPair[]; limits: string[]; serving: { freshness_classification: "HISTORICAL_NOT_LIVE" };
}
export class BboHistoryError extends Error { constructor(public code: string, public status: number | null = null) { super(code); this.name = "BboHistoryError"; } }

type O = Record<string, unknown>;
const obj = (v: unknown): v is O => typeof v === "object" && v !== null && !Array.isArray(v);
const keys = (v: unknown, k: readonly string[]): v is O => obj(v) && Object.keys(v).length === k.length && k.every(x => Object.hasOwn(v, x));
const int = (v: unknown, lo = 0, hi = Number.MAX_SAFE_INTEGER): v is number => typeof v === "number" && Number.isSafeInteger(v) && v >= lo && v <= hi;
const str = (v: unknown, max = 400): v is string => typeof v === "string" && v.length <= max;
const DEC = /^-?(0|[1-9][0-9]{0,30})(\.[0-9]{1,18})?$/, HEX64 = /^[0-9a-f]{64}$/, HEX40 = /^[0-9a-f]{40}$/;
const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);

function candleOk(c: unknown, ppw: number): boolean {
  if (!keys(c, ["open", "high", "low", "close", "points", "status"]) || !int(c.points, 0, ppw)) return false;
  const ohlc = [c.open, c.high, c.low, c.close];
  if (c.status === "INCOMPLETE") return c.points < ppw && ohlc.every(x => x === null);
  if (c.status !== "COMPLETE" || c.points !== ppw || !ohlc.every(x => str(x, 60) && DEC.test(x))) return false;
  const [o, h, l, cl] = ohlc as string[];
  return decimalCompare(l, o) <= 0 && decimalCompare(l, cl) <= 0 && decimalCompare(h, o) >= 0 && decimalCompare(h, cl) >= 0;
}

/** Contract check mirroring observability/radar_composite/bbo_history.validate_history. Comparisons only. */
export function validateBboHistory(v: unknown): BboHistory {
  const fail = (code: string): never => { throw new BboHistoryError("INVALID_BBO_HISTORY_" + code); };
  if (!keys(v, ["schema_version", "label", "scope", "evidence_kind", "generated_at_utc", "report", "pairs", "limits", "serving"])) return fail("TOP");
  if (v.schema_version !== "bbo-composite-history/1.0.0" || v.label !== BBO_HISTORY_LABEL || v.scope !== "HISTORICAL_PREVIEW_READ_ONLY") return fail("SCHEMA");
  if (!keys(v.serving, ["freshness_classification"]) || v.serving.freshness_classification !== "HISTORICAL_NOT_LIVE") return fail("SERVING");
  if (!["OBSERVATION", "SYNTHETIC", "MIXED"].includes(v.evidence_kind as string) || !str(v.generated_at_utc) || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/.test(v.generated_at_utc) || !str(v.report)) return fail("HEADER");
  if (!Array.isArray(v.limits) || !v.limits.every(x => str(x, 80))) return fail("LIMITS");
  if (!Array.isArray(v.pairs) || v.pairs.length < 1 || v.pairs.length > 8) return fail("PAIRS");
  if (new Set(v.pairs.map(p => obj(p) ? p.pair : null)).size !== v.pairs.length) return fail("PAIR_DUPLICATE");
  for (const p of v.pairs) {
    if (!keys(p, ["pair", "display_symbol", "market_type", "evidence_kind", "venues", "thresholds", "window_utc", "coverage", "windows", "sensitivity_composite_totals", "flux", "hypotheses", "kraken_checksums", "provenance"])) return fail("PAIR_KEYS");
    if (!str(p.pair, 20) || !str(p.display_symbol, 40) || p.market_type !== "SPOT" || !["OBSERVATION", "SYNTHETIC"].includes(p.evidence_kind as string)) return fail("PAIR_ID");
    if (!Array.isArray(p.venues) || p.venues.length !== 2 || !p.venues.every((x, i) => keys(x, ["venue", "native_symbol", "feed"]) && x.venue === BBO_VENUES[i] && str(x.native_symbol, 40) && str(x.feed, 120))) return fail("VENUES");
    const th = p.thresholds;
    if (!keys(th, ["liveness_max_ms", "gap_max_bps", "gap_boundary", "step_ms", "points_per_window", "weights", "reference_venue"]) || !int(th.points_per_window, 1, 1000) || !int(th.step_ms, 1) || !int(th.liveness_max_ms, 1) || !str(th.gap_max_bps, 20) || !DEC.test(th.gap_max_bps)) return fail("THRESHOLDS");
    const ppw = th.points_per_window, ws = p.windows;
    if (!Array.isArray(ws) || ws.length < 1 || ws.length > 288) return fail("WINDOWS");
    ws.forEach((w, i) => {
      if (!keys(w, ["index", "start_ms", "end_ms", "planned", "evaluated", "composite", "by_category", "by_source_state", "candle", "venue_candles", "sensitivity_composite"]) || w.index !== i) fail("WINDOW_KEYS");
      const W = w as O;
      if (!int(W.start_ms) || !int(W.end_ms) || W.end_ms - W.start_ms !== ppw * (th.step_ms as number)) fail("WINDOW_BOUNDS");
      if (i > 0 && (W.start_ms as number) < ((ws[i - 1] as O).end_ms as number)) fail("WINDOW_ORDER");
      const cats = W.by_category;
      if (!keys(cats, BBO_CATEGORIES) || !Object.values(cats).every(x => int(x)) || sum(Object.values(cats) as number[]) !== ppw || W.planned !== ppw) fail("WINDOW_PLANNED");
      if (W.composite !== (cats as O).COMPOSITE || W.evaluated !== ppw - ((cats as O).NOT_EVALUATED as number)) fail("WINDOW_COUNTS");
      if (!keys(W.by_source_state, BBO_VENUES) || !BBO_VENUES.every(x => { const s = (W.by_source_state as O)[x]; return keys(s, BBO_SOURCE_STATES) && Object.values(s).every(y => int(y)) && sum(Object.values(s) as number[]) === ppw; })) fail("WINDOW_SOURCES");
      if (!candleOk(W.candle, ppw) || !keys(W.venue_candles, BBO_VENUES) || !BBO_VENUES.every(x => candleOk((W.venue_candles as O)[x], ppw))) fail("WINDOW_CANDLE");
      if (!keys(W.sensitivity_composite, BBO_SENS_KEYS) || !Object.values(W.sensitivity_composite).every(x => int(x, 0, ppw)) || (W.sensitivity_composite as O).L2s_G50bps !== W.composite) fail("WINDOW_SENSITIVITY");
    });
    const wl = ws as BboWindow[], c = p.coverage;
    if (!keys(c, ["planned", "evaluated", "composite", "complete_composite_candles", "candles", "verdict_pre_registered"]) || !str(c.verdict_pre_registered, 60)) return fail("COVERAGE");
    if (c.planned !== sum(wl.map(w => w.planned)) || c.evaluated !== sum(wl.map(w => w.evaluated)) || c.composite !== sum(wl.map(w => w.composite)) || c.candles !== wl.length || c.complete_composite_candles !== wl.filter(w => w.candle.status === "COMPLETE").length) return fail("COVERAGE_SUM");
    if (!keys(p.window_utc, ["start_ms", "end_ms"]) || p.window_utc.start_ms !== wl[0].start_ms || p.window_utc.end_ms !== wl[wl.length - 1].end_ms) return fail("WINDOW_UTC");
    if (!keys(p.sensitivity_composite_totals, BBO_SENS_KEYS) || !BBO_SENS_KEYS.every(k => (p.sensitivity_composite_totals as O)[k] === sum(wl.map(w => w.sensitivity_composite[k])))) return fail("SENSITIVITY");
    if (!keys(p.flux, BBO_VENUES) || !BBO_VENUES.every(x => {
      const f = (p.flux as O)[x];
      return keys(f, ["eligible", "unchanged_verified", "evaluated", "unresolved_breaks", "verdict"]) && f.evaluated === c.evaluated && int(f.unresolved_breaks) && str(f.verdict, 40)
        && f.eligible === sum(wl.map(w => w.by_source_state[x].VALID + w.by_source_state[x].UNCHANGED_VERIFIED))
        && f.unchanged_verified === sum(wl.map(w => w.by_source_state[x].UNCHANGED_VERIFIED));
    })) return fail("FLUX");
    const a = obj(p.hypotheses) ? p.hypotheses.A_ORDER : null;
    const majority = BBO_VENUES.some(x => 2 * ((p.flux as O)[x] as BboFlux).unchanged_verified > (c.evaluated as number));
    if (!keys(p.hypotheses, ["A_ORDER"]) || !keys(a, ["statement", "majority_unchanged_verified"]) || !str(a.statement) || a.majority_unchanged_verified !== majority) return fail("A_ORDER");
    if (!keys(p.kraken_checksums, ["match", "mismatch"]) || !int(p.kraken_checksums.match) || !int(p.kraken_checksums.mismatch)) return fail("CHECKSUMS");
    const pv = p.provenance;
    if (!obj(pv) || !HEX40.test(String(pv.collection_commit)) || !["events_sha256", "frames_sha256", "summary_sha256", "archive_sha256"].every(k => HEX64.test(String(pv[k])))
      || !Array.isArray(pv.window_sha256) || pv.window_sha256.length !== wl.length || !pv.window_sha256.every(x => HEX64.test(String(x)))
      || !str(pv.archive_name, 120) || !int(pv.started_utc_ms) || !int(pv.ended_utc_ms) || !int(pv.frames) || !int(pv.events) || !str(pv.replay, 60)) return fail("PROVENANCE");
  }
  return v as unknown as BboHistory;
}

export async function fetchBboHistory(signal?: AbortSignal): Promise<BboHistory> {
  const controller = new AbortController(), abort = () => controller.abort(); let timed = false;
  signal?.addEventListener("abort", abort, { once: true }); if (signal?.aborted) abort();
  const timer = setTimeout(() => { timed = true; controller.abort(); }, 10_000);
  try {
    const response = await fetch(BBO_HISTORY_ENDPOINT, { method: "GET", signal: controller.signal, cache: "no-store" });
    const length = response.headers.get("content-length");
    if (length !== null && (!/^\d+$/.test(length) || Number(length) > BBO_HISTORY_MAX_BYTES)) throw new BboHistoryError("RESPONSE_LIMIT");
    if (!response.body) throw new BboHistoryError("INVALID_JSON");
    const reader = response.body.getReader(), chunks: Uint8Array[] = []; let size = 0;
    try { while (true) { const p = await reader.read(); if (p.done) break; size += p.value.byteLength; if (size > BBO_HISTORY_MAX_BYTES) { await reader.cancel(); throw new BboHistoryError("RESPONSE_LIMIT"); } chunks.push(p.value); } } finally { reader.releaseLock(); }
    const bytes = new Uint8Array(size); let at = 0; for (const ch of chunks) { bytes.set(ch, at); at += ch.length; }
    let value: unknown; try { value = parseIntradayJson(new TextDecoder("utf-8", { fatal: true }).decode(bytes)); } catch { throw new BboHistoryError("INVALID_JSON"); }
    if (!response.ok) { const o = value as O; throw new BboHistoryError(obj(o) && typeof o.error_code === "string" && /^[A-Z0-9_]{1,100}$/.test(o.error_code) ? o.error_code : "HTTP_" + response.status, response.status); }
    return validateBboHistory(value);
  } catch (e) { if (e instanceof BboHistoryError) throw e; throw new BboHistoryError(timed ? "TIMEOUT" : controller.signal.aborted ? "ABORTED" : "TRANSPORT_ERROR"); }
  finally { clearTimeout(timer); signal?.removeEventListener("abort", abort); }
}
