import React from "react";
import { fr } from "../lib/presentationFr";
import { FinancialHistory } from "../components/FinancialHistory";
import { formatDecimalText } from "../lib/decimalPresentation";
import { useFinancialReconciliation } from "../lib/financialReconciliationClient";
import type {
  FinancialReconciliationRecord,
  FinancialReconciliationStatus,
} from "../lib/financialReconciliationTypes";
import "../financial-reconciliation.css";

function display(value: string | null): string {
  return value === null ? "Indisponible" : value;
}

const AMOUNT_FIELDS = new Set(["cash_available", "capital_reserved", "capital_unresolved", "fees_paid", "realized_pnl", "book_capital_at_cost"]);
function recordDisplay(field: string, value: string | null): string {
  const raw = display(value);
  return AMOUNT_FIELDS.has(field) ? formatDecimalText(raw) : raw;
}

function tone(status: FinancialReconciliationStatus): string {
  if (status === "EXACT") return "exact";
  if (status === "WITHIN_TOLERANCE") return "tolerance";
  if (status === "DIVERGENT") return "divergent";
  return "unresolved";
}

const Metric: React.FC<{
  label: string;
  value: string | number;
  hint?: string;
}> = ({ label, value, hint }) => (
  <div className="fin-metric">
    <span>{label}</span>
    <strong className={value === "Indisponible" ? "fin-value-unavailable" : undefined}>{typeof value === "string" ? formatDecimalText(value) : value}</strong>
    {typeof value === "string" && /^-?\d+(\.\d+)?$/.test(value) && (
      <details className="fin-metric-exact"><summary>Valeur exacte</summary><code>{value}</code></details>
    )}
    {hint && <small>{hint}</small>}
  </div>
);

const RecordRow: React.FC<{ row: FinancialReconciliationRecord }> = ({ row }) => (
  <tr data-testid="fin-reconciliation-row">
    <td>
      <strong>{row.field}</strong>
      <small>{row.source_kind} · {row.source_id}</small>
    </td>
    <td>{recordDisplay(row.field, row.projected_value)}</td>
    <td>{recordDisplay(row.field, row.observed_value)}</td>
    <td>{recordDisplay(row.field, row.delta_observed_minus_projected)}</td>
    <td>{recordDisplay(row.field, row.unreconciled_amount)}</td>
    <td>
      <span className={"fin-status fin-status-" + tone(row.status)}>
        {fr(row.status)}
      </span>
      <small>{row.comparability} · {row.freshness}</small>
    </td>
    <td>
      <details>
        <summary>Valeurs exactes & preuves</summary>
        <div className="fin-evidence">
          <div><span>Projeté exact</span><code>{display(row.projected_value)}</code></div>
          <div><span>Observé exact</span><code>{display(row.observed_value)}</code></div>
          <div><span>Écart exact</span><code>{display(row.delta_observed_minus_projected)}</code></div>
          <div><span>Non réconcilié exact</span><code>{display(row.unreconciled_amount)}</code></div>
          <div><span>Projected</span><code>{row.projected_provenance}</code></div>
          <div><span>Observed</span><code>{row.observed_provenance}</code></div>
          {row.note && <p>{row.note}</p>}
        </div>
      </details>
    </td>
  </tr>
);

