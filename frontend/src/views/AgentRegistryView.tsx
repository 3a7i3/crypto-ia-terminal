// ── AgentRegistryView — équipe recensée et état de préparation ─────────────
//
// Affiche le registre source des profils d'agents par famille. Lecture seule :
// aucun bouton de lancement, d'arrêt, de trading ou de délégation. Le voyant
// d'activité vient de `classifyActivity` et reste gris sans preuve serveur.

import { ScheduleControl, useAgentSchedule } from "../agents/agentSchedule";
import { CartographerMiniTerminal, useInvocationHistory } from "../agents/invocationHistory";
import React from "react";
import "../agents/agentRegistry.css";
import {
  DPA_IDENTITY,
  EXPECTED_IDENTITY,
  INVOCATION_FLAG_ON,
  invocationUrl,
  localExpiryMs,
  parseUtc,
  useInvocationEvidence,
  type ExpectedIdentity,
  type PollState,
} from "../agents/invocationEvidence";
import {
  AGENT_REGISTRY,
  FAMILY_ORDER,
  GITHUB_SOURCE_BASE,
  RUNTIME_EVIDENCE_SOURCE,
  VALIDATION_LABEL,
  WIRING_LABEL,
  agentsOfFamily,
  classifyActivity,
  legacyAgents,
  type ActivityVerdict,
  type AgentIdentity,
  type AgentRegistry,
  type EvidenceSource,
} from "../agents/agentRegistry";

const LIGHT_TEXT: Record<ActivityVerdict["light"], string> = {
  GREEN: "Vert",
  RED: "Rouge",
  GRAY: "Gris",
};

const ActivityLightView: React.FC<{ verdict: ActivityVerdict }> = ({ verdict }) => (
  <div className={`agent-light agent-light-${verdict.light.toLowerCase()}`} data-testid="agent-activity" data-light={verdict.light}>
    <span className="agent-light-dot" aria-hidden="true" />
    <span className="agent-light-text">
      <strong>
        {LIGHT_TEXT[verdict.light]} · {verdict.label}
      </strong>
      <span>{verdict.reason}</span>
    </span>
  </div>
);

const SourceLink: React.FC<{ agent: AgentIdentity }> = ({ agent }) => (
  <a href={`${GITHUB_SOURCE_BASE}${agent.source_path}`} target="_blank" rel="noreferrer" className="agent-source-link">
    {agent.source_path}
  </a>
);

const AgentFacts: React.FC<{ agent: AgentIdentity; verdict: ActivityVerdict }> = ({ agent, verdict }) => (
  <>
    <p className="agent-mission">{agent.mission}</p>
    <ActivityLightView verdict={verdict} />
    <dl className="agent-facts">
      <div>
        <dt>Identifiant</dt>
        <dd>{agent.id}</dd>
      </div>
      <div>
        <dt>Source GitHub</dt>
        <dd>
          <SourceLink agent={agent} />
        </dd>
      </div>
      <div>
        <dt>Validation</dt>
        <dd>
          {VALIDATION_LABEL[agent.validation_status]} ({agent.validation_status}). {agent.validation_note}
        </dd>
      </div>
      <div>
        <dt>Branchement</dt>
        <dd data-testid="agent-wiring">{WIRING_LABEL[agent.wiring_status]}</dd>
      </div>
      <div>
        <dt>Dernière preuve d’activité</dt>
        <dd data-testid="agent-last-proof">{verdict.last_proof_at_utc ?? "Aucune preuve disponible"}</dd>
      </div>
    </dl>
  </>
);

/** Un emplacement reçoit la fiche de l'agent et l'affiche où il veut (ex. sous le titre du terminal). */
export type AgentSlot = (facts: React.ReactNode) => React.ReactNode;

const AgentProfile: React.FC<{ agent: AgentIdentity; verdict: ActivityVerdict; slot?: AgentSlot }> = ({
  agent,
  verdict,
  slot,
}) => {
  const facts = <AgentFacts agent={agent} verdict={verdict} />;
  if (slot) {
    return (
      <article className="agent-profile agent-profile-slotted" data-testid={`agent-profile-${agent.id}`}>
        {slot(facts)}
      </article>
    );
  }
  return (
    <article className="agent-profile" data-testid={`agent-profile-${agent.id}`}>
      <h4>{agent.display_name}</h4>
      {facts}
    </article>
  );
};

