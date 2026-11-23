/** Scanner V1 common universe (MEXC Spot ∩ MEXC Perp ∩ Kraken Spot ∩ Kraken Perp).
 *  Read through the GET-only Operator API. The server publishes the intersection
 *  and its four proofs per pair; this client validates the publication, never
 *  computes an intersection and never adds a pair. It only withdraws the current
 *  status when the publication itself or its age no longer allows it. */
import { parseIntradayJson } from "./intradayClient";

export const UNIVERSE_ENDPOINT = "/api/operator/v1/scanner-universe";
export const UNIVERSE_MAX_BYTES = 1_000_000;
export const UNIVERSE_MARKETS = ["MEXC_SPOT", "MEXC_PERPETUAL", "KRAKEN_SPOT", "KRAKEN_PERPETUAL"] as const;
export type UniverseMarket = typeof UNIVERSE_MARKETS[number];
export const MARKET_LABEL: Record<UniverseMarket, string> = {
  MEXC_SPOT: "MEXC Spot", MEXC_PERPETUAL: "MEXC Perpétuel", KRAKEN_SPOT: "Kraken Spot", KRAKEN_PERPETUAL: "Kraken Perpétuel",
};
export const MARKET_SHORT: Record<UniverseMarket, string> = {
  MEXC_SPOT: "MX·S", MEXC_PERPETUAL: "MX·P", KRAKEN_SPOT: "KR·S", KRAKEN_PERPETUAL: "KR·P",
};
const MARKET_IDENTITY: Record<UniverseMarket, [string, string]> = {
  MEXC_SPOT: ["mexc", "SPOT"], MEXC_PERPETUAL: ["mexc", "PERPETUAL"], KRAKEN_SPOT: ["kraken", "SPOT"], KRAKEN_PERPETUAL: ["kraken", "PERPETUAL"],
};
export type UniverseStatus = "VERIFIED" | "VERIFIED_EMPTY" | "UNVERIFIABLE";

export interface UniverseProof {
  exchange: string; market_type: "SPOT" | "PERPETUAL"; native_symbol: string; base: string; quote: string;
  native_base: string; native_quote: string; status: string; contract_type: string;
  settlement_asset: string | null; settlement_basis: string; collected_ms: number; exclusion: null;
}
export interface UniversePair { key: string; base: string; quote: string; proofs: Record<UniverseMarket, UniverseProof> }
export interface UniverseSource {
  market: UniverseMarket; state: string; catalogue_state: "COMPLETE" | "INCOMPLETE" | "UNAVAILABLE"; reason: string | null;
  collected_ms: number | null; age_ms: number | null; current: boolean; instruments: number; admissible: number;
  excluded: Record<string, number>; raw_sha256: Record<string, string>;
}
export interface UniverseExclusion { key: string; reasons: Record<UniverseMarket, string | null>; native_symbols: Partial<Record<UniverseMarket, string[]>> }
export interface ScannerUniverse {
  schema_version: "scanner-universe/1.0.0"; product: "ScannerCommonUniverse"; status: UniverseStatus;
  computed_ms: number; served_ms?: number; freshness_max_age_ms: number; cadence_ms: number;
  blocking_sources: { market: UniverseMarket; reason: string | null }[];
  sources: UniverseSource[]; pairs: UniversePair[]; pair_count: number;
  exclusions: UniverseExclusion[]; exclusions_truncated: boolean;
  reference: { universe_sha256: string; status: string; computed_ms: number; keys: string[]; current: false } | null;
  universe_sha256: string;
}
export class UniverseError extends Error { constructor(public code: string, public status: number | null = null) { super(code); this.name = "UniverseError"; } }

const fail = (): never => { throw new UniverseError("INVALID_UNIVERSE_CONTRACT"); };
const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const isInt = (v: unknown): v is number => typeof v === "number" && Number.isSafeInteger(v) && v >= 0;

