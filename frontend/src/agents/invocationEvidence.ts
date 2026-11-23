// ── Preuve d'invocation du Repository Cartographer (lecture seule) ─────────
//
// Contrat d'affichage partagé avec le serveur (`display` de cat.observation.invocation.v1) :
// le serveur décide du voyant (GREEN seulement si identité, preuve, observation de vie et
// fraîcheur sont valides ; RED pour une fin attestée ; GRAY sinon) et fournit
// `valid_until_utc`. L'interface ne recalcule rien : elle VALIDE la réponse à l'exécution,
// peut seulement rétrograder en gris, et retire la couleur à l'échéance sans attendre de
// nouvelle réponse.
//
// L'échéance locale est mesurée sur l'horloge du navigateur à partir de l'instant de
// réception : `reçu + (valid_until − observé côté serveur)`, bornée à DISPLAY_TTL_S. Un écart
// d'horloge entre serveur et navigateur ne prolonge donc jamais la couleur.
//
// Interrogation : une seule requête à la fois, délai maximal par requête (abandon), planifiée
// après la réponse précédente (pas d'accumulation), réponses obsolètes rejetées (numéro de
// séquence et date d'observation serveur), annulation complète au démontage.
// Désactivé par défaut : seul le build avec VITE_CARTOGRAPHER_INVOCATION=1 interroge l'API.

import { useEffect, useMemo, useState } from "react";
import {
  RUNTIME_EVIDENCE_SOURCE,
  type ActivityLight,
  type ActivityVerdict,
  type EvidenceSource,
} from "./agentRegistry";

export const AGENT_INVOCATIONS_BASE = "/api/operator/v1/agent-invocations";
export const invocationUrl = (agentId: string) => `${AGENT_INVOCATIONS_BASE}/${agentId}`;
export const CARTOGRAPHER_INVOCATION_URL = invocationUrl("repository-cartographer");
export const INVOCATION_CONTRACT = "cat.observation.invocation.v1";
/** Intervalle entre la fin d'une réponse et la requête suivante. */
export const INVOCATION_POLL_MS = 30_000;
/** Délai maximal d'une requête : au-delà, abandon et état « coupure ». */
export const REQUEST_TIMEOUT_MS = 10_000;
/** Durée maximale d'affichage d'une couleur sans nouvelle réponse (miroir de DISPLAY_TTL_S). */
export const DISPLAY_TTL_S = 90;
/** Tolérance d'horloge serveur ↔ navigateur pour refuser une date future. */
export const CLOCK_SKEW_S = 60;
export const INVOCATION_FLAG_ON = import.meta.env.VITE_CARTOGRAPHER_INVOCATION === "1";

/** Identité attendue côté serveur (cible autorisée), indépendante de l'état du registre. */
export const EXPECTED_IDENTITY = { id: "repository-cartographer", runner_id: "obs-repo-cartographer-ro-01" } as const;
/** Data Provenance Auditor : même bloc que le cartographe (opérateur, 2026-11-23). */
export const DPA_IDENTITY = { id: "data-provenance-auditor", runner_id: "obs-data-provenance-ro-01" } as const;
/** Observateur Marché : données du VPS (opérateur, 2026-11-23). */
export const MARKET_OBSERVER_IDENTITY = { id: "market-observer", runner_id: "obs-market-ro-01" } as const;
export type ExpectedIdentity = { id: string; runner_id: string | null };

const CONNECTIONS = ["AVAILABLE", "ABSENT", "ACCESS_DENIED", "UNREADABLE", "INCOMPLETE", "INVALID"] as const;
const ACTIVITIES = ["EN_COURS", "TERMINE", "INDETERMINE"] as const;
const LIGHTS = ["GREEN", "RED", "GRAY"] as const;
const RESULTS = ["COMPLETE", "PARTIAL", "BLOCKED", "FAILED"] as const;
const STATES = ["COMPLETED", "FAILED", "TIMEOUT", "INTERRUPTED", "ABANDONED"] as const;
const UTC_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;
const HEX32_RE = /^[0-9a-f]{32}$/;

export interface InvocationDisplay {
  light: ActivityLight;
  label: string;
  reason: string;
  valid_until_utc: string | null;
}

