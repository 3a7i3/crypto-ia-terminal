import React, { useEffect, useRef, useState } from "react";
import { useResearchStrategyBoard } from "../lib/researchStrategyClient";
import {
  STRATEGY_CRITERIA,
  type CriterionKey,
  type CriterionStatus,
  type ResearchStrategyRow,
  type StrategyCriterion,
} from "../lib/researchStrategyTypes";
import { formatDecimalText } from "../lib/decimalPresentation";

export const CRITERION_LABELS: Record<CriterionKey, string> = {
  PERFORMANCE: "Performance",
  POPULATION: "Population",
  VALIDATION: "Validation",
  STABILITY: "Stabilité",
  COSTS: "Coûts",
  DRAWDOWN: "Drawdown",
};
const labels: Record<CriterionStatus, string> = {
  PASS: "Satisfait",
  FAIL: "Non satisfait",
  PARTIAL: "Partiel / fragile",
  NOT_AVAILABLE: "Non évalué",
};
const icons: Record<CriterionStatus, string> = {
  PASS: "✓",
  FAIL: "×",
  PARTIAL: "!",
  NOT_AVAILABLE: "—",
};
function value(v: number | string | null): string {
  return v === null
    ? "NOT_AVAILABLE"
    : typeof v === "number"
      ? formatDecimalText(String(v), 4)
      : v;
}
const Criterion: React.FC<{
  row: ResearchStrategyRow;
  criterion: StrategyCriterion;
  onClick: (event: React.MouseEvent<HTMLButtonElement>) => void;
}> = ({ row, criterion, onClick }) => (
  <button
    className={`strategy-criterion strategy-criterion-${criterion.status.toLowerCase()}`}
    onClick={onClick}
    aria-label={`${row.label} · ${CRITERION_LABELS[criterion.criterion_id]} · ${labels[criterion.status]}`}
    title={criterion.reason}
    aria-controls="strategy-detail"
  >
    <span className="strategy-dot" aria-hidden="true">
      {icons[criterion.status]}
    </span>
    <span className="strategy-dot-label">{labels[criterion.status]}</span>
  </button>
);
export const ResearchStrategyBoardView: React.FC = () => {
  const state = useResearchStrategyBoard();
  const [query, setQuery] = useState("");
  const [candidateClass, setCandidateClass] = useState("ALL");
  const [group, setGroup] = useState("ALL");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [criterionKey, setCriterionKey] = useState<CriterionKey | null>(null);
  const detail = useRef<HTMLElement>(null),
    trigger = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    if (selectedId) detail.current?.focus();
  }, [selectedId, criterionKey]);
  if (state.status !== "success")
    return (
      <section
        className="research-panel strategy-state"
        data-testid="strategy-board-view"
      >
        <span className="workspace-eyebrow">
          STRATÉGIES · RESEARCH NON-AUTORITAIRE
        </span>
        <h2>Stratégies & critères</h2>
        <p>
          {state.status === "loading"
            ? "Lecture du catalogue Research…"
            : "Catalogue indisponible : aucun résultat ni classement actuel ne peut être présenté."}
        </p>
        {state.status === "error" && (
          <details>
            <summary>Détail de la source</summary>
            <code>{state.code}</code>
          </details>
        )}
      </section>
    );
  const snapshot = state.snapshot;
  const groups = [
    ...new Set(
      snapshot.rows.flatMap((r) => (r.ranking ? [r.ranking.group_id] : [])),
    ),
  ];
  const rows = snapshot.rows.filter(
    (r) =>
      (candidateClass === "ALL" || r.candidate_class === candidateClass) &&
      (group === "ALL" || r.ranking?.group_id === group) &&
      `${r.label} ${r.candidate_id} ${r.hypothesis}`
        .toLocaleLowerCase()
        .includes(query.toLocaleLowerCase().trim()),
  );
  if (group !== "ALL")
    rows.sort((a, b) => a.ranking!.position - b.ranking!.position);
  const selected = rows.find((r) => r.candidate_id === selectedId);
  const open = (
    row: ResearchStrategyRow,
    key: CriterionKey | null,
    event: React.MouseEvent<HTMLButtonElement>,
  ) => {
    trigger.current = event.currentTarget;
    setSelectedId(row.candidate_id);
    setCriterionKey(key);
  };
  const close = () => {
    setSelectedId(null);
    setCriterionKey(null);
    trigger.current?.focus();
  };
  return (
    <div className="strategy-stack" data-testid="strategy-board-view">
      <section className="research-panel strategy-hero">
        <div className="strategy-hero-heading">
          <div>
            <span className="workspace-eyebrow">RESEARCH NON-AUTORITAIRE</span>
            <h2>Stratégies & critères</h2>
            <p>
              Des évaluations traçables. Chaque pastille décrit un critère
              publié, jamais une permission de trading.
            </p>
            <p>
              Publication Research :{" "}
              <time dateTime={snapshot.generated_at_utc}>
                {snapshot.generated_at_utc}
              </time>
              . Résultats descriptifs et historiques.
            </p>
          </div>
          <span className="strategy-count">
            {snapshot.rows.length} ligne(s) publiée(s)
          </span>
        </div>
        <div className="strategy-legend" aria-label="Légende des critères">
          {Object.entries(labels).map(([status, label]) => (
            <span
              key={status}
              className={`strategy-criterion-${status.toLowerCase()}`}
            >
              <span className="strategy-dot" aria-hidden="true">
                {icons[status as CriterionStatus]}
              </span>
              {label}
            </span>
          ))}
        </div>
        <div className="strategy-filters">
          <label>
            Rechercher une stratégie
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Nom, hypothèse ou identifiant"
            />
          </label>
          <label>
            Type
            <select
              value={candidateClass}
              onChange={(e) => setCandidateClass(e.target.value)}
            >
              <option value="ALL">Tous les candidats</option>
              {["STRATEGY", "FEATURE", "CONFIG", "HYBRID"].map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </label>
          <label>
            Classement comparable
            <select value={group} onChange={(e) => setGroup(e.target.value)}>
              <option value="ALL">
                Toutes les cohortes · aucun classement global
              </option>
              {groups.map((g) => (
                <option value={g} key={g}>
                  Cohorte {g.slice(0, 10)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <p className="strategy-scope" role="status">
          {rows.length} résultat(s) dans les lignes publiées. Un PnL positif ne
          prouve pas une stratégie robuste ; les métriques et leurs populations
          restent visibles dans la fiche.
        </p>
      </section>
      {rows.length === 0 ? (
        <section
          className="research-panel strategy-state"
          data-testid="strategy-empty"
        >
          <h3>
            {snapshot.catalog_state === "EMPTY"
              ? "Publication explicitement vide"
              : "Aucun résultat pour ces filtres"}
          </h3>
          <p>
            {snapshot.catalog_state === "EMPTY"
              ? "Cette sélection ne publie aucune ligne. Elle ne prouve pas que le registre global est vide."
              : "Les autres stratégies de la publication restent accessibles en retirant les filtres."}
          </p>
        </section>
      ) : (
        <>
          <section className="research-panel strategy-table-desktop">
            <table className="strategy-table">
              <caption>
                Critères des stratégies — verdicts de la politique Research
                publiée
              </caption>
              <thead>
                <tr>
                  <th>Stratégie / version</th>
                  {STRATEGY_CRITERIA.map((k) => (
                    <th key={k}>{CRITERION_LABELS[k]}</th>
                  ))}
                  <th>Rang dans sa cohorte</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.candidate_id} data-testid="strategy-row">
                    <th scope="row">
                      <button
                        className="strategy-name"
                        onClick={(e) => open(row, null, e)}
                      >
                        {row.label}
                      </button>
                      <small>
                        {row.candidate_class} · {row.candidate_id.slice(0, 10)}
                      </small>
                      <small>
                        {row.evaluation
                          ? `${row.evaluation.run_status} · ${row.evaluation.role}`
                          : "Évaluation NOT_AVAILABLE"}
                      </small>
                    </th>
                    {STRATEGY_CRITERIA.map((k) => (
                      <td key={k}>
                        <Criterion
                          row={row}
                          criterion={
                            row.criteria.find((c) => c.criterion_id === k)!
                          }
                          onClick={(e) => open(row, k, e)}
                        />
                      </td>
                    ))}
                    <td>
                      {row.ranking ? (
                        <span>
                          #{row.ranking.position} / {row.ranking.group_size}
                          <small>
                            Cohorte {row.ranking.group_id.slice(0, 10)}
                          </small>
                        </span>
                      ) : (
                        "NOT_AVAILABLE"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <section
            className="strategy-mobile-cards"
            data-testid="strategy-mobile-cards"
          >
            {rows.map((row) => (
              <article
                className="research-panel strategy-mobile-card"
                key={row.candidate_id}
              >
                <button
                  className="strategy-name"
                  onClick={(e) => open(row, null, e)}
                >
                  {row.label}
                </button>
                <p>
                  {row.candidate_class} ·{" "}
                  {row.evaluation?.run_status ?? "NOT_AVAILABLE"}
                </p>
                <div className="strategy-mobile-criteria">
                  {STRATEGY_CRITERIA.map((k) => (
                    <div key={k}>
                      <span>{CRITERION_LABELS[k]}</span>
                      <Criterion
                        row={row}
                        criterion={
                          row.criteria.find((c) => c.criterion_id === k)!
                        }
                        onClick={(e) => open(row, k, e)}
                      />
                    </div>
                  ))}
                </div>
                <p>
                  Rang :{" "}
                  {row.ranking
                    ? `#${row.ranking.position} / ${row.ranking.group_size} · cohorte ${row.ranking.group_id.slice(0, 10)}`
                    : "NOT_AVAILABLE"}
                </p>
              </article>
            ))}
          </section>
        </>
      )}
      {selected && (
        <section
          id="strategy-detail"
          className="research-panel strategy-detail"
          ref={detail}
          tabIndex={-1}
          onKeyDown={(e) => {
            if (e.key === "Escape") close();
          }}
          aria-label={`Fiche ${selected.label}`}
          data-testid="strategy-detail"
        >
          <div className="strategy-hero-heading">
            <div>
              <span className="workspace-eyebrow">
                {selected.candidate_class} · FICHE RESEARCH
              </span>
              <h2>{selected.label}</h2>
            </div>
            <button onClick={close}>Fermer la fiche</button>
          </div>
          <h3>Hypothèse</h3>
          <p>{selected.hypothesis}</p>
          <p>{selected.rationale}</p>
          <h3>
            {criterionKey ? CRITERION_LABELS[criterionKey] : "Critères publiés"}
          </h3>
          <div className="strategy-assessment">
            {selected.criteria
              .filter(
                (c) => criterionKey === null || c.criterion_id === criterionKey,
              )
              .map((c) => (
                <article key={c.criterion_id}>
                  <strong
                    className={`strategy-criterion-${c.status.toLowerCase()}`}
                  >
                    {CRITERION_LABELS[c.criterion_id]} · {labels[c.status]}
                  </strong>
                  <p>{c.reason}</p>
                  <small>
                    Métriques référencées :{" "}
                    {c.metric_refs.join(", ") || "NOT_AVAILABLE"}
                  </small>
                </article>
              ))}
          </div>
          <h3>Résultats de l’évaluation</h3>
          {selected.evaluation ? (
            <>
              <p>
                {selected.evaluation.method} · {selected.evaluation.role} ·{" "}
                {selected.evaluation.run_status} · publié le{" "}
                {selected.evaluation.generated_at_utc}
              </p>
              <p>Population : {selected.evaluation.population_definition}</p>
              <div className="research-metric-grid">
                {selected.evaluation.metrics.map((m) => (
                  <article className="research-metric-card" key={m.metric_name}>
                    <span className="research-metric-label">
                      {m.metric_name}
                    </span>
                    <strong className="research-metric-value">
                      {value(m.value)}
                    </strong>
                    <p>
                      N={m.n} · {m.evidence_status} · {m.statistical_strength}
                    </p>
                    <details>
                      <summary>Valeurs exactes et méthode</summary>
                      <p>Valeur : {String(m.value ?? "NOT_AVAILABLE")}</p>
                      <p>
                        Baseline : {String(m.baseline_value ?? "NOT_AVAILABLE")}{" "}
                        · candidat :{" "}
                        {String(m.candidate_value ?? "NOT_AVAILABLE")} · delta
                        publié : {String(m.delta ?? "NOT_AVAILABLE")}
                      </p>
                      <p>
                        {m.derivation} · {m.metric_semantics_version}
                      </p>
                    </details>
                  </article>
                ))}
              </div>
            </>
          ) : (
            <p>Évaluation NOT_AVAILABLE : aucune métrique n’a été admise.</p>
          )}
          {selected.ranking && (
            <p>
              Classement publié : #{selected.ranking.position} /{" "}
              {selected.ranking.group_size}. {selected.ranking.reason}
            </p>
          )}
          <h3>Limites</h3>
          <ul>
            {selected.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
          <details>
            <summary>Identité, politique et provenance</summary>
            <dl className="research-provenance-grid">
              <div>
                <dt>Candidate ID</dt>
                <dd>
                  <code>{selected.candidate_id}</code>
                </dd>
              </div>
              <div>
                <dt>Code proposé</dt>
                <dd>
                  <code>{selected.source_code_sha}</code>
                </dd>
              </div>
              <div>
                <dt>Config référencée</dt>
                <dd>
                  <code>{selected.config_hash}</code>
                </dd>
              </div>
              <div>
                <dt>Policy</dt>
                <dd>
                  <code>
                    {selected.assessment_policy_id ?? "NOT_AVAILABLE"}
                  </code>{" "}
                  · {selected.assessment_policy_ref ?? "NOT_AVAILABLE"}
                </dd>
              </div>
              {selected.evaluation &&
                [
                  "evaluation_run_id",
                  "dataset_id",
                  "source_boundary_id",
                  "baseline_id",
                  "source_code_sha",
                  "config_hash",
                ].map((k) => (
                  <div key={k}>
                    <dt>{k}</dt>
                    <dd>
                      <code>
                        {String(
                          selected.evaluation![
                            k as keyof typeof selected.evaluation
                          ],
                        )}
                      </code>
                    </dd>
                  </div>
                ))}
            </dl>
          </details>
        </section>
      )}
      <details className="research-panel strategy-publication">
        <summary>Provenance de la publication & limites</summary>
        <p>
          {snapshot.admission_ref} · publié le {snapshot.generated_at_utc} ·
          builder {snapshot.builder_source_sha}
        </p>
        <ul>
          {snapshot.limitations.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
        <div className="research-provenance-grid">
          {snapshot.source_artifacts.map((a) => (
            <div key={a.artifact_ref}>
              <span>
                {a.artifact_ref} · {a.artifact_type}
              </span>
              <code>{a.sha256}</code>
            </div>
          ))}
        </div>
      </details>
    </div>
  );
};
