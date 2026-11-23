import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { render, screen, cleanup, act, within } from "@testing-library/react";
import {
  EXPECTED_IDENTITY,
  DISPLAY_TTL_S,
  INVOCATION_POLL_MS,
  InvocationPoller,
  REQUEST_TIMEOUT_MS,
  effectiveVerdict,
  evidenceFromPoll,
  localExpiryMs,
  parseInvocationSummary,
  parseUtc,
  type InvocationSummary,
  type PollState,
  type Received,
} from "../agents/invocationEvidence";
import { InvocationProofCard, AgentRegistryPanel } from "../views/AgentRegistryView";
import { AGENT_REGISTRY, classifyActivity, type AgentIdentity } from "../agents/agentRegistry";

const T0 = Date.parse("2026-11-22T01:00:00Z");
const iso = (ms: number) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");
const cart = AGENT_REGISTRY.agents.find((a) => a.id === "repository-cartographer")!;
// Profil de test : même identité, runner vérifié (le registre livré reste NOT_WIRED).
const wired: AgentIdentity = { ...cart, wiring_status: "VERIFIED", runner_id: "obs-repo-cartographer-ro-01" };

const terminated: InvocationSummary = {
  contract: "cat.observation.invocation.v1",
  agent_id: "repository-cartographer",
  runner_id: "obs-repo-cartographer-ro-01",
  mission_id: "02e0f78f43d1062ee0efed015ad9fe37329dbe480062f02c53e32c82e19fdece",
  server_observed_at_utc: iso(T0),
  connection: "AVAILABLE",
  connection_reason: "dernière preuve valide",
  activity: "TERMINE",
  activity_reason: "dernière invocation COMPLETED (aucun processus ne détient le verrou)",
  life_observed: false,
  lease_until_utc: null,
  last_activity_utc: iso(T0 - 6 * 60_000),
  last_mission_age_s: 360,
  mission_overdue: false,
  last_result: "PARTIAL",
  last_state: "COMPLETED",
  invocation_id: "a".repeat(32),
  display: { light: "RED", label: "Inactif · fin normale", reason: "dernière invocation COMPLETED", valid_until_utc: iso(T0 + 90_000) },
  read_only: true,
};

const running: InvocationSummary = {
  ...terminated,
  activity: "EN_COURS",
  activity_reason: "verrou noyau tenu, bail valide",
  life_observed: true,
  lease_until_utc: iso(T0 + 300_000),
  last_activity_utc: iso(T0 - 5_000),
  display: { light: "GREEN", label: "Actif", reason: "exécution en cours attestée", valid_until_utc: iso(T0 + 90_000) },
};

const rec = (summary: InvocationSummary, receivedAtMs = T0): Received => ({ summary, receivedAtMs });

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("validation à l'exécution de la réponse", () => {
  it("accepte une réponse conforme", () => {
    expect(parseInvocationSummary(running).ok).toBe(true);
  });

  it.each([
    ["non objet", null],
    ["contrat inconnu", { ...running, contract: "autre" }],
    ["date absente", { ...running, server_observed_at_utc: undefined }],
    ["date invalide", { ...running, server_observed_at_utc: "2026-02-31T00:00:00Z" }],
    ["date non UTC", { ...running, server_observed_at_utc: "2026-11-22T01:00:00+02:00" }],
    ["voyant inconnu", { ...running, display: { ...running.display, light: "BLUE" } }],
    ["affichage absent", { ...running, display: undefined }],
    ["activité inconnue", { ...running, activity: "ACTIF" }],
    ["vie non booléenne", { ...running, life_observed: "yes" }],
    ["identifiant malformé", { ...running, invocation_id: "zz" }],
    ["échéance invalide", { ...running, display: { ...running.display, valid_until_utc: "demain" } }],
    ["non lecture seule", { ...running, read_only: false }],
  ])("refuse : %s", (_why, body) => {
    expect(parseInvocationSummary(body).ok).toBe(false);
  });

  it("parseUtc exige l'aller-retour exact", () => {
    expect(parseUtc("2026-11-22T01:00:00Z")).toBe(T0);
    expect(parseUtc("2026-13-40T99:00:00Z")).toBeNull();
  });
});

