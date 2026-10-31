import React, { useState, useEffect, useRef } from "react";
import { useMarketSnapshot } from "../lib/marketClient";
import { fr } from "../lib/presentationFr";
import type { MarketOpportunity } from "../lib/marketTypes";
import { PublicationStamp } from "../components/PublicationStamp";
import "../market-catalogue.css";

function formatUtc(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toISOString().replace("T", " ").replace(".000Z", "Z");
}

const Stat: React.FC<{ label: string; value: React.ReactNode; hint?: string }> = ({ label, value, hint }) => (
  <div className="market-stat">
    <div className="market-stat-label">{label}</div>
    <div className="market-stat-value">{value}</div>
    {hint && <div className="market-stat-hint">{hint}</div>}
  </div>
);

const Side: React.FC<{ row: MarketOpportunity }> = ({ row }) => {
  const glyph = row.dominant_side === "LONG" ? "▲" : row.dominant_side === "SHORT" ? "▼" : "◆";
  const tone = row.dominant_side === "LONG" ? "long" : row.dominant_side === "SHORT" ? "short" : "neutral";
  return (
    <span className={`market-side market-side-${tone}`}>
      {glyph} {fr(row.dominant_side)}
    </span>
  );
};

function regimeTone(regime: string): string {
  const value = regime.toLowerCase();
  if (value.includes("bull")) return "bull";
  if (value.includes("bear")) return "bear";
  if (value.includes("range") || value.includes("sideway")) return "range";
  return "neutral";
}

const Regime: React.FC<{ value: string }> = ({ value }) => (
  <span className={`market-regime market-regime-${regimeTone(value)}`} title={value}>{fr(value)}</span>
);

