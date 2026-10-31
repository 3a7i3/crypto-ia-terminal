import React, { useEffect, useRef, useState } from "react";
import { useVenueComparison } from "../lib/venueComparisonClient";
import { PublicationStamp } from "../components/PublicationStamp";
import type { VenueRow } from "../lib/venueComparison";
import "../market-venues.css";
const names: Record<string, string> = { mexc: "MEXC", bybit: "Bybit", okx: "OKX", kraken: "Kraken", bitfinex: "Bitfinex", kucoin: "KuCoin", coinbase_exchange: "Coinbase Exchange", hyperliquid: "Hyperliquid" };
const kinds: Record<string, string> = { SPOT: "Spot", PERPETUAL_LINEAR: "Perpétuel linéaire", PERPETUAL_INVERSE: "Perpétuel inverse", FUTURE_LINEAR: "Échéance linéaire", FUTURE_INVERSE: "Échéance inverse" };
const time = (v: string | null) => v ? new Date(v).toISOString().replace("T", " ") : "Date non disponible";
const number = (v: string | null, unit = "") => v === null ? "—" : v + unit;
function reason(row: VenueRow): string {
  if (row.status === "AVAILABLE") return "Qualifiée à la publication";
  if (row.reason === "SOURCE_NOT_SUPPLIED") return "Source non reçue";
  if (row.reason === "STALE") return "Observation périmée";
  if (row.reason === "UNRESOLVED_TIMESTAMP_KIND" || row.reason === "MISSING_EXCHANGE_TIMESTAMP") return "Date exchange non qualifiée";
  if (row.reason === "CROSSED_BOOK") return "Carnet croisé";
  return "Qualité indisponible";
}
export const MarketVenuesView: React.FC = () => {
  const state = useVenueComparison();
  const [instrumentId, setInstrumentId] = useState("");
  const [reference, setReference] = useState("");
  const [selectedVenue, setSelectedVenue] = useState<string | null>(null);
  const detail = useRef<HTMLElement>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  useEffect(() => { if (selectedVenue) detail.current?.focus(); }, [selectedVenue]);
  useEffect(() => { setSelectedVenue(null); }, [instrumentId, reference]);
  const close = () => { setSelectedVenue(null); trigger.current?.focus(); };
  if (state.status === "loading") return <section className="market-panel venue-panel" data-testid="venue-comparison-view" role="status">Chargement de la comparaison des plateformes…</section>;
  if (state.status === "unavailable") return <section className="market-panel venue-panel" data-testid="venue-comparison-view">
    <h2>Comparaison des plateformes</h2><p role="status">Aucune publication de comparaison disponible.</p>
    <p>Les sources et prix ne sont pas déclarés vides. Leur disponibilité reste inconnue.</p>
    <details><summary>Source et diagnostic</summary><p>{state.diagnostic}</p></details>
  </section>;
  const pub = state.publication;
  const group = pub.groups.find(g => g.instrument_id === instrumentId) ?? pub.groups[0];
  const ref = group.rows.some(r => r.venue === reference) ? reference : group.default_reference;
  const selected = group.rows.find(r => r.venue === selectedVenue);
  const stale = pub.freshness_classification === "STALE";
  return <div className="market-stack venue-comparison" data-testid="venue-comparison-view">
    <section className="market-panel venue-panel">
      <PublicationStamp source="Cotations multi-plateformes · publication" generatedAt={pub.generated_at_utc} freshness={pub.freshness_classification} age={pub.publication_age_ms / 1000}/>
      <h2>Comparaison des plateformes</h2>
      {pub.evidence_kind === "SYNTHETIC" && <p className="venue-evidence" data-testid="venue-synthetic">Exemple synthétique · aucune connexion attestée</p>}
      <p className="venue-quality" role="status">{stale ? "Publication périmée · prix actuels INCONNUS." : pub.freshness_classification === "UNRESOLVED" ? "Qualité temporelle indisponible." : "Publication récente · aucune activité de collecteur attestée."}</p>
      <p>{pub.source_counts.supplied} cotation(s) reçue(s) sur {pub.source_counts.expected} attendue(s) · {pub.source_counts.available} qualifiée(s) à la publication.</p>
      <p className="venue-note">Les devises, actifs et contrats restent séparés. Frais, funding, conversions et exécution ne sont pas inclus.</p>
    </section>
    <section className="market-panel venue-panel">
      <div className="venue-controls">
        <label>Instrument observé<select aria-label="Instrument observé" value={group.instrument_id} onChange={e => { setInstrumentId(e.target.value); setReference(""); }}>
          {pub.groups.map(g => <option key={g.instrument_id} value={g.instrument_id}>{g.instrument.base_asset_id}/{g.instrument.quote_asset_id} · {kinds[g.instrument.market_kind]}</option>)}
        </select></label>
        <label>Plateforme de référence<select aria-label="Plateforme de référence" value={ref} onChange={e => setReference(e.target.value)}>
          {group.rows.map(r => <option key={r.venue} value={r.venue}>{names[r.venue]}</option>)}
        </select></label>
      </div>
      <p className="venue-note">Écarts publiés par rapport à {names[ref]} · ordre des sources conservé, sans classement.</p>
      <div className="venue-table-wrap" role="region" aria-label="Prix par plateforme · défilement horizontal" tabIndex={0}>
        <table className="market-table"><caption className="venue-caption">Prix en {group.instrument.quote_asset_id} · {kinds[group.instrument.market_kind]}</caption>
          <thead><tr><th>Plateforme</th><th>Acheteur (bid)</th><th>Vendeur (ask)</th><th>Spread interne</th><th>Écart des milieux</th><th>Qualité à la publication</th></tr></thead>
          <tbody>{group.rows.map(row => {
            const pair = group.comparisons.find(p => p.reference_venue === ref && p.other_venue === row.venue);
            return <tr key={row.venue} data-testid="venue-row">
              <td><button className="market-symbol-button" type="button" aria-label={"Détail source " + names[row.venue]} onClick={e => { trigger.current = e.currentTarget; setSelectedVenue(row.venue); }}>{names[row.venue]}</button></td>
              <td>{number(row.bid)}</td><td>{number(row.ask)}</td><td>{number(row.spread_bps, " bp")}</td>
              <td>{row.venue === ref ? "Référence" : number(pair?.mid_basis_bps ?? null, " bp")}</td><td>{reason(row)}</td>
            </tr>;
          })}</tbody>
        </table>
      </div>
      <p className="venue-note">« — » signifie non disponible, jamais zéro. Les métriques restent celles de la publication datée.</p>
    </section>
    {selected && <section className="market-panel venue-panel venue-detail" ref={detail} tabIndex={-1} onKeyDown={e => { if (e.key === "Escape") close(); }} data-testid="venue-source-detail" aria-label="Détail de la source">
      <div className="market-section-head"><h3>{names[selected.venue]} · détail de la source</h3><button type="button" onClick={close}>Fermer le détail de source</button></div>
      <dl>
        <div><dt>Symbole natif</dt><dd>{selected.native_symbol}</dd></div>
        <div><dt>Date exchange</dt><dd>{time(selected.observed_at_utc)}</dd></div>
        <div><dt>Réception</dt><dd>{time(selected.received_at_utc)}</dd></div>
        <div><dt>Sémantique temporelle</dt><dd>{selected.timestamp_kind} · {selected.source.timestamp_note}</dd></div>
        <div><dt>Qualité</dt><dd>{reason(selected)}{selected.reason && <> · <code>{selected.reason}</code></>}</dd></div>
        <div><dt>Quantités au meilleur prix, unité de base</dt><dd>Bid : {number(selected.bid_size_base)} · ask : {number(selected.ask_size_base)}</dd></div>
        <div><dt>Identité du contrat</dt><dd>{group.instrument.contract_identity} · règlement {group.instrument.settlement_asset_id}</dd></div>
        <div><dt>Mapping fourni</dt><dd>{selected.source.mapping_id}<br/><code>{selected.source.mapping_sha256}</code></dd></div>
        <div><dt>Capture et séquence natives</dt><dd>{selected.source.endpoint_id} · {selected.source.native_sequence ?? "Séquence non disponible"}<br/><code>{selected.source.payload_sha256 ?? "Empreinte de réponse non disponible"}</code></dd></div>
        <div><dt>Identité de la réponse</dt><dd>{selected.source.identity_evidence} · horloge {selected.observer_clock_id ?? "Non disponible"}</dd></div>
      </dl>
      {selected.venue !== ref && (() => { const pair = group.comparisons.find(p => p.reference_venue === ref && p.other_venue === selected.venue); return <p>Comparaison avec {names[ref]} : {pair?.status === "AVAILABLE" ? <>écart brut achat référence / vente source {number(pair.buy_reference_sell_other_gross_bps, " bp")} ; direction inverse {number(pair.buy_other_sell_reference_gross_bps, " bp")}. Frais non inclus.</> : <>Non disponible · <code>{pair?.reason ?? "NOT_AVAILABLE"}</code></>}</p>; })()}
    </section>}
    <details className="market-panel venue-panel"><summary>Comprendre les mesures et leurs limites</summary>
      <p>Le spread interne compare le bid et l’ask d’une même plateforme. L’écart des milieux compare deux cotations du même instrument. Un écart brut entre plateformes n’établit pas un bénéfice.</p>
      <p>Une date, un mapping ou une synchronisation non qualifiés rendent la comparaison indisponible. Un prix de dernier trade ne remplace pas un prix de carnet. Cette vue ne donne aucune autorité de trading.</p>
    </details>
  </div>;
};
