import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { SourceAvailability } from "../components/SourceAvailability";
import { DecisionsView } from "../views/DecisionsView";
import { OverviewView } from "../views/OverviewView";
import { ResearchLabView } from "../views/ResearchLabView";
import { BurnInStatusView } from "../views/BurnInStatusView";
import { baseSnapshot } from "./fixtures";
import { burnInFixture } from "./burnInFixtures";
import type { PerSymbolDecision } from "../types";
const response = (body: unknown, status = 200) => ({ok: status === 200, status, json: async () => body}) as Response;
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });
function decision(symbol: string, allowed: boolean | null): PerSymbolDecision {
  return {symbol, packet_id: symbol, context_id: "ctx", created_cycle_id: "cycle",
    created_at: {value:null, semantics:"UNKNOWN"}, latest_transition_at_utc: {value:null, semantics:"UNKNOWN"},
    side:{value:"long",semantics:"PRESENT"}, confidence_raw:{value:0.5,semantics:"PRESENT"}, confidence_adjusted:{value:0.5,semantics:"PRESENT"},
    regime:{value:"TREND_BULL",semantics:"PRESENT"}, lifecycle_state:{value:"APPROVED",semantics:"PRESENT"},
    is_actionable:{value:true,semantics:"PRESENT",authority:"EXECUTION_AUTHORITY"},
    trade_allowed:{value:allowed,semantics:allowed === null ? "UNKNOWN" : allowed ? "PRESENT" : "FALSE",authority:"OBSERVATIONAL_TELEMETRY"},
    first_blocker:{value:allowed === false ? "risk_gate" : null,semantics:allowed === false ? "PRESENT" : "UNKNOWN",authority:"OBSERVATIONAL_TELEMETRY"}};
}
describe("Contrats mobile et disponibilité sans autorité", () => {
  it("affiche loading sans zéro ou preuve antérieure", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    render(<><BurnInStatusView/><ResearchLabView/></>);
    expect(screen.getByTestId("burnin-view")).toHaveTextContent("CHARGEMENT");
    expect(screen.queryByTestId("source-availability")).toBeNull();
    expect(screen.queryByTestId("burnin-open-row")).toBeNull();
    expect(screen.queryByTestId("research-metric-card")).toBeNull();
  });

  it("distingue admissibilité, signal exploitable et inconnus; filtre sans toucher au compte source", () => {
    const snapshot = baseSnapshot(); snapshot.decision_pipeline.per_symbol_decisions = [decision("BTCUSDT", true),decision("ETHUSDT",false),decision("SOLUSDT",null)];
    render(<DecisionsView snapshot={snapshot}/>);
    const summary = screen.getByLabelText("Résumé des lignes observées");
    expect(summary).toHaveTextContent("Décisions observées3Admissible1Non admissible1Admission inconnue1");
    fireEvent.change(screen.getByLabelText("Décision"), {target:{value:"Non admissible"}});
    expect(screen.getAllByTestId("decision-mobile-card")).toHaveLength(1);
    expect(screen.getByTestId("decision-mobile-card")).toHaveTextContent("ETHUSDT");
    expect(screen.getByTestId("decision-mobile-card")).toHaveTextContent("Signal exploitableOui");
    fireEvent.change(screen.getByLabelText("Recherche par symbole"), {target:{value:"BTC"}});
    expect(screen.queryAllByTestId("decision-mobile-card")).toHaveLength(0);
    expect(summary).toHaveTextContent("Décisions observées3");
    fireEvent.click(screen.getByRole("button", {name:"Réinitialiser"}));
    fireEvent.change(screen.getByLabelText("Bloqueur"), {target:{value:"risk_gate"}});
    expect(screen.getByTestId("decision-mobile-card")).toHaveTextContent("ETHUSDT");
  });
  it("garde les comptes inconnus si les lignes manquent", () => {
    const snapshot = baseSnapshot(); snapshot.decision_pipeline.per_symbol_decisions = null as unknown as PerSymbolDecision[];
    render(<DecisionsView snapshot={snapshot}/>);
    expect(screen.getByLabelText("Résumé des lignes observées")).toHaveTextContent("Décisions observéesInconnu");
    expect(screen.queryAllByTestId("decision-mobile-card")).toHaveLength(0);
  });
  it("signale les captures périmées et ferme les diagnostics bruts", () => {
    const snapshot = baseSnapshot(); snapshot.freshness_classification = "STALE";
    const {unmount} = render(<DecisionsView snapshot={snapshot}/>);
    expect(screen.getByText(/Données périmées : résumé/)).toHaveTextContent("aucune admission actuelle attestée"); unmount();
    render(<OverviewView snapshot={snapshot}/>);
    const details = screen.getByText("Diagnostics techniques").closest("details")!;
    expect(details).not.toHaveAttribute("open"); expect(within(details).getByText("snapshot_id")).toBeInTheDocument();
    expect(screen.getByTestId("overview-view")).toHaveTextContent("Santé globale inconnue");
  });
  it.each(["RESEARCH_LAB_SNAPSHOT_MISSING", "RESEARCH_LAB_UNREADABLE", "RESEARCH_LAB_INVALID_PATH", "RESEARCH_LAB_INVALID_SCHEMA"])("explique %s sans métrique inventée", code => {
    render(<SourceAvailability source="research" code={code} httpStatus={503}/>);
    expect(screen.getByRole("status")).toHaveTextContent("UNKNOWN");
    expect(screen.getByRole("status")).toHaveTextContent("Dernière preuve runtime : inconnue");
    expect(screen.getByRole("status")).toHaveTextContent("Action nécessaire");
  });
  it("conserve seulement les métadonnées validées après un échec de reprise, jamais les positions", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValueOnce(response(burnInFixture())).mockResolvedValue(response({error_code:"BURN_IN_STATUS_MISSING"},503));
    vi.stubGlobal("fetch", fetchMock); render(<BurnInStatusView/>);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByTestId("burnin-view")).toHaveTextContent("BTC/USDT");
    await act(async () => { await vi.advanceTimersByTimeAsync(20000); });
    const unavailable = screen.getByTestId("source-availability");
    expect(unavailable).toHaveTextContent(burnInFixture().generated_at_utc);
    expect(unavailable).toHaveTextContent("aucune valeur passée n’est affichée comme actuelle");
    expect(unavailable).not.toHaveTextContent("BTC/USDT");
    expect(unavailable).toHaveTextContent("ne prouve ni la fin du burn-in");
    expect(fetchMock.mock.calls.every(call => call[1].method === "GET")).toBe(true);
  });
});
