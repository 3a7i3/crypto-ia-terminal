import { describe, it, expect } from "vitest";
import { isObservedValue } from "../lib/observedValue";

describe("isObservedValue — strict invariant matrix (Correction A)", () => {
  const valid: Array<[string, unknown]> = [
    ["PRESENT number", { value: 42, semantics: "PRESENT" }],
    ["PRESENT string", { value: "btc", semantics: "PRESENT" }],
    ["PRESENT non-empty array", { value: [1, 2], semantics: "PRESENT" }],
    ["PRESENT non-empty object", { value: { a: 1 }, semantics: "PRESENT" }],
    ["ZERO genuine numeric zero", { value: 0, semantics: "ZERO" }],
    ["FALSE exact boolean false", { value: false, semantics: "FALSE" }],
    ["EMPTY empty string", { value: "", semantics: "EMPTY" }],
    ["EMPTY empty array", { value: [], semantics: "EMPTY" }],
    ["EMPTY empty object", { value: {}, semantics: "EMPTY" }],
    ["UNKNOWN null", { value: null, semantics: "UNKNOWN" }],
    ["UNAVAILABLE null", { value: null, semantics: "UNAVAILABLE" }],
    ["NOT_APPLICABLE null", { value: null, semantics: "NOT_APPLICABLE" }],
    ["STALE non-null number", { value: 7, semantics: "STALE" }],
    ["STALE non-null false", { value: false, semantics: "STALE" }],
    ["STALE non-null empty array", { value: [], semantics: "STALE" }],
    ["STALE non-null array of positions", { value: [{ symbol: "BTCUSDT" }], semantics: "STALE" }],
  ];

  it.each(valid)("accepts %s", (_label, candidate) => {
    expect(isObservedValue(candidate)).toBe(true);
  });

  const invalid: Array<[string, unknown]> = [
    ["PRESENT with null value", { value: null, semantics: "PRESENT" }],
    ["PRESENT with numeric zero", { value: 0, semantics: "PRESENT" }],
    ["PRESENT with boolean false", { value: false, semantics: "PRESENT" }],
    ["PRESENT with empty array", { value: [], semantics: "PRESENT" }],
    ["PRESENT with empty string", { value: "", semantics: "PRESENT" }],
    ["ZERO with non-zero number", { value: 7, semantics: "ZERO" }],
    ["ZERO with boolean false", { value: false, semantics: "ZERO" }],
    ["ZERO with null", { value: null, semantics: "ZERO" }],
    ["FALSE with numeric zero", { value: 0, semantics: "FALSE" }],
    ["FALSE with true", { value: true, semantics: "FALSE" }],
    ["FALSE with null", { value: null, semantics: "FALSE" }],
    ["EMPTY with non-empty array", { value: ["x"], semantics: "EMPTY" }],
    ["EMPTY with null", { value: null, semantics: "EMPTY" }],
    ["EMPTY with a number", { value: 0, semantics: "EMPTY" }],
    ["UNKNOWN with a value", { value: 99, semantics: "UNKNOWN" }],
    ["UNAVAILABLE with a value", { value: "x", semantics: "UNAVAILABLE" }],
    ["NOT_APPLICABLE with a value", { value: false, semantics: "NOT_APPLICABLE" }],
    ["STALE with null", { value: null, semantics: "STALE" }],
    ["unknown semantics tag", { value: 1, semantics: "TOTALLY_INVENTED" }],
    ["missing semantics key", { value: 1 }],
    ["missing value key", { semantics: "PRESENT" }],
    ["array instead of object", [{ value: 1, semantics: "PRESENT" }]],
    ["null envelope", null],
    ["primitive envelope", "not-an-object"],
  ];

  it.each(invalid)("rejects %s", (_label, candidate) => {
    expect(isObservedValue(candidate)).toBe(false);
  });
});