describe("contrat d'affichage partagé : le serveur décide, l'interface filtre", () => {
  it("terminé : rouge « fin normale », jamais vert", () => {
    const v = effectiveVerdict(rec(terminated), wired, T0 + 1_000);
    expect(v.light).toBe("RED");
    expect(v.label).toBe("Inactif · fin normale");
  });

  it("en cours attesté : vert tant que l'échéance n'est pas atteinte", () => {
    expect(effectiveVerdict(rec(running), wired, T0 + 89_000).light).toBe("GREEN");
    expect(effectiveVerdict(rec(running), wired, T0 + 90_000).light).toBe("GRAY");
  });

  it("INVALID avec EN_COURS : gris, même si le serveur (ou un intermédiaire) annonçait vert", () => {
    const bad = { ...running, connection: "INVALID" as const, connection_reason: "INVALID: empreinte altérée" };
    expect(effectiveVerdict(rec(bad), wired, T0).light).toBe("GRAY");
    const grayFromServer = { ...bad, display: { light: "GRAY" as const, label: "Non attesté", reason: "exécution signalée mais preuve INVALID", valid_until_utc: null } };
    const v = effectiveVerdict(rec(grayFromServer), wired, T0);
    expect(v.light).toBe("GRAY");
    expect(v.reason).toMatch(/preuve INVALID/);
  });

  it("vert sans observation de vie : gris", () => {
    expect(effectiveVerdict(rec({ ...running, life_observed: false }), wired, T0).light).toBe("GRAY");
  });

  it("rouge sans fin attestée : gris", () => {
    expect(effectiveVerdict(rec({ ...terminated, activity: "INDETERMINE" }), wired, T0).light).toBe("GRAY");
  });

  it("mauvaise identité : gris", () => {
    expect(effectiveVerdict(rec({ ...running, runner_id: "autre-runner-01" }), wired, T0).light).toBe("GRAY");
    expect(effectiveVerdict(rec({ ...running, agent_id: "observability-cartographer" }), wired, T0).light).toBe("GRAY");
  });

  it("date d'observation dans le futur : gris", () => {
    const future = { ...running, server_observed_at_utc: iso(T0 + 3_600_000), display: { ...running.display, valid_until_utc: iso(T0 + 3_690_000) } };
    expect(effectiveVerdict(rec(future), wired, T0).light).toBe("GRAY");
  });

  it("échéance absente ou déjà échue : gris", () => {
    expect(effectiveVerdict(rec({ ...running, display: { ...running.display, valid_until_utc: null } }), wired, T0).light).toBe("GRAY");
    expect(effectiveVerdict(rec({ ...running, display: { ...running.display, valid_until_utc: iso(T0) } }), wired, T0).light).toBe("GRAY");
  });

  it("échéance excessive bornée à DISPLAY_TTL_S, mesurée sur l'horloge locale de réception", () => {
    const long = { ...running, display: { ...running.display, valid_until_utc: iso(T0 + 86_400_000) } };
    // Navigateur décalé d'une heure : l'échéance reste « réception + 90 s ».
    const received = rec(long, T0 + 3_600_000);
    expect(localExpiryMs(received)).toBe(T0 + 3_600_000 + DISPLAY_TTL_S * 1000);
    expect(effectiveVerdict(received, wired, T0 + 3_600_000 + DISPLAY_TTL_S * 1000).light).toBe("GRAY");
  });

  it("un profil NOT_WIRED garde le voyant gris, même avec une preuve en cours", () => {
    const ev = evidenceFromPoll({ status: "OK", received: rec(running) }, T0);
    const v = classifyActivity({ ...cart, wiring_status: "NOT_WIRED", runner_id: null }, ev, T0);
    expect(v.light).toBe("GRAY");
    expect(v.reason).toMatch(/Préproduction/);
  });

  it("le registre livré relie le cartographe au runner attendu", () => {
    expect([cart.wiring_status, cart.runner_id]).toEqual(["VERIFIED", EXPECTED_IDENTITY.runner_id]);
  });

  it("profil relié : le panneau applique le verdict serveur filtré", () => {
    const ev = evidenceFromPoll({ status: "OK", received: rec(running) }, T0);
    expect(classifyActivity(wired, ev, T0).light).toBe("GREEN");
    expect(classifyActivity(wired, evidenceFromPoll({ status: "UNREACHABLE", reason: "HTTP 503" }, T0), T0).light).toBe("GRAY");
  });
});

// --- Interrogation : séquentielle, bornée, annulable ---------------------------------------

type Pending = { resolve: (r: Response) => void; reject: (e: unknown) => void; signal: AbortSignal };

