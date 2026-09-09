// ── ObservedValue — canonical null/unknown-semantics wrapper ────────────────
// Mirrors observability/operator/contracts.py::ObservedValue.to_dict().
// React never reinterprets or upgrades these semantics.

export type NullSemantics =
  | "PRESENT"
  | "ZERO"
  | "FALSE"
  | "EMPTY"
  | "UNKNOWN"
  | "UNAVAILABLE"
  | "STALE"
  | "NOT_APPLICABLE";

const KNOWN_SEMANTICS: ReadonlySet<string> = new Set([
  "PRESENT",
  "ZERO",
  "FALSE",
  "EMPTY",
  "UNKNOWN",
  "UNAVAILABLE",
  "STALE",
  "NOT_APPLICABLE",
]);

export interface ObservedValue<T = unknown> {
  value: T | null;
  semantics: NullSemantics;
}

/** True only for a well-formed ObservedValue with a recognized semantics tag. */
export function isObservedValue(x: unknown): x is ObservedValue {
  if (x === null || typeof x !== "object") return false;
  const o = x as Record<string, unknown>;
  return "semantics" in o && "value" in o;
}

export function isKnownSemantics(s: unknown): s is NullSemantics {
  return typeof s === "string" && KNOWN_SEMANTICS.has(s);
}
