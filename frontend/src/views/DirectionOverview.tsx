import React from "react";
import { fr } from "../lib/presentationFr";
import { formatDecimalText } from "../lib/decimalPresentation";
import { useRuntimeService } from "../lib/runtimeServiceClient";
import { RuntimeServiceCard } from "./RuntimeServiceView";
import { useBurnInStatus } from "../lib/burnInStatusClient";
import type { BurnInState } from "../lib/burnInStatusClient";
import { useFinancialReconciliation } from "../lib/financialReconciliationClient";
import type { FinancialReconciliationState } from "../lib/financialReconciliationClient";
import { useMarketSnapshot } from "../lib/marketClient";
import type { MarketState } from "../lib/marketClient";
import { useResearchLabSnapshot } from "../lib/researchLabClient";
import type { ResearchLabState } from "../lib/researchLabClient";
import { useOperatorSnapshot } from "../lib/snapshotClient";
import type { SnapshotState } from "../lib/snapshotClient";
import type { ObservedValue } from "../lib/observedValue";
import type { OpenPosition, PortfolioStatus } from "../types";

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

function shortIdentity(value: string | null): string {
  if (value === null) return "UNKNOWN";
  return value.length > 14 ? `${value.slice(0, 12)}…` : value;
}

function formatPositionAgeAtSnapshot(openedAt: number | null, generatedAtUtc: string): string {
  if (openedAt === null || !Number.isFinite(openedAt)) return "NOT_AVAILABLE";
  const generatedMs = Date.parse(generatedAtUtc);
  if (!Number.isFinite(generatedMs)) return "NOT_AVAILABLE";

  const ageSeconds = Math.floor(generatedMs / 1000 - openedAt);
  if (ageSeconds < 0) return "INCOHÉRENT";

  const days = Math.floor(ageSeconds / 86400);
  const hours = Math.floor((ageSeconds % 86400) / 3600);
  const minutes = Math.floor((ageSeconds % 3600) / 60);

  if (days > 0) return `${days}j ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m`;
  return `${ageSeconds}s`;
}

type AdmissionPresentation = {
  limit: string;
  state: string;
  consistent: boolean | null;
};

function admissionPresentation(
  currentCount: ObservedValue<number>,
  status: PortfolioStatus | undefined,
): AdmissionPresentation {
  if (status === undefined) {
    return { limit: "NOT_AVAILABLE", state: "NOT_AVAILABLE", consistent: null };
  }

  if (currentCount.value === null) {
    return {
      limit: String(status.hard_position_limit),
      state: `NON VALIDÉ · ${currentCount.semantics}`,
      consistent: null,
    };
  }

  if (currentCount.value !== status.current_positions) {
    return {
      limit: String(status.hard_position_limit),
      state: "INCOHÉRENT",
      consistent: false,
    };
  }

  return {
    limit: String(status.hard_position_limit),
    state: status.admission_state,
    consistent: true,
  };
}

const PositionOwnerRow: React.FC<{
  position: OpenPosition;
  generatedAtUtc: string;
}> = ({ position, generatedAtUtc }) => (
  <div className="direction-position-row" data-testid="direction-owner-position">
    <div>
      <strong>{position.symbol}</strong>
      <span>{position.side ?? "NOT_AVAILABLE"}</span>
    </div>
    <div>
      <span>Taille</span>
      <strong>{position.size_usd ?? "NOT_AVAILABLE"}</strong>
    </div>
    <div>
      <span>PnL latent</span>
      <strong>{observed(position.unrealized_pnl_usd)}</strong>
    </div>
    <div>
      <span>Régime</span>
      <strong>{observed(position.regime)}</strong>
    </div>
    <div>
      <span>Âge à la capture · UI</span>
      <strong>{formatPositionAgeAtSnapshot(position.opened_at, generatedAtUtc)}</strong>
    </div>
  </div>
);

