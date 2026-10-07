import { runtimeServiceFixture } from "./runtimeServiceFixtures";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { DirectionOverview } from "../views/DirectionOverview";
import { baseSnapshot } from "./fixtures";
import { burnInFixture } from "./burnInFixtures";

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

function marketSnapshot() {
  return {
    schema_version: "1.0.0",
    product: "CryptoRadar",
    domain: "market",
    authority: "OBSERVATIONAL_TELEMETRY",
    mode: "OBSERVATION",
    generated_at_utc: "2026-09-27T20:00:00Z",
    source_updated_at_utc: "2026-09-27T19:59:00Z",
    window_hours: 24,
    min_confidence: 65,
    packets_observed: 86,
    market_regime: "bull_trend",
    universe_size: 33,
    actionable_count: 4,
    watchlist_count: 7,
    top_opportunities: [],
    snapshot_age_s: 8,
    freshness_classification: "FRESH",
  };
}

function researchSnapshot() {
  return {
    schema_version: "1.0.0",
    product: "ResearchLabSnapshot",
    domain: "research_lab",
    authority: "RESEARCH_NON_AUTHORITATIVE",
    generated_at_utc: "2026-09-27T20:00:00Z",
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
      source_artifacts: [
        {
          artifact_ref: "diag-a4",
          artifact_type: "RL_DIAG_RESULT",
          sha256: "6".repeat(64),
        },
      ],
    },
    population: {
      population_definition: "POSITION_CLOSED_FOR_PERFORMANCE",
      n: 13,
      evidence_status: "COMPLETE",
      statistical_strength: "LOW_SAMPLE",
    },
    performance: [],
    risk_stability: [],
    costs: [],
    attribution: [],
    candidate_registry: { candidate_count: 0, rows: [] },
    limitations: ["N=13 / LOW_SAMPLE"],
  };
}

