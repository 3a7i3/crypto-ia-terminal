import { describe, expect, it } from "vitest";
import {
  MARKET_FLOW_MAX_JSON_DEPTH, MARKET_FLOW_MAX_RESPONSE_BYTES, parseStrictJsonText, readStrictJson,
} from "../lib/marketFlowJson";

const enc = (s: string) => new TextEncoder().encode(s);
const ok = (s: string) => {
  const r = parseStrictJsonText(s);
  if (!r.ok) throw new Error("refused " + s + ": " + r.code);
  return r.value;
};
const refused = (s: string) => {
  const r = parseStrictJsonText(s);
  return r.ok ? null : r.code;
};

describe("strict raw JSON reading", () => {
  it("reads ordinary documents like JSON.parse does", () => {
    const text = '{"a":[1,2,{"b":null}],"c":"x","d":true,"e":false,"f":0,"g":-7}';
    expect(ok(text)).toEqual(JSON.parse(text));
    expect(ok(" \n\t\r[ ]\r\n ")).toEqual([]);
    expect(ok("{}")).toEqual({});
  });

  it("refuses a duplicate key, including one hidden by an escape", () => {
    expect(refused('{"a":1,"a":2}')).toBe("DUPLICATE_KEY");
    expect(refused('{"a":1,"\\u0061":2}')).toBe("DUPLICATE_KEY");
    expect(refused('{"x":{"a":1,"a":1}}')).toBe("DUPLICATE_KEY");
    expect(refused('{"\\ud83d\\ude00":1,"\u{1F600}":2}')).toBe("DUPLICATE_KEY");
    expect(ok('{"a":1,"b":{"a":2}}')).toEqual({ a: 1, b: { a: 2 } }); // the same key at another node is fine
  });

  it.each([["1.0"], ["1e0"], ["1E2"], ["0.5"], ["-1.5e-3"], ["1e400"]])("refuses the float lexeme %s", n => {
    expect(refused('{"n":' + n + "}")).toBe("NUMBER_NOT_INTEGER");
  });
  it.each([["9007199254740992"], ["9007199254740993"], ["-9007199254740993"], ["123456789012345678901234567890"]])(
    "refuses the integer %s beyond the safe range", n => {
      expect(refused("[" + n + "]")).toBe("NUMBER_OUT_OF_SAFE_RANGE");
    });
  it("keeps safe integers, normalising -0 to 0 like Python does", () => {
    expect(ok("[9007199254740991,-9007199254740991,0]")).toEqual([9007199254740991, -9007199254740991, 0]);
    const v = ok("[-0]") as number[];
    expect(Object.is(v[0], 0)).toBe(true);
  });
  it.each(["NaN", "Infinity", "-Infinity", "undefined", "+1", "01", "-", "1.", ".5", "0x10", "'a'", "{'a':1}", "[1,]", "{\"a\":1,}",
    "[1 2]", "", "   ", "[", "{\"a\"}", "{\"a\":}", "{1:2}", "tru", "nul", "[1]x", "[1][1]", "// c\n[1]", "[1]/*c*/"])("refuses malformed text %j", t => {
    expect(refused(t)).not.toBeNull();
  });
  it("refuses control characters and bad escapes in strings", () => {
    expect(refused('"\t"')).toBe("INVALID_JSON");
    expect(refused('"\n"')).toBe("INVALID_JSON");
    expect(refused('"\\x41"')).toBe("INVALID_JSON");
    expect(refused('"\\u12"')).toBe("INVALID_JSON");
    expect(refused('"\\')).toBe("INVALID_JSON");
    expect(refused('"abc')).toBe("INVALID_JSON");
  });
  it("decodes escapes exactly and never rewrites a string", () => {
    expect(ok('"\\u0041\\/\\n\\\\\\""')).toBe('A/\n\\"');
    expect(ok('"\\ud83d\\ude00"')).toBe("\u{1F600}");
    expect(ok('"\\ud800"')).toBe("\ud800"); // a lone surrogate survives; the text rules refuse it later
    expect(ok('"\u00e9\u{1F600}"')).toBe("\u00e9\u{1F600}");
    expect(ok('"  0.10  "')).toBe("  0.10  ");
  });
  it("treats __proto__ as an ordinary own key, never as a prototype", () => {
    const v = ok('{"__proto__":{"polluted":true},"a":1}') as Record<string, unknown>;
    expect(Object.keys(v)).toEqual(["__proto__", "a"]);
    expect(Object.getPrototypeOf(v)).toBe(Object.prototype);
    expect(({} as Record<string, unknown>).polluted).toBeUndefined();
  });
  it("bounds the nesting depth", () => {
    const depth = (n: number) => "[".repeat(n) + "]".repeat(n);
    expect(refused(depth(MARKET_FLOW_MAX_JSON_DEPTH))).toBeNull();
    expect(refused(depth(MARKET_FLOW_MAX_JSON_DEPTH + 1))).toBe("DEPTH_EXCEEDED");
    expect(refused(depth(100000))).toBe("DEPTH_EXCEEDED");
    expect(refused('{"a":'.repeat(MARKET_FLOW_MAX_JSON_DEPTH + 1) + "1" + "}".repeat(MARKET_FLOW_MAX_JSON_DEPTH + 1))).toBe("DEPTH_EXCEEDED");
  });
});

