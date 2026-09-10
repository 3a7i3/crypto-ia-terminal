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

  // Corrected by O-02W-D2-R1.2 Correction C: the certified field mapping is
  // now enforced exactly (is_actionable.authority === EXECUTION_AUTHORITY),
  // never merely "any non-blank string". A snapshot labeling is_actionable
  // OBSERVATIONAL_TELEMETRY is rejected outright — the validator never
  // repairs or relabels it back to the correct value.
  it("case 16: rejects is_actionable labeled OBSERVATIONAL_TELEMETRY instead of EXECUTION_AUTHORITY", () => {
    const snap = baseSnapshot();
    const decisionWithTelemetryActionable = {
      ...validDecision,
      is_actionable: { value: true, semantics: "PRESENT", authority: "OBSERVATIONAL_TELEMETRY" },
    };
    snap.decision_pipeline.per_symbol_decisions = [decisionWithTelemetryActionable] as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });
});

// ── O-02W-D2-R1.2 — typed ObservedValue and authority hardening ────────────
// MASTER independently reproduced a further hole: `isObservedValue()`
// validates only the generic null-semantics matrix, not the generic type
// `T`, so a string `"false"` could satisfy a boolean field's PRESENT
// semantics and a string could satisfy a numeric field's PRESENT semantics.
// React then renders "false" as `true` via JS truthiness — a false-
// liveness / false-execution-authority presentation. Every case below must
// return `false`.

