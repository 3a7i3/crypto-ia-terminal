import { describe, expect, it } from "vitest";
import {
  PYTHON_NONPRINTABLE_RANGES, codePointLength, decAdd, decCompare, decDivModPositive, decEquals, decIsZero,
  decSub, isContractText, isPythonPrintable, isSafeCounter, parseDecimal, parseNs,
} from "../lib/marketFlowExact";

const d = (x: string, signed = true) => {
  const v = parseDecimal(x, signed);
  if (v === null) throw new Error("unparsable " + x);
  return v;
};

describe("nanosecond text grammar (same as the Python regexes, ASCII only)", () => {
  it.each(["0", "1", "10", "999999999999999999999999999999", "9007199254740993", "1".padEnd(30, "0")])("accepts %s", v => {
    expect(parseNs(v)).toBe(BigInt(v));
  });
  it.each(["", "01", "-1", "+1", "1e3", "1.0", " 1", "1 ", "1\n", "\u0663", "9".repeat(31), "0x1", "NaN"])("refuses %j", v => {
    expect(parseNs(v)).toBeNull();
  });
  it("refuses non-strings, including numbers a client may have parsed", () => {
    for (const v of [1, 0, null, undefined, true, ["1"], { a: 1 }, 10n]) expect(parseNs(v)).toBeNull();
  });
  it("accepts a sign only where the contract allows it", () => {
    expect(parseNs("-5", true)).toBe(-5n);
    expect(parseNs("-0", true)).toBe(0n);
    expect(parseNs("-05", true)).toBeNull();
    expect(parseNs("-1")).toBeNull();
  });
});

describe("decimal text grammar and exact arithmetic", () => {
  it.each(["0", "0.0", "00", "007.500", "1", "125.5", "9".repeat(125), "9".repeat(125) + "." + "9".repeat(125), "0.10"])("accepts %s", v => {
    expect(parseDecimal(v)).not.toBeNull();
  });
  it.each(["", ".5", "5.", "1e5", "1E5", "NaN", "Infinity", "-1", "+1", "1,5", "1 .5", "\u0663", "1.5\n", "9".repeat(126),
    "1." + "9".repeat(126), "0x10", "--1", "1.2.3"])("refuses %j (unsigned)", v => {
    expect(parseDecimal(v)).toBeNull();
  });
  it("accepts a minus only for signed fields and refuses a double sign", () => {
    expect(parseDecimal("-1.5", true)).not.toBeNull();
    expect(parseDecimal("-1.5", false)).toBeNull();
    expect(parseDecimal("--1", true)).toBeNull();
    expect(parseDecimal("-", true)).toBeNull();
  });
  it("compares numerically whatever the spelling, without rewriting the text", () => {
    expect(decEquals(d("0.10"), d("0.1"))).toBe(true);
    expect(decEquals(d("007.500"), d("7.5"))).toBe(true);
    expect(decEquals(d("-0.0"), d("0"))).toBe(true);
    expect(decCompare(d("0.1"), d("0.09"))).toBe(1);
    expect(decCompare(d("-3"), d("-2.9999999999999999999"))).toBe(-1);
    expect(decIsZero(d("-0.000"))).toBe(true);
  });
  it("adds and subtracts exactly where binary floating point cannot", () => {
    expect(0.1 + 0.2).not.toBe(0.3);
    expect(decEquals(decAdd(d("0.1"), d("0.2")), d("0.3"))).toBe(true);
    const big = "9".repeat(125) + "." + "9".repeat(125);
    expect(decEquals(decSub(decAdd(d(big), d("0.000000000001")), d(big)), d("0.000000000001"))).toBe(true);
    expect(decEquals(decSub(d("1.0000000000000000001"), d("1")), d("0.0000000000000000001"))).toBe(true);
  });
  it("divides like Python divmod for the heatmap row count", () => {
    expect(decDivModPositive(d("6"), d("0.5"))).toEqual({ whole: 12n, hasRest: false });
    expect(decDivModPositive(d("6.1"), d("0.5"))).toEqual({ whole: 12n, hasRest: true });
    expect(decDivModPositive(d("0.3"), d("0.1"))).toEqual({ whole: 3n, hasRest: false });
  });
  it("refuses an out-of-bound lexeme before any BigInt work", () => {
    const huge = "9".repeat(2_000_000);
    const t0 = performance.now();
    expect(parseDecimal(huge)).toBeNull();
    expect(parseNs(huge)).toBeNull();
    expect(performance.now() - t0).toBeLessThan(500);
  });
});

describe("Python text rules (CPython 3.11 / Unicode 14.0.0 table)", () => {
  it("has a well-formed table: sorted, disjoint, non-adjacent, inclusive pairs", () => {
    const t = PYTHON_NONPRINTABLE_RANGES;
    expect(t.length % 2).toBe(0);
    for (let i = 0; i < t.length; i += 2) {
      expect(t[i]).toBeLessThanOrEqual(t[i + 1]);
      if (i > 0) expect(t[i]).toBeGreaterThan(t[i - 1] + 1);
    }
    expect(t[t.length - 1]).toBe(0x10ffff);
  });
  it.each([["abc", true], ["", true], [" ", true], ["~", true], ["\u00e9", true], ["\u20ac", true], ["\u{1F600}", true], ["\u3042", true],
    ["\t", false], ["\n", false], ["\x00", false], ["\x7f", false], ["\x9f", false], ["\u00a0", false], ["\u00ad", false],
    ["\u200b", false], ["\u2028", false], ["\u2029", false], ["\u3000", false], ["\ufeff", false], ["\u0378", false],
    ["\ud800", false], ["\udfff", false], ["\ue000", false], ["\u{10ffff}", false], ["\u{E0001}", false]] as const)(
    "isprintable(%j) = %s", (s, want) => {
      expect(isPythonPrintable(s)).toBe(want);
    });
  it("counts code points like Python len(), including non-BMP and lone surrogates", () => {
    expect(codePointLength("")).toBe(0);
    expect(codePointLength("abc")).toBe(3);
    expect(codePointLength("\u{1F600}")).toBe(1);
    expect("\u{1F600}".length).toBe(2);
    expect(codePointLength("a\u{1F600}b\u00e9")).toBe(4);
    expect(codePointLength("\ud800")).toBe(1);
    expect(codePointLength("\ud800\ud800")).toBe(2);
  });
  it("applies the contract length bound in code points, not UTF-16 units", () => {
    expect(isContractText("\u{1F600}".repeat(512))).toBe(true);
    expect(isContractText("\u{1F600}".repeat(513))).toBe(false);
    expect(isContractText("a".repeat(513))).toBe(false);
    expect(isContractText("a".repeat(64), 64)).toBe(true);
    expect(isContractText("a".repeat(65), 64)).toBe(false);
    expect(isContractText("")).toBe(false);
    expect(isContractText("ok\n")).toBe(false);
    expect(isContractText(5)).toBe(false);
  });
});

describe("JSON counters", () => {
  it("accepts safe non-negative integers only, never a boolean", () => {
    expect(isSafeCounter(0)).toBe(true);
    expect(isSafeCounter(Number.MAX_SAFE_INTEGER)).toBe(true);
    for (const v of [-1, 1.5, 2 ** 53, Number.NaN, Infinity, true, false, "1", null, undefined, 1n]) expect(isSafeCounter(v)).toBe(false);
    expect(isSafeCounter(0, 1)).toBe(false);
    expect(isSafeCounter(5, 0, 4)).toBe(false);
  });
});