function governedFetch(
  fin = financialSnapshot(),
  market = marketSnapshot(),
  research = researchSnapshot(),
  operator = baseSnapshot(),
  burnIn = burnInFixture(),
) {
  return vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/api/operator/v1/snapshot")) return Promise.resolve(response(operator));
    if (url.endsWith("/api/operator/v1/financial-reconciliation")) return Promise.resolve(response(fin));
    if (url.endsWith("/api/operator/v1/market")) return Promise.resolve(response(market));
    if (url.endsWith("/api/operator/v1/research-lab")) return Promise.resolve(response(research));
    if (url.endsWith("/api/operator/v1/runtime-service")) return Promise.resolve(response(runtimeServiceFixture()));
    if (url.endsWith("/api/operator/v1/burn-in")) return Promise.resolve(response(burnIn));
    return Promise.reject(new Error("unexpected endpoint " + url));
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("WEB-DIR-01 D4B/D4C/D4D/D4E DirectionOverview", () => {
  it("renders all six independent governed Direction cards with GET-only reads", async () => {
    const fetchMock = governedFetch();
    vi.stubGlobal("fetch", fetchMock);

    render(<DirectionOverview />);

    await waitFor(() => expect(screen.getByTestId("direction-global-card")).toHaveTextContent("PAPER"));
    await waitFor(() => expect(screen.getByTestId("direction-experiment-card")).toHaveTextContent("981.8435705815693 USDT"));
    await waitFor(() => expect(screen.getByTestId("direction-market-card")).toHaveTextContent("OBSERVATIONAL_TELEMETRY"));
    await waitFor(() => expect(screen.getByTestId("direction-research-card")).toHaveTextContent("RESEARCH_NON_AUTHORITATIVE"));
    await waitFor(() => expect(screen.getByTestId("direction-burnin-card")).toHaveTextContent("BURN-IN-EPOCH-01"));

    await waitFor(() => expect(screen.getByTestId("direction-runtime-service-card")).toHaveTextContent("ÉTAT OBSERVÉ · active"));
    expect(screen.getByTestId("direction-runtime-service-card")).toHaveTextContent("HOST_SYSTEMD_OBSERVATION");
    const burnIn = screen.getByTestId("direction-burnin-card");
    const global = screen.getByTestId("direction-global-card");
    const experiment = screen.getByTestId("direction-experiment-card");
    const market = screen.getByTestId("direction-market-card");
    const research = screen.getByTestId("direction-research-card");

    expect(burnIn).toHaveTextContent("Événements");
    expect(burnIn).toHaveTextContent("BEFORE_TIMEOUT");
    expect(burnIn).toHaveTextContent("T0 scientifique");
    expect(burnIn).toHaveTextContent("PPL_AUTHORITY_PRESENTATION");

    expect(global).toHaveTextContent("INCONNU");
    expect(global).toHaveTextContent("Mode");
    expect(global).toHaveTextContent("PAPER");
    expect(global).toHaveTextContent("Capital PAPER");
    expect(global).toHaveTextContent("Positions PAPER");
    expect(global).toHaveTextContent("0 / 2");
    expect(global).toHaveTextContent("Admission portefeuille");
    expect(global).toHaveTextContent("OPEN");
    expect(global).toHaveTextContent("Runtime source");
    expect(global).toHaveTextContent("VERIFIED");
    expect(global).toHaveTextContent("CURRENT_INSTANCE");
    expect(global).toHaveTextContent("boot_alive observation");
    expect(global).toHaveTextContent("NON DÉPLOYÉ");

    expect(experiment).toHaveTextContent("BURN-IN-EPOCH-01-20260926T064144Z");
    expect(experiment).toHaveTextContent("20.0 USDT");
    expect(experiment).toHaveTextContent("0.02 USDT");
    expect(experiment).toHaveTextContent("Population · NOT_AVAILABLE");
    expect(experiment).toHaveTextContent("PF · NOT_AVAILABLE");
    expect(experiment).toHaveTextContent("WR · NOT_AVAILABLE");

    expect(market).toHaveTextContent("OBSERVATION");
    expect(market).toHaveTextContent("bull_trend");
    expect(market).toHaveTextContent("Actionable observés");
    expect(market).toHaveTextContent("4");
    expect(market).toHaveTextContent("aucune permission de trade");

    expect(research).toHaveTextContent("RECHERCHE NON AUTORITAIRE");
    expect(research).toHaveTextContent("Population dataset N");
    expect(research).toHaveTextContent("13");
    expect(research).toHaveTextContent("LOW_SAMPLE");
    expect(research).toHaveTextContent("Candidats");
    expect(research).toHaveTextContent("0");
    expect(research).toHaveTextContent("ne remplissent jamais les métriques PAPER actives");

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));
    expect(fetchMock.mock.calls.map((call) => String(call[0]))).toEqual(
      expect.arrayContaining([
        "/api/operator/v1/snapshot",
        "/api/operator/v1/financial-reconciliation",
        "/api/operator/v1/market",
        "/api/operator/v1/research-lab",
        "/api/operator/v1/burn-in",
        "/api/operator/v1/runtime-service",
      ]),
    );
    for (const call of fetchMock.mock.calls) {
      expect(call[1]).toMatchObject({ method: "GET" });
    }
  });

  it("keeps provenance and freshness independent per card with no global roll-up", async () => {
    vi.stubGlobal("fetch", governedFetch());
    render(<DirectionOverview />);

    await waitFor(() =>
      expect(screen.getByTestId("direction-provenance-market")).toHaveTextContent("OBSERVATIONAL_TELEMETRY"),
    );

    const federation = screen.getByTestId("direction-federation-notice");
    expect(federation).toHaveTextContent("Sources indépendantes");
    expect(federation).toHaveTextContent("dates et fraîcheurs sont propres à chaque source");
    expect(federation).toHaveTextContent("observation simultanée");
    expect(federation).toHaveTextContent("Aucun état global ni observation simultanée ne sont déduits");

    const global = screen.getByTestId("direction-provenance-global");
    expect(global).toHaveTextContent("/api/operator/v1/snapshot");
    expect(global).toHaveTextContent("canonical_advisor_presentation");
    expect(global).toHaveTextContent("AUCUNE AUTORITÉ GLOBALE");

    const experiment = screen.getByTestId("direction-provenance-experiment");
    expect(experiment).toHaveTextContent("/api/operator/v1/financial-reconciliation");
    expect(experiment).toHaveTextContent("FINANCIAL_OBSERVATION");
    expect(experiment).toHaveTextContent("FRESH");
    expect(experiment).toHaveTextContent("4.5s");

    const market = screen.getByTestId("direction-provenance-market");
    expect(market).toHaveTextContent("/api/operator/v1/market");
    expect(market).toHaveTextContent("market");
    expect(market).toHaveTextContent("FRESH");
    expect(market).toHaveTextContent("8s");

    const burnInProvenance = screen.getByTestId("direction-provenance-burnin");
    expect(burnInProvenance).toHaveTextContent("/api/operator/v1/burn-in");
    expect(burnInProvenance).toHaveTextContent("PPL_AUTHORITY_PRESENTATION");
    expect(burnInProvenance).toHaveTextContent("FRESH");

    const research = screen.getByTestId("direction-provenance-research");
    expect(research).toHaveTextContent("/api/operator/v1/research-lab");
    expect(research).toHaveTextContent("RESEARCH_NON_AUTHORITATIVE");
    expect(research).toHaveTextContent("Fraîcheur NOT_AVAILABLE");
    expect(research).toHaveTextContent("Âge NOT_AVAILABLE");

    const globalCard = screen.getByTestId("direction-global-card");
    const experimentCard = screen.getByTestId("direction-experiment-card");
    const researchCard = screen.getByTestId("direction-research-card");

    expect(globalCard).toHaveTextContent("Snapshot ID");
    expect(globalCard).toHaveTextContent("Process instance ID");
    expect(experimentCard).toHaveTextContent("Financial snapshot ID");
    expect(experimentCard).toHaveTextContent("Reconciliation ID");
    expect(experimentCard).toHaveTextContent("c".repeat(64));
    expect(researchCard).toHaveTextContent("1".repeat(64));
    expect(researchCard).toHaveTextContent("2".repeat(64));
    expect(researchCard).toHaveTextContent("3".repeat(64));
    expect(researchCard).toHaveTextContent("4".repeat(64));
    expect(researchCard).toHaveTextContent("5".repeat(64));
    expect(researchCard).toHaveTextContent("a".repeat(40));
    expect(researchCard).toHaveTextContent("b".repeat(40));
  });

  it("preserves CLAIMED_ONLY, null age, stale reason and global INCONNU without synthetic health", async () => {
    const operator = baseSnapshot();
    operator.runtime_sha_evidence_status = "CLAIMED_ONLY";
    operator.snapshot_age_s = null;
    operator.freshness_classification = "STALE";
    operator.stale_reason = "SOURCE_TOO_OLD";
    operator.system_health.health_level = { value: "CRITICAL", semantics: "PRESENT" };

    vi.stubGlobal(
      "fetch",
      governedFetch(financialSnapshot(), marketSnapshot(), researchSnapshot(), operator),
    );
    render(<DirectionOverview />);

    await waitFor(() =>
      expect(screen.getByTestId("direction-global-card")).toHaveTextContent("CLAIMED_ONLY"),
    );

    const global = screen.getByTestId("direction-global-card");
    const provenance = screen.getByTestId("direction-provenance-global");

    expect(global).toHaveTextContent("INCONNU");
    expect(global).toHaveTextContent("CRITICAL");
    expect(global).toHaveTextContent("SOURCE_TOO_OLD");
    expect(global).toHaveTextContent("Âge snapshotNOT_AVAILABLE");
    expect(global).not.toHaveTextContent("VERIFIED");

    expect(provenance).toHaveTextContent("Fraîcheur STALE");
    expect(provenance).toHaveTextContent("Âge NOT_AVAILABLE");
  });

  it("guards admission state when portfolio_status count diverges from the canonical observed count", async () => {
    const operator = baseSnapshot();
    operator.portfolio.paper_open_positions_count = { value: 1, semantics: "PRESENT" };
    operator.portfolio.portfolio_status = {
      current_positions: 2,
      hard_position_limit: 2,
      admission_state: "SATURATED",
      positions_by_personality: { scalper: 2 },
      positions_by_regime: { trend: 2 },
    };

    vi.stubGlobal("fetch", governedFetch(financialSnapshot(), marketSnapshot(), researchSnapshot(), operator));
    render(<DirectionOverview />);

    await waitFor(() =>
      expect(screen.getByTestId("direction-admission-inconsistent")).toHaveTextContent(/compteurs divergents/i),
    );

    const global = screen.getByTestId("direction-global-card");
    expect(global).toHaveTextContent("1 / 2");
    expect(global).toHaveTextContent("INCOHÉRENT");
    expect(global).toHaveTextContent("Aucun état d’admission n’est déduit");
    expect(screen.getByTestId("direction-owner-pulse")).not.toHaveTextContent("SATURATED");
  });

  it("shows deterministic position age at snapshot time without presenting a timeout", async () => {
    const operator = baseSnapshot({ generated_at_utc: "2026-09-09T02:30:00+00:00" });
    operator.portfolio.paper_open_positions_count = { value: 1, semantics: "PRESENT" };
    operator.portfolio.portfolio_status = {
      current_positions: 1,
      hard_position_limit: 2,
      admission_state: "OPEN",
      positions_by_personality: { scalper: 1 },
      positions_by_regime: { trend: 1 },
    };
    operator.portfolio.open_positions = {
      semantics: "PRESENT",
      value: [
        {
          position_id: "pos-1",
          symbol: "BTCUSDT",
          side: "BUY",
          size_usd: 10,
          entry_price: 50000,
          current_price: { value: 50500, semantics: "PRESENT" },
          current_price_observed_at_utc: "2026-09-09T02:29:59+00:00",
          tp_price: 52000,
          sl_price: 49000,
          tp_sl_source: "original",
          unrealized_pnl_usd: { value: 0.1, semantics: "PRESENT" },
          unrealized_pnl_pct: { value: 1, semantics: "PRESENT" },
          opened_at: Date.parse("2026-09-09T00:00:00+00:00") / 1000,
          regime: { value: "trend", semantics: "PRESENT" },
          restored_without_regime: false,
          personality: "scalper",
          restored: false,
        },
      ],
    };

    vi.stubGlobal("fetch", governedFetch(financialSnapshot(), marketSnapshot(), researchSnapshot(), operator));
    render(<DirectionOverview />);

    await waitFor(() => expect(screen.getByTestId("direction-owner-positions")).toHaveTextContent("BTCUSDT"));
    const positions = screen.getByTestId("direction-owner-positions");
    expect(positions).toHaveTextContent("2h 30m");
    expect(positions).toHaveTextContent("Âge à la capture");
    expect(positions).toHaveTextContent("Ce n’est ni un timeout PPL ni une deadline scientifique");
  });

  it("treats an invalid HTTP 200 snapshot as a contract/transport error without erasing FIN", async () => {
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/operator/v1/snapshot")) {
        return Promise.resolve(response({ schema_version: "broken" }));
      }
      if (url.endsWith("/api/operator/v1/financial-reconciliation")) {
        return Promise.resolve(response(financialSnapshot()));
      }
      if (url.endsWith("/api/operator/v1/market")) return Promise.resolve(response(marketSnapshot()));
      if (url.endsWith("/api/operator/v1/research-lab")) return Promise.resolve(response(researchSnapshot()));
      if (url.endsWith("/api/operator/v1/runtime-service")) return Promise.resolve(response(runtimeServiceFixture()));
    if (url.endsWith("/api/operator/v1/burn-in")) return Promise.resolve(response(burnInFixture()));
      return Promise.reject(new Error("unexpected endpoint " + url));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<DirectionOverview />);

    await waitFor(() =>
      expect(screen.getByTestId("direction-global-card")).toHaveTextContent(
        "ERREUR TRANSPORT / CONTRAT",
      ),
    );
    expect(screen.getByTestId("direction-experiment-card")).toHaveTextContent(
      "981.8435705815693 USDT",
    );
    expect(screen.getByTestId("direction-market-card")).toHaveTextContent(
      "OBSERVATIONAL_TELEMETRY",
    );
    expect(screen.getByTestId("direction-research-card")).toHaveTextContent(
      "RESEARCH_NON_AUTHORITATIVE",
    );
  });

  it("isolates a Research network failure and never upgrades another card into global health", async () => {
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/operator/v1/snapshot")) return Promise.resolve(response(baseSnapshot()));
      if (url.endsWith("/api/operator/v1/financial-reconciliation")) {
        return Promise.resolve(response(financialSnapshot()));
      }
      if (url.endsWith("/api/operator/v1/market")) return Promise.resolve(response(marketSnapshot()));
      if (url.endsWith("/api/operator/v1/research-lab")) {
        return Promise.reject(new Error("research network unavailable"));
      }
      if (url.endsWith("/api/operator/v1/runtime-service")) return Promise.resolve(response(runtimeServiceFixture()));
    if (url.endsWith("/api/operator/v1/burn-in")) return Promise.resolve(response(burnInFixture()));
      return Promise.reject(new Error("unexpected endpoint " + url));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<DirectionOverview />);

    await waitFor(() =>
      expect(screen.getByTestId("direction-research-card")).toHaveTextContent(
        "ERREUR TRANSPORT / CONTRAT",
      ),
    );
    expect(screen.getByTestId("direction-global-card")).toHaveTextContent("INCONNU");
    expect(screen.getByTestId("direction-experiment-card")).toHaveTextContent(
      "981.8435705815693 USDT",
    );
    expect(screen.getByTestId("direction-market-card")).toHaveTextContent(
      "OBSERVATIONAL_TELEMETRY",
    );
  });

  it("preserves null realized PnL as evidence status instead of zero", async () => {
    vi.stubGlobal("fetch", governedFetch(financialSnapshot(null)));
    render(<DirectionOverview />);

    await waitFor(() =>
      expect(screen.getByTestId("direction-experiment-card")).toHaveTextContent("UNRESOLVED"),
    );
    expect(screen.getByTestId("direction-experiment-card")).not.toHaveTextContent("PnL réalisé0");
  });

  it("keeps Research zero candidates as an explicit producer zero without promoting Research into PAPER", async () => {
    vi.stubGlobal("fetch", governedFetch());
    render(<DirectionOverview />);

    await waitFor(() =>
      expect(screen.getByTestId("direction-research-card")).toHaveTextContent("Candidats"),
    );
    const research = screen.getByTestId("direction-research-card");
    const experiment = screen.getByTestId("direction-experiment-card");
    expect(research).toHaveTextContent("0");
    expect(research).toHaveTextContent("RESEARCH_NON_AUTHORITATIVE");
    expect(experiment).toHaveTextContent("PF · NOT_AVAILABLE");
    expect(experiment).toHaveTextContent("Population · NOT_AVAILABLE");
  });

  it("isolates a Market source failure without erasing Research or PAPER cards", async () => {
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/operator/v1/snapshot")) return Promise.resolve(response(baseSnapshot()));
      if (url.endsWith("/api/operator/v1/financial-reconciliation")) return Promise.resolve(response(financialSnapshot()));
      if (url.endsWith("/api/operator/v1/market")) {
        return Promise.resolve(response({ error_code: "MARKET_SNAPSHOT_MISSING", error_message: "missing" }, 503));
      }
      if (url.endsWith("/api/operator/v1/research-lab")) return Promise.resolve(response(researchSnapshot()));
      if (url.endsWith("/api/operator/v1/runtime-service")) return Promise.resolve(response(runtimeServiceFixture()));
    if (url.endsWith("/api/operator/v1/burn-in")) return Promise.resolve(response(burnInFixture()));
      return Promise.reject(new Error("unexpected endpoint " + url));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<DirectionOverview />);

    await waitFor(() =>
      expect(screen.getByTestId("direction-market-card")).toHaveTextContent("MARKET_SNAPSHOT_MISSING"),
    );
    expect(screen.getByTestId("direction-research-card")).toHaveTextContent("RESEARCH_NON_AUTHORITATIVE");
    expect(screen.getByTestId("direction-experiment-card")).toHaveTextContent("981.8435705815693 USDT");
  });
});