export interface InvocationSummary {
  contract: typeof INVOCATION_CONTRACT;
  agent_id: string;
  runner_id: string;
  mission_id: string;
  server_observed_at_utc: string;
  connection: (typeof CONNECTIONS)[number];
  connection_reason: string | null;
  activity: (typeof ACTIVITIES)[number];
  activity_reason: string | null;
  life_observed: boolean;
  lease_until_utc: string | null;
  last_activity_utc: string | null;
  last_mission_age_s: number | null;
  mission_overdue: boolean;
  last_result: (typeof RESULTS)[number] | null;
  last_state: (typeof STATES)[number] | null;
  invocation_id: string | null;
  display: InvocationDisplay;
  read_only: true;
}

export function parseUtc(v: unknown): number | null {
  if (typeof v !== "string" || !UTC_RE.test(v)) return null;
  const t = Date.parse(v);
  // Date.parse accepte « 2026-02-31 » en le décalant : on exige l'aller-retour exact.
  if (!Number.isFinite(t) || new Date(t).toISOString().replace(/\.000Z$/, "Z") !== v) return null;
  return t;
}

type Parsed = { ok: true; summary: InvocationSummary } | { ok: false; reason: string };

const isStr = (v: unknown): v is string => typeof v === "string";
const strOrNull = (v: unknown) => v === null || isStr(v);
const utcOrNull = (v: unknown) => v === null || parseUtc(v) !== null;
const oneOf = <T extends readonly string[]>(list: T, v: unknown): v is T[number] => isStr(v) && list.includes(v);

/** Validation à l'exécution de la réponse serveur : aucune conversion de type aveugle. */
export function parseInvocationSummary(raw: unknown): Parsed {
  const bad = (reason: string): Parsed => ({ ok: false, reason });
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return bad("réponse non objet");
  const r = raw as Record<string, unknown>;
  if (r.contract !== INVOCATION_CONTRACT) return bad("contrat inconnu");
  if (r.read_only !== true) return bad("réponse non marquée lecture seule");
  if (!isStr(r.agent_id) || !isStr(r.runner_id) || !isStr(r.mission_id)) return bad("identité absente");
  if (parseUtc(r.server_observed_at_utc) === null) return bad("date d'observation serveur absente ou invalide");
  if (!oneOf(CONNECTIONS, r.connection)) return bad("connexion inconnue");
  if (!oneOf(ACTIVITIES, r.activity)) return bad("activité inconnue");
  if (typeof r.life_observed !== "boolean" || typeof r.mission_overdue !== "boolean") return bad("champs booléens invalides");
  if (!strOrNull(r.connection_reason) || !strOrNull(r.activity_reason)) return bad("motifs invalides");
  if (!utcOrNull(r.lease_until_utc) || !utcOrNull(r.last_activity_utc)) return bad("dates invalides");
  if (!(r.last_mission_age_s === null || (typeof r.last_mission_age_s === "number" && r.last_mission_age_s >= 0)))
    return bad("âge de mission invalide");
  if (!(r.last_result === null || oneOf(RESULTS, r.last_result))) return bad("résultat inconnu");
  if (!(r.last_state === null || oneOf(STATES, r.last_state))) return bad("état d'exécution inconnu");
  if (!(r.invocation_id === null || (isStr(r.invocation_id) && HEX32_RE.test(r.invocation_id))))
    return bad("identifiant d'invocation invalide");
  const d = r.display as Record<string, unknown> | null;
  if (typeof d !== "object" || d === null) return bad("contrat d'affichage absent");
  if (!oneOf(LIGHTS, d.light) || !isStr(d.label) || !isStr(d.reason) || !utcOrNull(d.valid_until_utc))
    return bad("contrat d'affichage invalide");
  return { ok: true, summary: raw as InvocationSummary };
}

export interface Received {
  summary: InvocationSummary;
  /** Instant de réception, horloge du navigateur. */
  receivedAtMs: number;
}

const grayVerdict = (reason: string, last: string | null = null): ActivityVerdict => ({
  light: "GRAY",
  label: "Non attesté",
  reason,
  last_proof_at_utc: last,
});

/**
 * Voyant effectif à l'instant `nowMs`. Applique le voyant du serveur ; ne peut que le
 * rétrograder en gris (identité, cohérence, échéance). Ne recalcule aucun verdict.
 */
