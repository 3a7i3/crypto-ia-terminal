// ── AgentRegistryView — équipe recensée et état de préparation ─────────────
//
// Affiche le registre source des profils d'agents par famille. Lecture seule :
// aucun bouton de lancement, d'arrêt, de trading ou de délégation. Le voyant
// d'activité vient de `classifyActivity` et reste gris sans preuve serveur.

import React from "react";
import "../agents/agentRegistry.css";
import {
  INVOCATION_FLAG_ON,
  useInvocationEvidence,
  type InvocationSummary,
} from "../agents/invocationEvidence";
import {
  AGENT_REGISTRY,
  FAMILY_ORDER,
  GITHUB_SOURCE_BASE,
  MAX_PROOF_AGE_S,
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

const AgentProfile: React.FC<{ agent: AgentIdentity; verdict: ActivityVerdict }> = ({ agent, verdict }) => (
  <article className="agent-profile" data-testid={`agent-profile-${agent.id}`}>
    <h4>{agent.display_name}</h4>
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
  </article>
);

const countLights = (verdicts: ActivityVerdict[]) => {
  const c = { GREEN: 0, RED: 0, GRAY: 0 };
  verdicts.forEach((v) => (c[v.light] += 1));
  return c;
};

export const AgentRegistryPanel: React.FC<{
  registry: AgentRegistry;
  evidence: EvidenceSource;
  nowMs: number;
}> = ({ registry, evidence, nowMs }) => {
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
          const verdicts = agents.map((a) => classifyActivity(a, evidence, nowMs));
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
                    <AgentProfile key={a.id} agent={a} verdict={verdicts[i]} />
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

const ACTIVITY_LABEL: Record<string, string> = {
  EN_COURS: "En cours",
  TERMINE: "Terminé",
  INDETERMINE: "Indéterminé",
};

const RESULT_LABEL: Record<string, string> = {
  COMPLETE: "COMPLETE",
  PARTIAL: "PARTIAL",
  BLOCKED: "BLOCKED",
  FAILED: "FAILED",
};

/** Trois états séparés : connexion et preuve, activité, dernier résultat. */
export const InvocationProofCard: React.FC<{ summary: InvocationSummary | null; nowMs: number; unavailable?: boolean }> = ({
  summary,
  nowMs,
  unavailable,
}) => {
  const observed = summary?.observed_at_utc ? Date.parse(summary.observed_at_utc) : NaN;
  const stale = summary !== null && Number.isFinite(observed) && nowMs - observed > MAX_PROOF_AGE_S * 1000;
  const connection = unavailable || !summary ? "Coupure API ou preuve non reçue" : CONNECTION_LABEL[summary.connection ?? ""] ?? "Inconnue";
  const activityKey = summary && !stale ? summary.activity ?? "" : "";
  const activity = stale ? "Preuve périmée : état non attesté" : ACTIVITY_LABEL[activityKey] ?? "Non attesté";
  const greenAllowed = !stale && summary?.activity === "EN_COURS";
  const failedEnd = !stale && summary?.activity === "TERMINE" && ["FAILED", "TIMEOUT", "INTERRUPTED", "ABANDONED"].includes(summary?.last_state ?? "");
  // Vert : exécution en cours attestée. Rouge : inactivité attestée. Gris : non attestable.
  const activityLight = greenAllowed ? "green" : summary?.activity === "TERMINE" && !stale ? "red" : "gray";
  return (
    <section className="invocation-card" data-testid="invocation-card" aria-label="Preuve d'invocation du Repository Cartographer">
      <h3>Repository Cartographer · preuve d'invocation</h3>
      <dl>
        <div data-testid="invocation-connection">
          <dt>Connexion et preuve</dt>
          <dd>
            {connection}
            {summary?.connection_reason ? <span className="invocation-reason"> · {summary.connection_reason}</span> : null}
          </dd>
        </div>
        <div data-testid="invocation-activity" data-green={greenAllowed ? "yes" : "no"}>
          <dt>Activité</dt>
          <dd>
            <span className={`invocation-light invocation-light-${activityLight}`} aria-hidden="true" />
            {activity}
            {failedEnd ? <span className="invocation-reason"> · échec ({summary?.last_state})</span> : null}
            {summary?.last_activity_utc && !stale ? <span className="invocation-reason"> · {summary.last_activity_utc}</span> : null}
          </dd>
        </div>
        <div data-testid="invocation-result">
          <dt>Dernier résultat</dt>
          <dd>
            {summary?.last_result ? RESULT_LABEL[summary.last_result] ?? summary.last_result : "Aucun résultat attesté"}
            {summary?.last_result === "PARTIAL" ? (
              <span className="invocation-reason"> · PARTIAL ne signifie pas une panne</span>
            ) : null}
          </dd>
        </div>
      </dl>
      <p className="invocation-foot">
        Lecture seule. Terminé ≠ en cours : une mission réussie ne prouve pas que le runner travaille encore.
        Vert seulement pour une exécution en cours attestée par une preuve fraîche.
      </p>
    </section>
  );
};

const LiveAgentRegistryView: React.FC = () => {
  const { evidence, nowMs, summary } = useInvocationEvidence(true);
  return (
    <>
      <AgentRegistryPanel registry={AGENT_REGISTRY} evidence={evidence} nowMs={nowMs} />
      <InvocationProofCard summary={summary} nowMs={nowMs} unavailable={evidence.status === "UNREACHABLE"} />
    </>
  );
};

const StaticAgentRegistryView: React.FC = () => (
  <AgentRegistryPanel registry={AGENT_REGISTRY} evidence={RUNTIME_EVIDENCE_SOURCE} nowMs={Date.now()} />
);

export const AgentRegistryView: React.FC = () =>
  INVOCATION_FLAG_ON ? <LiveAgentRegistryView /> : <StaticAgentRegistryView />;
