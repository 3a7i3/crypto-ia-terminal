import { describe, it, expect, afterEach } from "vitest";
import { render, screen, within, cleanup } from "@testing-library/react";
import { evidenceFromInvocation, outcomeOf, type InvocationSummary } from "../agents/invocationEvidence";
import { InvocationProofCard, AgentRegistryPanel } from "../views/AgentRegistryView";
import { AGENT_REGISTRY, classifyActivity, type AgentIdentity } from "../agents/agentRegistry";

const NOW = Date.parse("2026-11-22T01:00:00Z");
const cart = AGENT_REGISTRY.agents.find((a) => a.id === "repository-cartographer")!;
// Profil de test : même identité, runner vérifié (la registre livré reste NOT_WIRED).
const wired: AgentIdentity = { ...cart, wiring_status: "VERIFIED", runner_id: "obs-repo-cartographer-ro-01" };

const base: InvocationSummary = {
  connection: "AVAILABLE",
  connection_reason: "dernière preuve valide",
  activity: "TERMINE",
  activity_reason: "dernière invocation COMPLETED",
  last_activity_utc: "2026-11-22T00:54:21Z",
  last_result: "PARTIAL",
  last_state: "COMPLETED",
  invocation_id: "a".repeat(32),
  observed_at_utc: "2026-11-22T00:59:50Z",
  agent_id: "repository-cartographer",
  runner_id: "obs-repo-cartographer-ro-01",
};

afterEach(() => cleanup());

describe("adaptateur de preuve d'invocation", () => {
  it("PARTIAL terminé : fin normale, jamais vert", () => {
    const ev = evidenceFromInvocation(base, wired);
    expect(ev.status).toBe("OK");
    const v = classifyActivity(wired, ev, NOW);
    expect(v.light).toBe("RED");
    expect(v.label).toBe("Inactif · fin normale");
  });

  it("échec terminal : libellé échec", () => {
    expect(outcomeOf("TIMEOUT")).toBe("ECHEC");
    const ev = evidenceFromInvocation({ ...base, last_state: "TIMEOUT", last_result: null }, wired);
    expect(classifyActivity(wired, ev, NOW).label).toBe("Inactif · échec");
  });

  it("exécution en cours attestée : vert seulement tant que la preuve est fraîche", () => {
    const running: InvocationSummary = { ...base, activity: "EN_COURS", last_activity_utc: "2026-11-22T00:58:00Z" };
    const ev = evidenceFromInvocation(running, wired);
    expect(classifyActivity(wired, ev, NOW).light).toBe("GREEN");
    expect(classifyActivity(wired, ev, NOW + 20 * 60 * 1000).light).toBe("GRAY");
  });

  it("absence ou preuve invalide : gris avec motif visible", () => {
    const absent = evidenceFromInvocation({ ...base, connection: "ABSENT", activity: "INDETERMINE" }, wired);
    expect(classifyActivity(wired, absent, NOW).light).toBe("GRAY");
    const invalid = evidenceFromInvocation({ ...base, connection: "INVALID", connection_reason: "INVALID: empreinte du contenu altérée" }, wired);
    const v = classifyActivity(wired, invalid, NOW);
    expect(v.light).toBe("GRAY");
    expect(v.reason).toMatch(/empreinte du contenu altérée/);
  });

  it("identité inattendue : refus", () => {
    const ev = evidenceFromInvocation({ ...base, runner_id: "autre-runner-01" }, wired);
    expect(ev.status).toBe("API_ERROR");
    expect(classifyActivity(wired, ev, NOW).light).toBe("GRAY");
  });

  it("lire un ancien rapport ne rajeunit pas la date d'activité", () => {
    const ev = evidenceFromInvocation(base, wired);
    const v = classifyActivity(wired, ev, NOW + 3 * 86_400_000);
    expect(v.last_proof_at_utc).toBe("2026-11-22T00:59:50Z");
  });
});

describe("carte de preuve (trois états séparés)", () => {
  it("affiche connexion, activité et dernier résultat séparément", () => {
    render(<InvocationProofCard summary={base} nowMs={NOW} />);
    expect(within(screen.getByTestId("invocation-connection")).getByText(/Disponible/)).toBeInTheDocument();
    expect(within(screen.getByTestId("invocation-activity")).getByText(/Terminé/)).toBeInTheDocument();
    expect(screen.getByTestId("invocation-activity")).toHaveAttribute("data-green", "no");
    expect(within(screen.getByTestId("invocation-result")).getByText(/PARTIAL ne signifie pas une panne/)).toBeInTheDocument();
  });

  it("coupure API : état explicite, aucune activité en cours", () => {
    render(<InvocationProofCard summary={null} nowMs={NOW} unavailable />);
    expect(screen.getByTestId("invocation-connection")).toHaveTextContent("Coupure API");
    expect(screen.getByTestId("invocation-activity")).toHaveAttribute("data-green", "no");
  });

  it("preuve périmée recalculée à l'affichage : gris, motif visible", () => {
    render(<InvocationProofCard summary={{ ...base, activity: "EN_COURS" }} nowMs={NOW + 3600_000} />);
    expect(screen.getByTestId("invocation-activity")).toHaveTextContent("Preuve périmée");
    expect(screen.getByTestId("invocation-activity")).toHaveAttribute("data-green", "no");
  });
});

describe("panneau et drapeau", () => {
  it("le registre livré garde le voyant gris, même avec une preuve en cours", () => {
    const ev = evidenceFromInvocation({ ...base, activity: "EN_COURS" }, cart);
    const v = classifyActivity(cart, ev, NOW);
    expect(v.light).toBe("GRAY");
    expect(v.reason).toMatch(/Préproduction/);
  });

  it("le panneau reste rendu sans régression avec une source non branchée", () => {
    render(<AgentRegistryPanel registry={AGENT_REGISTRY} evidence={{ status: "NOT_CONNECTED" }} nowMs={NOW} />);
    expect(screen.getByTestId("agent-registry")).toBeInTheDocument();
  });
});