export function validateUniverse(v: unknown): ScannerUniverse {
  if (!isObj(v) || v.schema_version !== "scanner-universe/1.0.0" || v.product !== "ScannerCommonUniverse") return fail();
  const d = v as unknown as ScannerUniverse;
  if (!["VERIFIED", "VERIFIED_EMPTY", "UNVERIFIABLE"].includes(d.status)) return fail();
  if (!isInt(d.computed_ms) || !isInt(d.freshness_max_age_ms) || !Array.isArray(d.pairs) || d.pairs.length !== d.pair_count) return fail();
  if (!Array.isArray(d.sources) || d.sources.map(s => s?.market).join() !== UNIVERSE_MARKETS.join()) return fail();
  if (!Array.isArray(d.blocking_sources) || !Array.isArray(d.exclusions)) return fail();
  const allCurrent = d.sources.every(s => s.current === true && s.catalogue_state === "COMPLETE" && isInt(s.collected_ms));
  if (d.status === "VERIFIED" && (!d.pairs.length || !allCurrent || d.blocking_sources.length)) return fail();
  if (d.status === "VERIFIED_EMPTY" && (d.pairs.length || !allCurrent || d.blocking_sources.length)) return fail();
  if (d.status === "UNVERIFIABLE" && (d.pairs.length || !d.blocking_sources.length)) return fail();
  if (d.reference !== null && (!isObj(d.reference) || d.reference.current !== false)) return fail();
  const seen = new Set<string>();
  for (const p of d.pairs) {
    if (!isObj(p) || seen.has(p.key) || p.key !== `${p.base}/${p.quote}`) return fail();
    seen.add(p.key);
    if (!isObj(p.proofs) || Object.keys(p.proofs).sort().join() !== [...UNIVERSE_MARKETS].sort().join()) return fail();
    for (const m of UNIVERSE_MARKETS) {
      const proof = p.proofs[m];
      const [exchange, type] = MARKET_IDENTITY[m];
      if (!isObj(proof) || proof.exchange !== exchange || proof.market_type !== type) return fail();
      if (proof.base !== p.base || proof.quote !== p.quote || proof.exclusion !== null || !isInt(proof.collected_ms)) return fail();
      if (typeof proof.native_symbol !== "string" || !proof.native_symbol) return fail();
      const perpetual = proof.contract_type === "LINEAR_PERPETUAL" || proof.contract_type === "INVERSE_PERPETUAL";
      if ((type === "PERPETUAL") !== perpetual || (type === "SPOT") !== (proof.contract_type === "SPOT")) return fail();
    }
  }
  return d;
}

export async function fetchScannerUniverse(signal?: AbortSignal): Promise<ScannerUniverse> {
  const controller = new AbortController(), abort = () => controller.abort(); let timed = false;
  signal?.addEventListener("abort", abort, { once: true }); if (signal?.aborted) abort();
  const timer = setTimeout(() => { timed = true; controller.abort(); }, 10_000);
  try {
    const response = await fetch(UNIVERSE_ENDPOINT, { method: "GET", signal: controller.signal, cache: "no-store" });
    const length = response.headers.get("content-length");
    if (length !== null && (!/^\d+$/.test(length) || Number(length) > UNIVERSE_MAX_BYTES)) throw new UniverseError("RESPONSE_LIMIT");
    if (!response.body) throw new UniverseError("INVALID_JSON");
    const reader = response.body.getReader(), chunks: Uint8Array[] = []; let size = 0;
    try { while (true) { const p = await reader.read(); if (p.done) break; size += p.value.byteLength; if (size > UNIVERSE_MAX_BYTES) { await reader.cancel(); throw new UniverseError("RESPONSE_LIMIT"); } chunks.push(p.value); } } finally { reader.releaseLock(); }
    const bytes = new Uint8Array(size); let at = 0; for (const c of chunks) { bytes.set(c, at); at += c.length; }
    let value: unknown; try { value = parseIntradayJson(new TextDecoder("utf-8", { fatal: true }).decode(bytes)); } catch { throw new UniverseError("INVALID_JSON"); }
    if (!response.ok) { const o = value as Record<string, unknown>; throw new UniverseError(isObj(o) && typeof o.error_code === "string" && /^[A-Z0-9_]{1,100}$/.test(o.error_code) ? o.error_code : "HTTP_" + response.status, response.status); }
    return validateUniverse(value);
  } catch (e) { if (e instanceof UniverseError) throw e; throw new UniverseError(timed ? "TIMEOUT" : controller.signal.aborted ? "ABORTED" : "TRANSPORT_ERROR"); }
  finally { clearTimeout(timer); signal?.removeEventListener("abort", abort); }
}

