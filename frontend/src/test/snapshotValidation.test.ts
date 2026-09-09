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

// ── O-02W-D2-R1.1 — final snapshot admission hardening ─────────────────────
// MASTER independently reproduced four admission holes on HEAD 29c1747:
// portfolio.status = {bad: true}, system_health.freshness = ["bad"],
// open_positions[].side = {bad: true}, and a contradictory confidence_raw
// — each previously returned `true`. Every case below must return `false`.

const validPosition = {
  position_id: "p1",
  symbol: "BTCUSDT",
  side: "long",
  size_usd: 100,
  entry_price: 50000,
  current_price: { value: 51000, semantics: "PRESENT" },
  current_price_observed_at_utc: "2026-09-09T00:00:00+00:00",
  tp_price: 52000,
  sl_price: 49000,
  tp_sl_source: "original",
  unrealized_pnl_usd: { value: 20, semantics: "PRESENT" },
  unrealized_pnl_pct: { value: 2, semantics: "PRESENT" },
  opened_at: "2026-09-08T00:00:00+00:00",
  regime: { value: "TREND_BULL", semantics: "PRESENT" },
  restored_without_regime: false,
  personality: "aggressive",
  restored: false,
};

const validDecision = {
  symbol: "ETHUSDT",
  packet_id: "pk1",
  context_id: "ctx1",
  created_cycle_id: "c1",
  created_at: { value: "2026-09-09T00:00:00+00:00", semantics: "PRESENT" },
  latest_transition_at_utc: { value: null, semantics: "UNKNOWN" },
  side: { value: "long", semantics: "PRESENT" },
  confidence_raw: { value: 0.8, semantics: "PRESENT" },
  confidence_adjusted: { value: 0.75, semantics: "PRESENT" },
  regime: { value: "TREND_BULL", semantics: "PRESENT" },
  lifecycle_state: { value: "APPROVED", semantics: "PRESENT" },
  is_actionable: { value: true, semantics: "PRESENT", authority: "EXECUTION_AUTHORITY" },
  trade_allowed: { value: false, semantics: "FALSE", authority: "OBSERVATIONAL_TELEMETRY" },
  first_blocker: { value: "risk_gate", semantics: "PRESENT", authority: "OBSERVATIONAL_TELEMETRY" },
};

describe("validateOperatorSnapshot — R1.1 domain spine (Correction A)", () => {
  it("case 1: portfolio.status = object -> false", () => {
    const snap = baseSnapshot();
    (snap.portfolio as unknown as Record<string, unknown>).status = { bad: true };
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 2: portfolio.status = invented string -> false", () => {
    const snap = baseSnapshot();
    (snap.portfolio as unknown as Record<string, unknown>).status = "TOTALLY_FINE";
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 3a: domain freshness = array -> false", () => {
    const snap = baseSnapshot();
    (snap.system_health as unknown as Record<string, unknown>).freshness = ["bad"];
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 3b: domain freshness = object -> false", () => {
    const snap = baseSnapshot();
    (snap.decision_pipeline as unknown as Record<string, unknown>).freshness = { bad: true };
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 3c: domain freshness = invented string -> false", () => {
    const snap = baseSnapshot();
    (snap.portfolio as unknown as Record<string, unknown>).freshness = "SUPER_FRESH";
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 4: incorrect domain ID -> false", () => {
    const snap = baseSnapshot();
    (snap.portfolio as unknown as Record<string, unknown>).domain = "decision_pipeline";
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });
});

