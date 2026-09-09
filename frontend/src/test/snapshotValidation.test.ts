import { describe, it, expect } from "vitest";
import { validateOperatorSnapshot } from "../lib/snapshotValidation";
import { baseSnapshot } from "./fixtures";

describe("validateOperatorSnapshot — Correction B runtime boundary", () => {
  it("accepts a well-formed snapshot", () => {
    expect(validateOperatorSnapshot(baseSnapshot())).toBe(true);
  });

  it("rejects portfolio: null", () => {
    const snap = baseSnapshot();
    (snap as unknown as Record<string, unknown>).portfolio = null;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects decision_pipeline: [] (array instead of object)", () => {
    const snap = baseSnapshot();
    (snap as unknown as Record<string, unknown>).decision_pipeline = [];
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it('rejects system_health: "healthy" (string instead of object)', () => {
    const snap = baseSnapshot();
    (snap as unknown as Record<string, unknown>).system_health = "healthy";
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects open_positions with PRESENT semantics but a null value", () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = { semantics: "PRESENT", value: null } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects per_symbol_decisions: {} (object instead of array)", () => {
    const snap = baseSnapshot();
    (snap.decision_pipeline as unknown as Record<string, unknown>).per_symbol_decisions = {};
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects stages that is not an array", () => {
    const snap = baseSnapshot();
    (snap.decision_pipeline as unknown as Record<string, unknown>).stages = "not-an-array";
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects module_statuses that is not a plain object", () => {
    const snap = baseSnapshot();
    (snap.system_health as unknown as Record<string, unknown>).module_statuses = [1, 2, 3];
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects an unrecognized portfolio.mode value", () => {
    const snap = baseSnapshot();
    (snap.portfolio as unknown as Record<string, unknown>).mode = "LIVE";
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects an unrecognized instance_relation value", () => {
    const snap = baseSnapshot();
    (snap as unknown as Record<string, unknown>).instance_relation = "SOMETHING_ELSE";
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects an unrecognized runtime_state value", () => {
    const snap = baseSnapshot();
    (snap as unknown as Record<string, unknown>).runtime_state = "STALE_FOREVER";
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects a contradictory ObservedValue field inside portfolio", () => {
    const snap = baseSnapshot();
    snap.portfolio.paper_equity_usd = { value: null, semantics: "PRESENT" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects a contradictory ObservedValue field inside system_health", () => {
    const snap = baseSnapshot();
    snap.system_health.boot_alive = { value: 1, semantics: "UNKNOWN" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects a per-symbol decision missing its authority tag", () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.per_symbol_decisions = [
      {
        symbol: "ETHUSDT",
        packet_id: null,
        context_id: null,
        created_cycle_id: null,
        created_at: { value: null, semantics: "UNKNOWN" },
        latest_transition_at_utc: { value: null, semantics: "UNKNOWN" },
        side: { value: null, semantics: "UNKNOWN" },
        confidence_raw: { value: null, semantics: "UNKNOWN" },
        confidence_adjusted: { value: null, semantics: "UNKNOWN" },
        regime: { value: null, semantics: "UNKNOWN" },
        lifecycle_state: { value: null, semantics: "UNKNOWN" },
        // missing `authority` — contradicts the contract's per-field tag requirement
        is_actionable: { value: false, semantics: "FALSE" } as never,
        trade_allowed: { value: null, semantics: "UNKNOWN", authority: "OBSERVATIONAL_TELEMETRY" },
        first_blocker: { value: null, semantics: "UNKNOWN", authority: "OBSERVATIONAL_TELEMETRY" },
      },
    ] as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects a non-object top-level response", () => {
    expect(validateOperatorSnapshot("not-an-object")).toBe(false);
    expect(validateOperatorSnapshot(null)).toBe(false);
    expect(validateOperatorSnapshot([1, 2, 3])).toBe(false);
  });
});
