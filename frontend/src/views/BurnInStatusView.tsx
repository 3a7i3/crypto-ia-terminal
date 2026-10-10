import { SourceAvailability } from "../components/SourceAvailability";
import React from "react";
import { fr } from "../lib/presentationFr";
import { useBurnInStatus } from "../lib/burnInStatusClient";
import type { BurnInHistoryRow, BurnInOpenLifecycle } from "../lib/burnInStatusTypes";

function duration(value: number | null): string {
  if (value === null) return "NOT_AVAILABLE";
  const total = Math.max(0, Math.floor(value));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days > 0) return `${days}j ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m`;
  return `${total}s`;
}
function num(value: number | null): string {
  return value === null ? "NOT_AVAILABLE" : String(value);
}
const OpenLifecycleCard: React.FC<{ row: BurnInOpenLifecycle }> = ({ row }) => (
  <article className="burnin-open-card" data-testid="burnin-open-row">
    <div className="burnin-open-head">
      <strong>{row.symbol}</strong>
      <span className={`burnin-status burnin-deadline-${row.deadline_state.toLowerCase()}`}>{row.deadline_state}</span>
    </div>
    <div className="burnin-open-grid">
      <span><b>Identité</b>{row.trade_id}</span>
      <span><b>Sens</b>{row.side}</span>
      <span><b>Principal USD</b>{row.principal_usd}</span>
      <span><b>Entrée</b>{row.entry_price}</span>
      <span><b>Âge</b>{duration(row.age_seconds)}</span>
      <span><b>Timeout</b>{row.timeout_at_utc ?? "NOT_AVAILABLE"}</span>
      <span><b>Limite de récupération</b>{row.recovery_eligible_until_utc ?? "NOT_AVAILABLE"}</span>
      <span><b>Décision</b>{row.decision_id ?? "NOT_AVAILABLE"}</span>
    </div>
  </article>
);

const HistoryMobileCard: React.FC<{ row: BurnInHistoryRow }> = ({ row }) => (
  <article className="burnin-history-card" data-testid="burnin-history-mobile-row">
    <div className="burnin-history-head">
      <div><strong>{row.symbol}</strong><span>{row.side}</span></div>
      <span className={`burnin-status burnin-status-${row.status.toLowerCase()}`}>{row.status}</span>
    </div>
    <dl>
      <div><dt>Ouverture</dt><dd>{row.opened_at_utc}</dd></div>
      <div><dt>Fin</dt><dd>{row.terminal_at_utc ?? "EN COURS"}</dd></div>
      <div><dt>Principal USD</dt><dd>{row.principal_usd}</dd></div>
      <div><dt>Entrée / sortie</dt><dd>{row.entry_price} / {num(row.exit_price)}</dd></div>
      <div><dt>Frais entrée / sortie</dt><dd>{row.entry_fee_usd} / {num(row.exit_fee_usd)}</dd></div>
      <div><dt>PnL net réalisé</dt><dd>{row.status === "UNRESOLVED" ? "UNRESOLVED" : num(row.net_realized_pnl_usd)}</dd></div>
      <div><dt>Durée</dt><dd>{duration(row.duration_seconds)}</dd></div>
      <div><dt>Trade ID</dt><dd>{row.trade_id}</dd></div>
      {row.unresolved_reason && <div><dt>Raison non résolue</dt><dd>{row.unresolved_reason}</dd></div>}
    </dl>
  </article>
);