describe("validateOperatorSnapshot — R1.1 open positions (Correction B)", () => {
  it("case 5: open_positions[].side = object -> false", () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = {
      semantics: "PRESENT",
      value: [{ ...validPosition, side: { bad: true } }],
    } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 6a: size_usd = object -> false", () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = {
      semantics: "PRESENT",
      value: [{ ...validPosition, size_usd: { bad: true } }],
    } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 6b: size_usd = string -> false", () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = {
      semantics: "PRESENT",
      value: [{ ...validPosition, size_usd: "100" }],
    } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 6c: size_usd = NaN/Infinity -> false", () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = {
      semantics: "PRESENT",
      value: [{ ...validPosition, size_usd: Infinity }],
    } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 7a: entry_price = object -> false", () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = {
      semantics: "PRESENT",
      value: [{ ...validPosition, entry_price: { bad: true } }],
    } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 7b: entry_price = string -> false", () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = {
      semantics: "PRESENT",
      value: [{ ...validPosition, entry_price: "50000" }],
    } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 7c: entry_price = NaN -> false", () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = {
      semantics: "PRESENT",
      value: [{ ...validPosition, entry_price: NaN }],
    } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 8: invalid tp_sl_source (blank string) -> false", () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = {
      semantics: "PRESENT",
      value: [{ ...validPosition, tp_sl_source: "   " }],
    } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 9: invalid restored_without_regime (non-boolean) -> false", () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = {
      semantics: "PRESENT",
      value: [{ ...validPosition, restored_without_regime: "false" }],
    } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 10: invalid personality (object) -> false", () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = {
      semantics: "PRESENT",
      value: [{ ...validPosition, personality: { bad: true } }],
    } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("accepts a fully valid open position", () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = { semantics: "PRESENT", value: [validPosition] } as never;
    expect(validateOperatorSnapshot(snap)).toBe(true);
  });
});

describe("validateOperatorSnapshot — R1.1 decision rows (Correction C)", () => {
  it("case 11: contradictory confidence_raw ({value: null, semantics: PRESENT}) -> false", () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.per_symbol_decisions = [
      { ...validDecision, confidence_raw: { value: null, semantics: "PRESENT" } },
    ] as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 12a: missing decision authority (is_actionable has no `authority` key) -> false", () => {
    const snap = baseSnapshot();
    const { authority: _drop, ...noAuthority } = validDecision.is_actionable;
    snap.decision_pipeline.per_symbol_decisions = [
      { ...validDecision, is_actionable: noAuthority },
    ] as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 12b: invalid decision authority (blank string) -> false", () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.per_symbol_decisions = [
      { ...validDecision, trade_allowed: { ...validDecision.trade_allowed, authority: "" } },
    ] as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects a malformed confidence_adjusted field", () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.per_symbol_decisions = [
      { ...validDecision, confidence_adjusted: { bad: true } },
    ] as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects a malformed created_at field", () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.per_symbol_decisions = [{ ...validDecision, created_at: "not-an-ov" }] as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("accepts a fully valid decision row", () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.per_symbol_decisions = [validDecision] as never;
    expect(validateOperatorSnapshot(snap)).toBe(true);
  });
});

describe("validateOperatorSnapshot — R1.1 top-level rendered primitives (Correction D)", () => {
  it("case 13a: cycle = object -> false", () => {
    const snap = baseSnapshot();
    (snap as unknown as Record<string, unknown>).cycle = { bad: true };
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 13b: cycle = negative -> false", () => {
    const snap = baseSnapshot({ cycle: -1 });
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 13c: cycle = non-integer -> false", () => {
    const snap = baseSnapshot({ cycle: 1.5 });
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 13d: snapshot_age_s = negative -> false", () => {
    const snap = baseSnapshot({ snapshot_age_s: -0.5 });
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 13e: snapshot_age_s = array -> false", () => {
    const snap = baseSnapshot();
    (snap as unknown as Record<string, unknown>).snapshot_age_s = [1];
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 13f: snapshot_id = blank string -> false", () => {
    const snap = baseSnapshot({ snapshot_id: "   " });
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 13g: generated_at_utc = object -> false", () => {
    const snap = baseSnapshot();
    (snap as unknown as Record<string, unknown>).generated_at_utc = { bad: true };
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 13h: freshness_classification = blank string -> false", () => {
    const snap = baseSnapshot({ freshness_classification: "" });
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 13i: stale_reason = object -> false", () => {
    const snap = baseSnapshot();
    (snap as unknown as Record<string, unknown>).stale_reason = { bad: true };
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 14: a fully valid canonical snapshot still passes", () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = { semantics: "PRESENT", value: [validPosition] } as never;
    snap.decision_pipeline.per_symbol_decisions = [validDecision] as never;
    expect(validateOperatorSnapshot(snap)).toBe(true);
  });
});

// ── O-02W-D2-R1.1 (second round) — Correction E + case-mismatch/padding ────
// MASTER's second pass also required a closed vocabulary for
// deployment_evidence.source and explicit rejection of case-mismatched /
// whitespace-padded alternatives to any closed-vocabulary field.

