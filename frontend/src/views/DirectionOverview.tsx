import React from "react";
import { useFinancialReconciliation } from "../lib/financialReconciliationClient";
import type { FinancialReconciliationState } from "../lib/financialReconciliationClient";
import { useMarketSnapshot } from "../lib/marketClient";
import type { MarketState } from "../lib/marketClient";
import { useResearchLabSnapshot } from "../lib/researchLabClient";
import type { ResearchLabState } from "../lib/researchLabClient";
import { useOperatorSnapshot } from "../lib/snapshotClient";
import type { SnapshotState } from "../lib/snapshotClient";
import type { ObservedValue } from "../lib/observedValue";

const unavailable = [
  "File de décisions",
  "Agents",
  "Bounties",
  "Économie AIC",
  "Coûts réels",
  "Sécurité / dette / incidents",
];

function observed(value: ObservedValue<unknown>): string {
  if (value.value === null || value.value === undefined) return value.semantics;
  if (typeof value.value === "boolean") return value.value ? "TRUE" : "FALSE";
  return String(value.value);
}

type DirectionApiErrorState = Extract<
  SnapshotState | FinancialReconciliationState | MarketState | ResearchLabState,
  { status: "api_error" }
>;

function apiError(state: DirectionApiErrorState): string {
  return state.error.error_code ?? state.error.error_message ?? `HTTP ${state.httpStatus}`;
}


type ProvenanceStripProps = {
  testId: string;
  endpoint: string;
  domain: string;
  authority: string;
  generatedAt: string;
  freshness: string;
  age: string;
};

const ProvenanceStrip: React.FC<ProvenanceStripProps> = ({
  testId,
  endpoint,
  domain,
  authority,
  generatedAt,
  freshness,
  age,
}) => (
  <div className="direction-source-strip" data-testid={testId}>
    <span><b>Source</b> {endpoint}</span>
    <span><b>Domaine</b> {domain}</span>
    <span><b>Autorité</b> {authority}</span>
    <span><b>Produit à</b> {generatedAt}</span>
    <span><b>Fraîcheur</b> {freshness}</span>
    <span><b>Âge</b> {age}</span>
  </div>
);

