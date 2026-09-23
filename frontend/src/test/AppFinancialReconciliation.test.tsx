import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "../App";
import { baseSnapshot } from "./fixtures";

function response(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

function financialSnapshot() {
  return {
    schema_version: "1.0.0",
    product: "FIN02FinancialCockpit",
    domain: "financial_reconciliation",
    authority: "FINANCIAL_OBSERVATION",
    generated_at_utc: "2026-09-21T07:30:27Z",
    reconciliation_id: "r".repeat(64),
    paper_epoch_id: "F00-EPOCH-01",
    financial_snapshot_id: "s".repeat(64),
    reconciliation_code_sha: "r".repeat(40),
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
      cash_available: "980.04",
      capital_reserved: "20.0",
      capital_deployed: "20.0",
      capital_unresolved: "0",
      gross_realized_price_pnl: "0.10",
      fees_paid: "0.06",
      funding_net: "0",
      funding_status: "NOT_APPLICABLE",
      funding_evidence_ref: "FIN-00:PAPER_LINEAR_PRINCIPAL_V1:FUNDING_NOT_MODELED",
      realized_pnl: "0.04",
      known_unrealized_pnl: "0",
      unrealized_pnl: null,
      certified_equity: null,
      evidence_status: "UNRESOLVED",
      reconciliation_status: "UNRESOLVED",
      valuation_as_of: "10",
      valuation_statuses: ["UNAVAILABLE"],
      open_position_count: 1,
      settled_position_count: 1,
      unresolved_position_count: 0,
    },
    reconciliation: {
      overall_status: "EXACT",
      as_of: "10",
      unresolved_capital: "0",
      unreconciled_capital: "0",
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
      ppl: {},
      simulator: {},
      external: null,
    },
    records: [],
    snapshot_age_s: 2,
    freshness_classification: "FRESH",
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("App FIN-02 domain", () => {
  it("loads Financial as an independent read-only domain", async () => {
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/operator/v1/financial-reconciliation") {
        return Promise.resolve(response(financialSnapshot()));
      }
      return Promise.resolve(response(baseSnapshot()));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await waitFor(() => expect(screen.getByTestId("overview-view")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("tab-finance"));

    await waitFor(() =>
      expect(screen.getByTestId("financial-reconciliation-view")).toHaveTextContent(
        "Financial Truth",
      ),
    );
    expect(screen.getByTestId("finance-domain-badge")).toHaveTextContent("FIN");
    expect(screen.queryByTestId("mode-badge")).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/operator/v1/financial-reconciliation",
      { method: "GET" },
    );
  });
});