describe("strict bytes", () => {
  it("decodes strict UTF-8 and keeps non-BMP text", () => {
    const r = readStrictJson(enc('{"t":"\u00e9\u{1F600}"}'));
    expect(r).toEqual({ ok: true, value: { t: "\u00e9\u{1F600}" } });
  });
  it("refuses invalid UTF-8: stray byte, overlong form, encoded surrogate, truncated sequence", () => {
    const wrap = (mid: number[]) => new Uint8Array([0x5b, 0x22, ...mid, 0x22, 0x5d]);
    for (const mid of [[0xff], [0xc0, 0xaf], [0xed, 0xa0, 0x80], [0xe2, 0x82], [0xf5, 0x80, 0x80, 0x80], [0x80]]) {
      const r = readStrictJson(wrap(mid));
      expect(r).toMatchObject({ ok: false, code: "INVALID_UTF8" });
    }
  });
  it("does not let a decoder swallow a byte-order mark", () => {
    const body = enc('{"a":1}');
    const withBom = new Uint8Array([0xef, 0xbb, 0xbf, ...body]);
    expect(readStrictJson(withBom)).toMatchObject({ ok: false, code: "INVALID_JSON" });
    expect(readStrictJson(body)).toMatchObject({ ok: true });
  });
  it("enforces the byte bound before decoding", () => {
    expect(MARKET_FLOW_MAX_RESPONSE_BYTES).toBe(4_001_024);
    const big = new Uint8Array(MARKET_FLOW_MAX_RESPONSE_BYTES + 1).fill(32);
    expect(readStrictJson(big)).toMatchObject({ ok: false, code: "BYTES_TOO_LARGE" });
    const edge = new Uint8Array(MARKET_FLOW_MAX_RESPONSE_BYTES).fill(32);
    edge.set(enc("[]"), 0);
    expect(readStrictJson(edge)).toEqual({ ok: true, value: [] });
    expect(readStrictJson(enc("[1,2,3]"), 3)).toMatchObject({ code: "BYTES_TOO_LARGE" });
  });
  it("reads a document at the bound in bounded time", () => {
    const item = '{"index":0,"status":"NOT_COVERED","trade_count":null},';
    const text = "[" + item.repeat(Math.floor(3_900_000 / item.length)) + "null]";
    const bytes = enc(text);
    expect(bytes.length).toBeLessThanOrEqual(MARKET_FLOW_MAX_RESPONSE_BYTES);
    const t0 = performance.now();
    const r = readStrictJson(bytes);
    const ms = performance.now() - t0;
    expect(r.ok).toBe(true);
    expect(ms).toBeLessThan(5_000);
    console.info("[market-flow] strict read of %d bytes: %s ms", bytes.length, ms.toFixed(0));
  });
});
