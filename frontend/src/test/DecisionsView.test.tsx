import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { DecisionsView } from "../views/DecisionsView";
import { baseSnapshot } from "./fixtures";

describe("DecisionsView", () => {
  it("renders is_actionable exactly as supplied, with its EXECUTION_AUTHORITY label", () => {
    const snap = baseSnapshot();
    snap.decision_pipeline.per_symbol_decisions = [
      {
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
      },
    ];

    render(<DecisionsView snapshot={snap} />);
    const row = screen.getByTestId("decision-row");
    expect(row).toHaveTextContent("ETHUSDT");
    expect(row).toHaveTextContent("true");

    const authorityTags = screen.getAllByTestId("authority-tag");
    expect(authorityTags.some((t) => t.getAttribute("data-authority") === "EXECUTION_AUTHORITY")).toBe(true);
    expect(authorityTags.some((t) => t.getAttribute("data-authority") === "OBSERVATIONAL_TELEMETRY")).toBe(true);
  });

  it("displays UNKNOWN honestly for an UNKNOWN aggregate trade_allowed, never a fabricated value", () => {
    render(<DecisionsView snapshot={baseSnapshot()} />);
    expect(screen.getByTestId("decisions-view")).toHaveTextContent("UNKNOWN");
  });

  it("computes no execution rate / rejection rate / win rate numeric field from the rows", () => {
    render(<DecisionsView snapshot={baseSnapshot()} />);
    expect(screen.queryByTestId("execution-rate")).toBeNull();
    expect(screen.queryByTestId("rejection-rate")).toBeNull();
    expect(screen.queryByTestId("win-rate")).toBeNull();
  });
});