type DirectionApiErrorState = Extract<
  SnapshotState | FinancialReconciliationState | MarketState | ResearchLabState | BurnInState,
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
  const p = s.portfolio;
  const admission = admissionPresentation(p.paper_open_positions_count, p.portfolio_status);
  const positions = Array.isArray(p.open_positions.value) ? p.open_positions.value : [];

  return (
    <article className="direction-card direction-card-governed direction-owner-card" data-testid="direction-global-card">
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
      <div className="direction-owner-pulse" data-testid="direction-owner-pulse">
        <div>
          <span>Mode</span>
          <strong>{p.mode}</strong>
          <small>canonique · non inféré</small>
        </div>
        <div>
          <span>Capital PAPER</span>
          <strong>{observed(p.paper_equity_usd)}</strong>
          <small>{p.paper_equity_usd.semantics}</small>
        </div>
        <div>
          <span>Positions PAPER</span>
          <strong>{observed(p.paper_open_positions_count)} / {admission.limit}</strong>
          <small>compteur canonique / plafond producteur</small>
        </div>
        <div>
          <span>Admission portefeuille</span>
          <strong>{admission.state}</strong>
          <small>{admission.consistent === true ? "compteurs cohérents" : admission.consistent === false ? "compteurs divergents" : "validation indisponible"}</small>
        </div>
        <div>
          <span>Snapshot</span>
          <strong>{s.freshness_classification}</strong>
          <small>{s.snapshot_age_s === null ? "âge NOT_AVAILABLE" : `âge ${s.snapshot_age_s}s`}</small>
        </div>
        <div>
          <span>Runtime source</span>
          <strong>{shortIdentity(s.source_sha)}</strong>
          <small>{s.runtime_sha_evidence_status}</small>
        </div>
      </div>

      {admission.consistent === false && p.portfolio_status !== undefined && (
        <p className="direction-warning" data-testid="direction-admission-inconsistent">
          Compteurs divergents : admission non fiable pour le niveau 1. portfolio_status.current_positions={p.portfolio_status.current_positions}
          {" "}≠ paper_open_positions_count={observed(p.paper_open_positions_count)}. Aucun état d’admission n’est déduit.
        </p>
      )}

      <dl className="direction-fact-grid direction-owner-facts">
        <div><dt>Runtime</dt><dd>{s.runtime_state}</dd></div>
        <div><dt>Instance</dt><dd>{s.instance_relation}</dd></div>
        <div><dt>Worktree</dt><dd>{s.worktree_state}</dd></div>
        <div><dt>Âge snapshot</dt><dd>{s.snapshot_age_s === null ? "NOT_AVAILABLE" : `${s.snapshot_age_s}s`}</dd></div>
        <div><dt>Stale reason</dt><dd>{s.stale_reason ?? "NOT_AVAILABLE"}</dd></div>
        <div><dt>Inventaire positions</dt><dd>{p.open_positions.semantics}</dd></div>
        <div><dt>PnL réalisé PAPER</dt><dd>{observed(p.paper_realized_pnl_usd)}</dd></div>
        <div><dt>Advisor · boot_alive observation</dt><dd>{observed(s.system_health.boot_alive)}</dd></div>
        <div><dt>Health level · producteur</dt><dd>{observed(s.system_health.health_level)}</dd></div>
        <div><dt>Watchdog</dt><dd>NON DÉPLOYÉ</dd></div>
        <div><dt>Alertes critiques</dt><dd>NON DÉPLOYÉ</dd></div>
      </dl>

      {positions.length > 0 && (
        <section className="direction-owner-positions" data-testid="direction-owner-positions">
          <div className="direction-owner-section-head">
            <strong>Positions ouvertes · snapshot opérateur</strong>
            <span>{p.open_positions.semantics}</span>
          </div>
          <div className="direction-position-list">
            {positions.map((position) => (
              <PositionOwnerRow
                key={position.position_id || position.symbol}
                position={position}
                generatedAtUtc={s.generated_at_utc}
              />
            ))}
          </div>
          <p>Âge à la capture = calcul de présentation entre opened_at et generated_at_utc du même snapshot. Ce n’est ni un timeout PPL ni une deadline scientifique.</p>
        </section>
      )}
      <details className="direction-provenance">
        <summary>Voir provenance</summary>
        <dl className="direction-fact-grid">
          <div><dt>Endpoint</dt><dd>/api/operator/v1/snapshot</dd></div>
          <div><dt>Domaine</dt><dd>canonical_advisor_presentation</dd></div>
          <div><dt>Snapshot ID</dt><dd>{s.snapshot_id}</dd></div>
          <div><dt>Process instance ID</dt><dd>{s.process_instance_id}</dd></div>
          <div><dt>Runtime source SHA</dt><dd>{s.source_sha ?? "UNKNOWN"}</dd></div>
          <div><dt>Preuve SHA</dt><dd>{s.runtime_sha_evidence_status}</dd></div>
          <div><dt>Positions PAPER · compteur</dt><dd>{observed(p.paper_open_positions_count)}</dd></div>
          <div><dt>Plafond producteur</dt><dd>{p.portfolio_status?.hard_position_limit ?? "NOT_AVAILABLE"}</dd></div>
          <div><dt>Admission brute producteur</dt><dd>{p.portfolio_status?.admission_state ?? "NOT_AVAILABLE"}</dd></div>
          <div><dt>Généré</dt><dd>{s.generated_at_utc}</dd></div>
          <div><dt>Stale reason</dt><dd>{s.stale_reason ?? "NOT_AVAILABLE"}</dd></div>
        </dl>
      </details>
    </article>
  );
};