describe("validateOperatorSnapshot — Correction E (deployment-evidence consistency)", () => {
  it("case 17a: deployment_evidence.status = invented string -> false", () => {
    const snap = baseSnapshot();
    snap.deployment_evidence = { ...snap.deployment_evidence, status: "PARTIALLY_VERIFIED" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 17b: deployment_evidence.source = invented string -> false", () => {
    const snap = baseSnapshot();
    snap.deployment_evidence = { ...snap.deployment_evidence, source: "manual_ssh" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 17c: deployment_evidence.source = case-mismatched valid value -> false", () => {
    const snap = baseSnapshot();
    snap.deployment_evidence = { ...snap.deployment_evidence, source: "Deploy_Tag" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 17d: deployment_evidence.source = whitespace-padded valid value -> false", () => {
    const snap = baseSnapshot();
    snap.deployment_evidence = { ...snap.deployment_evidence, source: " deploy_tag " } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 17e: deployment_evidence.evidence_ref = blank string -> false", () => {
    const snap = baseSnapshot();
    snap.deployment_evidence = { ...snap.deployment_evidence, evidence_ref: "   " } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 17f: deployment_evidence.evidence_ref = object -> false", () => {
    const snap = baseSnapshot();
    snap.deployment_evidence = { ...snap.deployment_evidence, evidence_ref: { bad: true } } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("accepts deployment_evidence.source = null (unconfigured)", () => {
    const snap = baseSnapshot();
    snap.deployment_evidence = { ...snap.deployment_evidence, source: null };
    expect(validateOperatorSnapshot(snap)).toBe(true);
  });

  it.each(["deploy_tag", "deploy_audit", "post_deploy_verification"])(
    "accepts deployment_evidence.source = %s (closed vocabulary member)",
    (source) => {
      const snap = baseSnapshot();
      snap.deployment_evidence = { ...snap.deployment_evidence, source };
      expect(validateOperatorSnapshot(snap)).toBe(true);
    },
  );
});

describe("validateOperatorSnapshot — case-mismatch / whitespace-padding rejection", () => {
  it("rejects a lowercase portfolio.mode", () => {
    const snap = baseSnapshot();
    (snap.portfolio as unknown as Record<string, unknown>).mode = "paper";
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects a whitespace-padded portfolio.status", () => {
    const snap = baseSnapshot();
    (snap.portfolio as unknown as Record<string, unknown>).status = " DEGRADED ";
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects a lowercase domain freshness value", () => {
    const snap = baseSnapshot();
    (snap.system_health as unknown as Record<string, unknown>).freshness = "unknown";
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects a whitespace-padded instance_relation", () => {
    const snap = baseSnapshot();
    (snap as unknown as Record<string, unknown>).instance_relation = " CURRENT_INSTANCE ";
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });
});

describe("validateOperatorSnapshot — invalid decision identifiers (case 15)", () => {
  it("rejects a decision row with a blank symbol", () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.per_symbol_decisions = [{ ...validDecision, symbol: "   " }] as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects a decision row with a non-string packet_id", () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.per_symbol_decisions = [{ ...validDecision, packet_id: 12345 }] as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects a decision row with an object context_id", () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.per_symbol_decisions = [{ ...validDecision, context_id: { bad: true } }] as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("never relabels OBSERVATIONAL_TELEMETRY as EXECUTION_AUTHORITY (authority is validated, not normalized)", () => {
    const snap = baseSnapshot();
    const decisionWithTelemetryActionable = {
      ...validDecision,
      is_actionable: { value: true, semantics: "PRESENT", authority: "OBSERVATIONAL_TELEMETRY" },
    };
    snap.decision_pipeline.per_symbol_decisions = [decisionWithTelemetryActionable] as never;
    // The validator only checks that `authority` is a non-blank string — it
    // never inspects or rewrites its value, so this passes exactly as
    // supplied (the mission forbids relabeling, not merely rendering it).
    expect(validateOperatorSnapshot(snap)).toBe(true);
    expect(snap.decision_pipeline.per_symbol_decisions[0].is_actionable.authority).toBe(
      "OBSERVATIONAL_TELEMETRY",
    );
  });
});