describe("validateOperatorSnapshot — R1.2 typed boolean fields (Correction A/B)", () => {
  it('case 1: boot_alive PRESENT "false" -> false', () => {
    const snap = baseSnapshot();
    snap.system_health.boot_alive = { value: "false", semantics: "PRESENT" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 2: boot_alive ZERO 0 -> false", () => {
    const snap = baseSnapshot();
    snap.system_health.boot_alive = { value: 0, semantics: "ZERO" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it('case 3: exchange_connectivity_healthy PRESENT "true" -> false', () => {
    const snap = baseSnapshot();
    snap.system_health.exchange_connectivity_healthy = { value: "true", semantics: "PRESENT" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 4: real_account_stale PRESENT 1 -> false", () => {
    const snap = baseSnapshot();
    snap.portfolio.real_account_stale = { value: 1, semantics: "PRESENT" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it('case 5: is_actionable PRESENT "false" -> false', () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.per_symbol_decisions = [
      { ...validDecision, is_actionable: { value: "false", semantics: "PRESENT", authority: "EXECUTION_AUTHORITY" } },
    ] as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it('case 6: trade_allowed PRESENT "true" -> false', () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.per_symbol_decisions = [
      {
        ...validDecision,
        trade_allowed: { value: "true", semantics: "PRESENT", authority: "OBSERVATIONAL_TELEMETRY" },
      },
    ] as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects aggregate decision_pipeline.trade_allowed carrying a string", () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.trade_allowed = { value: "true", semantics: "PRESENT" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("boolean ZERO/other-numeric non-null values are rejected for a boolean field", () => {
    const snap = baseSnapshot();
    snap.system_health.exchange_connectivity_healthy = { value: [], semantics: "PRESENT" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("positive: boolean FALSE (exact false) remains valid", () => {
    const snap = baseSnapshot();
    snap.system_health.exchange_connectivity_healthy = { value: false, semantics: "FALSE" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(true);
  });

  it("positive: boolean PRESENT true remains valid", () => {
    const snap = baseSnapshot();
    snap.system_health.exchange_connectivity_healthy = { value: true, semantics: "PRESENT" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(true);
  });

  it("positive: boolean STALE (true or false) remains valid", () => {
    const snap = baseSnapshot();
    snap.system_health.boot_alive = { value: true, semantics: "STALE" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(true);
    snap.system_health.boot_alive = { value: false, semantics: "STALE" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(true);
  });
});

describe("validateOperatorSnapshot — R1.2 typed numeric fields (Correction A/B)", () => {
  it("case 7a: paper_equity_usd carries a string -> false", () => {
    const snap = baseSnapshot();
    snap.portfolio.paper_equity_usd = { value: "1000", semantics: "PRESENT" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 7b: real_account_equity_usd carries a string -> false", () => {
    const snap = baseSnapshot();
    snap.portfolio.real_account_equity_usd = { value: "5000", semantics: "PRESENT" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 8a: capital_x_usd carries a boolean -> false", () => {
    const snap = baseSnapshot();
    snap.portfolio.capital_x_usd = { value: true, semantics: "PRESENT" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 8b: exchange_latency_ms carries a boolean -> false", () => {
    const snap = baseSnapshot();
    snap.system_health.exchange_latency_ms = { value: false, semantics: "FALSE" } as never;
    // FALSE is not a legal semantics for a numeric field's generic matrix
    // either way, but the typed check independently rejects the boolean
    // value regardless of which layer catches it first.
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 9a: confidence_raw STALE carries a string -> false", () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.per_symbol_decisions = [
      { ...validDecision, confidence_raw: { value: "0.8", semantics: "STALE" } },
    ] as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 9b: health_score STALE carries an object -> false", () => {
    const snap = baseSnapshot();
    snap.system_health.health_score = { value: { bad: true }, semantics: "STALE" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 9c: exchange_latency_ms STALE carries NaN-equivalent (non-finite) -> false", () => {
    const snap = baseSnapshot();
    snap.system_health.exchange_latency_ms = { value: Infinity, semantics: "STALE" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects OpenPosition.current_price carrying a string", () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = {
      semantics: "PRESENT",
      value: [{ ...validPosition, current_price: { value: "51000", semantics: "PRESENT" } }],
    } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("positive: numeric ZERO remains valid", () => {
    const snap = baseSnapshot();
    snap.portfolio.paper_equity_usd = { value: 0, semantics: "ZERO" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(true);
  });

  it("positive: numeric STALE with zero remains valid", () => {
    const snap = baseSnapshot();
    snap.system_health.health_score = { value: 0, semantics: "STALE" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(true);
  });

  it("positive: numeric PRESENT finite non-zero remains valid", () => {
    const snap = baseSnapshot();
    snap.portfolio.capital_x_usd = { value: 42.5, semantics: "PRESENT" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(true);
  });
});

describe("validateOperatorSnapshot — R1.2 typed string fields (Correction A/B)", () => {
  it("case 10a: side carries an object -> false", () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.per_symbol_decisions = [
      { ...validDecision, side: { value: { bad: true }, semantics: "PRESENT" } },
    ] as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 10b: regime carries a number -> false", () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.per_symbol_decisions = [
      { ...validDecision, regime: { value: 42, semantics: "PRESENT" } },
    ] as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 10c: health_level carries a number -> false", () => {
    const snap = baseSnapshot();
    snap.system_health.health_level = { value: 100, semantics: "PRESENT" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 10d: OpenPosition.regime carries an array -> false", () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = {
      semantics: "PRESENT",
      value: [{ ...validPosition, regime: { value: ["bad"], semantics: "PRESENT" } }],
    } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects aggregate decision_pipeline.first_blocker carrying a number", () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.first_blocker = { value: 1, semantics: "PRESENT" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("positive: string EMPTY remains valid where meaningful", () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.per_symbol_decisions = [
      { ...validDecision, regime: { value: "", semantics: "EMPTY" } },
    ] as never;
    expect(validateOperatorSnapshot(snap)).toBe(true);
  });

  it("positive: string STALE remains valid", () => {
    const snap = baseSnapshot();
    snap.system_health.health_level = { value: "DEGRADED_LAST_KNOWN", semantics: "STALE" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(true);
  });
});

describe("validateOperatorSnapshot — R1.2 typed list field (open_positions, Correction A/B)", () => {
  it('case 11: open_positions EMPTY "" -> false', () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = { semantics: "EMPTY", value: "" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 12: open_positions EMPTY {} -> false", () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = { semantics: "EMPTY", value: {} } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 13: open_positions PRESENT with a non-array (string) -> false", () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = { semantics: "PRESENT", value: "not-an-array" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("open_positions PRESENT with a non-array (object) -> false", () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = { semantics: "PRESENT", value: { bad: true } } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("open_positions STALE with a non-array -> false", () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = { semantics: "STALE", value: "not-an-array" } as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("positive: open_positions EMPTY [] remains valid", () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = { semantics: "EMPTY", value: [] } as never;
    expect(validateOperatorSnapshot(snap)).toBe(true);
  });

  it("positive: open_positions STALE with a valid array remains valid", () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = { semantics: "STALE", value: [validPosition] } as never;
    expect(validateOperatorSnapshot(snap)).toBe(true);
  });
});

describe("validateOperatorSnapshot — R1.2 authority contract (Correction C)", () => {
  it("case 14: invented authority -> false", () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.per_symbol_decisions = [
      { ...validDecision, is_actionable: { ...validDecision.is_actionable, authority: "SOMETHING_ELSE" } },
    ] as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 15: padded authority -> false", () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.per_symbol_decisions = [
      {
        ...validDecision,
        trade_allowed: { ...validDecision.trade_allowed, authority: " OBSERVATIONAL_TELEMETRY " },
      },
    ] as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 17: trade_allowed labeled EXECUTION_AUTHORITY instead of OBSERVATIONAL_TELEMETRY -> false", () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.per_symbol_decisions = [
      { ...validDecision, trade_allowed: { ...validDecision.trade_allowed, authority: "EXECUTION_AUTHORITY" } },
    ] as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("case 18: first_blocker labeled EXECUTION_AUTHORITY instead of OBSERVATIONAL_TELEMETRY -> false", () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.per_symbol_decisions = [
      { ...validDecision, first_blocker: { ...validDecision.first_blocker, authority: "EXECUTION_AUTHORITY" } },
    ] as never;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects a domain-level authority value outside the closed vocabulary", () => {
    const snap = baseSnapshot();
    (snap.portfolio as unknown as Record<string, unknown>).authority = "SOMETHING_ELSE";
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("rejects a numeric domain-level authority value", () => {
    const snap = baseSnapshot();
    (snap.system_health as unknown as Record<string, unknown>).authority = 1;
    expect(validateOperatorSnapshot(snap)).toBe(false);
  });

  it("positive: valid producer authority mappings remain valid", () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.per_symbol_decisions = [validDecision] as never;
    expect(validateOperatorSnapshot(snap)).toBe(true);
  });

  it("positive: DECISION_OUTCOME_EVIDENCE is a legal domain-level authority value", () => {
    const snap = baseSnapshot();
    (snap.system_health as unknown as Record<string, unknown>).authority = "DECISION_OUTCOME_EVIDENCE";
    expect(validateOperatorSnapshot(snap)).toBe(true);
  });
});

describe("validateOperatorSnapshot — R1.2 a complete canonical snapshot still passes", () => {
  it("accepts a fully valid canonical snapshot with typed fields and correct authority mapping", () => {
    const snap = baseSnapshot();
    snap.portfolio.open_positions = { semantics: "PRESENT", value: [validPosition] } as never;
    snap.decision_pipeline.per_symbol_decisions = [validDecision] as never;
    expect(validateOperatorSnapshot(snap)).toBe(true);
  });
});
