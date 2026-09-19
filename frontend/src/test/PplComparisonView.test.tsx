import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { PplComparisonView } from "../views/PplComparisonView";

function response(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

function snapshot(active = true) {
  const comparisons = active
    ? [
        {
          comparison_id: "web02-cash",
          domain: "accounting",
          field: "free_cash",
          trade_id: null,
          classification: "COMPARABLE",
          relation: "DIFFERENT",
          legacy: { value: 678.46, status: "PRESENT", provenance: "MEXC_SIM._capital" },
          ppl: { value: 678.4625, status: "PRESENT", provenance: "PPL.projection.available_cash" },
          delta_ppl_minus_legacy: 0.0025,
          comparison_rule: "numeric_abs_tol_1e-9",
          note: "Raw accounting divergence.",
        },
        {
          comparison_id: "web02-fees",
          domain: "accounting",
          field: "fees_paid",
          trade_id: null,
          classification: "UNRESOLVED",
          relation: "NOT_COMPARABLE",
          legacy: { value: null, status: "UNRESOLVED", provenance: "legacy lacks exit-fee evidence" },
          ppl: { value: 0.02, status: "PRESENT", provenance: "PPL.projection.fees_paid" },
          delta_ppl_minus_legacy: null,
          comparison_rule: "exact",
          note: "UNKNOWN != ZERO.",
        },
      ]
    : [];

  return {
    schema_version: "1.0.0",
    product: "PPLComparator",
    domain: "ppl_comparison",
    authority: "OBSERVATIONAL_TELEMETRY",
    mode: "SHADOW_COMPARISON",
    generated_at_utc: "2026-09-18T01:00:00Z",
    process_instance_id: "proc-1",
    cycle: 42,
    source_sha: "a".repeat(40),
    shadow_status: active ? "ACTIVE" : "OFF",
    paper_epoch_id: active ? "epoch-1" : null,
    comparison_available: active,
    comparison_unavailable_reason: active ? null : "PPL SHADOW is OFF; convergence must not be inferred.",
    legacy_source: { source: "MEXC_SIM", authority: "PAPER_AUTHORITY", scope: "live_process_state" },
    ppl_source: { source: "PPL", authority: "NONE", scope: "configured_shadow_epoch", last_error: null },
    legacy_quiescence: {
      pending_order_count: { value: 0, status: "PRESENT", provenance: "MEXC_SIM._orders where status=PENDING" },
      lifecycle_transitions_in_flight: { value: 0, status: "PRESENT", provenance: "MEXC_SIM._legacy_transitions_in_flight" },
      admissions_state: { value: null, status: "UNRESOLVED", provenance: "No canonical Legacy lifecycle admission-freeze state is materialized by the running process." },
      generation: { value: 0, status: "PRESENT", provenance: "MEXC_SIM._legacy_generation" },
    },
    summary: {
      total: comparisons.length,
      comparable: active ? 1 : 0,
      partial: 0,
      unresolved: active ? 1 : 0,
      equal: 0,
      different: active ? 1 : 0,
      legacy_only: 0,
      ppl_only: 0,
      not_comparable: active ? 1 : 0,
    },
    comparisons,
    positions: [],
    closed_session: [],
    ppl_events: active
      ? [
          {
            event_id: "evt-1",
            sequence: 1,
            event_type: "EPOCH_CREATED",
            trade_id: null,
            decision_id: null,
            timestamp: 1789693200,
            payload: {},
          },
        ]
      : [],
    snapshot_age_s: 12,
    freshness_classification: "FRESH",
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("PplComparisonView", () => {
  it("renders raw legacy/PPL values and producer-authored delta", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(snapshot())));
    render(<PplComparisonView />);

    await waitFor(() => expect(screen.getByText("Legacy PAPER ⇄ PPL")).toBeInTheDocument());
    const view = screen.getByTestId("ppl-comparison-view");
    expect(view).toHaveTextContent("678.46");
    expect(view).toHaveTextContent("678.4625");
    expect(view).toHaveTextContent("0.0025");
    expect(view).toHaveTextContent("DIFFERENT");
    expect(view).toHaveTextContent("UNRESOLVED");
    expect(view).toHaveTextContent("UNKNOWN != ZERO");
    expect(view).toHaveTextContent("PAPER_AUTHORITY");
    expect(view).toHaveTextContent("NONE");
  });

  it("does not fabricate convergence while SHADOW is OFF", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(snapshot(false))));
    render(<PplComparisonView />);

    await waitFor(() => expect(screen.getByTestId("ppl-comparison-unavailable")).toBeInTheDocument());
    expect(screen.getByTestId("ppl-comparison-unavailable")).toHaveTextContent(
      "convergence must not be inferred",
    );
    expect(screen.queryAllByTestId("ppl-comparison-row")).toHaveLength(0);
  });

  it("surfaces a structured API failure instead of an empty healthy comparator", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response(
          {
            error_code: "PPL_COMPARISON_SNAPSHOT_MISSING",
            error_message: "artifact absent",
          },
          503,
        ),
      ),
    );
    render(<PplComparisonView />);

    await waitFor(() =>
      expect(screen.getByTestId("ppl-comparison-view")).toHaveTextContent(
        "PPL_COMPARISON_SNAPSHOT_MISSING",
      ),
    );
  });


  it("rejects a PPL authority escalation instead of rendering it", async () => {
    const mutated = snapshot() as any;
    mutated.ppl_source.authority = "PAPER_AUTHORITY";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(mutated)));
    render(<PplComparisonView />);

    await waitFor(() =>
      expect(screen.getByTestId("ppl-comparison-view")).toHaveTextContent(
        "did not satisfy the WEB-02 PPL comparison contract",
      ),
    );
  });
});
