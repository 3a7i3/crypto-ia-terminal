import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "../App";
import { ResearchLabView } from "../views/ResearchLabView";
import { validateResearchLabSnapshot } from "../lib/researchLabValidation";
import { baseSnapshot } from "./fixtures";

function response(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

function researchSnapshot() {
  const artifact = {
    artifact_ref: "diag-a4",
    artifact_type: "RL_DIAG_RESULT",
    sha256: "6".repeat(64),
  };

  const metric = (
    metric_name: string,
    value: number | string | null,
    evidence_status = "COMPLETE",
    statistical_strength = "LOW_SAMPLE",
    unit = "usd",
    reason: string | null = null,
  ) => ({
    metric_name,
    value,
    unit,
    evidence_status,
    statistical_strength,
    population_n: 13,
    derivation: "producer-authored fixture evidence",
    source_ref: artifact.artifact_ref,
    reason,
  });

  return {
    schema_version: "1.0.0",
    product: "ResearchLabSnapshot",
    domain: "research_lab",
    authority: "RESEARCH_NON_AUTHORITATIVE",
    generated_at_utc: "2026-09-26T01:00:00Z",
    presentation_builder_source_sha: "b".repeat(40),
    research_state: "AVAILABLE",
    provenance: {
      primary_context: {
        dataset_id: "1".repeat(64),
        source_boundary_id: "2".repeat(64),
        paper_epoch_id: "F00-EPOCH-01-20260920T084335Z",
        research_run_id: "3".repeat(64),
        diagnostic_run_id: "4".repeat(64),
        research_source_code_sha: "a".repeat(40),
        research_config_hash: "5".repeat(64),
        presentation_builder_source_sha: "b".repeat(40),
        population_definition: "POSITION_CLOSED_FOR_PERFORMANCE",
        n: 13,
        evidence_status: "COMPLETE",
        statistical_strength: "LOW_SAMPLE",
      },
      source_artifacts: [artifact],
    },
    population: {
      population_definition: "POSITION_CLOSED_FOR_PERFORMANCE",
      n: 13,
      evidence_status: "COMPLETE",
      statistical_strength: "LOW_SAMPLE",
    },
    performance: [
      metric("net_realized_pnl_usd", 1.86357),
      metric("profit_factor", 3.4994, "COMPLETE", "LOW_SAMPLE", "ratio"),
      metric(
        "annualized_sharpe",
        null,
        "NOT_AVAILABLE",
        "NOT_EVALUATED",
        "ratio",
        "No certified time-series/annualized return basis.",
      ),
    ],
    risk_stability: [
      metric(
        "mark_to_market_maxdd",
        null,
        "NOT_AVAILABLE",
        "NOT_EVALUATED",
        "ratio",
        "No authoritative mark-to-market path.",
      ),
    ],
    costs: [
      metric("fees_usd", 0.26),
      metric(
        "funding_usd",
        null,
        "NOT_AVAILABLE",
        "NOT_EVALUATED",
        "usd",
        "No certified funding stream.",
      ),
    ],
    attribution: [
      {
        dimension: "packet_regime",
        evidence_status: "COMPLETE",
        statistical_strength: "LOW_SAMPLE",
        rows: [
          {
            label: "TREND_BULL",
            population_n: 9,
            metrics: [
              {
                ...metric("net_realized_pnl_usd", 1.97),
                population_n: 9,
              },
            ],
          },
        ],
      },
    ],
    candidate_registry: {
      candidate_count: 0,
      rows: [],
    },
    limitations: [
      "N=13 / LOW_SAMPLE",
      "No causal inference",
      "No mark-to-market path",
    ],
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("WEB-RL Research Lab", () => {
  it("accepts the exact closed Research presentation schema", () => {
    expect(validateResearchLabSnapshot(researchSnapshot())).toBe(true);
  });

  it("rejects numeric zero substituted for NOT_AVAILABLE", () => {
    const snapshot = researchSnapshot();
    const sharpe = snapshot.performance.find((metric) => metric.metric_name === "annualized_sharpe");
    if (!sharpe) throw new Error("fixture missing Sharpe");
    sharpe.value = 0;
    expect(validateResearchLabSnapshot(snapshot)).toBe(false);
  });

  it("renders provenance, LOW_SAMPLE and explicit NOT_AVAILABLE without invented candidate", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(researchSnapshot())));

    render(<ResearchLabView />);

    await waitFor(() =>
      expect(screen.getByTestId("research-domain-banner")).toHaveTextContent(
        "NON-AUTHORITATIVE",
      ),
    );
    const view = screen.getByTestId("research-lab-view");
    expect(view).toHaveTextContent("LOW_SAMPLE");
    expect(view).toHaveTextContent("N");
    expect(view).toHaveTextContent("13");
    expect(view).toHaveTextContent("annualized_sharpe");
    expect(view).toHaveTextContent("NOT_AVAILABLE");
    expect(view).toHaveTextContent("No certified time-series/annualized return basis.");
    expect(screen.getByTestId("research-candidate-empty")).toHaveTextContent(
      "No substantive candidate",
    );
  });

  it("surfaces malformed HTTP 200 as a contract error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response({
          schema_version: "1.0.0",
          product: "ResearchLabSnapshot",
          domain: "research_lab",
          authority: "PPL_AUTHORITY",
        }),
      ),
    );

    render(<ResearchLabView />);

    await waitFor(() =>
      expect(screen.getByTestId("research-lab-view")).toHaveTextContent(
        "contract/transport error",
      ),
    );
  });

  it("keeps Research independently available when canonical PAPER snapshot is missing", async () => {
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/operator/v1/research-lab") {
        return Promise.resolve(response(researchSnapshot()));
      }
      if (url === "/api/operator/v1/snapshot") {
        return Promise.resolve(
          response(
            {
              error_code: "SNAPSHOT_MISSING",
              error_message: "canonical artifact absent",
            },
            503,
          ),
        );
      }
      return Promise.resolve(response(baseSnapshot()));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await waitFor(() =>
      expect(screen.getByTestId("snapshot-status-api-error")).toHaveTextContent(
        "SNAPSHOT_MISSING",
      ),
    );

    fireEvent.click(screen.getByTestId("tab-research"));

    await waitFor(() =>
      expect(screen.getByTestId("research-domain-banner")).toHaveTextContent(
        "RESEARCH LAB",
      ),
    );
    expect(screen.queryByTestId("snapshot-status-api-error")).toBeNull();
    expect(screen.getByTestId("research-lab-view")).toHaveTextContent(
      "RESEARCH_NON_AUTHORITATIVE",
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/operator/v1/research-lab",
      { method: "GET" },
    );

    fireEvent.click(screen.getByTestId("tab-overview"));
    expect(screen.getByTestId("snapshot-status-api-error")).toHaveTextContent(
      "SNAPSHOT_MISSING",
    );
  });
});
