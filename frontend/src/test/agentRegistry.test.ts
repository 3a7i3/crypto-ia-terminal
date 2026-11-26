import { describe, it, expect } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import { createHash } from "node:crypto";
import { resolve } from "node:path";
import registryJson from "../agents/agentIdentityRegistry.v1.json";
import {
  AGENT_REGISTRY,
  FAMILY_ORDER,
  MAX_PROOF_AGE_S,
  RUNTIME_EVIDENCE_SOURCE,
  agentsOfFamily,
  classifyActivity,
  legacyAgents,
  validateRegistry,
  type ActivityEvidence,
  type AgentIdentity,
  type EvidenceSource,
} from "../agents/agentRegistry";

const REPO_ROOT = resolve(__dirname, "../../..");
const gitBlobSha1 = (buf: Buffer) =>
  createHash("sha1").update(Buffer.concat([Buffer.from(`blob ${buf.length}\0`), buf])).digest("hex");

const clone = () => JSON.parse(JSON.stringify(registryJson));

describe("registre des identités d'agents", () => {
  it("recense 13 profils distincts avec identifiants et sources uniques", () => {
    expect(AGENT_REGISTRY.agents).toHaveLength(13);
    expect(new Set(AGENT_REGISTRY.agents.map((a) => a.id)).size).toBe(13);
    expect(new Set(AGENT_REGISTRY.agents.map((a) => a.source_path)).size).toBe(13);
  });

  it("chaque source existe dans le dépôt et correspond à l'empreinte enregistrée", () => {
    for (const a of AGENT_REGISTRY.agents) {
      const p = resolve(REPO_ROOT, a.source_path);
      expect(existsSync(p), a.source_path).toBe(true);
      expect(gitBlobSha1(readFileSync(p)), a.source_path).toBe(a.source_blob_sha1);
    }
  });

  it("couvre exactement les 13 profils .agent.md présents sous .github", () => {
    const expected = [
      ".github/agents/data-provenance-auditor.agent.md",
      ".github/agents/decision-path-forensic.agent.md",
      ".github/agents/hedge-fund-architect.agent.md",
      ".github/agents/market-observer.agent.md",
      ".github/agents/mission-preparation-researcher.agent.md",
      ".github/agents/observability-cartographer.agent.md",
      ".github/agents/repository-cartographer.agent.md",
      ".github/agents/security-Guardian-agent.agent.md",
      ".github/agents/sniper-engine.agent.md",
      ".github/agents/statistician-agent.agent.md",
      ".github/agents/system-diagnostic.agent.md",
      ".github/repo-architect.agent.md",
      ".github/research-scientist.agent.md",
    ];
    expect(AGENT_REGISTRY.agents.map((a) => a.source_path).sort()).toEqual(expected);
  });

  it("définit six familles dans l'ordre validé", () => {
    expect(AGENT_REGISTRY.families.map((f) => f.label)).toEqual([
      "Observation",
      "Recherche",
      "Évaluation",
      "Risque et gouvernance",
      "Exécution PAPER",
      "Maintenance",
    ]);
    expect(AGENT_REGISTRY.families.map((f) => f.id)).toEqual(FAMILY_ORDER);
  });

  it("répartit 11 profils en familles et bloque deux héritages", () => {
    const counts = FAMILY_ORDER.map((f) => agentsOfFamily(AGENT_REGISTRY, f).length);
    expect(counts).toEqual([5, 2, 1, 2, 0, 1]);
    expect(legacyAgents(AGENT_REGISTRY).map((a) => a.id).sort()).toEqual(["hedge-fund-architect", "sniper-engine"]);
    for (const a of legacyAgents(AGENT_REGISTRY)) {
      expect(a.validation_status).toBe("BLOCKED_LEGACY_RECONCILIATION");
      expect(a.wiring_status).toBe("BLOCKED");
      expect(a.family).toBeNull();
    }
  });

  it("ne qualifie aucun profil PAPER et ne relie que le cartographe, le DPA et l'Observateur Marché (décisions opérateur 2026-11-22/23)", () => {
    expect(agentsOfFamily(AGENT_REGISTRY, "EXECUTION_PAPER")).toHaveLength(0);
    const wired = AGENT_REGISTRY.agents.filter((a) => a.wiring_status === "VERIFIED" || a.runner_id !== null);
    expect(wired.map((a) => [a.id, a.runner_id])).toEqual([
      ["data-provenance-auditor", "obs-data-provenance-ro-01"],
      ["repository-cartographer", "obs-repo-cartographer-ro-01"],
      ["market-observer", "obs-market-ro-01"],
    ]);
  });

  it("ne contient ni secret ni donnée d'exécution", () => {
    const text = JSON.stringify(registryJson);
    expect(text).not.toMatch(/token|password|secret_|api_key|private_key|BEGIN [A-Z ]*KEY/i);
    expect(text).not.toMatch(/last_activity|observed_at|heartbeat|\bpid\b|main_pid/i);
    for (const a of AGENT_REGISTRY.agents)
      expect(Object.keys(a).sort()).toEqual(
        [
          "display_name",
          "family",
          "id",
          "legacy_blocked",
          "mission",
          "runner_id",
          "source_blob_sha1",
          "source_path",
          "validation_note",
          "validation_status",
          "wiring_status",
        ].sort(),
      );
  });

  it("rejette les registres incohérents", () => {
    const dup = clone();
    dup.agents[1].id = dup.agents[0].id;
    expect(() => validateRegistry(dup)).toThrow(/dupliqué/);
    const paper = clone();
    paper.agents[0].family = "EXECUTION_PAPER";
    expect(() => validateRegistry(paper)).toThrow(/PAPER/);
    const legacy = clone();
    legacy.agents[11].family = "OBSERVATION";
    expect(() => validateRegistry(legacy)).toThrow(/héritage/);
    const runner = clone();
    runner.agents.find((a: { wiring_status: string }) => a.wiring_status === "NOT_WIRED")!.runner_id = "runner-x";
    expect(() => validateRegistry(runner)).toThrow(/runner/);
    const path = clone();
    path.agents[0].source_path = "../etc/passwd";
    expect(() => validateRegistry(path)).toThrow(/chemin/);
  });
});