const GlobalStateCard: React.FC<{ state: SnapshotState }> = ({ state }) => {
  if (state.status === "loading") {
    return <article className="direction-card direction-card-governed" data-testid="direction-global-card"><h3>État global</h3><strong>CHARGEMENT</strong><p>Lecture du snapshot opérateur gouverné.</p></article>;
  }
  if (state.status === "api_error") {
    return <article className="direction-card direction-card-governed direction-card-error" data-testid="direction-global-card"><h3>État global</h3><strong>ERREUR SOURCE</strong><p>{apiError(state)}</p></article>;
  }
  if (state.status === "transport_error") {
    return <article className="direction-card direction-card-governed direction-card-error" data-testid="direction-global-card"><h3>État global</h3><strong>ERREUR TRANSPORT / CONTRAT</strong><p>{state.message}</p></article>;
  }

  const s = state.snapshot;
  return (
    <article className="direction-card direction-card-governed" data-testid="direction-global-card">
      <div className="direction-card-heading">
        <h3>État global</h3>
        <span className="direction-card-badge">INCONNU</span>
      </div>
      <ProvenanceStrip
        testId="direction-provenance-global"
        endpoint="/api/operator/v1/snapshot"
        domain="canonical_advisor_presentation"
        authority="PAR CHAMP · AUCUNE AUTORITÉ GLOBALE"
        generatedAt={s.generated_at_utc}
        freshness={s.freshness_classification}
        age={s.snapshot_age_s === null ? "NOT_AVAILABLE" : `${s.snapshot_age_s}s`}
      />
      <dl className="direction-fact-grid">
        <div><dt>Mode</dt><dd>{s.portfolio.mode}</dd></div>
        <div><dt>Runtime</dt><dd>{s.runtime_state}</dd></div>
        <div><dt>Instance</dt><dd>{s.instance_relation}</dd></div>
        <div><dt>Worktree</dt><dd>{s.worktree_state}</dd></div>
        <div><dt>Fraîcheur</dt><dd>{s.freshness_classification}</dd></div>
        <div><dt>Âge snapshot</dt><dd>{s.snapshot_age_s === null ? "NOT_AVAILABLE" : `${s.snapshot_age_s}s`}</dd></div>
        <div><dt>Advisor · boot_alive observation</dt><dd>{observed(s.system_health.boot_alive)}</dd></div>
        <div><dt>Health level · producteur</dt><dd>{observed(s.system_health.health_level)}</dd></div>
        <div><dt>Watchdog</dt><dd>NON DÉPLOYÉ</dd></div>
        <div><dt>Alertes critiques</dt><dd>NON DÉPLOYÉ</dd></div>
      </dl>
      <details className="direction-provenance">
        <summary>Voir provenance</summary>
        <dl className="direction-fact-grid">
          <div><dt>Endpoint</dt><dd>/api/operator/v1/snapshot</dd></div>
          <div><dt>Domaine</dt><dd>canonical_advisor_presentation</dd></div>
          <div><dt>Snapshot ID</dt><dd>{s.snapshot_id}</dd></div>
          <div><dt>Process instance ID</dt><dd>{s.process_instance_id}</dd></div>
          <div><dt>Runtime source SHA</dt><dd>{s.source_sha ?? "UNKNOWN"}</dd></div>
          <div><dt>Preuve SHA</dt><dd>{s.runtime_sha_evidence_status}</dd></div>
          <div><dt>Généré</dt><dd>{s.generated_at_utc}</dd></div>
          <div><dt>Stale reason</dt><dd>{s.stale_reason ?? "NOT_AVAILABLE"}</dd></div>
        </dl>
      </details>
    </article>
  );
};

