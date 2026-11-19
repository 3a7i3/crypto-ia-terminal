/** Intraday 0.2: GET-only. Decimal values stay text; no trading authority. */
export const INTRADAY_BASE = "/api/operator/v1/intraday/";
export const MAX_BYTES = 1_000_000;
export const TIMEOUT_MS = 10_000;
export type Market = "spot" | "swap";
export type Field = "last" | "bid" | "ask" | "sp" | "qv" | "chg";
export const fields: Field[] = ["last", "bid", "ask", "sp", "qv", "chg"];
export interface IntradayRow {
  instrument_id: string;
  identity: { venue: "mexc"; market: Market; native_symbol: string };
  contract_status: "UNRESOLVED"; capture_epoch_s: string;
  timestamp_kind: "LOCAL_CYCLE_START"; source_timestamp: null; source_freshness: "UNRESOLVED";
  quote_volume_origin: "LEGACY_NATIVE_OR_ESTIMATED_UNRESOLVED";
  exchange_origin: "EXPLICIT" | "LEGACY_ASSUMED_MEXC";
  values: Record<Field, string | null>;
  field_states: Record<Field, "VALUE" | "LEGACY_ZERO_AMBIGUOUS" | "ABSENT" | "NULL">;
}
interface Input { compressed_bytes: number; decompressed_bytes: number; compressed_sha256: string; content_sha256: string }
export interface Envelope {
  schema_version: "0.2.0"; snapshot_id: string; population: "OBSERVATIONS";
  evidence_kind: "SYNTHETIC" | "HISTORICAL";
  provenance: { producer_sha: string; qualification_version: "legacy-mexc-0.2.0"; as_of_epoch_s: string;
    inputs: Input[]; coverage: string; published_at_utc: string | null };
  serving: { observation_age_s: number | null; freshness: string; source_freshness: "UNRESOLVED" };
  io: { bytes_read: number; pages_read: number; validated_rows: number };
  validation_scope: string; distinct_instruments: number;
}
export interface Overview extends Envelope {
  counts: { input: number; admitted: number; duplicates: number; conflicts: number; rejected: number };
  collector_status: "NOT_ATTESTED";
}
export interface ScannerPage extends Envelope {
  rows: IntradayRow[]; returned_count: number; total_observations: number; matched_observations: number;
  next_cursor: string | null; complete: boolean;
}
export class IntradayError extends Error {
  constructor(public code: string, public status: number | null = null) { super(code); this.name = "IntradayError"; }
}
const fail = (): never => { throw new IntradayError("INVALID_CONTRACT"); };
const obj = (v: unknown): Record<string, unknown> => {
  if (!v || typeof v !== "object" || Array.isArray(v)) return fail();
  return v as Record<string, unknown>;
};
const keys = (v: unknown, names: string[]): Record<string, unknown> => {
  const o = obj(v); if (Object.keys(o).sort().join("|") !== [...names].sort().join("|")) fail(); return o;
};
const text = (v: unknown, re: RegExp): string => { if (typeof v !== "string" || !re.test(v)) return fail(); return v; };
const hex = (v: unknown) => text(v, /^[0-9a-f]{64}$/);
const integer = (v: unknown, max = 600000): number => {
  if (typeof v !== "number" || !Number.isSafeInteger(v) || v < 0 || v > max) return fail(); return v;
};
const constant = (v: unknown, allowed: unknown[]) => { if (!allowed.includes(v)) fail(); };
export function decimalCompare(a: string, b: string): number {
  const parts = (s: string) => { const [x, y = ""] = s.split("."); return { n: BigInt(x + y), scale: y.length }; };
  const x = parts(a), y = parts(b), scale = Math.max(x.scale, y.scale);
  const n = x.n * 10n ** BigInt(scale - x.scale), m = y.n * 10n ** BigInt(scale - y.scale);
  return n < m ? -1 : n > m ? 1 : 0;
}
function decimal(v: unknown): string {
  const s = text(v, /^-?[0-9]{1,101}(?:\.[0-9]{1,100})?$/);
  if (decimalCompare(s, "1" + "0".repeat(100)) > 0 || decimalCompare(s, "-1" + "0".repeat(100)) < 0) fail(); return s;
}
function stamp(v: unknown) {
  if (v === null) return;
  const s = text(v, /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z$/);
  if (!Number.isFinite(Date.parse(s))) fail();
}
function row(v: unknown): IntradayRow {
  const r = keys(v, ["instrument_id","identity","contract_status","capture_epoch_s","timestamp_kind","source_timestamp","source_freshness","quote_volume_origin","exchange_origin","values","field_states"]);
  hex(r.instrument_id);
  const i = keys(r.identity, ["venue","market","native_symbol"]);
  constant(i.venue, ["mexc"]); constant(i.market, ["spot","swap"]); text(i.native_symbol, /^[\x20-\x7e]{1,120}$/);
  constant(r.contract_status, ["UNRESOLVED"]); constant(r.timestamp_kind, ["LOCAL_CYCLE_START"]);
  constant(r.source_timestamp, [null]); constant(r.source_freshness, ["UNRESOLVED"]);
  constant(r.quote_volume_origin, ["LEGACY_NATIVE_OR_ESTIMATED_UNRESOLVED"]);
  constant(r.exchange_origin, ["EXPLICIT","LEGACY_ASSUMED_MEXC"]);
  if (decimalCompare(decimal(r.capture_epoch_s), "0") <= 0 || !/^(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$/.test(r.capture_epoch_s as string)) fail();
  const values = keys(r.values, fields), states = keys(r.field_states, fields);
  for (const k of fields) {
    if (values[k] === null) { constant(states[k], ["ABSENT","NULL"]); if (k === "last") fail(); }
    else {
      const s = decimal(values[k]); constant(states[k], [decimalCompare(s, "0") === 0 ? "LEGACY_ZERO_AMBIGUOUS" : "VALUE"]);
      if (["last","bid","ask"].includes(k) && decimalCompare(s,"0") <= 0) fail();
      if (["sp","qv"].includes(k) && decimalCompare(s,"0") < 0) fail();
    }
  }
  if (values.bid !== null && values.ask !== null && decimalCompare(values.bid as string, values.ask as string) > 0) fail();
  return v as IntradayRow;
}
const envelopeKeys = ["schema_version","snapshot_id","population","evidence_kind","provenance","serving","io","validation_scope","distinct_instruments"];
export function validateIntraday(v: unknown, kind: "scanner" | "overview" | "health"): Overview | ScannerPage {
  const o = keys(v, [...envelopeKeys, ...(kind === "scanner" ? ["rows","returned_count","total_observations","matched_observations","next_cursor","complete"] : ["counts","collector_status"])]);
  constant(o.schema_version, ["0.2.0"]); hex(o.snapshot_id); constant(o.population, ["OBSERVATIONS"]);
  constant(o.evidence_kind, ["SYNTHETIC","HISTORICAL"]); integer(o.distinct_instruments,10000);
  const p = keys(o.provenance, ["producer_sha","qualification_version","as_of_epoch_s","inputs","coverage","published_at_utc"]);
  text(p.producer_sha, /^[0-9a-f]{40}$/); constant(p.qualification_version, ["legacy-mexc-0.2.0"]);
  if (decimalCompare(decimal(p.as_of_epoch_s),"0") <= 0) fail();
  constant(p.coverage, ["UNRESOLVED_EXPECTED_SCHEDULE_NOT_SUPPLIED"]); stamp(p.published_at_utc);
  if (!Array.isArray(p.inputs) || p.inputs.length < 1 || p.inputs.length > 2) fail();
  let totalBytes = 0;
  for (const x of p.inputs as unknown[]) {
    const s = keys(x, ["compressed_bytes","decompressed_bytes","compressed_sha256","content_sha256"]);
    if (!integer(s.compressed_bytes,16000000)) fail();
    totalBytes += integer(s.decompressed_bytes,64000000); hex(s.compressed_sha256); hex(s.content_sha256);
  }
  if (totalBytes > 128000000) fail();
  const s = keys(o.serving, ["observation_age_s","freshness","source_freshness"]);
  if (s.observation_age_s !== null && (typeof s.observation_age_s !== "number" || !Number.isFinite(s.observation_age_s))) fail();
  constant(s.source_freshness, ["UNRESOLVED"]);
  constant(s.freshness, o.evidence_kind === "SYNTHETIC" ? ["NOT_ASSESSED_SYNTHETIC"] : ["UNRESOLVED","STALE","RECENT"]);
  const io = keys(o.io, ["bytes_read","pages_read","validated_rows"]);
  integer(io.bytes_read,8*1024*1024); integer(io.pages_read,101); integer(io.validated_rows,10100);
  if (kind === "scanner") {
    constant(o.validation_scope, ["MANIFEST_AND_CONSULTED_PAGES"]);
    if (!Array.isArray(o.rows) || o.rows.length > 100) fail();
    const rows = (o.rows as unknown[]).map(row);
    const count = integer(o.returned_count,100), matched = integer(o.matched_observations), total = integer(o.total_observations);
    if (count !== rows.length || count > matched || matched > total) fail();
    constant(o.complete, [true,false]);
    if (o.next_cursor !== null) text(o.next_cursor, /^[A-Za-z0-9_-]{1,4096}$/);
    if ((o.next_cursor === null) !== o.complete) fail();
    const seen = new Set<string>();
    for (const r of rows) {
      const key = r.instrument_id + "|" + r.capture_epoch_s;
      if (seen.has(key) || decimalCompare(r.capture_epoch_s,p.as_of_epoch_s as string) > 0) fail(); seen.add(key);
    }
  } else {
    constant(o.validation_scope, ["MANIFEST_ONLY"]); constant(o.collector_status, ["NOT_ATTESTED"]);
    const c = keys(o.counts, ["input","admitted","duplicates","conflicts","rejected"]);
    for (const x of Object.values(c)) integer(x);
    if (c.input !== (c.admitted as number)+(c.duplicates as number)+(c.conflicts as number)+(c.rejected as number)) fail();
  }
  return v as Overview | ScannerPage;
}

/** Separate parser: existing Flow parser rejects valid Intraday serving-age floats. */
export function parseIntradayJson(raw: string): unknown {
  if (raw.length > MAX_BYTES) throw new IntradayError("RESPONSE_LIMIT");
  let i = 0;
  const ws = () => { while (/[\x20\t\r\n]/.test(raw[i] || "X")) i++; };
  const str = (): string => {
    const start = i++; let escaped = false;
    while (i < raw.length) { const c = raw[i++]; if (c === '"' && !escaped) return JSON.parse(raw.slice(start,i)); escaped = c === "\\" && !escaped; }
    return fail();
  };
  const value = (depth: number, path: string): unknown => {
    if (depth > 32) return fail(); ws();
    if (raw[i] === '"') return str();
    if (raw[i] === "{") {
      i++; ws(); const o = Object.create(null) as Record<string,unknown>;
      if (raw[i] === "}") { i++; return o; }
      while (true) {
        ws(); if (raw[i] !== '"') return fail(); const k = str();
        if (Object.hasOwn(o,k)) return fail(); ws(); if (raw[i++] !== ":") return fail();
        o[k] = value(depth+1,path+"/"+k); ws(); const c = raw[i++]; if (c === "}") return o; if (c !== ",") return fail();
      }
    }
    if (raw[i] === "[") {
      i++; ws(); const a: unknown[] = []; if (raw[i] === "]") { i++; return a; }
      while (true) { a.push(value(depth+1,path+"[]")); ws(); const c = raw[i++]; if (c === "]") return a; if (c !== ",") return fail(); }
    }
    const match = /^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(raw.slice(i));
    if (!match) return fail(); i+=match[0].length; const v = JSON.parse(match[0]);
    if (typeof v === "number" && path !== "/serving/observation_age_s" && /[.eE]/.test(match[0])) return fail();
    if (typeof v === "number" && (!Number.isFinite(v) || Math.abs(v) > Number.MAX_SAFE_INTEGER)) return fail(); return v;
  };
  const result=value(0,""); ws(); if (i !== raw.length) return fail(); return result;
}
export interface ScannerQuery { query?: string; market?: Market; cursor?: string; snapshot_id?: string; limit?: number }
export async function fetchIntraday(kind: "scanner" | "overview" | "health", query: ScannerQuery = {}, signal?: AbortSignal): Promise<Overview | ScannerPage> {
  const controller = new AbortController();
  const abort = () => controller.abort(); signal?.addEventListener("abort",abort,{once:true});
  if (signal?.aborted) abort();
  let timeout = false;
  const timer = setTimeout(() => { timeout=true; controller.abort(); }, TIMEOUT_MS);
  try {
    const params = new URLSearchParams();
    for (const [k,v] of Object.entries(query)) if (v !== undefined && v !== "") params.set(k,String(v));
    const response = await fetch(INTRADAY_BASE+kind+(params.size ? "?"+params : ""), {method:"GET",signal:controller.signal,cache:"no-store"});
    const declared = response.headers.get("content-length");
    if (declared !== null && (!/^\d+$/.test(declared) || Number(declared)>MAX_BYTES)) throw new IntradayError("RESPONSE_LIMIT");
    if (!response.body) throw new IntradayError("INVALID_JSON");
    const reader=response.body.getReader(); const chunks: Uint8Array[]=[]; let size=0;
    try { while (true) { const part=await reader.read(); if (part.done) break; size+=part.value.byteLength; if(size>MAX_BYTES) { await reader.cancel(); throw new IntradayError("RESPONSE_LIMIT"); } chunks.push(part.value); } }
    finally { reader.releaseLock(); }
    const bytes=new Uint8Array(size); let at=0; for(const c of chunks){bytes.set(c,at);at+=c.length;}
    let body: unknown;
    try { body=parseIntradayJson(new TextDecoder("utf-8",{fatal:true,ignoreBOM:true}).decode(bytes)); }
    catch(err) { if(err instanceof IntradayError) throw err; throw new IntradayError("INVALID_JSON"); }
    if (!response.ok) {
      const e=obj(body);
      const code=typeof e.error_code==="string" && /^[A-Z0-9_]{1,100}$/.test(e.error_code) ? e.error_code : "HTTP_"+response.status;
      throw new IntradayError(code,response.status);
    }
    const result=validateIntraday(body,kind);
    if (query.snapshot_id && result.snapshot_id!==query.snapshot_id) fail();
    if (kind==="scanner") {
      for(const r of (result as ScannerPage).rows) {
        if(query.market && r.identity.market!==query.market) fail();
        if(query.query && !r.identity.native_symbol.toLowerCase().includes(query.query.trim().toLowerCase())) fail();
        const canonical=JSON.stringify({market:r.identity.market,native_symbol:r.identity.native_symbol,venue:r.identity.venue});
        const digest=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(canonical));
        const id=Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,"0")).join("");
        if(id!==r.instrument_id) fail();
      }
    }
    return result;
  } catch(e) {
    if(e instanceof IntradayError) throw e;
    if(controller.signal.aborted) throw new IntradayError(timeout?"TIMEOUT":"ABORTED");
    throw new IntradayError("TRANSPORT_ERROR");
  } finally { clearTimeout(timer); signal?.removeEventListener("abort",abort); }
}
