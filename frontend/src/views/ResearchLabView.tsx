import React from "react";
import { fr } from "../lib/presentationFr";
import { useResearchLabSnapshot } from "../lib/researchLabClient";
import type {
  ResearchAttributionSection,
  ResearchCandidateRow,
  ResearchMetric,
} from "../lib/researchLabTypes";

function displayValue(metric: ResearchMetric): string {
  if (metric.value === null) return metric.evidence_status;
  if (typeof metric.value === "number") {
    return `${metric.value.toLocaleString(undefined, { maximumFractionDigits: 8 })} ${metric.unit}`;
  }
  return `${metric.value} ${metric.unit}`;
}

const MetricCard: React.FC<{ metric: ResearchMetric }> = ({ metric }) => (
  <article className="research-metric-card" data-testid="research-metric-card">
    <div className="research-metric-label">{metric.metric_name}</div>
    <div className={`research-metric-value research-evidence-${metric.evidence_status.toLowerCase()}`}>
      {displayValue(metric)}
    </div>
    <div className="research-metric-meta">
      <span>{metric.evidence_status}</span>
      <span>{metric.statistical_strength}</span>
      <span>N={metric.population_n}</span>
    </div>
    {metric.reason && <div className="research-metric-reason">{metric.reason}</div>}
    <details className="research-metric-details">
      <summary>Preuves</summary>
      <div>Source : {metric.source_ref}</div>
      <div>Dérivation : {metric.derivation}</div>
    </details>
  </article>
);

const MetricSection: React.FC<{
  title: string;
  metrics: ResearchMetric[];
}> = ({ title, metrics }) => (
  <section className="research-panel">
    <div className="research-section-title">{title}</div>
    {metrics.length === 0 ? (
      <div className="research-empty-section">Aucune métrique publiée dans cette catégorie.</div>
    ) : (
      <div className="research-metric-grid">
        {metrics.map((metric) => (
          <MetricCard key={metric.metric_name} metric={metric} />
        ))}
      </div>
    )}
  </section>
);

const AttributionSection: React.FC<{ section: ResearchAttributionSection }> = ({ section }) => (
  <section className="research-panel">
    <div className="research-section-title">
      Attribution · {section.dimension}
      <span className="research-section-status">{section.evidence_status} · {section.statistical_strength}</span>
    </div>
    <div className="research-attribution-grid">
      {section.rows.map((row) => (
        <article className="research-attribution-card" key={row.label}>
          <div className="research-attribution-head">
            <strong>{row.label}</strong>
            <span>N={row.population_n}</span>
          </div>
          <div className="research-metric-grid research-metric-grid-compact">
            {row.metrics.map((metric) => (
              <MetricCard key={metric.metric_name} metric={metric} />
            ))}
          </div>
        </article>
      ))}
    </div>
  </section>
);

const CandidateCard: React.FC<{ candidate: ResearchCandidateRow }> = ({ candidate }) => (
  <article className="research-candidate-card" data-testid="research-candidate-card">
    <div className="research-candidate-head">
      <div>
        <div className="research-candidate-class">{candidate.candidate_class}</div>
        <div className="research-candidate-id">{candidate.candidate_id}</div>
      </div>
      <span className="research-candidate-state">{candidate.lifecycle_state}</span>
    </div>
    <div className="research-candidate-hypothesis">{candidate.hypothesis_summary}</div>
    <div className="research-candidate-meta">
      <span>{candidate.evaluation_status}</span>
      <span>{candidate.target_domains.join(" · ")}</span>
    </div>
    <details className="research-metric-details">
      <summary>Provenance du candidat</summary>
      <div>Source : {candidate.source_code_sha}</div>
      <div>Configuration : {candidate.config_hash}</div>
      <div>Preuves parentes : {candidate.parent_evidence_refs.join(", ")}</div>
      <div>Limites : {candidate.known_limitations.join(" · ")}</div>
    </details>
  </article>
);