function fakeFetch() {
  const calls: Pending[] = [];
  const impl = (u: string, init: RequestInit) =>
    // L'historique du mini terminal a sa propre requête : hors du décompte de la preuve.
    // Les blocs du DPA et de l'Observateur Marché ont leurs propres lectures : hors du décompte du cartographe.
    String(u).includes("data-provenance-auditor") || String(u).includes("market-observer")
      ? new Promise<Response>(() => undefined)
      : String(u).endsWith("/history")
      ? Promise.resolve(new Response(JSON.stringify({ contract: "cat.observation.invocation.v1", read_only: true, connection: "ABSENT", connection_reason: null, total: 0, items: [] }), { status: 200 }))
      : new Promise<Response>((resolve, reject) => {
      const signal = init.signal as AbortSignal;
      signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      calls.push({ resolve, reject, signal });
    });
  return { calls, impl };
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("InvocationPoller", () => {
  beforeEach(() => vi.useFakeTimers({ now: T0 }));

  it("une seule requête en vol : pas d'accumulation si le serveur ne répond pas", async () => {
    const f = fakeFetch();
    const states: PollState[] = [];
    const p = new InvocationPoller({ fetchImpl: f.impl, onChange: (s) => states.push(s) });
    void p.refresh();
    await vi.advanceTimersByTimeAsync(INVOCATION_POLL_MS * 3);
    // La requête bloquée a été abandonnée au délai maximal, puis UNE suivante planifiée.
    expect(f.calls[0].signal.aborted).toBe(true);
    expect(states[0]).toEqual({ status: "UNREACHABLE", reason: "requête abandonnée (délai dépassé)" });
    const inflight = f.calls.filter((c) => !c.signal.aborted);
    expect(inflight.length).toBeLessThanOrEqual(1);
    expect(f.calls.length).toBeLessThanOrEqual(Math.ceil((INVOCATION_POLL_MS * 3) / (INVOCATION_POLL_MS + REQUEST_TIMEOUT_MS)) + 1);
    p.stop();
  });

  it("requête bloquée : gris après le délai maximal, la preuve précédente disparaît", async () => {
    const f = fakeFetch();
    let last = { status: "LOADING" } as PollState;
    const p = new InvocationPoller({ fetchImpl: f.impl, onChange: (s) => (last = s) });
    void p.refresh();
    f.calls[0].resolve(json(running));
    await vi.advanceTimersByTimeAsync(0);
    expect(last.status).toBe("OK");
    await vi.advanceTimersByTimeAsync(INVOCATION_POLL_MS); // requête suivante lancée, jamais servie
    expect(f.calls.length).toBe(2);
    await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS);
    expect(last.status).toBe("UNREACHABLE");
    p.stop();
  });

  it("réponses inversées : une réponse plus ancienne n'écrase jamais la plus récente", async () => {
    const f = fakeFetch();
    const states: PollState[] = [];
    const p = new InvocationPoller({ fetchImpl: f.impl, onChange: (s) => states.push(s) });
    void p.refresh();
    void p.refresh(); // la première est abandonnée et remplacée
    f.calls[1].resolve(json({ ...terminated, server_observed_at_utc: iso(T0 + 10_000), display: { ...terminated.display, valid_until_utc: iso(T0 + 100_000) } }));
    await vi.advanceTimersByTimeAsync(0);
    f.calls[0].resolve(json(running)); // arrive après, ignorée (requête remplacée)
    await vi.advanceTimersByTimeAsync(0);
    expect(states).toHaveLength(1);
    expect(states[0].status === "OK" && states[0].received.summary.activity).toBe("TERMINE");
    // Une réponse plus ancienne servie ensuite (cache intermédiaire) est aussi rejetée.
    void p.refresh();
    f.calls[2].resolve(json(running)); // observée à T0 < T0+10 s
    await vi.advanceTimersByTimeAsync(0);
    expect(states).toHaveLength(1);
    p.stop();
  });

  it("coupure API : état explicite, la preuve précédente est retirée", async () => {
    const f = fakeFetch();
    let last = { status: "LOADING" } as PollState;
    const p = new InvocationPoller({ fetchImpl: f.impl, onChange: (s) => (last = s) });
    void p.refresh();
    f.calls[0].resolve(json(running));
    await vi.advanceTimersByTimeAsync(0);
    void p.refresh();
    f.calls[1].resolve(json({}, 503));
    await vi.advanceTimersByTimeAsync(0);
    expect(last).toEqual({ status: "UNREACHABLE", reason: "HTTP 503" });
    void p.refresh();
    f.calls[2].reject(new TypeError("Failed to fetch"));
    await vi.advanceTimersByTimeAsync(0);
    expect(last.status).toBe("UNREACHABLE");
    p.stop();
  });

  it("réponse non conforme : refusée, jamais convertie aveuglément", async () => {
    const f = fakeFetch();
    let last = { status: "LOADING" } as PollState;
    const p = new InvocationPoller({ fetchImpl: f.impl, onChange: (s) => (last = s) });
    void p.refresh();
    f.calls[0].resolve(json({ ...running, display: { light: "GREEN" } }));
    await vi.advanceTimersByTimeAsync(0);
    expect(last.status).toBe("UNREACHABLE");
    expect(last.status === "UNREACHABLE" && last.reason).toMatch(/réponse invalide/);
    p.stop();
  });

  it("arrêt : requête en vol annulée, plus aucune planification ni notification", async () => {
    const f = fakeFetch();
    const onChange = vi.fn();
    const p = new InvocationPoller({ fetchImpl: f.impl, onChange });
    void p.refresh();
    p.stop();
    expect(f.calls[0].signal.aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(INVOCATION_POLL_MS * 4);
    expect(f.calls).toHaveLength(1);
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("carte de preuve : expiration pendant que la page reste ouverte", () => {
  const carto = () => within(screen.getByTestId("live-agent-repository-cartographer"));
  it("échéance seule : sans aucune nouvelle requête, le vert devient gris à valid_until", async () => {
    vi.useFakeTimers({ now: T0 });
    const f = fakeFetch();
    vi.stubGlobal("fetch", f.impl);
    const { AgentRegistryLiveForTest } = await import("../views/AgentRegistryView");
    // Intervalle supérieur à l'échéance : aucune requête ni abandon avant 90 s.
    render(<AgentRegistryLiveForTest pollMs={10 * 60_000} />);
    await act(async () => {
      f.calls[0].resolve(json(running));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(carto().getByTestId("invocation-activity")).toHaveAttribute("data-light", "GREEN");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DISPLAY_TTL_S * 1000 - 1_000);
    });
    expect(carto().getByTestId("invocation-activity")).toHaveAttribute("data-light", "GREEN");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_010);
    });
    expect(f.calls).toHaveLength(1);
    expect(carto().getByTestId("invocation-activity")).toHaveAttribute("data-light", "GRAY");
    expect(carto().getByTestId("invocation-activity")).toHaveTextContent("Preuve échue");
    vi.unstubAllGlobals();
  });

  it("serveur bloqué en cours de page : gris au plus tard à l'abandon de la requête", async () => {
    vi.useFakeTimers({ now: T0 });
    const f = fakeFetch();
    vi.stubGlobal("fetch", f.impl);
    const { AgentRegistryLiveForTest } = await import("../views/AgentRegistryView");
    render(<AgentRegistryLiveForTest />);
    await act(async () => {
      f.calls[0].resolve(json(running));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(carto().getByTestId("invocation-activity")).toHaveAttribute("data-light", "GREEN");
    // Le serveur ne répond plus : requête suivante à 30 s, abandonnée à 40 s → gris.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(INVOCATION_POLL_MS + REQUEST_TIMEOUT_MS - 10);
    });
    expect(carto().getByTestId("invocation-activity")).toHaveAttribute("data-light", "GREEN");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20);
    });
    expect(carto().getByTestId("invocation-activity")).toHaveAttribute("data-light", "GRAY");
    vi.unstubAllGlobals();
  });
});

