// ── Preuve d'invocation du Repository Cartographer (lecture seule) ─────────
//
// Lit la route serveur `agent-invocations/repository-cartographer`, la convertit en
// `EvidenceSource` et la réévalue pendant que la page reste ouverte. Une coupure API
// retire toute preuve précédente : aucun voyant vert ne reste figé.
// Désactivé par défaut : seul le build avec VITE_CARTOGRAPHER_INVOCATION=1 interroge l'API.

import { useEffect, useState } from "react";
import {
  AGENT_REGISTRY,
  RUNTIME_EVIDENCE_SOURCE,
  type ActivityEvidence,
  type AgentIdentity,
  type EvidenceSource,
} from "./agentRegistry";

export const CARTOGRAPHER_INVOCATION_URL = "/api/operator/v1/agent-invocations/repository-cartographer";
export const INVOCATION_POLL_MS = 30_000;
export const CLOCK_TICK_MS = 15_000;
export const INVOCATION_FLAG_ON = import.meta.env.VITE_CARTOGRAPHER_INVOCATION === "1";

export interface InvocationSummary {
  connection: string | null;
  connection_reason: string | null;
  activity: string | null;
  activity_reason: string | null;
  last_activity_utc: string | null;
  last_result: string | null;
  last_state: string | null;
  invocation_id: string | null;
  observed_at_utc: string | null;
  agent_id: string;
  runner_id: string;
}

const FAILED_STATES = ["FAILED", "TIMEOUT", "INTERRUPTED", "ABANDONED"];

export function outcomeOf(state: string | null): "FIN_NORMALE" | "ECHEC" | null {
  if (state === "COMPLETED") return "FIN_NORMALE";
  if (state && FAILED_STATES.includes(state)) return "ECHEC";
  return null;
}

/** Convertit le résumé serveur en source d'évidence, sans rien inventer. */
export function evidenceFromInvocation(s: InvocationSummary, agent: AgentIdentity): EvidenceSource {
  if (s.agent_id !== agent.id || s.runner_id !== agent.runner_id) {
    return { status: "API_ERROR", code: "IDENTITE_INATTENDUE" };
  }
  if (s.activity === "EN_COURS") {
    const rec: ActivityEvidence = {
      agent_id: agent.id,
      runner_id: agent.runner_id as string,
      observed_at_utc: s.observed_at_utc ?? "",
      last_activity_at_utc: s.last_activity_utc,
      server_proof_ref: s.invocation_id ?? "bail-en-cours",
      execution_state: "EN_COURS",
      outcome: null,
    };
    return { status: "OK", records: [rec] };
  }
  if (s.connection === "AVAILABLE") {
    const rec: ActivityEvidence = {
      agent_id: agent.id,
      runner_id: agent.runner_id as string,
      observed_at_utc: s.observed_at_utc ?? "",
      last_activity_at_utc: s.last_activity_utc,
      server_proof_ref: s.invocation_id ?? "invocation",
      execution_state: s.activity === "TERMINE" ? "TERMINE" : "INDETERMINE",
      outcome: outcomeOf(s.last_state),
    };
    return { status: "OK", records: [rec] };
  }
  if (s.connection === "ABSENT") return { status: "OK", records: [] };
  return { status: "API_ERROR", code: `${s.connection ?? "INCONNU"}: ${s.connection_reason ?? "motif absent"}` };
}

interface State {
  summary: InvocationSummary | null;
  failed: boolean;
  loaded: boolean;
  nowMs: number;
}

/** Lecture périodique et réévaluation de l'âge pendant que la page reste ouverte. */
export function useInvocationEvidence(enabled: boolean): { evidence: EvidenceSource; nowMs: number; summary: InvocationSummary | null } {
  const [state, setState] = useState<State>({ summary: null, failed: false, loaded: false, nowMs: Date.now() });

  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;
    const load = async () => {
      try {
        const r = await fetch(CARTOGRAPHER_INVOCATION_URL, { headers: { Accept: "application/json" }, cache: "no-store" });
        if (!r.ok) throw new Error(String(r.status));
        const body = (await r.json()) as InvocationSummary;
        if (!cancelled) setState((p) => ({ ...p, summary: body, failed: false, loaded: true, nowMs: Date.now() }));
      } catch {
        // Coupure : l'ancienne preuve disparaît tout de suite.
        if (!cancelled) setState((p) => ({ ...p, summary: null, failed: true, loaded: true, nowMs: Date.now() }));
      }
    };
    void load();
    const poll = window.setInterval(load, INVOCATION_POLL_MS);
    const tick = window.setInterval(() => setState((p) => ({ ...p, nowMs: Date.now() })), CLOCK_TICK_MS);
    return () => {
      cancelled = true;
      window.clearInterval(poll);
      window.clearInterval(tick);
    };
  }, [enabled]);

  const agent = AGENT_REGISTRY.agents.find((a) => a.id === "repository-cartographer");
  if (!enabled || !agent) return { evidence: RUNTIME_EVIDENCE_SOURCE, nowMs: Date.now(), summary: null };
  if (!state.loaded) return { evidence: { status: "LOADING" }, nowMs: state.nowMs, summary: null };
  if (state.failed || !state.summary) return { evidence: { status: "UNREACHABLE" }, nowMs: state.nowMs, summary: null };
  return { evidence: evidenceFromInvocation(state.summary, agent), nowMs: state.nowMs, summary: state.summary };
}