export function effectiveVerdict(rec: Received | null, agent: ExpectedIdentity, nowMs: number): ActivityVerdict {
  if (!rec) return grayVerdict("Preuve non reçue.");
  const s = rec.summary;
  const observed = parseUtc(s.server_observed_at_utc) as number;
  const seen = s.server_observed_at_utc;
  if (s.agent_id !== agent.id || s.runner_id !== agent.runner_id)
    return grayVerdict("Identité inattendue dans la réponse.", seen);
  if (observed > rec.receivedAtMs + CLOCK_SKEW_S * 1000)
    return grayVerdict("Date d'observation serveur dans le futur.", seen);
  const d = s.display;
  if (d.light === "GRAY") return grayVerdict(d.reason, seen);
  // Garde-fous de cohérence (filtrage, pas recalcul) : une couleur exige son fondement.
  if (d.light === "GREEN" && !(s.activity === "EN_COURS" && s.life_observed && (s.connection === "AVAILABLE" || s.connection === "ABSENT")))
    return grayVerdict("Voyant vert sans exécution en cours attestée.", seen);
  if (d.light === "RED" && !(s.activity === "TERMINE" && s.connection === "AVAILABLE"))
    return grayVerdict("Voyant rouge sans fin attestée.", seen);
  const until = parseUtc(d.valid_until_utc);
  if (until === null) return grayVerdict("Durée de validité absente.", seen);
  const span = Math.min(until - observed, DISPLAY_TTL_S * 1000);
  if (span <= 0) return grayVerdict("Durée de validité déjà échue.", seen);
  if (nowMs >= rec.receivedAtMs + span) return grayVerdict("Preuve échue : aucune nouvelle réponse du serveur.", seen);
  return { light: d.light, label: d.label, reason: d.reason, last_proof_at_utc: seen };
}

/** Instant local (navigateur) où la couleur affichée doit disparaître, ou null si gris. */
export function localExpiryMs(rec: Received | null): number | null {
  if (!rec || rec.summary.display.light === "GRAY") return null;
  const observed = parseUtc(rec.summary.server_observed_at_utc);
  const until = parseUtc(rec.summary.display.valid_until_utc);
  if (observed === null || until === null) return null;
  return rec.receivedAtMs + Math.max(0, Math.min(until - observed, DISPLAY_TTL_S * 1000));
}

export type PollState =
  | { status: "LOADING" }
  | { status: "OK"; received: Received }
  | { status: "UNREACHABLE"; reason: string };

type FetchLike = (url: string, init: RequestInit) => Promise<Response>;

interface PollerOptions {
  fetchImpl?: FetchLike;
  now?: () => number;
  pollMs?: number;
  timeoutMs?: number;
  /** Route de l'agent lu ; défaut : le cartographe. */
  url?: string;
  onChange: (s: PollState) => void;
}

/**
 * Interrogation séquentielle. Au plus une requête en vol ; la suivante est planifiée après
 * la réponse (ou l'abandon). Une réponse plus ancienne que la dernière appliquée est ignorée.
 */
export class InvocationPoller {
  private seq = 0;
  private applied = 0;
  private lastObserved = -Infinity;
  private inflight: AbortController | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private stopped = false;
  private readonly fetchImpl: FetchLike;
  private readonly now: () => number;
  private readonly pollMs: number;
  private readonly timeoutMs: number;
  private readonly onChange: (s: PollState) => void;
  private readonly url: string;

  constructor(o: PollerOptions) {
    this.url = o.url ?? CARTOGRAPHER_INVOCATION_URL;
    this.fetchImpl = o.fetchImpl ?? ((u, i) => fetch(u, i));
    this.now = o.now ?? Date.now;
    this.pollMs = o.pollMs ?? INVOCATION_POLL_MS;
    this.timeoutMs = o.timeoutMs ?? REQUEST_TIMEOUT_MS;
    this.onChange = o.onChange;
  }

  /** Lance une lecture maintenant ; abandonne la lecture en vol éventuelle. */
  refresh(): Promise<void> {
    if (this.stopped) return Promise.resolve();
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    this.inflight?.abort();
    const id = ++this.seq;
    const ctrl = new AbortController();
    this.inflight = ctrl;
    const guard = setTimeout(() => ctrl.abort(), this.timeoutMs);
    return this.fetchImpl(this.url, {
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal: ctrl.signal,
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return parseInvocationSummary(await r.json());
      })
      .then(
        (p) => this.settle(id, p.ok ? { kind: "ok", summary: p.summary } : { kind: "err", reason: `réponse invalide : ${p.reason}` }),
        (e: unknown) => this.settle(id, { kind: "err", reason: ctrl.signal.aborted ? "requête abandonnée (délai dépassé)" : String((e as Error)?.message ?? e) }),
      )
      .finally(() => clearTimeout(guard));
  }

