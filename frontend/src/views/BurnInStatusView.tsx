import { SourceAvailability } from "../components/SourceAvailability";
import React, { useState } from "react";
import { BurnInStatistics } from "../components/BurnInStatistics";
import { fr } from "../lib/presentationFr";
import { useBurnInStatus } from "../lib/burnInStatusClient";
import type { BurnInHistoryRow, BurnInOpenLifecycle, BurnInStatusSnapshot } from "../lib/burnInStatusTypes";

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
      <div><dt>PnL brut USD</dt><dd>{num(row.gross_pnl_usd)}</dd></div>
      <div><dt>PnL net réalisé</dt><dd>{row.status === "UNRESOLVED" ? "UNRESOLVED" : num(row.net_realized_pnl_usd)}</dd></div>
      <div><dt>Durée</dt><dd>{duration(row.duration_seconds)}</dd></div>
      <div><dt>Trade ID</dt><dd>{row.trade_id}</dd></div>
      {row.unresolved_reason && <div><dt>Raison non résolue</dt><dd>{row.unresolved_reason}</dd></div>}
    </dl>
  </article>
);

export function BurnInHistory({ s }: { s: BurnInStatusSnapshot }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("ALL");
  const [side, setSide] = useState("ALL");
  const [from, setFrom] = useState("");
  const [until, setUntil] = useState("");
  const [page, setPage] = useState(0);
  const filtered = s.lifecycle_history.filter(row =>
    (status === "ALL" || row.status === status) && (side === "ALL" || row.side === side) &&
    (!from || row.opened_at_utc.slice(0, 10) >= from) && (!until || row.opened_at_utc.slice(0, 10) <= until) &&
    [row.symbol, row.trade_id, row.open_decision_id ?? "", row.terminal_decision_id ?? ""].some(value => value.toLowerCase().includes(query.trim().toLowerCase())));
  const pages = Math.max(1, Math.ceil(filtered.length / 20));
  const currentPage = Math.min(page, pages - 1);
  const visible = filtered.slice(currentPage * 20, (currentPage + 1) * 20);
  return (
      <section className="burnin-panel" data-testid="burnin-history">
        <div className="burnin-section-head">
          <div><h3>Historique des ordres PAPER</h3><span>Une ligne par lifecycle PPL · plus récent en premier.</span></div>
          <strong>{s.lifecycle_history.length}</strong>
        </div>
        <div className="burnin-history-controls">
          <label>Rechercher un symbole ou une identité<input aria-label="Rechercher un ordre" value={query} onChange={event => { setQuery(event.target.value); setPage(0); }} /></label>
          <label>Statut<select aria-label="Statut des ordres" value={status} onChange={event => { setStatus(event.target.value); setPage(0); }}><option value="ALL">Tous les statuts</option><option value="OPEN">Ouverts</option><option value="CLOSED">Clôturés</option><option value="UNRESOLVED">Non résolus</option></select></label>
          <label>Sens<select aria-label="Sens des ordres" value={side} onChange={event => { setSide(event.target.value); setPage(0); }}><option value="ALL">Tous les sens</option><option value="LONG">LONG</option><option value="SHORT">SHORT</option></select></label>
          <label>Ouverture à partir du (UTC)<input type="date" aria-label="Date de début" value={from} onChange={event => { setFrom(event.target.value); setPage(0); }} /></label>
          <label>Ouverture jusqu’au (UTC)<input type="date" aria-label="Date de fin" value={until} onChange={event => { setUntil(event.target.value); setPage(0); }} /></label>
        </div>
        <p role="status">{filtered.length} ordres correspondent sur {s.lifecycle_history.length} cycles capturés. Page {currentPage + 1} sur {pages}.</p>
        {filtered.length === 0 && <p>Aucun ordre ne correspond aux filtres.</p>}
        <div className="burnin-history-table-wrap">
          <table className="burnin-history-table">
            <thead><tr>
              <th>Identité</th><th>Statut</th><th>Symbole</th><th>Sens</th><th>Ouverture</th><th>Fin</th>
              <th>Principal USD</th><th>Entrée</th><th>Sortie</th><th>Frais E/X</th><th>PnL brut</th><th>PnL net</th><th>Durée</th><th>Raison</th>
            </tr></thead>
            <tbody>
              {visible.map((row) => (
                <tr key={row.trade_id} data-testid="burnin-history-row">
                  <td>{row.trade_id}</td><td><span className={`burnin-status burnin-status-${row.status.toLowerCase()}`}>{row.status}</span></td>
                  <td>{row.symbol}</td><td>{row.side}</td><td>{row.opened_at_utc}</td><td>{row.terminal_at_utc ?? "EN COURS"}</td>
                  <td>{row.principal_usd}</td><td>{row.entry_price}</td><td>{num(row.exit_price)}</td>
                  <td>{row.entry_fee_usd} / {num(row.exit_fee_usd)}</td>
                  <td>{num(row.gross_pnl_usd)}</td>
                  <td>{row.status === "UNRESOLVED" ? "UNRESOLVED" : num(row.net_realized_pnl_usd)}</td>
                  <td>{duration(row.duration_seconds)}</td>
                  <td>{row.unresolved_reason ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="burnin-history-mobile">
          {visible.map((row) => <HistoryMobileCard key={row.trade_id} row={row} />)}
        </div>
        <nav className="burnin-history-pagination" aria-label="Pagination des ordres"><button disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Page précédente</button><button disabled={currentPage + 1 >= pages} onClick={() => setPage(currentPage + 1)}>Page suivante</button></nav>
      </section>

  );
}

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

      <BurnInStatistics snapshot={s} />
      <BurnInHistory s={s} />

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
