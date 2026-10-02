import { describe, expect, it } from "vitest";
import { formatDecimalText } from "../lib/decimalPresentation";

describe("financial decimal presentation preserves precision boundaries", () => {
  it.each([
    ["1001.863576581569075825468382", "≈ 1\u202f001,86"],
    [
      "999999999999999999999.995",
      "≈ 1\u202f000\u202f000\u202f000\u202f000\u202f000\u202f000\u202f000,00",
    ],
    ["0.0000000000224174531618", "< 0,01"],
    ["-0.0000000000224174531618", "> −0,01"],
    ["0", "0,00"],
    ["-0.000", "0,00"],
    ["-12.3", "−12,30"],
    ["999.999", "≈ 1\u202f000,00"],
    ["1.23000", "1,23"],
    ["NOT_AVAILABLE", "NOT_AVAILABLE"],
    ["1e-9", "1e-9"],
  ])("formats %s without a floating-point conversion", (input, output) => {
    expect(formatDecimalText(input)).toBe(output);
  });
  it("keeps unsupported precision and oversized source text unchanged", () => {
    expect(formatDecimalText("1.23", 9)).toBe("1.23");
    expect(formatDecimalText("1".repeat(1025))).toBe("1".repeat(1025));
  });
});
