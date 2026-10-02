import React from "react";
import { formatDecimalText } from "../lib/decimalPresentation";
import { useFinancialReconciliation } from "../lib/financialReconciliationClient";
import type {
  FinancialReconciliationRecord,
  FinancialReconciliationStatus,
} from "../lib/financialReconciliationTypes";
import "../financial-reconciliation.css";

function display(value: string | null): string {
  return value === null ? "UNAVAILABLE" : value;
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
    <strong className={value === "UNAVAILABLE" ? "fin-value-unavailable" : undefined}>{typeof value === "string" ? formatDecimalText(value) : value}</strong>
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
    <td>{formatDecimalText(display(row.projected_value))}</td>
    <td>{formatDecimalText(display(row.observed_value))}</td>
    <td>{formatDecimalText(display(row.delta_observed_minus_projected))}</td>
    <td>{formatDecimalText(display(row.unreconciled_amount))}</td>
    <td>
      <span className={"fin-status fin-status-" + tone(row.status)}>
        {row.status.replaceAll("_", " ")}
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

export const FinancialReconciliationView: React.FC = () => {
  const state = useFinancialReconciliation();

  if (state.status === "loading") {
    return (
      <div className="fin-panel fin-state" data-testid="financial-reconciliation-view">
        Loading financial reconciliation…
      </div>
    );
  }

  if (state.status === "api_error") {
    return (
      <div className="fin-panel fin-state fin-state-error" data-testid="financial-reconciliation-view">
        <strong>FIN-02 artifact unavailable</strong>
        <span>
          {state.error.error_code ?? "UNKNOWN_ERROR"} ·{" "}
          {state.error.error_message ?? "no detail"}
        </span>
      </div>
    );
  }

  if (state.status === "transport_error") {
    return (
      <div className="fin-panel fin-state fin-state-error" data-testid="financial-reconciliation-view">
        <strong>Financial cockpit transport/contract failure</strong>
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
            <div className="fin-eyebrow">FINANCIAL INSTITUTE · READ-ONLY RECONCILIATION</div>
            <h2>Financial Truth</h2>
            <p>
              FIN-01 accounting, PPL lifecycle truth and explicit observations.
              Deltas are evidence only; no auto-correction.
            </p>
          </div>
          <div className="fin-status-block">
            <span className={"fin-status fin-status-" + tone(recon.overall_status)}>
              {recon.overall_status.replaceAll("_", " ")}
            </span>
            <span className={"fin-freshness " + (stale ? "stale" : "fresh")}>
              {snapshot.freshness_classification} · {Math.round(snapshot.snapshot_age_s)}s
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

      <section className="fin-metrics" aria-label="Financial truth summary">
        <Metric label="Cash available" value={display(fin.cash_available)} hint={snapshot.asset} />
        <Metric label="Reserved" value={display(fin.capital_reserved)} hint="historical principal" />
        <Metric label="Deployed" value={display(fin.capital_deployed)} hint="operational measure" />
        <Metric
          label="Certified equity"
          value={display(fin.certified_equity)}
          hint={fin.certified_equity === null ? "mark evidence incomplete" : snapshot.asset}
        />
        <Metric label="Realized PnL" value={display(fin.realized_pnl)} hint="FIN semantics" />
        <Metric label="Unrealized PnL" value={display(fin.unrealized_pnl)} hint="mark-to-market" />
        <Metric label="Fees" value={display(fin.fees_paid)} />
        <Metric label="Funding" value={display(fin.funding_net)} hint={fin.funding_status} />
        <Metric label="Unresolved capital" value={recon.unresolved_capital} />
        <Metric
          label="Unreconciled capital"
          value={display(recon.unreconciled_capital)}
          hint="single designated book-capital delta"
        />
        <Metric label="Divergences" value={divergences} />
        <Metric label="Unresolved checks" value={unresolved} />
      </section>

      <section className="fin-panel">
        <div className="fin-section-head">
          <div>
            <h3>Reconciliation evidence</h3>
            <p>
              observed − projected. NON_COMPARABLE facts stay visible but do not degrade
              the aggregate reconciliation verdict.
            </p>
          </div>
          <span>{snapshot.records.length} records</span>
        </div>

        <div className="fin-table-wrap">
          <table className="fin-table">
            <thead>
              <tr>
                <th>Fact</th>
                <th>FIN projected</th>
                <th>Observed</th>
                <th>Delta</th>
                <th>Unreconciled</th>
                <th>Status</th>
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
              <div className="fin-record-head"><strong>{row.field}</strong><span className={"fin-status fin-status-" + tone(row.status)}>{row.status.replaceAll("_", " ")}</span></div>
              <dl className="fin-record-values">
                <div><dt>FIN projeté</dt><dd>{row.projected_value === null ? "UNAVAILABLE" : formatDecimalText(row.projected_value)}</dd></div>
                <div><dt>Observé</dt><dd>{row.observed_value === null ? "UNAVAILABLE" : formatDecimalText(row.observed_value)}</dd></div>
                <div><dt>Écart</dt><dd>{row.delta_observed_minus_projected === null ? "UNAVAILABLE" : formatDecimalText(row.delta_observed_minus_projected)}</dd></div>
                <div><dt>Non réconcilié</dt><dd>{row.unreconciled_amount === null ? "UNAVAILABLE" : formatDecimalText(row.unreconciled_amount)}</dd></div>
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
      </section>

      <section className="fin-panel fin-footer">
        <strong>Boundary</strong>
        <span>
          PAPER capital is never arithmetically merged with a real exchange account.
          Unknown marks remain UNAVAILABLE; UNKNOWN is never rendered as zero.
        </span>
      </section>
    </div>
  );
};