const countLights = (verdicts: ActivityVerdict[]) => {
  const c = { GREEN: 0, RED: 0, GRAY: 0 };
  verdicts.forEach((v) => (c[v.light] += 1));
  return c;
};

export const AgentRegistryPanel: React.FC<{
  registry: AgentRegistry;
  evidence: EvidenceSource;
  nowMs: number;
  /** Source de preuve propre à un agent (sinon `evidence`), par identifiant. */
  evidenceByAgent?: Record<string, EvidenceSource>;
  /** Contenu supplémentaire affiché dans le bloc d'un agent (ex. mini terminal), par identifiant. */
  slots?: Record<string, AgentSlot>;
}> = ({ registry, evidence, evidenceByAgent, nowMs, slots }) => {
  const families = FAMILY_ORDER.map((id) => registry.families.find((f) => f.id === id)!);
  const legacy = legacyAgents(registry);
  return (
    <section className="agent-registry" data-testid="agent-registry" aria-labelledby="agent-registry-title">
      <div className="agent-registry-head">
        <h2 id="agent-registry-title">Agents · équipe recensée</h2>
        <p>
          {registry.agents.length - legacy.length} profils répartis en {families.length} familles, plus{" "}
          {legacy.length} profils hérités à arbitrer. Être recensé ne vaut ni exécution, ni activité, ni
          autorisation.
        </p>
        <p className="agent-registry-boundary">
          Les moteurs Python (génération de stratégies, backtest, moteur PAPER, gate de risque) sont des
          composants de la machine, pas des agents autonomes : ils n’apparaissent pas ici.
        </p>
      </div>
      <div className="agent-family-grid">
        {families.map((family) => {
          const agents = agentsOfFamily(registry, family.id);
          const verdicts = agents.map((a) => classifyActivity(a, evidenceByAgent?.[a.id] ?? evidence, nowMs));
          const c = countLights(verdicts);
          return (
            <details className="agent-family-card" key={family.id} data-testid={`agent-family-${family.id}`}>
              <summary>
                <span className="agent-family-title">{family.label}</span>
                <span className="agent-family-count" data-testid="agent-family-count">
                  {agents.length === 0
                    ? "Aucun profil qualifié"
                    : `${agents.length} profil${agents.length > 1 ? "s" : ""} · ${c.GREEN} vert · ${c.RED} rouge · ${c.GRAY} gris`}
                </span>
                <span className="agent-family-summary">{family.summary}</span>
              </summary>
              {agents.length === 0 ? (
                <p className="agent-empty" data-testid="agent-family-empty">
                  Aucun profil qualifié. Aucun profil GitHub n’est autorisé à exécuter, simuler ou proposer des
                  ordres PAPER. Le nom d’un profil hérité ne vaut pas qualification.
                </p>
              ) : (
                <div className="agent-profile-list">
                  {agents.map((a, i) => (
                    <AgentProfile key={a.id} agent={a} verdict={verdicts[i]} slot={slots?.[a.id]} />
                  ))}
                </div>
              )}
            </details>
          );
        })}
      </div>
      <details className="agent-legacy" data-testid="agent-legacy">
        <summary>
          <span className="agent-family-title">Héritage à arbitrer</span>
          <span className="agent-family-count">{legacy.length} profils bloqués · sans statut opérationnel</span>
        </summary>
        <div className="agent-profile-list">
          {legacy.map((a) => (
            <article className="agent-profile agent-profile-legacy" key={a.id} data-testid={`agent-legacy-${a.id}`}>
              <h4>{a.display_name}</h4>
              <p className="agent-mission">{a.mission}</p>
              <dl className="agent-facts">
                <div>
                  <dt>Source GitHub</dt>
                  <dd>
                    <SourceLink agent={a} />
                  </dd>
                </div>
                <div>
                  <dt>Validation</dt>
                  <dd>
                    {VALIDATION_LABEL[a.validation_status]} ({a.validation_status}). {a.validation_note}
                  </dd>
                </div>
                <div>
                  <dt>Statut</dt>
                  <dd>Bloqué en attente d’arbitrage. Aucun statut opérationnel n’est affiché.</dd>
                </div>
              </dl>
            </article>
          ))}
        </div>
      </details>
      <p className="agent-registry-foot">
        Registre source v{registry.registry_version} · métadonnées seulement. Preuve d’activité serveur :{" "}
        {evidence.status === "NOT_CONNECTED" ? "aucune source branchée, tous les voyants restent gris." : evidence.status}
      </p>
    </section>
  );
};