/** What the Scanner may show as current. Built from one validated publication,
 *  the time it was received and the current time; never from the Spot Radar rows. */
export type UniverseView =
  | { state: "LOADING" }
  | { state: "VERIFIED"; doc: ScannerUniverse; pairs: UniversePair[] }
  | { state: "VERIFIED_EMPTY"; doc: ScannerUniverse }
  | { state: "UNAVAILABLE"; doc: ScannerUniverse | null; code: string; blocking: { market: UniverseMarket | null; reason: string }[] };

/** Re-checks source ages with the elapsed time since reception: a list that was
 *  current when served stops being current here as soon as one source exceeds
 *  the published bound, or when the last successful read itself is too old. */
export function universeView(doc: ScannerUniverse | null, error: string | null, receivedAt: number, now: number, maxReadAgeMs = 180_000): UniverseView {
  if (!doc && !error) return { state: "LOADING" };
  if (!doc) return { state: "UNAVAILABLE", doc: null, code: error!, blocking: [{ market: null, reason: error! }] };
  const elapsed = Math.max(0, now - receivedAt);
  const serverNow = (doc.served_ms ?? doc.computed_ms) + elapsed;
  const stale = doc.sources.filter(s => s.collected_ms === null || serverNow - s.collected_ms > doc.freshness_max_age_ms);
  if (error) return { state: "UNAVAILABLE", doc, code: error, blocking: [{ market: null, reason: error }] };
  if (doc.status === "UNVERIFIABLE") return { state: "UNAVAILABLE", doc, code: "UNVERIFIABLE", blocking: doc.blocking_sources.map(b => ({ market: b.market, reason: b.reason ?? "UNKNOWN" })) };
  if (elapsed > maxReadAgeMs) return { state: "UNAVAILABLE", doc, code: "READ_TOO_OLD", blocking: [{ market: null, reason: "READ_TOO_OLD" }] };
  if (stale.length) return { state: "UNAVAILABLE", doc, code: "SOURCE_STALE", blocking: stale.map(s => ({ market: s.market, reason: "STALE" })) };
  return doc.status === "VERIFIED" ? { state: "VERIFIED", doc, pairs: doc.pairs } : { state: "VERIFIED_EMPTY", doc };
}

/** MEXC Spot native symbols that the current verified universe admits. Empty
 *  unless the view is VERIFIED: an unavailable or empty universe shows no row. */
export function admittedMexcSpot(view: UniverseView): ReadonlySet<string> {
  return view.state === "VERIFIED" ? new Set(view.pairs.map(p => p.proofs.MEXC_SPOT.native_symbol)) : new Set();
}
export function admittedKeys(view: UniverseView): ReadonlySet<string> {
  return view.state === "VERIFIED" ? new Set(view.pairs.map(p => p.key)) : new Set();
}

/** Filter handed to every Scanner sub-view. Built only from the universe view. */
export interface ScannerGate { admitted: ReadonlySet<string>; keys: ReadonlySet<string>; state: UniverseView["state"] }
export function gateNotice(state: UniverseView["state"]): string {
  return state === "VERIFIED" ? "Aucune ligne observée n’appartient à l’univers commun."
    : state === "VERIFIED_EMPTY" ? "Univers commun vide vérifié : aucune ligne n’est affichée."
    : state === "LOADING" ? "Univers commun en chargement : aucune ligne n’est encore affichée."
    : "Univers commun indisponible : aucune ligne n’est présentée comme courante.";
}