export const BurnInStatusView: React.FC = () => {
  const state = useBurnInStatus();

  if (state.status === "loading") {
    return <section className="burnin-state" data-testid="burnin-view"><strong>BURN-IN · CHARGEMENT</strong><span>Lecture de la projection PPL gouvernée.</span></section>;
  }
  if (state.status === "api_error" || state.status === "transport_error") {
    return <div data-testid="burnin-view"><SourceAvailability source="burn-in"
      code={state.status === "api_error" ? state.error.error_code ?? "BURN_IN_API_ERROR" : "BURN_IN_TRANSPORT_OR_CONTRACT"}
      httpStatus={state.status === "api_error" ? state.httpStatus : undefined}
      message={state.status === "api_error" ? state.error.error_message : state.message}
      lastEvidence={state.lastEvidence} /></div>;
  }

  const s = state.snapshot;
  return (
    <div className="burnin-stack" data-testid="burnin-view">
      <section className="burnin-hero">
        <div className="burnin-hero-head">
          <div>
            <div className="burnin-eyebrow">PPL AUTORITAIRE · PRÉSENTATION READ-ONLY</div>
            <h2>Burn-in · observation scientifique</h2>
            <code>{s.paper_epoch_id}</code>
          </div>
          <div className="burnin-badges">
            <span>{fr(s.freshness_classification)}</span>
            <span>{s.authority}</span>
          </div>
        </div>
        <div className="burnin-summary-grid">
          <div><span>Événements</span><strong>{s.event_count}</strong><small>séquence {s.last_sequence}</small></div>
          <div><span>Positions ouvertes</span><strong>{s.lifecycle_counts.open}</strong><small>lifecycles courants</small></div>
          <div><span>Clôtures résolues</span><strong>{s.lifecycle_counts.closed}</strong><small>résolus connus</small></div>
          <div><span>Non résolues</span><strong>{s.lifecycle_counts.unresolved}</strong><small>aucun PnL fabriqué</small></div>
          <div><span>Dernier événement</span><strong>{s.last_event.event_type}</strong><small>#{s.last_event.sequence}</small></div>
          <div><span>T0 scientifique</span><strong>{s.scientific_t0.status}</strong><small>{s.scientific_t0.value_utc ?? "source non matérialisée"}</small></div>
        </div>
        <div className="burnin-source-line">
          <span>Produit {s.generated_at_utc}</span>
          <span>Source mise à jour {s.source_updated_at_utc}</span>
          <span>Âge snapshot {s.snapshot_age_s}s</span>
        </div>
      </section>

      <p className="source-date">Certification de fin : non disponible. La progression ci-dessus décrit seulement la frontière PPL capturée; aucun objectif ni pourcentage d’achèvement n’est inféré.</p>
      <section className="burnin-panel">
        <div className="burnin-section-head">
          <div><h3>Positions ouvertes</h3><span>Échéances calculées côté producteur U2, jamais dans React.</span></div>
          <strong>{s.open_lifecycles.length}</strong>
        </div>
        {s.open_lifecycles.length === 0 ? (
          <div className="burnin-empty">Aucune position OPEN dans la frontière PPL capturée.</div>
        ) : (
          <div className="burnin-open-list">
            {s.open_lifecycles.map((row) => <OpenLifecycleCard key={row.trade_id} row={row} />)}
          </div>
        )}
      </section>

      <section className="burnin-panel" data-testid="burnin-history">
        <div className="burnin-section-head">
          <div><h3>Historique des ordres PAPER</h3><span>Une ligne par lifecycle PPL · plus récent en premier.</span></div>
          <strong>{s.lifecycle_history.length}</strong>
        </div>
        <div className="burnin-history-table-wrap">
          <table className="burnin-history-table">
            <thead><tr>
              <th>Statut</th><th>Symbole</th><th>Sens</th><th>Ouverture</th><th>Fin</th>
              <th>Principal USD</th><th>Entrée</th><th>Sortie</th><th>Frais E/X</th><th>PnL net</th><th>Durée</th><th>Raison</th>
            </tr></thead>
            <tbody>
              {s.lifecycle_history.map((row) => (
                <tr key={row.trade_id} data-testid="burnin-history-row">
                  <td><span className={`burnin-status burnin-status-${row.status.toLowerCase()}`}>{row.status}</span></td>
                  <td>{row.symbol}</td><td>{row.side}</td><td>{row.opened_at_utc}</td><td>{row.terminal_at_utc ?? "EN COURS"}</td>
                  <td>{row.principal_usd}</td><td>{row.entry_price}</td><td>{num(row.exit_price)}</td>
                  <td>{row.entry_fee_usd} / {num(row.exit_fee_usd)}</td>
                  <td>{row.status === "UNRESOLVED" ? "UNRESOLVED" : num(row.net_realized_pnl_usd)}</td>
                  <td>{duration(row.duration_seconds)}</td>
                  <td>{row.unresolved_reason ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="burnin-history-mobile">
          {s.lifecycle_history.map((row) => <HistoryMobileCard key={row.trade_id} row={row} />)}
        </div>
      </section>

      <details className="burnin-panel"><summary>Diagnostics techniques · configuration et provenance</summary>
        <div className="burnin-section-head"><div><h3>Configuration gelée & provenance</h3><span>Whitelist issue du snapshot BURN_IN_EXPERIMENT_CONFIG_V1.</span></div></div>
        <dl className="burnin-provenance-grid">
          <div><dt>Runtime source SHA</dt><dd>{s.source_code_sha}</dd></div>
          <div><dt>Config hash</dt><dd>{s.config_snapshot_hash}</dd></div>
          <div><dt>PPL stream SHA</dt><dd>{s.ppl_stream_sha256}</dd></div>
          <div><dt>PB_MAX_POSITIONS</dt><dd>{s.frozen_config.pb_max_positions}</dd></div>
          <div><dt>PAPER_PORTFOLIO_BRAIN_LEVEL</dt><dd>{s.frozen_config.paper_portfolio_brain_level}</dd></div>
          <div><dt>MEXC_SIM_MAX_POSITION_USD</dt><dd>{s.frozen_config.mexc_sim_max_position_usd}</dd></div>
          <div><dt>MEXC_SIM_MAX_AGE_H</dt><dd>{s.frozen_config.mexc_sim_max_age_h}</dd></div>
          <div><dt>Lifecycle authority</dt><dd>{s.frozen_config.paper_lifecycle_authority}</dd></div>
          <div><dt>Finalisation</dt><dd>{s.finalization.state}</dd></div>
          <div><dt>Finalisation reason</dt><dd>{s.finalization.reason}</dd></div>
        </dl>
      </details>

      <p className="burnin-boundary">Projection de présentation uniquement : aucune mutation PPL/epoch/stratégie/risk/sizing. CLOSED suit la comptabilité PPL canonique ; UNRESOLVED reste inconnu.</p>
    </div>
  );
};