describe("Machine regroupée — synthèse fidèle aux sources", () => {
  it("conserve les montants inconnus et les zéros explicites sans inventer de courbe", async () => {
    const fin = financialSnapshot(null);
    fin.financial.fees_paid = "0";
    vi.stubGlobal("fetch", governedFetch(fin));
    render(<DirectionOverview />);
    await waitFor(() => expect(screen.getByRole("region", { name: "Portefeuille et finances" })).toHaveTextContent("981,84"));
    const section = screen.getByRole("region", { name: "Portefeuille et finances" });
    const fact = (label: string) => Array.from(section.querySelectorAll("dt")).find((dt) => dt.textContent === label)?.nextElementSibling;
    expect(fact("Résultat réalisé")).toHaveTextContent("Non disponible");
    expect(fact("Résultat latent")).toHaveTextContent("Non disponible");
    expect(fact("Frais payés")).toHaveTextContent(/^0/);
    expect(section).toHaveTextContent("Historique non disponible");
    expect(section.querySelector("svg")).toBeNull();
    expect(section).not.toHaveTextContent("Illustration fictive");
    expect(screen.getByText("Expérience, état du service et preuves complètes").parentElement).not.toHaveAttribute("open");
  });

  it("n’affirme pas un Advisor actuel en cours depuis une preuve ancienne", async () => {
    const runtime = runtimeServiceFixture();
    runtime.freshness_classification = "STALE";
    runtime.snapshot_age_s = 86400;
    const other = governedFetch();
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => String(input).endsWith("/runtime-service") ? Promise.resolve(response(runtime)) : other(input)));
    render(<DirectionOverview />);
    await waitFor(() => expect(screen.getByText("Advisor observé").nextElementSibling).toHaveTextContent("Inconnu"));
    expect(screen.getByRole("region", { name: "État et expérience" })).toHaveTextContent("Preuve Advisor périmée : état actuel inconnu");
    expect(screen.getByText("Advisor observé").nextElementSibling).not.toHaveTextContent("En cours");
  });
});
