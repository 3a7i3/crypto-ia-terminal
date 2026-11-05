// CryptoRadar Flux — strict raw JSON reading (lot 3A).
//
// JSON.parse is permissive in ways the Flux contract is not: it silently keeps
// the last of two equal keys, turns 1.0 / 1e0 / 9007199254740993 into plain
// numbers and cannot say which lexeme it saw. Conformance of the TRANSPORT
// therefore needs the raw bytes. This module decodes UTF-8 strictly and parses
// the text with its own small recursive-descent reader that refuses:
//   - invalid UTF-8; a byte-order mark (kept as U+FEFF, which is not JSON);
//   - duplicate object keys, compared after escape decoding;
//   - any number that is not a JSON integer inside the safe range (the Python
//     contract refuses every float, however it was spelt, and every counter
//     above 2**53 - 1);
//   - NaN / Infinity / anything outside RFC 8259; trailing content;
//   - nesting deeper than MARKET_FLOW_MAX_JSON_DEPTH; bodies above the byte bound.
// It returns plain values; it never rewrites a string.

/**
 * Transport bound (a proposal to be proved, NOT a Python contract bound). The
 * reader refuses an artifact file above 4_000_000 bytes and then adds only
 * `"serving":{"freshness_classification":"NOT_ASSESSED_<LABEL>"}` (at most 66
 * bytes) in a compact serialisation that is never longer than the file text.
 */
export const MARKET_FLOW_MAX_RESPONSE_BYTES = 4_001_024;
/** A valid artifact is 7 levels deep at most; 64 is a generous transport bound. */
export const MARKET_FLOW_MAX_JSON_DEPTH = 64;

export type StrictJsonErrorCode =
  | "BYTES_TOO_LARGE"
  | "INVALID_UTF8"
  | "INVALID_JSON"
  | "DUPLICATE_KEY"
  | "NUMBER_NOT_INTEGER"
  | "NUMBER_OUT_OF_SAFE_RANGE"
  | "DEPTH_EXCEEDED";

export type StrictJsonResult =
  | { readonly ok: true; readonly value: unknown }
  | { readonly ok: false; readonly code: StrictJsonErrorCode; readonly offset: number | null };

class StrictJsonFailure {
  constructor(readonly code: StrictJsonErrorCode, readonly offset: number | null) {}
}

function fail(code: StrictJsonErrorCode, offset: number | null): never {
  throw new StrictJsonFailure(code, offset);
}

const isDigit = (c: number): boolean => c >= 48 && c <= 57;

class Reader {
  private i = 0;
  constructor(private readonly s: string) {}

  parseDocument(): unknown {
    this.skipWs();
    const value = this.value(1);
    this.skipWs();
    if (this.i !== this.s.length) fail("INVALID_JSON", this.i);
    return value;
  }

  private skipWs(): void {
    const s = this.s;
    for (;;) {
      const c = s.charCodeAt(this.i);
      if (c === 32 || c === 9 || c === 10 || c === 13) this.i += 1;
      else return;
    }
  }

  private value(depth: number): unknown {
    const c = this.s.charCodeAt(this.i);
    if (c === 123) return this.object(depth);
    if (c === 91) return this.array(depth);
    if (c === 34) return this.string();
    if (c === 45 || isDigit(c)) return this.number();
    if (this.s.startsWith("true", this.i)) { this.i += 4; return true; }
    if (this.s.startsWith("false", this.i)) { this.i += 5; return false; }
    if (this.s.startsWith("null", this.i)) { this.i += 4; return null; }
    return fail("INVALID_JSON", this.i); // includes NaN, Infinity, end of input
  }

  private object(depth: number): unknown {
    if (depth > MARKET_FLOW_MAX_JSON_DEPTH) fail("DEPTH_EXCEEDED", this.i);
    this.i += 1;
    const out: Record<string, unknown> = {};
    const seen = new Set<string>();
    this.skipWs();
    if (this.s.charCodeAt(this.i) === 125) { this.i += 1; return out; }
    for (;;) {
      this.skipWs();
      if (this.s.charCodeAt(this.i) !== 34) fail("INVALID_JSON", this.i);
      const keyAt = this.i;
      const key = this.string();
      if (seen.has(key)) fail("DUPLICATE_KEY", keyAt);
      seen.add(key);
      this.skipWs();
      if (this.s.charCodeAt(this.i) !== 58) fail("INVALID_JSON", this.i);
      this.i += 1;
      this.skipWs();
      const v = this.value(depth + 1);
      // defineProperty: "__proto__" is an ordinary own key here, never the prototype.
      Object.defineProperty(out, key, { value: v, enumerable: true, writable: true, configurable: true });
      this.skipWs();
      const c = this.s.charCodeAt(this.i);
      this.i += 1;
      if (c === 125) return out;
      if (c !== 44) fail("INVALID_JSON", this.i - 1);
    }
  }