const FinancialReconciliationContent: React.FC = () => {
  const state = useFinancialReconciliation();

  if (state.status === "loading") {
    return (
      <div className="fin-panel fin-state" data-testid="financial-reconciliation-view">
        Chargement de la réconciliation financière…
      </div>
    );
  }

  if (state.status === "api_error") {
    return (
      <div className="fin-panel fin-state fin-state-error" data-testid="financial-reconciliation-view">
        <strong>Publication FIN-02 indisponible</strong>
        <span>
          {state.error.error_code ?? "UNKNOWN_ERROR"} ·{" "}
          {state.error.error_message ?? "Aucun détail"}
        </span>
      </div>
    );
  }

  if (state.status === "transport_error") {
    return (
      <div className="fin-panel fin-state fin-state-error" data-testid="financial-reconciliation-view">
        <strong>Erreur de transport ou de contrat financier</strong>
        <span>{state.message}</span>
      </div>
    );
  }

  const snapshot = state.snapshot;
  const fin = snapshot.financial;
  const recon = snapshot.reconciliation;
  const stale = snapshot.freshness_classification === "STALE";
  const material = snapshot.records.filter(
    (row) => row.comparability === "COMPARABLE" || row.comparability === "UNAVAILABLE",
  );
  const divergences = material.filter((row) => row.status === "DIVERGENT").length;
  const unresolved = material.filter((row) => row.status === "UNRESOLVED").length;

  return (
    <div className="fin-stack" data-testid="financial-reconciliation-view">
      <section className="fin-panel fin-hero">
        <div className="fin-hero-row">
          <div>
            <div className="fin-eyebrow">FINANCES · LECTURE SEULE</div>
            <h2>Portefeuille et finances</h2>
            <p>
              Montants publiés par FIN-01 et rapprochement avec les observations PPL.
              Les écarts servent de preuves ; aucune correction automatique.
            </p>
          </div>
          <div className="fin-status-block">
            <span className={"fin-status fin-status-" + tone(recon.overall_status)}>
              {fr(recon.overall_status)}
            </span>
            <span className={"fin-freshness " + (stale ? "stale" : "fresh")}>
              {fr(snapshot.freshness_classification)} · {Math.round(snapshot.snapshot_age_s)}s
            </span>
          </div>
        </div>

        <details className="fin-provenance-details"><summary>Provenance financière</summary><div className="fin-provenance">
          <div><span>Epoch</span><code>{snapshot.paper_epoch_id}</code></div>
          <div><span>FIN snapshot</span><code>{snapshot.financial_snapshot_id.slice(0, 16)}…</code></div>
          <div><span>FIN-02 SHA</span><code>{snapshot.reconciliation_code_sha}</code></div>
          <div><span>PPL sequence</span><code>{snapshot.last_source_sequence}</code></div>
          <div><span>Model</span><code>{snapshot.financial_model}</code></div>
          <div><span>Asset</span><code>{snapshot.asset}</code></div>
          <div><span>FIN evidence</span><code>{fin.evidence_status}</code></div>
        </div></details>
      </section>

      <section className="fin-panel finance-summary"><h3>Capital PAPER · {snapshot.asset}</h3><div className="fin-metrics" aria-label="Synthèse du capital">
        <Metric label="Capital disponible" value={display(fin.cash_available)} hint={snapshot.asset} />
        <Metric label="Principal réservé" value={display(fin.capital_reserved)} hint="principal au coût historique" />

        <Metric
          label="Capital certifié"
          value={display(fin.certified_equity)}
          hint={fin.certified_equity === null ? "preuves de valorisation incomplètes" : snapshot.asset}
        />
        <Metric label="Capital non résolu" value={recon.unresolved_capital} />
      </div><p>Montants distincts. Le principal déployé représente le capital réservé ; il ne constitue pas une part supplémentaire.</p></section>
      <section className="fin-panel finance-summary"><h3>Résultat et frais · {snapshot.asset}</h3><div className="fin-metrics" aria-label="Résultat et frais">
        <Metric label="Résultat réalisé" value={display(fin.realized_pnl)} hint="résultat FIN publié" />
        <Metric label="Résultat latent" value={display(fin.unrealized_pnl)} hint="valorisation publiée" />
        <Metric label="Frais payés" value={display(fin.fees_paid)} />
      </div></section>
      <details className="fin-panel finance-summary"><summary>Autres montants et contrôles publiés</summary><div className="fin-metrics">
        <Metric label="Capital déployé" value={display(fin.capital_deployed)} hint="mesure d’exposition, non additionnelle" />
        <Metric label="Financement" value={display(fin.funding_net)} hint={fin.funding_status} />
        <Metric
          label="Capital non réconcilié"
          value={display(recon.unreconciled_capital)}
          hint="écart comptable désigné"
        />
        <Metric label="Divergences" value={divergences} />
        <Metric label="Contrôles non résolus" value={unresolved} />
      </div></details>

      <details className="fin-panel financial-evidence"><summary>Preuves de réconciliation · {snapshot.records.length} faits publiés</summary>
        <div className="fin-section-head">
          <div>
            <h3>Preuves de réconciliation</h3>
            <p>
              Observé − projeté. Les faits non comparables restent visibles, sans modifier
              le verdict de réconciliation publié.
            </p>
          </div>
          <span>{snapshot.records.length} faits</span>
        </div>

        <div className="fin-table-wrap">
          <table className="fin-table">
            <thead>
              <tr>
                <th>Fait</th>
                <th>FIN projeté</th>
                <th>Observé</th>
                <th>Écart</th>
                <th>Non réconcilié</th>
                <th>État</th>
                <th>Provenance</th>
              </tr>
            </thead>
            <tbody>
              {snapshot.records.map((row) => (
                <RecordRow key={row.record_id} row={row} />
              ))}
            </tbody>
          </table>
        </div>
        <div className="fin-mobile-records" data-testid="fin-mobile-records">
          {snapshot.records.map((row) => (
            <article className="fin-record-card" key={row.record_id}>
              <div className="fin-record-head"><strong>{row.field}</strong><span className={"fin-status fin-status-" + tone(row.status)}>{fr(row.status)}</span></div>
              <dl className="fin-record-values">
                <div><dt>FIN projeté</dt><dd>{recordDisplay(row.field, row.projected_value)}</dd></div>
                <div><dt>Observé</dt><dd>{recordDisplay(row.field, row.observed_value)}</dd></div>
                <div><dt>Écart</dt><dd>{recordDisplay(row.field, row.delta_observed_minus_projected)}</dd></div>
                <div><dt>Non réconcilié</dt><dd>{recordDisplay(row.field, row.unreconciled_amount)}</dd></div>
              </dl>
              <details><summary>Valeurs exactes & preuves</summary><div className="fin-evidence">
                <div><span>Projeté</span><code>{display(row.projected_value)}</code></div>
                <div><span>Observé</span><code>{display(row.observed_value)}</code></div>
                <div><span>Écart</span><code>{display(row.delta_observed_minus_projected)}</code></div>
                <div><span>Non réconcilié</span><code>{display(row.unreconciled_amount)}</code></div>
                <div><span>Source</span><code>{row.projected_provenance} · {row.observed_provenance}</code></div>
                <div>{row.comparability} · {row.freshness}</div>{row.note && <p>{row.note}</p>}
              </div></details>
            </article>
          ))}
        </div>
      </details>

      <section className="fin-panel fin-footer">
        <strong>Périmètre</strong>
        <span>
          Le capital PAPER reste séparé des comptes exchange.
          Une valorisation inconnue reste indisponible ; elle n’est jamais remplacée par zéro.
        </span>
      </section>
    </div>
  );
};

export const FinancialReconciliationView: React.FC = () => <div className="fin-stack"><FinancialHistory /><FinancialReconciliationContent /></div>;
