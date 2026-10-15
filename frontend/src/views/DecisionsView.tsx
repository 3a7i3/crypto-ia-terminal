// ── DecisionsView — decision_pipeline.per_symbol_decisions, as-supplied ────
//
// EXECUTION_AUTHORITY, OBSERVATIONAL_TELEMETRY, and any other authority
// label are always distinguished. `is_actionable` is rendered exactly as
// produced — never inferred from score/conviction/regime/blockers/lifecycle
// state. No execution rate, rejection rate, win rate, or aggregate pipeline
// statistic is computed here. Descriptive counts cover only supplied rows.

import React, { useState } from "react";
import { fr } from "../lib/presentationFr";
import type { OperatorSnapshot, PerSymbolDecision } from "../types";
import { ObservedValueView } from "../components/ObservedValueView";

const AuthorityTag: React.FC<{ authority: string }> = ({ authority }) => (
  <span
    data-testid="authority-tag"
    data-authority={authority}
    className="font-mono text-[9px] px-1 py-0.5 ml-1"
    style={{
      borderRadius: "var(--r-chip)",
      color: "var(--accent)",
      background: "var(--bg-card-soft)",
    }}
  >
    {authority}
  </span>
);

const DecisionRow: React.FC<{ rec: PerSymbolDecision }> = ({ rec }) => (
  <tr data-testid="decision-row" className="border-b" style={{ borderColor: "var(--bg-border)" }}>
    <td className="py-1.5 pr-3 font-mono text-xs">{rec.symbol}</td>
    <td className="py-1.5 pr-3 font-mono text-xs">
      <ObservedValueView ov={rec.is_actionable} render={(v) => (v ? "true" : "false")} />
      <AuthorityTag authority={rec.is_actionable.authority} />
    </td>
    <td className="py-1.5 pr-3 font-mono text-xs">
      <ObservedValueView ov={rec.trade_allowed} render={(v) => (v ? "true" : "false")} />
      <AuthorityTag authority={rec.trade_allowed.authority} />
    </td>
    <td className="py-1.5 pr-3 font-mono text-xs">
      <ObservedValueView ov={rec.first_blocker} />
      <AuthorityTag authority={rec.first_blocker.authority} />
    </td>
    <td className="py-1.5 pr-3 font-mono text-xs">
      <ObservedValueView ov={rec.side} />
    </td>
    <td className="py-1.5 pr-3 font-mono text-xs">
      <ObservedValueView ov={rec.regime} />
    </td>
    <td className="py-1.5 pr-3 font-mono text-xs">
      <ObservedValueView ov={rec.lifecycle_state} />
    </td>
    <td className="py-1.5 pr-3 font-mono text-xs">
      <ObservedValueView ov={rec.confidence_raw} />
    </td>
  </tr>
);

function text(value: { value: unknown; semantics: string }): string {
  return (value.semantics === "PRESENT" || value.semantics === "STALE") && typeof value.value === "string" ? value.value : "UNKNOWN";
}
function admission(rec: PerSymbolDecision): string {
  const ov = rec.trade_allowed;
  if (ov.semantics === "PRESENT" && ov.value === true) return "Admissible";
  if ((ov.semantics === "PRESENT" || ov.semantics === "FALSE") && ov.value === false) return "Non admissible";
  return "Inconnu";
}

