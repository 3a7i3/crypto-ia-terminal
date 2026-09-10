// ── ObservedValueView — reusable presentation for ObservedValue fields ──────
//
// Rules enforced here (mission O-02W-D2):
// - ZERO/FALSE/EMPTY are genuine observations, never shown as "missing".
// - UNKNOWN/UNAVAILABLE/NOT_APPLICABLE are never displayed as numeric zero.
// - STALE carries its last-known value but is always visibly marked stale.
// - An unrecognized semantics value fails visibly and safely (never crashes
//   the cockpit, never silently maps to a healthy-looking state).

import React from "react";
import { isKnownSemantics, isObservedValue } from "../lib/observedValue";

export interface ObservedValueViewProps {
  ov: unknown;
  /** Optional custom renderer for the raw value when present/zero/false/stale. */
  render?: (value: unknown) => React.ReactNode;
  className?: string;
}

export const ObservedValueView: React.FC<ObservedValueViewProps> = ({ ov, render, className }) => {
  if (!isObservedValue(ov)) {
    return (
      <span className={`ov ov-invalid ${className ?? ""}`} data-testid="ov-invalid">
        INVALID_OBSERVED_VALUE
      </span>
    );
  }

  const { value, semantics } = ov;
  const show = (v: unknown) => (render ? render(v) : String(v));

  if (!isKnownSemantics(semantics)) {
    return (
      <span className={`ov ov-invalid ${className ?? ""}`} data-testid="ov-invalid">
        UNKNOWN_SEMANTICS({String(semantics)})
      </span>
    );
  }

  switch (semantics) {
    case "PRESENT":
      return (
        <span className={`ov ov-present ${className ?? ""}`} data-testid="ov-present">
          {show(value)}
        </span>
      );
    case "ZERO":
      return (
        <span className={`ov ov-zero ${className ?? ""}`} data-testid="ov-zero">
          {show(value)}
        </span>
      );
    case "FALSE":
      return (
        <span className={`ov ov-false ${className ?? ""}`} data-testid="ov-false">
          {render ? render(false) : "false"}
        </span>
      );
    case "EMPTY":
      return (
        <span className={`ov ov-empty ${className ?? ""}`} data-testid="ov-empty">
          (empty)
        </span>
      );
    case "UNKNOWN":
      return (
        <span className={`ov ov-unknown ${className ?? ""}`} data-testid="ov-unknown">
          UNKNOWN
        </span>
      );
    case "UNAVAILABLE":
      return (
        <span className={`ov ov-unavailable ${className ?? ""}`} data-testid="ov-unavailable">
          UNAVAILABLE
        </span>
      );
    case "NOT_APPLICABLE":
      return (
        <span className={`ov ov-na ${className ?? ""}`} data-testid="ov-not-applicable">
          NOT_APPLICABLE
        </span>
      );
    case "STALE":
      return (
        <span className={`ov ov-stale ${className ?? ""}`} data-testid="ov-stale">
          {show(value)} <span data-testid="ov-stale-badge">⚠ STALE</span>
        </span>
      );
    default:
      // Unreachable given isKnownSemantics(), kept for exhaustiveness safety.
      return (
        <span className={`ov ov-invalid ${className ?? ""}`} data-testid="ov-invalid">
          UNKNOWN_SEMANTICS
        </span>
      );
  }
};