describe("voyant d'activité", () => {
  const NOW = Date.parse("2026-11-21T20:00:00Z");
  const base = AGENT_REGISTRY.agents.find((a) => a.id === "system-diagnostic")!;
  const wired: AgentIdentity = { ...base, wiring_status: "VERIFIED", runner_id: "runner-vps-diag-01" };
  const ev = (over: Partial<ActivityEvidence> = {}): EvidenceSource => ({
    status: "OK",
    records: [
      {
        agent_id: wired.id,
        runner_id: "runner-vps-diag-01",
        observed_at_utc: "2026-11-21T19:58:00Z",
        last_activity_at_utc: "2026-11-21T19:40:00Z",
        server_proof_ref: "journal:runner-vps-diag-01#42",
        execution_state: "TERMINE",
        outcome: "FIN_NORMALE",
        ...over,
      },
    ],
  });

  it("par défaut, les 12 profils sont gris (aucune source branchée)", () => {
    expect(RUNTIME_EVIDENCE_SOURCE.status).toBe("NOT_CONNECTED");
    for (const a of AGENT_REGISTRY.agents) {
      const v = classifyActivity(a, RUNTIME_EVIDENCE_SOURCE, NOW);
      expect(v.light).toBe("GRAY");
      expect(v.reason.length).toBeGreaterThan(10);
    }
  });

  it("vert : runner vérifié, preuve fraîche, exécution en cours attestée", () => {
    const v = classifyActivity(wired, ev({ execution_state: "EN_COURS", last_activity_at_utc: "2026-11-21T19:57:00Z" }), NOW);
    expect(v.light).toBe("GREEN");
    expect(v.last_proof_at_utc).toBe("2026-11-21T19:58:00Z");
  });

  it("une activité récente terminée n'est jamais verte", () => {
    const recent = classifyActivity(wired, ev({ last_activity_at_utc: "2026-11-21T19:59:00Z" }), NOW);
    expect(recent.light).toBe("RED");
    expect(recent.label).toBe("Inactif · fin normale");
  });

  it("rouge distingue fin normale et échec", () => {
    expect(classifyActivity(wired, ev({ outcome: "ECHEC" }), NOW).label).toBe("Inactif · échec");
    expect(classifyActivity(wired, ev({ outcome: "FIN_NORMALE" }), NOW).label).toBe("Inactif · fin normale");
    expect(classifyActivity(wired, ev({ last_activity_at_utc: null }), NOW).light).toBe("RED");
  });

  it("gris sans état d'exécution attesté ou avec bail expiré", () => {
    expect(classifyActivity(wired, ev({ execution_state: undefined }), NOW).light).toBe("GRAY");
    const indet = classifyActivity(wired, ev({ execution_state: "INDETERMINE" }), NOW);
    expect(indet.light).toBe("GRAY");
    expect(indet.reason).toMatch(/bail expiré/);
  });

  it("gris : preuve de cours d'exécution périmée", () => {
    const v = classifyActivity(wired, ev({ execution_state: "EN_COURS", observed_at_utc: "2026-11-21T19:00:00Z" }), NOW);
    expect(v.light).toBe("GRAY");
  });

  it("une preuve valide ne rend jamais vert un profil sans runner vérifié", () => {
    expect(classifyActivity(base, ev(), NOW).light).toBe("GRAY");
    expect(classifyActivity({ ...wired, wiring_status: "NOT_WIRED" }, ev(), NOW).light).toBe("GRAY");
    const legacy = AGENT_REGISTRY.agents.find((a) => a.id === "sniper-engine")!;
    const v = classifyActivity({ ...legacy, runner_id: "runner-vps-diag-01" }, ev({ agent_id: "sniper-engine" }), NOW);
    expect(v.light).toBe("GRAY");
    expect(v.reason).toMatch(/Héritage/);
  });

  const grayCases: [string, EvidenceSource, RegExp][] = [
    ["source non branchée", { status: "NOT_CONNECTED" }, /branchée/],
    ["chargement", { status: "LOADING" }, /cours/],
    ["serveur inaccessible", { status: "UNREACHABLE" }, /inaccessible/],
    ["erreur API", { status: "API_ERROR", code: "HTTP_503" }, /HTTP_503/],
    ["preuve absente", { status: "OK", records: [] }, /Aucune preuve/],
    ["preuve d'un autre agent", ev({ agent_id: "repo-architect" }), /Aucune preuve/],
    ["preuve périmée", ev({ observed_at_utc: new Date(NOW - (MAX_PROOF_AGE_S + 1) * 1000).toISOString() }), /périmée/],
    ["runner différent", ev({ runner_id: "runner-autre" }), /runner différent/],
    ["référence serveur absente", ev({ server_proof_ref: " " }), /référence/],
    ["date d'observation invalide", ev({ observed_at_utc: "hier" }), /invalide/],
    ["date sans fuseau UTC", ev({ observed_at_utc: "2026-11-21T19:58:00" }), /invalide/],
    ["observation future", ev({ observed_at_utc: "2026-11-21T21:00:00Z" }), /futur/],
    ["activité invalide", ev({ last_activity_at_utc: "n/a" }), /invalide/],
    ["activité postérieure à l'observation", ev({ last_activity_at_utc: "2026-11-21T19:59:30Z" }), /postérieure/],
  ];
  it.each(grayCases)("gris : %s", (_label, source, reason) => {
    const v = classifyActivity(wired, source, NOW);
    expect(v.light).toBe("GRAY");
    expect(v.reason).toMatch(reason);
  });

  it("gris : preuves multiples contradictoires", () => {
    const one = ev() as Extract<EvidenceSource, { status: "OK" }>;
    const v = classifyActivity(wired, { status: "OK", records: [...one.records, ...one.records] }, NOW);
    expect(v.light).toBe("GRAY");
  });
});