const ActiveExperimentCard: React.FC<{ state: FinancialReconciliationState }> = ({ state }) => {
  if (state.status === "loading") {
    return <article className="direction-card direction-card-governed" data-testid="direction-experiment-card"><h3>Expérience active</h3><strong>CHARGEMENT</strong><p>Lecture de l’observation financière FIN-02.</p></article>;
  }
  if (state.status === "api_error") {
    return <article className="direction-card direction-card-governed direction-card-error" data-testid="direction-experiment-card"><h3>Expérience active</h3><strong>ERREUR SOURCE</strong><p>{apiError(state)}</p></article>;
  }
  if (state.status === "transport_error") {
    return <article className="direction-card direction-card-governed direction-card-error" data-testid="direction-experiment-card"><h3>Expérience active</h3><strong>ERREUR TRANSPORT / CONTRAT</strong><p>{state.message}</p></article>;
  }

  const s = state.snapshot;
  const f = s.financial;
  const reconciliationDiffers = f.reconciliation_status !== s.reconciliation.overall_status;

  return (
    <article className="direction-card direction-card-governed" data-testid="direction-experiment-card">
      <div className="direction-card-heading">
        <h3>Expérience active</h3>
        <span className="direction-card-badge">{s.freshness_classification}</span>
      </div>
      <ProvenanceStrip
        testId="direction-provenance-experiment"
        endpoint="/api/operator/v1/financial-reconciliation"
        domain={s.domain}
        authority={s.authority}
        generatedAt={s.generated_at_utc}
        freshness={s.freshness_classification}
        age={`${s.snapshot_age_s}s`}
      />
      <div className="direction-epoch-id">{s.paper_epoch_id}</div>
      <dl className="direction-fact-grid">
        <div><dt>Cash disponible</dt><dd>{f.cash_available} {s.asset}</dd></div>
        <div><dt>Capital réservé</dt><dd>{f.capital_reserved} {s.asset}</dd></div>
        <div><dt>Capital déployé</dt><dd>{f.capital_deployed} {s.asset}</dd></div>
        <div><dt>Capital unresolved</dt><dd>{f.capital_unresolved} {s.asset}</dd></div>
        <div><dt>PnL réalisé</dt><dd>{f.realized_pnl ?? f.evidence_status}</dd></div>
        <div><dt>Frais</dt><dd>{f.fees_paid} {s.asset}</dd></div>
        <div><dt>Positions OPEN</dt><dd>{f.open_position_count}</dd></div>
        <div><dt>Positions settled</dt><dd>{f.settled_position_count}</dd></div>
        <div><dt>Positions unresolved</dt><dd>{f.unresolved_position_count}</dd></div>
        <div><dt>Réconciliation FIN</dt><dd>{f.reconciliation_status}</dd></div>
        <div><dt>Réconciliation globale</dt><dd>{s.reconciliation.overall_status}</dd></div>
        <div><dt>Unreconciled capital</dt><dd>{s.reconciliation.unreconciled_capital ?? "NOT_AVAILABLE"}</dd></div>
      </dl>
      {reconciliationDiffers && <p className="direction-warning">Les deux statuts de réconciliation diffèrent ; aucun statut n’est masqué.</p>}
      <div className="direction-not-available" aria-label="Métriques actives non disponibles">
        <span>Population · NOT_AVAILABLE</span>
        <span>PF · NOT_AVAILABLE</span>
        <span>WR · NOT_AVAILABLE</span>
        <span>Expectancy · NOT_AVAILABLE</span>
        <span>MaxDD · NOT_AVAILABLE</span>
      </div>
      <details className="direction-provenance">
        <summary>Voir provenance</summary>
        <dl className="direction-fact-grid">
          <div><dt>Endpoint</dt><dd>/api/operator/v1/financial-reconciliation</dd></div>
          <div><dt>Domaine</dt><dd>{s.domain}</dd></div>
          <div><dt>Epoch ID</dt><dd>{s.paper_epoch_id}</dd></div>
          <div><dt>Financial snapshot ID</dt><dd>{s.financial_snapshot_id}</dd></div>
          <div><dt>Reconciliation ID</dt><dd>{s.reconciliation_id}</dd></div>
          <div><dt>Source stream digest</dt><dd>{s.source_stream_digest}</dd></div>
          <div><dt>Source FIN</dt><dd>{s.source_code_sha}</dd></div>
          <div><dt>FIN code SHA</dt><dd>{s.fin_code_sha}</dd></div>
          <div><dt>Reconciliation code SHA</dt><dd>{s.reconciliation_code_sha}</dd></div>
          <div><dt>Config hash</dt><dd>{s.config_hash}</dd></div>
          <div><dt>Généré</dt><dd>{s.generated_at_utc}</dd></div>
          <div><dt>Âge snapshot</dt><dd>{s.snapshot_age_s}s</dd></div>
          <div><dt>Evidence</dt><dd>{f.evidence_status}</dd></div>
          <div><dt>Autorité</dt><dd>{s.authority}</dd></div>
        </dl>
      </details>
    </article>
  );
};