export const DecisionsView: React.FC<{ snapshot: OperatorSnapshot }> = ({ snapshot }) => {
  const dp = snapshot.decision_pipeline;
  const records = Array.isArray(dp.per_symbol_decisions) ? dp.per_symbol_decisions : null;
  const [symbol, setSymbol] = useState("");
  const [decision, setDecision] = useState("");
  const [regime, setRegime] = useState("");
  const [blocker, setBlocker] = useState("");
  const rows = records ?? [];
  const filtered = rows.filter(rec => rec.symbol.toLocaleLowerCase().includes(symbol.trim().toLocaleLowerCase())
    && (!decision || admission(rec) === decision)
    && (!regime || text(rec.regime) === regime)
    && (!blocker || text(rec.first_blocker) === blocker));
  const regimes = [...new Set(rows.map(rec => text(rec.regime)))].sort();
  const blockers = [...new Set(rows.map(rec => text(rec.first_blocker)))].sort((a, b) => rows.filter(rec => text(rec.first_blocker) === b).length - rows.filter(rec => text(rec.first_blocker) === a).length || a.localeCompare(b));
  const tone = (value: string) => value === "Admissible" ? "ok" : value === "Non admissible" ? "reject" : "unknown";
  return (
    <div className="decisions-stack" data-testid="decisions-view">
      <section className="mobile-panel">
        <h2>Décisions observées</h2>
        <p>Cette vue décrit les lignes de la capture, sans autoriser un ordre. « Signal exploitable » (is_actionable), « admissible » (trade_allowed) et exécution effective sont trois notions distinctes.</p>
        <p className="source-date">Source : {dp.source} · observation : {dp.observed_at_utc} · {fr(dp.freshness)}.<br />Capture opérateur : {snapshot.generated_at_utc} · {fr(snapshot.freshness_classification)}.</p>
        {(dp.freshness === "STALE" || snapshot.freshness_classification === "STALE") && <p className="mobile-attention" role="status">Données périmées : résumé de la dernière capture, aucune admission actuelle attestée.</p>}
        <dl className="mobile-metrics" aria-label="Résumé des lignes observées">
          <div><dt>Décisions observées</dt><dd>{records === null ? "Inconnu" : rows.length}</dd></div>
          {(["Admissible", "Non admissible", "Inconnu"] as const).map(label => <div key={label}><dt>{label === "Inconnu" ? "Admission inconnue" : label}</dt><dd>{records === null ? "Inconnu" : rows.filter(rec => admission(rec) === label).length}</dd></div>)}
        </dl>
        <h3>Principaux bloqueurs de cette capture</h3>
        {records === null ? <p>Répartition inconnue.</p> : blockers.length === 0 ? <p>Aucun bloqueur renseigné dans les lignes publiées.</p> : <ul className="blocker-list">{blockers.map(value => <li key={value}>{fr(value)} : {rows.filter(rec => text(rec.first_blocker) === value).length}</li>)}</ul>}
        <p>Ces comptes descriptifs ne remplacent pas l’admission agrégée du producteur, ni une mesure de performance.</p>
      </section>
      <section className="mobile-panel">
        <h3>Rechercher et filtrer</h3>
        <div className="decision-filters">
          <label>Recherche par symbole<input value={symbol} onChange={event => setSymbol(event.target.value)} type="search" /></label>
          <label>Décision<select aria-label="Décision" value={decision} onChange={event => setDecision(event.target.value)}><option value="">Toutes</option>{["Admissible", "Non admissible", "Inconnu"].map(value => <option key={value}>{value}</option>)}</select></label>
          <label>Régime<select aria-label="Régime" value={regime} onChange={event => setRegime(event.target.value)}><option value="">Tous</option>{regimes.map(value => <option key={value} value={value}>{fr(value)}</option>)}</select></label>
          <label>Bloqueur<select aria-label="Bloqueur" value={blocker} onChange={event => setBlocker(event.target.value)}><option value="">Tous</option>{blockers.map(value => <option key={value} value={value}>{fr(value)}</option>)}</select></label>
          <button type="button" onClick={() => { setSymbol(""); setDecision(""); setRegime(""); setBlocker(""); }}>Réinitialiser</button>
        </div>
        <p>{filtered.length} ligne(s) affichée(s){records === null && " · source inconnue"}.</p>
        {filtered.length === 0 && <p role="status">{records === null ? "Décisions non disponibles." : rows.length === 0 ? "Aucune décision dans cette capture." : "Aucun résultat pour ces filtres."}</p>}
        <div className="decision-mobile-cards">
          {filtered.map((rec, index) => <article className="decision-card" key={`${rec.packet_id ?? rec.symbol}-${index}`} data-testid="decision-mobile-card">
            <header><h3>{rec.symbol}</h3><span className={`decision-state tone-${tone(admission(rec))}`}>{admission(rec)}</span></header>
            <dl className="mobile-facts"><div><dt>Sens</dt><dd><ObservedValueView ov={rec.side} render={value => fr(String(value).toUpperCase())} /></dd></div>
              <div><dt>Régime</dt><dd><ObservedValueView ov={rec.regime} render={value => fr(String(value))} /></dd></div>
              <div><dt>Bloqueur</dt><dd><ObservedValueView ov={rec.first_blocker} /></dd></div>
              <div><dt>Signal exploitable</dt><dd><ObservedValueView ov={rec.is_actionable} render={value => value ? "Oui" : "Non"} /></dd></div></dl>
            <details><summary>Détails et provenance</summary><dl className="mobile-facts">
              <div><dt>Admissibilité publiée</dt><dd><ObservedValueView ov={rec.trade_allowed} render={value => value ? "Oui" : "Non"} /></dd></div>
              <div><dt>Dernière transition UTC</dt><dd><ObservedValueView ov={rec.latest_transition_at_utc} /></dd></div>
              <div><dt>Décision créée UTC</dt><dd><ObservedValueView ov={rec.created_at} /></dd></div>
              <div><dt>État du cycle</dt><dd><ObservedValueView ov={rec.lifecycle_state} /></dd></div>
              <div><dt>Confiance brute</dt><dd><ObservedValueView ov={rec.confidence_raw} /></dd></div>
            </dl><p>Identité : {rec.packet_id ?? "Inconnu"} · contexte : {rec.context_id ?? "Inconnu"}</p>
              <p>Autorité du signal : {rec.is_actionable.authority} · admissibilité : {rec.trade_allowed.authority}</p></details>
          </article>)}
        </div>
        <details className="decision-technical"><summary>Vue technique · tableau complet</summary>
          <p>UNKNOWN ≠ 0. Aucune statistique d’exécution, de rejet ou de gain n’est calculée.</p>
          <p>Admission agrégée du producteur : <ObservedValueView ov={dp.trade_allowed} render={value => value ? "Oui" : "Non"} /> · bloqueur : <ObservedValueView ov={dp.first_blocker} /></p>
          <div className="technical-table" role="region" aria-label="Tableau technique des décisions" tabIndex={0}><table><thead><tr>{["Symbole", "is_actionable", "trade_allowed", "first_blocker", "Sens", "Régime", "Cycle", "Confiance"].map(label => <th key={label}>{label}</th>)}</tr></thead><tbody>{filtered.map((rec, index) => <DecisionRow key={`${rec.packet_id ?? rec.symbol}-${index}`} rec={rec} />)}</tbody></table></div>
        </details>
      </section>
    </div>
  );
};