export const ResearchLabView: React.FC = () => {
  const state = useResearchLabSnapshot();

  if (state.status === "loading") {
    return (
      <div className="research-panel research-state" data-testid="research-lab-view">
        Chargement de la publication de recherche…
      </div>
    );
  }

  if (state.status === "api_error") {
    return (
      <div className="research-panel research-state research-state-error" data-testid="research-lab-view">
        <strong>Laboratoire indisponible — HTTP {state.httpStatus}</strong>
        <span>
          {state.error.error_code ?? "RESEARCH_LAB_API_ERROR"} · {state.error.error_message ?? "Aucune publication de recherche gouvernée disponible."}
        </span>
      </div>
    );
  }

  if (state.status === "transport_error") {
    return (
      <div className="research-panel research-state research-state-error" data-testid="research-lab-view">
        <strong>Erreur de contrat ou de transport du Laboratoire</strong>
        <span>{state.message}</span>
      </div>
    );
  }

  const snapshot = state.snapshot;
  const context = snapshot.provenance.primary_context;

  return (
    <div className="research-stack" data-testid="research-lab-view">
      <section className="research-panel research-hero">
        <div className="research-domain-banner" data-testid="research-domain-banner">
          RECHERCHE HORS LIGNE · NON AUTORITAIRE
        </div>
        <div className="research-hero-grid">
          <div>
            <div className="research-title">Évaluations et preuves</div>
            <div className="research-subtitle">
              {fr(snapshot.research_state)} · résultats publiés, sans autorité sur la machine
            </div>
          </div>
          <div className="research-strength">
            {fr(context.statistical_strength)}
          </div>
        </div>

        <div className="research-context-grid">
          <div><span>Population</span><strong>{context.population_definition}</strong></div>
          <div><span>N</span><strong>{context.n}</strong></div>
          <div><span>Preuves</span><strong>{fr(context.evidence_status)}</strong></div>
          <div><span>Epoch</span><strong>{context.paper_epoch_id ?? "NOT_APPLICABLE"}</strong></div>
        </div>

        <details className="research-provenance">
          <summary>Provenance complète de la recherche</summary>
          <div className="research-provenance-grid"><div><span>Autorité</span><code>{snapshot.authority}</code></div>
            <div><span>dataset_id</span><code>{context.dataset_id}</code></div>
            <div><span>source_boundary_id</span><code>{context.source_boundary_id}</code></div>
            <div><span>research_run_id</span><code>{context.research_run_id}</code></div>
            <div><span>diagnostic_run_id</span><code>{context.diagnostic_run_id ?? "NOT_AVAILABLE"}</code></div>
            <div><span>SHA source de recherche</span><code>{context.research_source_code_sha}</code></div>
            <div><span>Hash de configuration</span><code>{context.research_config_hash ?? "NOT_AVAILABLE"}</code></div>
            <div><span>SHA de présentation</span><code>{context.presentation_builder_source_sha}</code></div>
            <div><span>Publication</span><code>{snapshot.generated_at_utc}</code></div>
          </div>
          <div className="research-provenance-grid" data-testid="research-source-artifacts">
            {snapshot.provenance.source_artifacts.map((artifact) => (
              <div key={artifact.artifact_ref}>
                <span>{artifact.artifact_ref} · {artifact.artifact_type}</span>
                <code>{artifact.sha256}</code>
              </div>
            ))}
          </div>
        </details>
      </section>

      <div className="research-domain-note">
        Les résultats décrivent cette population historique ; ils ne valident pas à eux seuls une stratégie.
      </div>

      <section className="research-panel research-results">
        <h2>Résultats de l’évaluation publiée</h2>
        <MetricSection title="Performance" metrics={snapshot.performance} />
        <MetricSection title="Risque et stabilité" metrics={snapshot.risk_stability} />
        <MetricSection title="Coûts" metrics={snapshot.costs} />
      </section>
      <details className="research-panel research-methodology"><summary>Attributions et méthodologie détaillée</summary>

      {snapshot.attribution.map((section) => (
        <AttributionSection key={section.dimension} section={section} />
      ))}

      </details>
      <details className="research-panel research-methodology"><summary>Registre des candidats et provenance</summary>
        <div className="research-section-title">
          Registre des candidats
          <span className="research-section-status">
            {snapshot.candidate_registry.candidate_count} candidat(s)
          </span>
        </div>
        {snapshot.candidate_registry.candidate_count === 0 ? (
          <div className="research-candidate-empty" data-testid="research-candidate-empty">
            Aucun candidat substantiel publié dans ce snapshot de recherche.
          </div>
        ) : (
          <div className="research-candidate-grid">
            {snapshot.candidate_registry.rows.map((candidate) => (
              <CandidateCard key={candidate.candidate_id} candidate={candidate} />
            ))}
          </div>
        )}
      </details>

      <details className="research-panel research-methodology">
        <summary>Limites connues · {snapshot.limitations.length} mentions publiées</summary>
        <ul className="research-limitations">
          {snapshot.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      </details>
    </div>
  );
};
