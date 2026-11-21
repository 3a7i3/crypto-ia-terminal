import React, { useState } from "react";
import { useDerivativesStress } from "../lib/derivativesStressClient";
import type { Funding, OpenInterest, StressLeg, Underlying } from "../lib/derivativesStress";
import { PublicationStamp } from "./PublicationStamp";
import { MarketSourceNotice } from "./MarketSourceNotice";
import { marketSourceSetup } from "../lib/marketSourceSetup";
import { legLabel, reasonLabel, signLabel, windowLabel } from "../lib/stressLabels";
import { venueName } from "../lib/venueNames";
import "../market-stress.css";

const dash = (reason: string | null, status: string) => status === "AVAILABLE" ? null :
  <span className="stress-unavailable">{reason === "NOT_APPLICABLE" ? "Sans objet" : "—"}{reason !== "NOT_APPLICABLE" && <small>{reasonLabel(reason)} · <code>{reason}</code></small>}</span>;

function FundingCell({ f }: { f: Funding }) {
  return dash(f.reason, f.status) ?? <>{f.rate}<small>par {f.interval_s! / 3600} h · équivalent 8 h {f.rate_8h_equivalent} · annualisé simple {f.annualized_simple_pct} %</small></>;
}
function OpenInterestCell({ o, quote }: { o: OpenInterest; quote: string }) {
  if (o.value === null) return dash(o.reason, o.status);
  return <>{o.value} {o.unit?.toLowerCase()}<small>{o.notional_quote !== null ? `${o.notional_quote} ${quote} (notionnel)` : `Notionnel indisponible · ${reasonLabel(o.reason)}`}</small></>;
}

function Legs({ u }: { u: Underlying }) {
  return <div className="stress-table-wrap" role="region" aria-label="Dérivés par plateforme · défilement horizontal" tabIndex={0}>
    <table className="market-table"><caption className="venue-caption">Prix en {u.quote_asset_id} · valeurs telles que publiées</caption>
      <thead><tr><th>Plateforme et produit</th><th>Prix</th><th>Prime vs indice (bp)</th><th>Base vs spot (bp)</th><th>Funding</th><th>Open interest</th><th>Qualité</th></tr></thead>
      <tbody>{u.legs.map(l => <tr key={l.instrument_id + l.venue} data-testid="stress-leg">
        <th scope="row" className="stress-cell">{venueName(l.venue)}<small>{l.instrument.market_kind} · {l.native_symbol}</small></th>
        <td className="stress-cell">{l.price ?? "—"}<small>{l.price_kind ?? ""}{l.index_price && " · indice " + l.index_price}</small></td>
        <td className="stress-cell">{dash(l.premium_to_index.reason, l.premium_to_index.status) ?? l.premium_to_index.bps}</td>
        <td className="stress-cell">{dash(l.basis_vs_spot.reason, l.basis_vs_spot.status) ?? <>{l.basis_vs_spot.bps}<small>contre {venueName(l.basis_vs_spot.against_venue!)}{l.basis_vs_spot.annualized_pct && " · annualisé simple " + l.basis_vs_spot.annualized_pct + " %"}</small></>}</td>
        <td className="stress-cell"><FundingCell f={l.funding}/></td>
        <td className="stress-cell"><OpenInterestCell o={l.open_interest} quote={u.quote_asset_id}/></td>
        <td className="stress-cell">{l.status === "AVAILABLE" ? "Qualifiée à la publication" : reasonLabel(l.reason)}<small>{l.timestamp_kind}</small></td>
      </tr>)}</tbody></table>
  </div>;
}

function Windows({ legs }: { legs: StressLeg[] }) {
  const derivatives = legs.filter(l => l.windows.some(w => w.status === "AVAILABLE") || l.instrument.market_kind !== "SPOT");
  return <details className="market-panel venue-panel"><summary>Prix et open interest sur fenêtres ({derivatives.length} marché(s))</summary>
    <p className="venue-note">Variations entre l’échantillon publié au début de la fenêtre et l’observation courante. Les sens sont publiés sans interprétation : une hausse simultanée du prix et de l’open interest n’établit ni acheteurs ni vendeurs agressifs.</p>
    <div className="stress-table-wrap" role="region" aria-label="Fenêtres · défilement horizontal" tabIndex={0}><table className="market-table">
      <thead><tr><th>Marché</th>{derivatives[0]?.windows.map(w => <th key={w.window_s}>{windowLabel(w.window_s)}</th>)}</tr></thead>
      <tbody>{derivatives.map(l => <tr key={l.instrument_id + l.venue}><th scope="row">{legLabel(l)}</th>
        {l.windows.map(w => <td key={w.window_s} className="stress-cell" data-testid="stress-window">{w.status !== "AVAILABLE" ? dash(w.reason, w.status) : <>
          {w.price_change_bps !== null ? <span className={"stress-sign-" + w.price_sign}>Prix {signLabel(w.price_sign)} {w.price_change_bps} bp</span> : <span className="stress-unavailable">Prix —</span>}
          <small>{w.oi_change_pct !== null ? <span className={"stress-sign-" + w.oi_sign}>OI {signLabel(w.oi_sign)} {w.oi_change_pct} %</span> : "OI —"} · écart à la cible {w.sample_gap_ms} ms</small></>}</td>)}
      </tr>)}</tbody></table></div></details>;
}

