import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { FinancialReconciliationView } from "../views/FinancialReconciliationView";

function response(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

function snapshot() {
  return {
    schema_version: "1.0.0",
    product: "FIN02FinancialCockpit",
    domain: "financial_reconciliation",
    authority: "FINANCIAL_OBSERVATION",
    generated_at_utc: "2026-09-21T07:30:27Z",
    reconciliation_id: "r".repeat(64),
    paper_epoch_id: "F00-EPOCH-01",
    financial_snapshot_id: "s".repeat(64),
    source_stream_digest: "p".repeat(64),
    last_source_sequence: 7,
    fin_schema_version: 1,
    fin_code_sha: "f".repeat(40),
    source_code_sha: "a".repeat(40),
    config_hash: "c".repeat(64),
    financial_model: "PAPER_LINEAR_PRINCIPAL_V1",
    asset: "USDT",
    financial: {
      initial_epoch_capital: "1000.0",
      cash_available: "980.0486506774129714893128911",
      capital_reserved: "20.0",
      capital_deployed: "20.0",
      capital_unresolved: "0",
      gross_realized_price_pnl: "0.1086506774129714893128911054",
      fees_paid: "0.06",
      funding_net: "0",
      funding_status: "NOT_APPLICABLE",
      funding_evidence_ref: "FIN-00:PAPER_LINEAR_PRINCIPAL_V1:FUNDING_NOT_MODELED",
      realized_pnl: "0.0486506774129714893128911054",
      known_unrealized_pnl: "0",
      unrealized_pnl: null,
      certified_equity: null,
      evidence_status: "UNRESOLVED",
      reconciliation_status: "UNRESOLVED",
      valuation_as_of: "1789975303.322754",
      valuation_statuses: ["UNAVAILABLE", "UNAVAILABLE"],
      open_position_count: 2,
      settled_position_count: 2,
      unresolved_position_count: 0,
    },
    reconciliation: {
      overall_status: "DIVERGENT",
      as_of: "1789975303.322754",
      unresolved_capital: "0",
      unreconciled_capital: "1.0",
      policy: {
        absolute_tolerance: "0.000000000001",
        relative_tolerance: "0",
        stale_after_s: "30",
      },
      ppl_observation_digest: "1".repeat(64),
      simulator_observation_digest: "2".repeat(64),
      external_observation_digest: null,
    },
    sources: {
      ppl: { provenance: "PPL durable replay" },
      simulator: { provenance: "MEXC_SIM lock snapshot" },
      external: null,
    },
    records: [
      {
        record_id: "cash-record",
        source_kind: "SIMULATOR",
        source_id: "MEXC_SIM",
        field: "cash_available",
        projected_value: "980.0486506774129714893128911",
        observed_value: "981.0486506774129714893128911",
        delta_observed_minus_projected: "1.0",
        unreconciled_amount: "1.0",
        status: "DIVERGENT",
        comparability: "COMPARABLE",
        freshness: "LIVE",
        observed_at: "1789975303.322754",
        projected_provenance: "FIN-01 Treasury.cash_available",
        observed_provenance: "MEXC_SIM._capital",
        note: "Visible difference; no correction.",
      },
      {
        record_id: "realized-record",
        source_kind: "PPL",
        source_id: "PPL_AUTHORITY",
        field: "realized_pnl",
        projected_value: "0.0486506774129714893128911054",
        observed_value: "0.06865067741297093",
        delta_observed_minus_projected: null,
        unreconciled_amount: null,
        status: "UNRESOLVED",
        comparability: "NON_COMPARABLE",
        freshness: "LIVE",
        observed_at: "1789975303.322754",
        projected_provenance: "FIN-01 realized PnL to date",
        observed_provenance: "PPL lifecycle realized PnL",
        note: "Different accounting recognition semantics.",
      },
    ],
    snapshot_age_s: 12,
    freshness_classification: "FRESH",
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("FinancialReconciliationView", () => {
  it("shows financial truth, explicit unknown equity and visible divergence", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(snapshot())));
    render(<FinancialReconciliationView />);

    await waitFor(() => expect(screen.getByText("Financial Truth")).toBeInTheDocument());

    const view = screen.getByTestId("financial-reconciliation-view");
    expect(view).toHaveTextContent("980.0486506774129714893128911");
    expect(view).toHaveTextContent("UNAVAILABLE");
    expect(view).toHaveTextContent("DIVERGENT");
    expect(view).toHaveTextContent("1.0");
    expect(view).toHaveTextContent("NON_COMPARABLE");
    expect(view).toHaveTextContent("no auto-correction");
  });

  it("surfaces structured API failure rather than fake zero balances", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response(
          {
            error_code: "FINANCIAL_RECONCILIATION_SNAPSHOT_MISSING",
            error_message: "artifact absent",
          },
          503,
        ),
      ),
    );

    render(<FinancialReconciliationView />);

    await waitFor(() =>
      expect(screen.getByTestId("financial-reconciliation-view")).toHaveTextContent(
        "FINANCIAL_RECONCILIATION_SNAPSHOT_MISSING",
      ),
    );
    expect(screen.getByTestId("financial-reconciliation-view")).not.toHaveTextContent("0 USDT");
  });

  it("rejects malformed financial transport instead of rendering it", async () => {
    const bad = snapshot() as any;
    bad.financial.cash_available = 980.04;

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(bad)));
    render(<FinancialReconciliationView />);

    await waitFor(() =>
      expect(screen.getByTestId("financial-reconciliation-view")).toHaveTextContent(
        "did not satisfy the FIN-02 financial reconciliation contract",
      ),
    );
  });
});
