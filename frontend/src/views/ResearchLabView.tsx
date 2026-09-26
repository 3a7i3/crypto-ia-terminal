import React from "react";
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
      <summary>Evidence</summary>
      <div>source: {metric.source_ref}</div>
      <div>derivation: {metric.derivation}</div>
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
      <div className="research-empty-section">No producer-authored metrics in this section.</div>
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
      <summary>Candidate provenance</summary>
      <div>source: {candidate.source_code_sha}</div>
      <div>config: {candidate.config_hash}</div>
      <div>parents: {candidate.parent_evidence_refs.join(", ")}</div>
      <div>limitations: {candidate.known_limitations.join(" · ")}</div>
    </details>
  </article>
);

export const ResearchLabView: React.FC = () => {
  const state = useResearchLabSnapshot();

  if (state.status === "loading") {
    return (
      <div className="research-panel research-state" data-testid="research-lab-view">
        Loading governed Research presentation…
      </div>
    );
  }

  if (state.status === "api_error") {
    return (
      <div className="research-panel research-state research-state-error" data-testid="research-lab-view">
        <strong>RESEARCH LAB unavailable — HTTP {state.httpStatus}</strong>
        <span>
          {state.error.error_code ?? "RESEARCH_LAB_API_ERROR"} · {state.error.error_message ?? "No governed Research presentation artifact."}
        </span>
      </div>
    );
  }

  if (state.status === "transport_error") {
    return (
      <div className="research-panel research-state research-state-error" data-testid="research-lab-view">
        <strong>RESEARCH LAB contract/transport error</strong>
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
          RESEARCH LAB · OFFLINE ANALYSIS · NOT PAPER CAPITAL · NON-AUTHORITATIVE
        </div>
        <div className="research-hero-grid">
          <div>
            <div className="research-title">Research evidence workspace</div>
            <div className="research-subtitle">
              {snapshot.authority} · {snapshot.research_state} · producer-authored scientific facts only
            </div>
          </div>
          <div className="research-strength">
            {context.statistical_strength}
          </div>
        </div>

        <div className="research-context-grid">
          <div><span>Population</span><strong>{context.population_definition}</strong></div>
          <div><span>N</span><strong>{context.n}</strong></div>
          <div><span>Evidence</span><strong>{context.evidence_status}</strong></div>
          <div><span>Epoch</span><strong>{context.paper_epoch_id ?? "NOT_APPLICABLE"}</strong></div>
        </div>

        <details className="research-provenance">
          <summary>Full Research provenance</summary>
          <div className="research-provenance-grid">
            <div><span>dataset_id</span><code>{context.dataset_id}</code></div>
            <div><span>source_boundary_id</span><code>{context.source_boundary_id}</code></div>
            <div><span>research_run_id</span><code>{context.research_run_id}</code></div>
            <div><span>diagnostic_run_id</span><code>{context.diagnostic_run_id ?? "NOT_APPLICABLE"}</code></div>
            <div><span>research source SHA</span><code>{context.research_source_code_sha}</code></div>
            <div><span>research config hash</span><code>{context.research_config_hash ?? "NOT_AVAILABLE"}</code></div>
            <div><span>presentation builder SHA</span><code>{context.presentation_builder_source_sha}</code></div>
            <div><span>published</span><code>{snapshot.generated_at_utc}</code></div>
          </div>
        </details>
      </section>

      <div className="research-domain-note">
        Research metrics are descriptive/non-authoritative. They are never combined with active PAPER capital.
      </div>

      <MetricSection title="Performance" metrics={snapshot.performance} />
      <MetricSection title="Risk / Stability" metrics={snapshot.risk_stability} />
      <MetricSection title="Costs" metrics={snapshot.costs} />

      {snapshot.attribution.map((section) => (
        <AttributionSection key={section.dimension} section={section} />
      ))}

      <section className="research-panel">
        <div className="research-section-title">
          Candidate Registry
          <span className="research-section-status">
            {snapshot.candidate_registry.candidate_count} candidate(s)
          </span>
        </div>
        {snapshot.candidate_registry.candidate_count === 0 ? (
          <div className="research-candidate-empty" data-testid="research-candidate-empty">
            No substantive candidate is published in this Research snapshot.
          </div>
        ) : (
          <div className="research-candidate-grid">
            {snapshot.candidate_registry.rows.map((candidate) => (
              <CandidateCard key={candidate.candidate_id} candidate={candidate} />
            ))}
          </div>
        )}
      </section>

      <section className="research-panel">
        <div className="research-section-title">Known limitations</div>
        <ul className="research-limitations">
          {snapshot.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      </section>
    </div>
  );
};
