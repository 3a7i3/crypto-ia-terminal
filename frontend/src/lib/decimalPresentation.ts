/** Decimal-string formatting only: never converts canonical financial values to Number. */
export function formatDecimalText(value: string, digits = 2): string {
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value);
  if (
    !match ||
    value.length > 1024 ||
    !Number.isInteger(digits) ||
    digits < 0 ||
    digits > 8
  )
    return value;
  const [, sign, whole, fraction = ""] = match;
  const nonzero = /[1-9]/.test(whole + fraction);
  const wholeZero = !/[1-9]/.test(whole);
  const kept = fraction.slice(0, digits).padEnd(digits, "0");
  if (nonzero && wholeZero && !/[1-9]/.test(kept)) {
    const bound = digits ? `0,${"0".repeat(digits - 1)}1` : "1";
    return sign ? `> −${bound}` : `< ${bound}`;
  }
  let scaled = BigInt(whole + kept);
  if (fraction.length > digits && fraction[digits] >= "5") scaled += 1n;
  const numeric = scaled.toString().padStart(digits + 1, "0");
  const integer = (digits ? numeric.slice(0, -digits) : numeric).replace(
    /\B(?=(\d{3})+(?!\d))/g,
    "\u202f",
  );
  const decimals = digits ? `,${numeric.slice(-digits)}` : "";
  const approximate = /[1-9]/.test(fraction.slice(digits));
  return `${approximate ? "≈ " : ""}${sign && nonzero ? "−" : ""}${integer}${decimals}`;
}