  private settle(id: number, out: { kind: "ok"; summary: InvocationSummary } | { kind: "err"; reason: string }) {
    if (this.stopped || id < this.applied) return;
    // Une réponse d'une requête remplacée est ignorée, sauf si plus aucune n'est attendue.
    if (id !== this.seq) return;
    this.inflight = null;
    this.applied = id;
    if (out.kind === "ok") {
      const observed = parseUtc(out.summary.server_observed_at_utc) as number;
      if (observed < this.lastObserved) {
        // Réponse plus ancienne que celle déjà affichée (cache intermédiaire, inversion) : rejetée.
        this.schedule();
        return;
      }
      this.lastObserved = observed;
      this.onChange({ status: "OK", received: { summary: out.summary, receivedAtMs: this.now() } });
    } else {
      // Coupure ou réponse invalide : la preuve précédente disparaît immédiatement.
      this.onChange({ status: "UNREACHABLE", reason: out.reason });
    }
    this.schedule();
  }

  private schedule() {
    if (this.stopped) return;
    this.timer = setTimeout(() => void this.refresh(), this.pollMs);
  }

  stop() {
    this.stopped = true;
    if (this.timer !== null) clearTimeout(this.timer);
    this.inflight?.abort();
    this.inflight = null;
  }
}

/** Source d'évidence pour le panneau : verdict serveur appliqué, ou état de connexion. */
export function evidenceFromPoll(state: PollState, nowMs: number, expected: ExpectedIdentity = EXPECTED_IDENTITY): EvidenceSource {
  if (state.status === "LOADING") return { status: "LOADING" };
  if (state.status === "UNREACHABLE") return { status: "UNREACHABLE" };
  return {
    status: "SERVER_VERDICT",
    agent_id: expected.id,
    runner_id: expected.runner_id ?? "",
    verdict: effectiveVerdict(state.received, expected, nowMs),
  };
}

/** Lecture périodique + réévaluation exacte à l'échéance pendant que la page reste ouverte. */
export function useInvocationEvidence(
  enabled: boolean,
  opts: { pollMs?: number; timeoutMs?: number; agent?: ExpectedIdentity } = {},
): {
  evidence: EvidenceSource;
  nowMs: number;
  state: PollState;
  verdict: ActivityVerdict;
} {
  const [state, setState] = useState<PollState>({ status: "LOADING" });
  const [nowMs, setNowMs] = useState(Date.now());
  const agent = opts.agent ?? EXPECTED_IDENTITY;
  const agentId = agent.id;

  useEffect(() => {
    if (!enabled) return undefined;
    const p = new InvocationPoller({
      url: invocationUrl(agentId),
      pollMs: opts.pollMs,
      timeoutMs: opts.timeoutMs,
      onChange: (s) => {
        setState(s);
        setNowMs(Date.now());
      },
    });
    void p.refresh();
    return () => p.stop();
  }, [enabled, agentId, opts.pollMs, opts.timeoutMs]);

  // Réveil exact à l'échéance locale : la couleur disparaît sans nouvelle réponse.
  const expiry = state.status === "OK" ? localExpiryMs(state.received) : null;
  useEffect(() => {
    if (expiry === null) return undefined;
    const t = setTimeout(() => setNowMs(Date.now()), Math.max(0, expiry - Date.now()) + 5);
    return () => clearTimeout(t);
  }, [expiry]);

  return useMemo(() => {
    if (!enabled) {
      return { evidence: RUNTIME_EVIDENCE_SOURCE, nowMs, state, verdict: grayVerdict("Lecture désactivée.") };
    }
    const verdict = state.status === "OK" ? effectiveVerdict(state.received, agent, nowMs) : grayVerdict(
      state.status === "LOADING" ? "Lecture de la preuve serveur en cours." : `Coupure : ${state.reason}.`,
    );
    return { evidence: evidenceFromPoll(state, nowMs, agent), nowMs, state, verdict };
  }, [enabled, state, nowMs, agent]);
}