const CONNECTION_LABEL: Record<string, string> = {
  AVAILABLE: "Disponible",
  ABSENT: "Absente",
  ACCESS_DENIED: "Accès refusé",
  UNREADABLE: "Inaccessible",
  INCOMPLETE: "Fichier incomplet",
  INVALID: "Preuve invalide",
};

const RESULT_LABEL: Record<string, string> = {
  COMPLETE: "COMPLETE",
  PARTIAL: "PARTIAL",
  BLOCKED: "BLOCKED",
  FAILED: "FAILED",
};

const LIGHT_CLASS: Record<string, string> = { GREEN: "green", RED: "red", GRAY: "gray" };

/**
 * Trois états séparés : connexion et preuve, activité (voyant du contrat partagé, retiré à
 * l'échéance locale), dernier résultat scientifique. `verdict` vient de `effectiveVerdict`.
 */
export const InvocationProofCard: React.FC<{ state: PollState; verdict: ActivityVerdict; nowMs: number; title?: string }> = ({
  state,
  verdict,
  nowMs,
  title = "Repository Cartographer",
}) => {
  const s = state.status === "OK" ? state.received.summary : null;
  const expiry = state.status === "OK" ? localExpiryMs(state.received) : null;
  const connection =
    state.status === "LOADING"
      ? "Lecture en cours"
      : state.status === "UNREACHABLE"
        ? `Coupure API ou réponse refusée · ${state.reason}`
        : CONNECTION_LABEL[s?.connection ?? ""] ?? "Inconnue";
  // Échéance locale affichée en heure du navigateur ; la couleur s'éteint à cet instant.
  const until = expiry !== null && verdict.light !== "GRAY" && expiry > nowMs
    ? new Date(expiry).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : null;
  return (
    <section className="invocation-card" data-testid="invocation-card" aria-label={`Preuve d'invocation du ${title}`}>
      <h3>{title} · preuve d'invocation</h3>
      <dl>
        <div data-testid="invocation-connection">
          <dt>Connexion et preuve</dt>
          <dd>
            {connection}
            {s?.connection_reason ? <span className="invocation-reason"> · {s.connection_reason}</span> : null}
          </dd>
        </div>
        <div data-testid="invocation-activity" data-light={verdict.light} data-green={verdict.light === "GREEN" ? "yes" : "no"}>
          <dt>Activité</dt>
          <dd>
            <span className={`invocation-light invocation-light-${LIGHT_CLASS[verdict.light]}`} aria-hidden="true" />
            {verdict.label}
            <span className="invocation-reason"> · {verdict.reason}</span>
            {until !== null ? <span className="invocation-reason"> · couleur valable jusqu'à {until} sans nouvelle réponse</span> : null}
          </dd>
        </div>
        <div data-testid="invocation-times">
          <dt>Observation serveur / dernière mission</dt>
          <dd>
            {s ? s.server_observed_at_utc : "—"}
            <span className="invocation-reason">
              {" · dernière mission : "}
              {s?.last_activity_utc ?? "aucune attestée"}
              {s?.mission_overdue ? " · aucune mission depuis plus de 36 h" : ""}
            </span>
          </dd>
        </div>
        <div data-testid="invocation-result">
          <dt>Dernier résultat</dt>
          <dd>
            {s?.last_result ? RESULT_LABEL[s.last_result] ?? s.last_result : "Aucun résultat attesté"}
            {s?.last_result === "PARTIAL" ? (
              <span className="invocation-reason"> · PARTIAL ne signifie pas une panne</span>
            ) : null}
          </dd>
        </div>
      </dl>
      <p className="invocation-foot">
        Lecture seule. Terminé ≠ en cours : une mission réussie ne prouve pas que le runner travaille encore.
        Vert seulement pour une exécution en cours attestée (verrou noyau tenu) ; la couleur s'éteint
        d'elle-même à l'échéance si le serveur ne répond plus.
      </p>
    </section>
  );
};

/** Un agent branché : identité attendue, route du programmateur, libellé du bloc. */
interface LiveAgent {
  identity: ExpectedIdentity;
  title: string;
}
const LIVE_AGENTS: LiveAgent[] = [
  { identity: EXPECTED_IDENTITY, title: "Repository Cartographer" },
  { identity: DPA_IDENTITY, title: "Data Provenance Auditor" },
];

interface LiveAgentData {
  evidence: EvidenceSource;
  nowMs: number;
  slot: AgentSlot;
}

/**
 * Lectures d'un agent branché (preuve, historique, programmateur) et son bloc : gyrophare,
 * mini terminal, bouton ⏰. Le même bloc sert au cartographe et au Data Provenance Auditor.
 */
function useLiveAgent(agent: LiveAgent, pollMs?: number): LiveAgentData {
  const base = invocationUrl(agent.identity.id);
  const sched = useAgentSchedule(true, undefined, `${base}/schedule`);
  // Le passage dure moins d'une seconde : lecture rapprochée autour de l'heure prévue pour
  // que le vert (exécution attestée par le verrou noyau) soit visible.
  const [burst, setBurst] = React.useState(false);
  const next = sched.schedule?.applied && sched.schedule.applied !== "off" ? parseUtc(sched.schedule.next_utc) : null;
  React.useEffect(() => {
    if (next === null) return undefined;
    const startIn = Math.max(0, next - Date.now() - 2_000);
    const a = setTimeout(() => setBurst(true), startIn);
    const b = setTimeout(() => setBurst(false), startIn + 12_000);
    return () => { clearTimeout(a); clearTimeout(b); setBurst(false); };
  }, [next]);
  const { evidence, nowMs, state, verdict } = useInvocationEvidence(true, { pollMs: burst ? 100 : pollMs, agent: agent.identity });
  const history = useInvocationHistory(true, burst ? 3_000 : pollMs, `${base}/history`);
  const off = sched.schedule?.applied === "off";
  const slot: AgentSlot = (facts) => (
    <div data-testid={`live-agent-${agent.identity.id}`}>
      <CartographerMiniTerminal
        title={agent.title}
        info={facts}
        light={off && verdict.light !== "GREEN" ? "GRAY" : verdict.light}
        lightReason={off ? "Agent arrêté (Off)" : `${verdict.label} · ${verdict.reason}`}
        history={history}
        controls={<ScheduleControl schedule={sched.schedule} error={sched.error} sending={sched.sending} onPick={(v) => void sched.request(v)} />}
        footer={
          <details className="invocation-details">
            <summary>Détail de la preuve</summary>
            <InvocationProofCard state={state} verdict={verdict} nowMs={nowMs} title={agent.title} />
          </details>
        }
      />
    </div>
  );
  return { evidence, nowMs, slot };
}

/** Vue branchée (drapeau actif) ; exportée pour les tests d'expiration. */
export const AgentRegistryLiveForTest: React.FC<{ pollMs?: number }> = ({ pollMs }) => {
  // Nombre d'agents fixe (constante du module) : l'ordre des hooks reste stable.
  const carto = useLiveAgent(LIVE_AGENTS[0], pollMs);
  const dpa = useLiveAgent(LIVE_AGENTS[1], pollMs);
  return (
    <AgentRegistryPanel
      registry={AGENT_REGISTRY}
      evidence={carto.evidence}
      evidenceByAgent={{ [DPA_IDENTITY.id]: dpa.evidence }}
      nowMs={Math.max(carto.nowMs, dpa.nowMs)}
      slots={{ [EXPECTED_IDENTITY.id]: carto.slot, [DPA_IDENTITY.id]: dpa.slot }}
    />
  );
};

const StaticAgentRegistryView: React.FC = () => (
  <AgentRegistryPanel registry={AGENT_REGISTRY} evidence={RUNTIME_EVIDENCE_SOURCE} nowMs={Date.now()} />
);

export const AgentRegistryView: React.FC = () =>
  INVOCATION_FLAG_ON ? <AgentRegistryLiveForTest /> : <StaticAgentRegistryView />;