describe("carte de preuve (trois états séparés)", () => {
  const show = (state: PollState, nowMs = T0 + 1_000) => {
    const verdict = state.status === "OK" ? effectiveVerdict(state.received, wired, nowMs) : effectiveVerdict(null, wired, nowMs);
    render(<InvocationProofCard state={state} verdict={verdict} nowMs={nowMs} />);
  };

  it("affiche connexion, activité, observation serveur ≠ dernière mission et résultat séparément", () => {
    show({ status: "OK", received: rec(terminated) });
    expect(screen.getByTestId("invocation-connection")).toHaveTextContent("Disponible");
    expect(screen.getByTestId("invocation-activity")).toHaveAttribute("data-light", "RED");
    expect(screen.getByTestId("invocation-activity")).toHaveTextContent("Inactif · fin normale");
    expect(screen.getByTestId("invocation-times")).toHaveTextContent(terminated.server_observed_at_utc);
    expect(screen.getByTestId("invocation-times")).toHaveTextContent(`dernière mission : ${terminated.last_activity_utc}`);
    expect(screen.getByTestId("invocation-result")).toHaveTextContent("PARTIAL ne signifie pas une panne");
  });

  it("règle des 36 h visible", () => {
    show({ status: "OK", received: rec({ ...terminated, mission_overdue: true, display: { ...terminated.display, label: "Inactif · fin normale · aucune mission depuis plus de 36 h" } }) });
    expect(screen.getByTestId("invocation-times")).toHaveTextContent("plus de 36 h");
  });

  it("coupure API : état explicite, aucune activité verte", () => {
    show({ status: "UNREACHABLE", reason: "HTTP 503" });
    expect(screen.getByTestId("invocation-connection")).toHaveTextContent("Coupure API");
    expect(screen.getByTestId("invocation-activity")).toHaveAttribute("data-green", "no");
  });

  it("le panneau reste rendu sans régression avec une source non branchée", () => {
    render(<AgentRegistryPanel registry={AGENT_REGISTRY} evidence={{ status: "NOT_CONNECTED" }} nowMs={T0} />);
    expect(screen.getByTestId("agent-registry")).toBeInTheDocument();
  });
});
