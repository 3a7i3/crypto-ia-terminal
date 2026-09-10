// ── ObservedValue — canonical null/unknown-semantics wrapper ────────────────
// Mirrors observability/operator/contracts.py::ObservedValue.__post_init__'s
// invariant matrix (O-02W-D2-R1 Correction A) — not just key presence.
// React never reinterprets, repairs, or upgrades a contradictory value: a
// value/semantics pair that violates the matrix below is INVALID, full stop.

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

export function isKnownSemantics(s: unknown): s is NullSemantics {
  return typeof s === "string" && KNOWN_SEMANTICS.has(s);
}

function isPlainObject(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

/** A "sized" value in the sense the Python EMPTY/PRESENT rules use:
 * string, array, or plain object — never a Map/Set/etc, which the
 * canonical producer never emits over JSON anyway. */
function sizedLength(value: unknown): number | null {
  if (typeof value === "string") return value.length;
  if (Array.isArray(value)) return value.length;
  if (isPlainObject(value)) return Object.keys(value).length;
  return null;
}

function isGenuineNumericZero(value: unknown): boolean {
  return typeof value === "number" && value === 0;
}

/** Runtime validation matching the canonical Python ObservedValue invariant
 * matrix (O-02W-D2-R1 Correction A). A contradictory value/semantics
 * combination — e.g. {value: null, semantics: "PRESENT"} or
 * {value: 7, semantics: "ZERO"} — is INVALID, never repaired/reinterpreted. */
export function isObservedValue(x: unknown): x is ObservedValue {
  if (!isPlainObject(x)) return false;
  if (!("semantics" in x) || !("value" in x)) return false;

  const { value, semantics } = x as { value: unknown; semantics: unknown };
  if (!isKnownSemantics(semantics)) return false;

  switch (semantics) {
    case "PRESENT": {
      if (value === null) return false;
      if (value === false) return false;
      if (isGenuineNumericZero(value)) return false;
      const len = sizedLength(value);
      if (len === 0) return false;
      return true;
    }
    case "ZERO":
      return isGenuineNumericZero(value);
    case "FALSE":
      // Identity, not equality: 0 !== false here.
      return value === false;
    case "EMPTY": {
      if (value === null) return false;
      const len = sizedLength(value);
      return len === 0;
    }
    case "UNKNOWN":
      return value === null;
    case "UNAVAILABLE":
      return value === null;
    case "NOT_APPLICABLE":
      return value === null;
    case "STALE":
      return value !== null;
    default:
      return false;
  }
}