  private array(depth: number): unknown {
    if (depth > MARKET_FLOW_MAX_JSON_DEPTH) fail("DEPTH_EXCEEDED", this.i);
    this.i += 1;
    const out: unknown[] = [];
    this.skipWs();
    if (this.s.charCodeAt(this.i) === 93) { this.i += 1; return out; }
    for (;;) {
      this.skipWs();
      out.push(this.value(depth + 1));
      this.skipWs();
      const c = this.s.charCodeAt(this.i);
      this.i += 1;
      if (c === 93) return out;
      if (c !== 44) fail("INVALID_JSON", this.i - 1);
    }
  }

  private string(): string {
    const s = this.s;
    this.i += 1; // opening quote
    let out = "";
    let from = this.i;
    for (;;) {
      if (this.i >= s.length) fail("INVALID_JSON", this.i);
      const c = s.charCodeAt(this.i);
      if (c === 34) {
        out += s.slice(from, this.i);
        this.i += 1;
        return out;
      }
      if (c < 0x20) fail("INVALID_JSON", this.i);
      if (c !== 92) { this.i += 1; continue; }
      out += s.slice(from, this.i);
      const e = s.charAt(this.i + 1);
      this.i += 2;
      switch (e) {
        case '"': out += '"'; break;
        case "\\": out += "\\"; break;
        case "/": out += "/"; break;
        case "b": out += "\b"; break;
        case "f": out += "\f"; break;
        case "n": out += "\n"; break;
        case "r": out += "\r"; break;
        case "t": out += "\t"; break;
        case "u": {
          const hex = s.slice(this.i, this.i + 4);
          if (!/^[0-9a-fA-F]{4}$/.test(hex)) fail("INVALID_JSON", this.i);
          out += String.fromCharCode(parseInt(hex, 16));
          this.i += 4;
          break;
        }
        default:
          fail("INVALID_JSON", this.i - 1);
      }
      from = this.i;
    }
  }

  private number(): number {
    const s = this.s;
    const start = this.i;
    if (s.charCodeAt(this.i) === 45) this.i += 1;
    const first = s.charCodeAt(this.i);
    if (!isDigit(first)) fail("INVALID_JSON", this.i);
    if (first === 48) this.i += 1;
    else while (isDigit(s.charCodeAt(this.i))) this.i += 1;
    const intEnd = this.i;
    const next = s.charCodeAt(this.i);
    if (next === 46 || next === 101 || next === 69) {
      // Well-formed or not, a fraction / exponent is a float for the contract.
      const tail = /(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/y;
      tail.lastIndex = this.i;
      const rest = tail.exec(s);
      if (rest === null || rest[0].length === 0) fail("INVALID_JSON", this.i);
      fail("NUMBER_NOT_INTEGER", start);
    }
    const digits = intEnd - start - (s.charCodeAt(start) === 45 ? 1 : 0);
    if (digits > 16) fail("NUMBER_OUT_OF_SAFE_RANGE", start);
    const n = Number(s.slice(start, intEnd));
    if (!Number.isSafeInteger(n)) fail("NUMBER_OUT_OF_SAFE_RANGE", start);
    return n === 0 ? 0 : n; // "-0" is the integer 0 for Python as well
  }
}

/** Strict UTF-8 -> text. Invalid sequences throw; a BOM is kept (U+FEFF), not dropped. */
export function decodeStrictUtf8(bytes: Uint8Array): string | null {
  try {
    return new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes);
  } catch {
    return null;
  }
}

/** Strict reading of a raw JSON text. */
export function parseStrictJsonText(text: string): StrictJsonResult {
  try {
    return { ok: true, value: new Reader(text).parseDocument() };
  } catch (error) {
    if (error instanceof StrictJsonFailure) return { ok: false, code: error.code, offset: error.offset };
    // Fail closed on anything unexpected (for instance a stack limit).
    return { ok: false, code: "INVALID_JSON", offset: null };
  }
}

/** Raw response bytes -> value, with the byte bound enforced first. */
export function readStrictJson(bytes: Uint8Array, maxBytes = MARKET_FLOW_MAX_RESPONSE_BYTES): StrictJsonResult {
  if (bytes.length > maxBytes) return { ok: false, code: "BYTES_TOO_LARGE", offset: null };
  const text = decodeStrictUtf8(bytes);
  if (text === null) return { ok: false, code: "INVALID_UTF8", offset: null };
  return parseStrictJsonText(text);
}