export const MarketView: React.FC = () => {
  const state = useMarketSnapshot();
  const [query, setQuery] = useState("");
  const [side, setSide] = useState("ALL");
  const [population, setPopulation] = useState("qualified");
  const [regime, setRegime] = useState("ALL");
  const [page, setPage] = useState(0);
  const [view, setView] = useState("table");
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);

  useEffect(() => { setPage(0); setSelectedSymbol(null); }, [query, side, population, regime, view]);

  const detail = useRef<HTMLElement>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  useEffect(() => { if (selectedSymbol) detail.current?.focus(); }, [selectedSymbol]);
  const close = () => { setSelectedSymbol(null); trigger.current?.focus(); };

  if (state.status === "loading") {
    return (
      <div data-testid="market-view" className="market-panel market-loading">
        Chargement des observations CryptoRadar…
      </div>
    );
  }

  if (state.status === "api_error") {
    return (
      <div data-testid="market-view" className="market-panel market-error">
        <div data-testid="market-error" className="market-error-title">
          Observations du marché indisponibles
        </div>
        <details className="market-error-detail"><summary>Source et diagnostic</summary><p>HTTP {state.httpStatus}</p>
          {state.error.error_code ?? "MARKET_API_ERROR"}: {state.error.error_message ?? "Aucune publication de marché disponible."}
        </details>
      </div>
    );
  }

  if (state.status === "transport_error") {
    return (
      <div data-testid="market-view" className="market-panel market-error">
        <div data-testid="market-error" className="market-error-title">
          Erreur de contrat ou de transport du marché
        </div>
        <details className="market-error-detail"><summary>Source et diagnostic</summary>{state.message}</details>
      </div>
    );
  }

  const m = state.snapshot;
  const stale = m.freshness_classification === "STALE";
  const complete = m.catalogue;
  // Global symbol search includes below-threshold observations when the source supplies them.
  const allPopulation = Boolean(complete) && (population === "all" || query.trim() !== "");
  const available = complete ? (allPopulation ? complete.rows : complete.qualified_rows) : m.top_opportunities;
  const rows = available.filter((row) =>
    row.symbol.toUpperCase().includes(query.trim().toUpperCase()) &&
    (side === "ALL" || row.dominant_side === side) &&
    (regime === "ALL" || row.regime === regime));
  const pageCount = Math.max(1, Math.ceil(rows.length / 20));
  const currentPage = Math.min(page, pageCount - 1);
  const visibleRows = rows.slice(currentPage * 20, currentPage * 20 + 20);
  const populationLabel = allPopulation ? "tous les paquets observés" : `paquets au seuil ≥ ${m.min_confidence}`;
  const changePage = (next: number) => { setPage(next); setSelectedSymbol(null); };
  const reset = () => { setQuery(""); setSide("ALL"); setPopulation("qualified"); setRegime("ALL"); setPage(0); setSelectedSymbol(null); };
  // Resolve from the current validated snapshot: never retain a stale row
  // object after polling replaces the source or the selection is filtered out.
  const selected = visibleRows.find((row) => row.symbol === selectedSymbol);

  return (
    <div className="market-stack" data-testid="market-view">
      <section className="market-panel market-summary">
        <PublicationStamp source="CryptoRadar · observation" generatedAt={m.generated_at_utc} freshness={m.freshness_classification} age={m.snapshot_age_s}/>
        <div className="market-summary-row">
          <div>
            <div className="market-eyebrow">OBSERVATION DU MARCHÉ</div>
            <div className="market-title">CryptoRadar</div>
            <div className="market-subtitle">
              Fenêtre d’observation de {m.window_hours}h · lecture seule
            </div>
          </div>
          <div
            data-testid="market-freshness"
            className={`market-freshness ${stale ? "market-freshness-stale" : "market-freshness-fresh"}`}
          >
            <span className="market-freshness-dot" aria-hidden="true" />
            {fr(m.freshness_classification)} · {Math.round(m.snapshot_age_s)}s
          </div>
        </div>

        <details className="market-provenance-details">
          <summary>Provenance et dates des sources</summary>
          <p className="market-catalogue-window" data-testid="market-venue-provenance">Plateforme et type de marché : non attestés dans cette publication. Le symbole seul ne prouve ni l’exchange ni le contrat observé.</p>
          {complete && <p className="market-catalogue-window">Fenêtre UTC bornée : {formatUtc(complete.coverage.start_at_utc)} → {formatUtc(complete.coverage.end_at_utc)}. {complete.coverage.included_packets} observations incluses sur {complete.coverage.input_packets} chargées ; {complete.coverage.outside_window_packets} hors fenêtre, {complete.coverage.future_packets} futures, {complete.coverage.unresolved_timestamp_packets} sans date résolue. L’univers observé ne représente pas toutes les paires d’un exchange.</p>}
          <div className="market-provenance-grid"><div className="market-provenance">Autorité : <code>{m.authority}</code></div>
            <div className="market-provenance">
              Publication : <span className="market-provenance-value">{formatUtc(m.generated_at_utc)}</span>
            </div>
            <div className="market-provenance">
              Dernier paquet source : <span className="market-provenance-value">{formatUtc(m.source_updated_at_utc)}</span>
            </div>
          </div>
        </details>
      </section>

      <section className="market-stats" aria-label="Synthèse du marché observé">
        <Stat label="Régime publié" value={m.market_regime ? <Regime value={m.market_regime} /> : "Inconnu"} hint="contexte observé" />
        <Stat label="Symboles observés" value={m.universe_size} hint={`fenêtre de ${m.window_hours}h`} />
        <Stat label={`Radar ≥ ${m.min_confidence}`} value={m.actionable_count} hint="seuil d’affichage" />
        <Stat label="À surveiller" value={m.watchlist_count} hint="sous le seuil du scanner" />
      </section>

      <section className="market-panel market-opportunities-panel">
        <div className="market-section-head">
          <div>
            <div className="market-section-title">Scanner des symboles</div>
            <div className="market-section-subtitle">Ordre source conservé · le score n’est pas une probabilité de gain.</div>
          </div>
          <div className="market-table-meta">
            {m.packets_observed} paquets observés
          </div>
        </div>

        <div className="market-scanner-controls">
          <label>Recherche symbole
            <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={complete ? "BTC ou ETH…" : "Symbole dans les lignes publiées…"} />
          </label>
          <label>Biais dominant
            <select value={side} onChange={(event) => setSide(event.target.value)}>
              <option value="ALL">Tous</option><option value="LONG">Acheteur</option>
              <option value="SHORT">Vendeur</option><option value="MIXED">Mixte</option>
            </select>
          </label>
          {complete && <label>Population
            <select aria-label="Population" value={allPopulation ? "all" : population} disabled={query.trim() !== ""} onChange={(event) => setPopulation(event.target.value)}>
              <option value="qualified">Au seuil publié</option><option value="all">Tous les observés</option>
            </select>
          </label>}
          <label>Régime publié
            <select aria-label="Régime publié" value={regime} onChange={(event) => setRegime(event.target.value)}>
              <option value="ALL">Tous</option>
              {[...new Set(available.map((row) => row.regime))].sort().map((r) => <option key={r} value={r}>{fr(r)}</option>)}
            </select>
          </label>
          <button type="button" onClick={reset}>Réinitialiser</button>
        </div>
        <div className="market-scanner-coverage" role="status" data-testid="market-scanner-coverage">
          {complete ? <>{rows.length} résultat(s) · {available.length} symbole(s) consultables · {populationLabel} · univers observé : {m.universe_size}. {query.trim() && "Recherche élargie à tous les observés, hors seuil inclus."}</> : <>{rows.length} résultat(s) · {m.top_opportunities.length} ligne(s) publiée(s) sur {m.actionable_count} symbole(s) au seuil · univers observé : {m.universe_size}
            {m.top_opportunities.length < m.actionable_count && <span> · Couverture partielle : recherche et filtres limités aux lignes publiées. Un symbole absent de ce fichier ne peut pas être retrouvé ici.</span>}</>}
        </div>
        <div className="market-display-choice" role="group" aria-label="Affichage du scanner">
          <button type="button" aria-pressed={view === "table"} onClick={() => setView("table")}>Tableau</button>
          <button type="button" aria-pressed={view === "map"} onClick={() => setView("map")}>Carte des symboles</button>
        </div>
        {stale && <div className="market-scanner-coverage">Données historiques périmées · état actuel du marché INCONNU.</div>}
        {selected && <section className="market-symbol-detail" ref={detail} tabIndex={-1} onKeyDown={(event) => { if (event.key === "Escape") close(); }} aria-label="Détail observationnel" data-testid="market-symbol-detail">
          <div className="market-section-head"><strong>{selected.symbol} · détail observationnel</strong>
            <button type="button" onClick={close}>Fermer le détail</button></div>
          <p>Population : {populationLabel}, fenêtre {m.window_hours}h. {stale ? "Ancien · périmé · historique" : "Publication récente · observation"}.</p>
          <dl>
            <div><dt>Score moyen</dt><dd>{selected.avg_confidence.toFixed(1)}</dd></div>
            <div><dt>Score maximal</dt><dd>{selected.max_confidence.toFixed(1)}</dd></div>
            <div><dt>Signaux</dt><dd>{selected.n_signals}</dd></div>
            <div><dt>Biais dominant</dt><dd><Side row={selected} /></dd></div>
            <div><dt>Dominance</dt><dd>{selected.dominance_pct.toFixed(0)}%</dd></div>
            <div><dt>Régime</dt><dd><Regime value={selected.regime} /></dd></div>
          </dl>
          <p>Comptages LONG/SHORT exacts non disponibles · NOT_AVAILABLE dans cette projection. Aucune permission de trading.</p>
        </section>}
        {available.length === 0 ? (
          <div className="market-empty" data-testid="market-empty">
            {allPopulation ? "Aucune observation datée dans cette publication." : "Aucun symbole n’atteint le seuil d’affichage dans cette fenêtre d’observation."}
          </div>
        ) : rows.length === 0 ? (
          <div className="market-empty" data-testid="market-filter-empty">Aucun résultat dans les lignes publiées pour ces filtres. Le marché n’est pas déclaré vide.</div>
        ) : (
          <>
            {view === "map" ? <div className="market-heatmap" data-testid="market-heatmap">
              <p className="market-heatmap-legend">Couleur : biais publié · intensité : score moyen. Même population et même ordre que le tableau, sans score de timing.</p>
              <div className="market-heatmap-grid">
                {visibleRows.map((row) => <button type="button" key={row.symbol} className={`market-heat-cell market-heat-${row.dominant_side.toLowerCase()}`} style={{ "--heat-fill": `${Math.min(30, Math.max(5, row.avg_confidence * 0.3))}%` } as React.CSSProperties} aria-label={`Détail ${row.symbol}`} onClick={(event) => { trigger.current = event.currentTarget; setSelectedSymbol(row.symbol); }}>
                  <strong>{row.symbol}</strong><span>{row.avg_confidence.toFixed(1)} · score moyen</span><span>{fr(row.dominant_side)} · {fr(row.regime)}</span><span>{row.n_signals} observation(s)</span>
                </button>)}
              </div>
            </div> : <div className="market-table-wrap market-table-desktop" role="region" aria-label="Scanner CryptoRadar · défilement horizontal" tabIndex={0}>
              <table className="market-table">
                <thead>
                  <tr>
                    <th>Symbole</th>
                    <th className="market-num">Score moyen</th>
                    <th className="market-num">Score maximal</th>
                    <th>Biais</th>
                    <th className="market-num">Dominance</th>
                    <th className="market-num">Signaux</th>
                    <th>Régime</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map((row) => (
                    <tr key={row.symbol} data-testid="market-opportunity-row">
                      <td className="market-table-symbol"><button type="button" className="market-symbol-button" aria-label={`Détail ${row.symbol}`} onClick={(event) => { trigger.current = event.currentTarget; setSelectedSymbol(row.symbol); }}>{row.symbol}</button></td>
                      <td className="market-num">{row.avg_confidence.toFixed(1)}</td>
                      <td className="market-num">{row.max_confidence.toFixed(1)}</td>
                      <td><Side row={row} /></td>
                      <td className="market-num">{row.dominance_pct.toFixed(0)}%</td>
                      <td className="market-num">{row.n_signals}</td>
                      <td><Regime value={row.regime} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>}
            <nav className="market-pagination" aria-label="Pages des symboles">
              <button type="button" onClick={() => changePage(currentPage - 1)} disabled={currentPage === 0}>Page précédente</button>
              <span role="status">Page {currentPage + 1} / {pageCount} · {rows.length} résultat(s)</span>
              <button type="button" onClick={() => changePage(currentPage + 1)} disabled={currentPage + 1 >= pageCount}>Page suivante</button>
            </nav>
          </>
        )}
      </section>

      <details className="market-panel market-analysis-notes">
        <summary>Timing, volume et limites du scanner</summary>
        <p>Le score moyen décrit les observations de la fenêtre publiée. « Signaux » compte des paquets d’observation, pas des ordres, des transactions ou du volume échangé. La dominance décrit leurs biais, pas une part de volume acheteur ou vendeur.</p>
        <dl>
          <div><dt>Variation du score sur 5 / 15 min</dt><dd>Non disponible : cette projection ne publie pas les points horodatés de comparaison.</dd></div>
          <div><dt>Volume relatif / RVOL</dt><dd>Non disponible : les volumes de marché et leur référence ne sont pas publiés.</dd></div>
          <div><dt>Transition de régime</dt><dd>Non disponible : le régime agrégé ne date pas son dernier changement.</dd></div>
        </dl>
        <p>Les fenêtres 1 h ou 4 h exigent leur propre publication bornée. Recharger une capture de 24 h ne crée pas ces observations. Aucun score ne certifie une opportunité exploitable.</p>
      </details>
      <div className="market-footer">
        Le scanner décrit des observations au seuil publié. Aucun score ne donne une permission de trading.
      </div>
    </div>
  );
};
