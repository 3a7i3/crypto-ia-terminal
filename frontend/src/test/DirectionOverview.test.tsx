import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { DirectionOverview } from "../views/DirectionOverview";
import { baseSnapshot } from "./fixtures";

function response(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

function financialSnapshot(realizedPnl: string | null = "0.0486506774129714893128911054") {
  return {
    schema_version: "1.0.0",
    product: "FIN02FinancialCockpit",
    domain: "financial_reconciliation",
    authority: "FINANCIAL_OBSERVATION",
    generated_at_utc: "2026-09-27T20:00:00Z",
    reconciliation_id: "r".repeat(64),
    paper_epoch_id: "BURN-IN-EPOCH-01-20260926T064144Z",
    financial_snapshot_id: "s".repeat(64),
    reconciliation_code_sha: "r".repeat(40),
    source_stream_digest: "p".repeat(64),
    last_source_sequence: 3,
    fin_schema_version: 1,
    fin_code_sha: "f".repeat(40),
    source_code_sha: "a".repeat(40),
    config_hash: "c".repeat(64),
    financial_model: "PAPER_LINEAR_PRINCIPAL_V1",
    asset: "USDT",
    financial: {
      initial_epoch_capital: "1001.8635705815693",
      cash_available: "981.8435705815693",
      capital_reserved: "20.0",
      capital_deployed: "20.0",
      capital_unresolved: "0",
      gross_realized_price_pnl: "0",
      fees_paid: "0.02",
      funding_net: null,
      funding_status: "NOT_APPLICABLE",
      funding_evidence_ref: null,
      realized_pnl: realizedPnl,
      known_unrealized_pnl: "0",
      unrealized_pnl: null,
      certified_equity: null,
      evidence_status: realizedPnl === null ? "UNRESOLVED" : "PRESENT",
      reconciliation_status: "UNRESOLVED",
      valuation_as_of: "1790540000.0",
      valuation_statuses: ["UNAVAILABLE"],
      open_position_count: 2,
      settled_position_count: 0,
      unresolved_position_count: 0,
    },
    reconciliation: {
      overall_status: "DIVERGENT",
      as_of: "1790540000.0",
      unresolved_capital: "0",
      unreconciled_capital: null,
      policy: {
        absolute_tolerance: "0.000000000001",
        relative_tolerance: "0",
        stale_after_s: "30",
      },
      ppl_observation_digest: "1".repeat(64),
      simulator_observation_digest: null,
      external_observation_digest: null,
    },
    sources: { ppl: {}, simulator: null, external: null },
    records: [],
    snapshot_age_s: 4.5,
    freshness_classification: "FRESH",
  };
}

function governedFetch(fin = financialSnapshot()) {
  return vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/api/operator/v1/snapshot")) return Promise.resolve(response(baseSnapshot()));
    if (url.endsWith("/api/operator/v1/financial-reconciliation")) return Promise.resolve(response(fin));
    return Promise.reject(new Error("unexpected endpoint " + url));
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("WEB-DIR-01 D4B DirectionOverview", () => {
  it("renders independent governed Global State and Active Experiment cards", async () => {
    const fetchMock = governedFetch();
    vi.stubGlobal("fetch", fetchMock);

    render(<DirectionOverview />);

    await waitFor(() => expect(screen.getByTestId("direction-global-card")).toHaveTextContent("PAPER"));
    await waitFor(() => expect(screen.getByTestId("direction-experiment-card")).toHaveTextContent("981.8435705815693 USDT"));

    const global = screen.getByTestId("direction-global-card");
    const experiment = screen.getByTestId("direction-experiment-card");

    expect(global).toHaveTextContent("INCONNU");
    expect(global).toHaveTextContent("CURRENT_INSTANCE");
    expect(global).toHaveTextContent("boot_alive observation");
    expect(global).toHaveTextContent("NON DÉPLOYÉ");

    expect(experiment).toHaveTextContent("BURN-IN-EPOCH-01-20260926T064144Z");
    expect(experiment).toHaveTextContent("20.0 USDT");
    expect(experiment).toHaveTextContent("0.02 USDT");
    expect(experiment).toHaveTextContent("Positions OPEN");
    expect(experiment).toHaveTextContent("2");
    expect(experiment).toHaveTextContent("Population · NOT_AVAILABLE");
    expect(experiment).toHaveTextContent("PF · NOT_AVAILABLE");
    expect(experiment).toHaveTextContent("WR · NOT_AVAILABLE");
    expect(experiment).toHaveTextContent("Les deux statuts de réconciliation diffèrent");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls.map((call) => String(call[0]))).toEqual(
      expect.arrayContaining([
        "/api/operator/v1/snapshot",
        "/api/operator/v1/financial-reconciliation",
      ]),
    );
    for (const call of fetchMock.mock.calls) expect(call[1]).toEqual({ method: "GET" });
  });

  it("preserves null realized PnL as evidence status instead of zero", async () => {
    vi.stubGlobal("fetch", governedFetch(financialSnapshot(null)));
    render(<DirectionOverview />);

    await waitFor(() =>
      expect(screen.getByTestId("direction-experiment-card")).toHaveTextContent("UNRESOLVED"),
    );
    expect(screen.getByTestId("direction-experiment-card")).not.toHaveTextContent("PnL réalisé0");
  });

  it("isolates one endpoint failure without fabricating or erasing the other card", async () => {
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/operator/v1/snapshot")) {
        return Promise.resolve(
          response({ error_code: "SNAPSHOT_UNAVAILABLE", error_message: "missing" }, 503),
        );
      }
      return Promise.resolve(response(financialSnapshot()));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<DirectionOverview />);

    await waitFor(() =>
      expect(screen.getByTestId("direction-global-card")).toHaveTextContent("SNAPSHOT_UNAVAILABLE"),
    );
    expect(screen.getByTestId("direction-experiment-card")).toHaveTextContent(
      "981.8435705815693 USDT",
    );
  });
});