function Pairs({ u }: { u: Underlying }) {
  const label = (id: string) => legLabel(u.legs.find(l => l.instrument_id === id)!);
  return <details className="market-panel venue-panel"><summary>Écarts entre plateformes, même instrument ({u.pairs.length} paire(s) orientée(s))</summary>
    {u.pairs.length === 0 ? <p>Aucun instrument n’est suivi sur au moins deux plateformes pour ce sous-jacent.</p> :
      <div className="stress-table-wrap" role="region" aria-label="Paires · défilement horizontal" tabIndex={0}><table className="market-table">
        <thead><tr><th>Instrument</th><th>Référence → autre</th><th>Écart de prix (bp)</th><th>Écart de funding par 8 h</th><th>Décalage (ms)</th></tr></thead>
        <tbody>{u.pairs.map((p, i) => <tr key={i} data-testid="stress-pair"><th scope="row">{label(p.instrument_id)}</th><td>{venueName(p.reference_venue)} → {venueName(p.other_venue)}</td>
          {p.status === "AVAILABLE" ? <><td>{p.price_gap_bps}</td><td>{p.funding_8h_difference ?? "—"}</td><td>{p.event_skew_ms}</td></> : <td colSpan={3} className="stress-unavailable">— {reasonLabel(p.reason)} · <code>{p.reason}</code></td>}</tr>)}</tbody></table></div>}
  </details>;
}

export const DerivativesStressPanel: React.FC = () => {
  const state = useDerivativesStress();
  const [chosen, setChosen] = useState("");
  if (state.status === "loading") return <section className="market-panel venue-panel stress-panel" data-testid="stress-panel" role="status">Chargement du stress des dérivés…</section>;
  if (state.status === "unavailable") return <section className="market-panel venue-panel stress-panel" data-testid="stress-panel">
    <h2>Stress du levier et déséquilibre des dérivés</h2><p role="status">Aucune publication de dérivés disponible.</p>
    {marketSourceSetup(state.errorCode) && <MarketSourceNotice source="Stress des dérivés" setup={marketSourceSetup(state.errorCode)!} code={state.errorCode!} httpStatus={state.httpStatus}/>}
    <p>Les prix, le funding et l’open interest ne sont pas déclarés vides ni nuls. Leur disponibilité reste inconnue.</p>
    <details><summary>Source et diagnostic</summary><p>{state.diagnostic}</p></details></section>;
  const pub = state.publication;
  const u = pub.underlyings.find(x => x.underlying_id === chosen) ?? pub.underlyings[0];
  const total = u.open_interest_total;
  return <div className="stress-stack stress-panel" data-testid="stress-panel">
    <section className="market-panel venue-panel">
      <PublicationStamp source="Stress des dérivés · publication" generatedAt={pub.generated_at_utc} freshness={pub.freshness_classification} age={pub.publication_age_ms / 1000}/>
      <h2>Stress du levier et déséquilibre des dérivés</h2>
      {pub.evidence_kind === "SYNTHETIC" && <p className="venue-evidence" data-testid="stress-synthetic">Exemple synthétique · aucune connexion attestée</p>}
      <p className="venue-quality" role="status">{pub.freshness_classification === "STALE" ? "Publication périmée · valeurs actuelles INCONNUES." : pub.freshness_classification === "UNRESOLVED" ? "Qualité temporelle indisponible." : "Publication récente · aucune activité de collecteur attestée."}</p>
      <p>{pub.source_counts.supplied} marché(s) reçu(s) sur {pub.source_counts.expected} attendu(s) · {pub.source_counts.available} qualifié(s) à la publication.</p>
      <p className="venue-note">Association prix, prime des dérivés, funding et open interest. Observation seulement : aucun score, seuil ni signal. Frais, conversions et exécution ne sont pas inclus.</p>
      <div className="venue-controls"><label>Sous-jacent observé<select aria-label="Sous-jacent observé" value={u.underlying_id} onChange={e => setChosen(e.target.value)}>
        {pub.underlyings.map(x => <option key={x.underlying_id} value={x.underlying_id}>{x.base_asset_id}/{x.quote_asset_id}</option>)}</select></label></div>
      <p data-testid="stress-oi-total">{total.status === "AVAILABLE" ? <>Open interest total des dérivés suivis : {total.notional_quote} {u.quote_asset_id} (notionnel) · {total.coverage.available}/{total.coverage.expected} marché(s).</> :
        <>Open interest total : non publié · {reasonLabel(total.reason)} · {total.coverage.available}/{total.coverage.expected} marché(s){total.coverage.missing.length > 0 && <> · manquant(s) : {total.coverage.missing.join(", ")}</>}.</>}</p>
      <Legs u={u}/>
    </section>
    <Windows legs={u.legs}/>
    <Pairs u={u}/>
    <details className="market-panel venue-panel"><summary>Comprendre les mesures et leurs limites</summary>
      <p>La prime compare le prix du dérivé à l’indice de sa plateforme. La base compare ce prix à un spot du même actif et de la même devise de cotation, de préférence sur la même plateforme ; USD, USDT et USDC restent séparés. Elle n’est publiée que si les deux observations partagent horloge, sémantique de date et tolérance de synchronisation.</p>
      <p>Le funding est publié tel que reçu, avec son intervalle ; l’équivalent 8 h et l’annualisation sont des conversions linéaires simples d’affichage, pas des taux garantis. Un open interest en contrats n’est converti en notionnel que si la taille de contrat est connue ; un total n’est publié que si tous les dérivés attendus sont couverts.</p>
      <p>Les sens des variations ne désignent ni acheteurs ni vendeurs. Cette vue ne donne aucune autorité de trading.</p>
    </details>
  </div>;
};