const MarketCard: React.FC<{ state: MarketState }> = ({ state }) => {
  if (state.status === "loading") {
    return <article className="direction-card direction-card-governed" data-testid="direction-market-card"><h3>Marché</h3><strong>CHARGEMENT</strong><p>Lecture de CryptoRadar en observation.</p></article>;
  }
  if (state.status === "api_error") {
    return <article className="direction-card direction-card-governed direction-card-error" data-testid="direction-market-card"><h3>Marché</h3><strong>ERREUR SOURCE</strong><p>{apiError(state)}</p></article>;
  }
  if (state.status === "transport_error") {
    return <article className="direction-card direction-card-governed direction-card-error" data-testid="direction-market-card"><h3>Marché</h3><strong>ERREUR TRANSPORT / CONTRAT</strong><p>{state.message}</p></article>;
  }

  const s = state.snapshot;
  return (
    <article className="direction-card direction-card-governed" data-testid="direction-market-card">
      <div className="direction-card-heading">
        <h3>Marché</h3>
        <span className="direction-card-badge">{s.authority}</span>
      </div>
      <ProvenanceStrip
        testId="direction-provenance-market"
        endpoint="/api/operator/v1/market"
        domain={s.domain}
        authority={s.authority}
        generatedAt={s.generated_at_utc}
        freshness={s.freshness_classification}
        age={`${s.snapshot_age_s}s`}
      />
      <dl className="direction-fact-grid">
        <div><dt>Mode</dt><dd>{s.mode}</dd></div>
        <div><dt>Fraîcheur</dt><dd>{s.freshness_classification}</dd></div>
        <div><dt>Fenêtre</dt><dd>{s.window_hours}h</dd></div>
        <div><dt>Packets observés</dt><dd>{s.packets_observed}</dd></div>
        <div><dt>Régime marché</dt><dd>{s.market_regime ?? "NOT_AVAILABLE"}</dd></div>
        <div><dt>Univers</dt><dd>{s.universe_size}</dd></div>
        <div><dt>Actionable observés</dt><dd>{s.actionable_count}</dd></div>
        <div><dt>Watchlist</dt><dd>{s.watchlist_count}</dd></div>
      </dl>
      <p className="direction-boundary">Actionable = observation uniquement. Cette carte ne crée aucune permission de trade.</p>
      <details className="direction-provenance">
        <summary>Voir provenance</summary>
        <dl className="direction-fact-grid">
          <div><dt>Endpoint</dt><dd>/api/operator/v1/market</dd></div>
          <div><dt>Domaine</dt><dd>{s.domain}</dd></div>
          <div><dt>Produit</dt><dd>{s.product}</dd></div>
          <div><dt>Autorité</dt><dd>{s.authority}</dd></div>
          <div><dt>Généré</dt><dd>{s.generated_at_utc}</dd></div>
          <div><dt>Source mise à jour</dt><dd>{s.source_updated_at_utc ?? "NOT_AVAILABLE"}</dd></div>
          <div><dt>Âge snapshot</dt><dd>{s.snapshot_age_s}s</dd></div>
        </dl>
      </details>
    </article>
  );
};

