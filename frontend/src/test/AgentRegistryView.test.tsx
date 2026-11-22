import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { AgentRegistryPanel, AgentRegistryView } from "../views/AgentRegistryView";
import { AGENT_REGISTRY, type ActivityEvidence, type AgentRegistry } from "../agents/agentRegistry";

const NOW = Date.parse("2026-11-21T20:00:00Z");

describe("AgentRegistryView", () => {
  it("affiche six cartes de familles et l'espace Héritage", () => {
    render(<AgentRegistryView />);
    for (const id of ["OBSERVATION", "RECHERCHE", "EVALUATION", "RISQUE_GOUVERNANCE", "EXECUTION_PAPER", "MAINTENANCE"])
      expect(screen.getByTestId(`agent-family-${id}`)).toBeInTheDocument();
    expect(screen.getByTestId("agent-legacy")).toHaveTextContent("Héritage à arbitrer");
  });

  it("Exécution PAPER indique « Aucun profil qualifié »", () => {
    render(<AgentRegistryView />);
    const card = screen.getByTestId("agent-family-EXECUTION_PAPER");
    expect(within(card).getByTestId("agent-family-count")).toHaveTextContent("Aucun profil qualifié");
    expect(within(card).queryAllByTestId(/agent-profile-/)).toHaveLength(0);
  });

  it("affiche les 10 profils avec un voyant gris et un motif lisible", () => {
    render(<AgentRegistryView />);
    const lights = screen.getAllByTestId("agent-activity");
    expect(lights).toHaveLength(10);
    for (const l of lights) {
      expect(l).toHaveAttribute("data-light", "GRAY");
      expect(l).toHaveTextContent(/Gris · Non attesté/);
      // Le cartographe est relié, mais sans source de preuve branchée il reste gris.
      expect(l).toHaveTextContent(/runner relié|Aucune source de preuve/);
    }
    expect(screen.queryByText(/Vert ·/)).toBeNull();
    expect(screen.queryByText(/Rouge ·/)).toBeNull();
    expect(screen.getAllByTestId("agent-last-proof").every((n) => n.textContent === "Aucune preuve disponible")).toBe(true);
  });

  it("chaque profil expose identité, mission, source GitHub, validation et branchement", () => {
    render(<AgentRegistryView />);
    const p = screen.getByTestId("agent-profile-data-provenance-auditor");
    expect(p).toHaveTextContent("Data Provenance Auditor");
    expect(p).toHaveTextContent("Auditer provenance");
    expect(p).toHaveTextContent("MIGRATION_CANDIDATE");
    expect(within(p).getByTestId("agent-wiring")).toHaveTextContent("Aucun runner relié");
    expect(within(p).getByRole("link")).toHaveAttribute(
      "href",
      "https://github.com/3a7i3/crypto-ia-terminal/blob/main/.github/agents/data-provenance-auditor.agent.md",
    );
  });

  it("les héritages n'ont ni voyant ni statut opérationnel", () => {
    render(<AgentRegistryView />);
    const legacy = screen.getByTestId("agent-legacy");
    expect(within(legacy).queryAllByTestId("agent-activity")).toHaveLength(0);
    expect(within(legacy).getByTestId("agent-legacy-hedge-fund-architect")).toHaveTextContent("BLOCKED_LEGACY_RECONCILIATION");
    expect(within(legacy).getByTestId("agent-legacy-sniper-engine")).toHaveTextContent("Aucun statut opérationnel");
  });

  it("n'expose aucune commande de lancement, d'arrêt, de trading ou de délégation", () => {
    const { container } = render(<AgentRegistryView />);
    expect(container.querySelectorAll("button, form, input, select")).toHaveLength(0);
    expect(container.textContent).not.toMatch(/Lancer|Démarrer|Arrêter|Stopper|Acheter|Vendre|Déléguer/);
  });

  it("une preuve contrôlée ne s'applique qu'à un runner vérifié", () => {
    const reg: AgentRegistry = JSON.parse(JSON.stringify(AGENT_REGISTRY));
    const diag = reg.agents.find((a) => a.id === "system-diagnostic")!;
    diag.wiring_status = "VERIFIED";
    diag.runner_id = "runner-test";
    const records: ActivityEvidence[] = [
      { agent_id: "system-diagnostic", runner_id: "runner-test", observed_at_utc: "2026-11-21T19:59:00Z", last_activity_at_utc: "2026-11-21T19:50:00Z", server_proof_ref: "test#1", execution_state: "EN_COURS" as const, outcome: null },
      { agent_id: "repo-architect", runner_id: "runner-test", observed_at_utc: "2026-11-21T19:59:00Z", last_activity_at_utc: "2026-11-21T19:50:00Z", server_proof_ref: "test#2" },
    ];
    render(<AgentRegistryPanel registry={reg} evidence={{ status: "OK", records }} nowMs={NOW} />);
    expect(within(screen.getByTestId("agent-profile-system-diagnostic")).getByTestId("agent-activity")).toHaveAttribute("data-light", "GREEN");
    expect(within(screen.getByTestId("agent-profile-repo-architect")).getByTestId("agent-activity")).toHaveAttribute("data-light", "GRAY");
    expect(within(screen.getByTestId("agent-family-MAINTENANCE")).getByTestId("agent-family-count")).toHaveTextContent("1 profil · 1 vert · 0 rouge · 0 gris");
  });
});