const BurnInCard: React.FC<{ state: BurnInState }> = ({ state }) => {
  if (state.status === "loading") {
    return <article className="direction-card direction-card-governed direction-burnin-card" data-testid="direction-burnin-card"><h3>Burn-in</h3><strong>CHARGEMENT</strong><p>Lecture de la projection PPL U2.</p></article>;
  }
  if (state.status === "api_error") {
    return <article className="direction-card direction-card-governed direction-card-error direction-burnin-card" data-testid="direction-burnin-card"><h3>Burn-in</h3><strong>ERREUR SOURCE</strong><p>{apiError(state)}</p></article>;
  }
  if (state.status === "transport_error") {
    return <article className="direction-card direction-card-governed direction-card-error direction-burnin-card" data-testid="direction-burnin-card"><h3>Burn-in</h3><strong>ERREUR TRANSPORT / CONTRAT</strong><p>{state.message}</p></article>;
  }

  const s = state.snapshot;
  return (
    <article className="direction-card direction-card-governed direction-burnin-card" data-testid="direction-burnin-card">
      <div className="direction-card-heading">
        <h3>Burn-in actif</h3>
        <span className="direction-card-badge">{s.freshness_classification}</span>
      </div>
      <ProvenanceStrip
        testId="direction-provenance-burnin"
        endpoint="/api/operator/v1/burn-in"
        domain={s.domain}
        authority={s.authority}
        generatedAt={s.generated_at_utc}
        freshness={s.freshness_classification}
        age={`${s.snapshot_age_s}s`}
      />
      <div className="direction-epoch-id">{s.paper_epoch_id}</div>
      <div className="direction-burnin-pulse">
        <div><span>Événements</span><strong>{s.event_count}</strong><small>last seq {s.last_sequence}</small></div>
        <div><span>OPEN</span><strong>{s.lifecycle_counts.open}</strong><small>courants</small></div>
        <div><span>CLOSED</span><strong>{s.lifecycle_counts.closed}</strong><small>résolus connus</small></div>
        <div><span>UNRESOLVED</span><strong>{s.lifecycle_counts.unresolved}</strong><small>outcome inconnu</small></div>
        <div><span>T0 scientifique</span><strong>{s.scientific_t0.status}</strong><small>{s.scientific_t0.value_utc ?? "NOT_AVAILABLE"}</small></div>
        <div><span>Dernier événement</span><strong>{s.last_event.event_type}</strong><small>#{s.last_event.sequence}</small></div>
      </div>
      {s.open_lifecycles.length > 0 && (
        <div className="direction-burnin-open" data-testid="direction-burnin-open">
          {s.open_lifecycles.map((row) => (
            <div key={row.trade_id}>
              <strong>{row.symbol}</strong>
              <span>{row.side} · {row.deadline_state}</span>
              <small>{Math.floor(row.age_seconds / 3600)}h · timeout {row.timeout_at_utc ?? "NOT_AVAILABLE"}</small>
            </div>
          ))}
        </div>
      )}
      <details className="direction-provenance">
        <summary>Voir provenance / config</summary>
        <dl className="direction-fact-grid">
          <div><dt>Runtime source SHA</dt><dd>{s.source_code_sha}</dd></div>
          <div><dt>Config hash</dt><dd>{s.config_snapshot_hash}</dd></div>
          <div><dt>PPL stream SHA</dt><dd>{s.ppl_stream_sha256}</dd></div>
          <div><dt>PB_MAX_POSITIONS</dt><dd>{s.frozen_config.pb_max_positions}</dd></div>
          <div><dt>MEXC_SIM_MAX_AGE_H</dt><dd>{s.frozen_config.mexc_sim_max_age_h}</dd></div>
          <div><dt>Finalisation</dt><dd>{s.finalization.state}</dd></div>
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
        <span className="direction-card-badge">RECHERCHE NON AUTORITAIRE</span>
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
        <div><dt>Candidats publiés dans cette projection</dt><dd>{s.candidate_registry.candidate_count}</dd></div>
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
  const runtimeServiceState = useRuntimeService();
  const operatorState = useOperatorSnapshot();
  const burnInState = useBurnInStatus();
  const financialState = useFinancialReconciliation();
  const marketState = useMarketSnapshot();
  const researchState = useResearchLabSnapshot();

  const runtime = runtimeServiceState.status === "success" ? runtimeServiceState.snapshot : null;
  const burn = burnInState.status === "success" ? burnInState.snapshot : null;
  const finance = financialState.status === "success" ? financialState.snapshot : null;
  const market = marketState.status === "success" ? marketState.snapshot : null;
  const advisor = runtime && runtime.freshness_classification === "FRESH" && runtime.service.query_status === "OK"
    ? fr(runtime.service.active_state) : "Inconnu";
  const amount = (v: string | null | undefined) => v == null ? "Non disponible" : formatDecimalText(v);
  const sourceStatus = (state: { status: string }, freshness?: string) =>
    state.status === "success" ? fr(freshness) : state.status === "loading" ? "Chargement…" : "Source indisponible";

  return (
    <div className="direction-stack" data-testid="direction-view">
      <section className="machine-lead">
        <div><span className="workspace-eyebrow">MACHINE · LECTURE SEULE</span><h2>Comprendre la situation</h2></div>
        <p>État global inconnu : aucune synthèse de santé certifiée.</p>
        <dl className="machine-pulse">
          <div><dt>Advisor observé</dt><dd>{advisor}</dd><small>{sourceStatus(runtimeServiceState, runtime?.freshness_classification)}</small></div>
          <div><dt>Disponible · {finance?.asset ?? "unité non disponible"}</dt><dd>{amount(finance?.financial.cash_available)}</dd><small>{sourceStatus(financialState, finance?.freshness_classification)}</small></div>
          <div><dt>Positions de l’expérience</dt><dd>{burn ? `${burn.lifecycle_counts.open} ouvertes` : "Non disponible"}</dd><small>{sourceStatus(burnInState, burn?.freshness_classification)}</small></div>
        </dl>
        <nav className="category-links" aria-label="Catégories Machine">
          <a href="#machine-state">État</a><a href="#machine-finance">Portefeuille et finances</a><a href="#machine-market">Marché</a>
        </nav>
      </section>
      <aside className="direction-federation-notice" data-testid="direction-federation-notice">
        <strong>Sources indépendantes</strong><span>Les dates et fraîcheurs sont propres à chaque source. Aucun état global ni observation simultanée ne sont déduits.</span>
      </aside>
      <section className="machine-section" id="machine-state" aria-label="État et expérience">
        <h2>État</h2>
        <dl className="summary-facts">
          <div><dt>Advisor · service observé</dt><dd>{advisor}</dd><small>{sourceStatus(runtimeServiceState, runtime?.freshness_classification)} · {runtime?.observed_at_utc ?? "Date non disponible"}</small></div>
          <div><dt>Expérience observée</dt><dd>{burn ? `${burn.lifecycle_counts.open} ouvertes · ${burn.lifecycle_counts.closed} clôturées` : sourceStatus(burnInState)}</dd><small>{burn ? `${burn.lifecycle_counts.unresolved} non résolues · ${fr(burn.freshness_classification)} · ${burn.generated_at_utc}` : "Population non disponible"}</small></div>
          <div><dt>Dernier événement</dt><dd>{burn ? fr(burn.last_event.event_type) : "Non disponible"}</dd><small>{burn?.last_event.timestamp_utc ?? "Date non disponible"}</small></div>
        </dl>
        <p className="attention-line">{runtime?.freshness_classification === "STALE" ? "Preuve Advisor périmée : état actuel inconnu. " : ""}{burn?.freshness_classification === "STALE" ? "Expérience : données anciennes. " : ""}Alertes critiques non déployées ; leur absence ne prouve pas une machine saine.</p>
        <details className="section-evidence"><summary>Expérience, état du service et preuves complètes</summary>
          <BurnInCard state={burnInState} /><RuntimeServiceCard state={runtimeServiceState} testId="direction-runtime-service-card" /><GlobalStateCard state={operatorState} />
        </details>
        <a className="section-link" href="/paper-live/burn-in">Explorer l’expérience →</a>
      </section>
      <section className="machine-section" id="machine-finance" aria-label="Portefeuille et finances">
        <div className="section-heading"><h2>Portefeuille et finances</h2><span>{sourceStatus(financialState, finance?.freshness_classification)}</span></div>
        <p className="source-date">Observation FIN : {finance?.generated_at_utc ?? "Date non disponible"}{finance && ` · ${finance.asset}`}</p>
        <dl className="summary-facts">
          <div><dt>Capital disponible</dt><dd>{amount(finance?.financial.cash_available)}</dd></div>
          <div><dt>Principal réservé</dt><dd>{amount(finance?.financial.capital_reserved)}</dd></div>
          <div><dt>Capital non résolu</dt><dd>{amount(finance?.financial.capital_unresolved)}</dd></div>
          <div><dt>Résultat réalisé</dt><dd>{amount(finance?.financial.realized_pnl)}</dd></div>
          <div><dt>Résultat latent</dt><dd>{amount(finance?.financial.unrealized_pnl)}</dd></div>
          <div><dt>Frais payés</dt><dd>{amount(finance?.financial.fees_paid)}</dd></div>
        </dl>
        <p>Réconciliation : {finance ? fr(finance.reconciliation.overall_status) : "Non disponible"} · fonds PAPER.</p>
        <p className="source-date">Source FIN : /api/operator/v1/financial-reconciliation · observation indépendante de la capture PPL. Les courbes et leurs preuves sont dans Finance.</p>
        <details className="section-evidence"><summary>Montants exacts, rapprochement et provenance</summary><ActiveExperimentCard state={financialState} /></details>
        <div className="category-links"><a href="/paper-live/portfolio">Positions →</a><a href="/paper-live/finance">Réconciliation →</a></div>
      </section>
      <section className="machine-section" id="machine-market" aria-label="Marché observé">
        <div className="section-heading"><h2>Marché</h2><span>{sourceStatus(marketState, market?.freshness_classification)}</span></div>
        <dl className="summary-facts">
          <div><dt>Univers observé</dt><dd>{market?.universe_size ?? "Non disponible"}</dd></div>
          <div><dt>Régime publié</dt><dd>{fr(market?.market_regime)}</dd></div>
          <div><dt>Couverture du scanner</dt><dd>{market ? `${market.top_opportunities.length} lignes / ${market.actionable_count} au seuil` : "Non disponible"}</dd></div>
        </dl>
        <p className="source-date">{market?.generated_at_utc ?? "Date non disponible"} · observations sans permission de trading.</p>
        {market && market.top_opportunities.length < market.actionable_count && <p className="attention-line">Couverture partielle : recherche limitée aux lignes publiées.</p>}
        <details className="section-evidence"><summary>Contexte du marché et provenance</summary><MarketCard state={marketState} /></details>
        <a className="section-link" href="/paper-live/market">Explorer CryptoRadar →</a>
      </section>
      <details className="machine-section"><summary>Recherche et capacités non déployées</summary>
        <ResearchCard state={researchState} />
        <p>{unavailable.join(" · ")} : NON DÉPLOYÉ. Aucune projection gouvernée disponible.</p>
        <a className="section-link" href="/research">Ouvrir le Laboratoire quantitatif →</a>
      </details>
    </div>
  );
};