const ResearchCard: React.FC<{ state: ResearchLabState }> = ({ state }) => {
  if (state.status === "loading") {
    return <article className="direction-card direction-card-governed" data-testid="direction-research-card"><h3>Research</h3><strong>CHARGEMENT</strong><p>Lecture de la projection Research non autoritaire.</p></article>;
  }
  if (state.status === "api_error") {
    return <article className="direction-card direction-card-governed direction-card-error" data-testid="direction-research-card"><h3>Research</h3><strong>ERREUR SOURCE</strong><p>{apiError(state)}</p></article>;
  }
  if (state.status === "transport_error") {
    return <article className="direction-card direction-card-governed direction-card-error" data-testid="direction-research-card"><h3>Research</h3><strong>ERREUR TRANSPORT / CONTRAT</strong><p>{state.message}</p></article>;
  }

  const s = state.snapshot;
  const p = s.provenance.primary_context;
  return (
    <article className="direction-card direction-card-governed" data-testid="direction-research-card">
      <div className="direction-card-heading">
        <h3>Research</h3>
        <span className="direction-card-badge">RESEARCH NON-AUTORITAIRE</span>
      </div>
      <ProvenanceStrip
        testId="direction-provenance-research"
        endpoint="/api/operator/v1/research-lab"
        domain={s.domain}
        authority={s.authority}
        generatedAt={s.generated_at_utc}
        freshness="NOT_AVAILABLE"
        age="NOT_AVAILABLE"
      />
      <dl className="direction-fact-grid">
        <div><dt>État Research</dt><dd>{s.research_state}</dd></div>
        <div><dt>Population dataset N</dt><dd>{s.population.n}</dd></div>
        <div><dt>Evidence</dt><dd>{s.population.evidence_status}</dd></div>
        <div><dt>Force statistique</dt><dd>{s.population.statistical_strength}</dd></div>
        <div><dt>Candidats</dt><dd>{s.candidate_registry.candidate_count}</dd></div>
        <div><dt>Autorité</dt><dd>{s.authority}</dd></div>
      </dl>
      <p className="direction-boundary">Les faits Research décrivent leur dataset uniquement et ne remplissent jamais les métriques PAPER actives.</p>
      <details className="direction-provenance">
        <summary>Voir provenance</summary>
        <dl className="direction-fact-grid">
          <div><dt>Endpoint</dt><dd>/api/operator/v1/research-lab</dd></div>
          <div><dt>Domaine</dt><dd>{s.domain}</dd></div>
          <div><dt>Dataset</dt><dd>{p.dataset_id}</dd></div>
          <div><dt>Source boundary</dt><dd>{p.source_boundary_id}</dd></div>
          <div><dt>Epoch PAPER référencée</dt><dd>{p.paper_epoch_id ?? "NOT_AVAILABLE"}</dd></div>
          <div><dt>Research run</dt><dd>{p.research_run_id}</dd></div>
          <div><dt>Diagnostic run</dt><dd>{p.diagnostic_run_id ?? "NOT_AVAILABLE"}</dd></div>
          <div><dt>Research source SHA</dt><dd>{p.research_source_code_sha}</dd></div>
          <div><dt>Research config hash</dt><dd>{p.research_config_hash ?? "NOT_AVAILABLE"}</dd></div>
          <div><dt>Presentation builder SHA</dt><dd>{s.presentation_builder_source_sha}</dd></div>
          <div><dt>Généré</dt><dd>{s.generated_at_utc}</dd></div>
        </dl>
      </details>
    </article>
  );
};

export const DirectionOverview: React.FC = () => {
  const operatorState = useOperatorSnapshot();
  const financialState = useFinancialReconciliation();
  const marketState = useMarketSnapshot();
  const researchState = useResearchLabSnapshot();

  return (
    <div className="direction-stack" data-testid="direction-view">
      <section className="direction-intro">
        <div><div className="direction-eyebrow">SURFACE PROPRIÉTAIRE · PRÉSENTATION / GOUVERNANCE</div><h2>Vue Direction</h2></div>
        <span className="direction-status-unknown">ÉTAT GLOBAL · INCONNU</span>
      </section>

      <aside className="direction-federation-notice" data-testid="direction-federation-notice">
        <strong>FÉDÉRÉ · NON ATOMIQUE</strong>
        <span>4 sources indépendantes · aucun timestamp global · aucune fraîcheur globale · aucun état de santé global dérivé.</span>
      </aside>

      <section className="direction-primary-grid" aria-label="Synthèse gouvernée Direction">
        <GlobalStateCard state={operatorState} />
        <ActiveExperimentCard state={financialState} />
      </section>

      <section className="direction-primary-grid" aria-label="Observatoires Direction">
        <MarketCard state={marketState} />
        <ResearchCard state={researchState} />
      </section>

      <section className="direction-grid" aria-label="Capacités Direction futures">
        {unavailable.map((label) => <article className="direction-card" key={label}><h3>{label}</h3><strong>NON DÉPLOYÉ</strong><p>Aucune projection gouvernée n’est disponible pour ce bloc.</p></article>)}
      </section>

      <p className="direction-boundary">Les cartes Direction sont fédérées, non atomiques et conservent chacune leur propre temps d’observation et leur propre statut de fraîcheur. Direction ne crée aucune vérité scientifique, aucun timestamp global et aucune fraîcheur globale ; elle ne peut ni merger, ni déployer, ni modifier l’epoch PAPER active.</p>
    </div>
  );
};
