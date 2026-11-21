import React, { useState } from "react";
import { useDerivativesPositioning } from "../lib/derivativesPositioningClient";
import type { Leg, OiWindow, Positioning, Series } from "../lib/derivativesPositioning";
import { MarketSourceNotice } from "./MarketSourceNotice";
import { marketSourceSetup } from "../lib/marketSourceSetup";
import { venueName, marketKindLabel } from "../lib/venueNames";
import { windowLabel } from "../lib/stressLabels";
import { FIELD, OI_UNIT, positioningReason } from "../lib/positioningLabels";
import "../market-positioning.css";

const Missing: React.FC<{ reason: string | null }> = ({ reason }) =>
  <p className="pos-missing">— <span>{positioningReason(reason)}</span> <code>{reason}</code></p>;
const time = (v: string | null) => v ? v.replace("T", " ").replace(/\.\d+Z$/, " UTC") : "non disponible";
const legName = (l: Leg) => `${venueName(l.venue)} · ${l.native_symbol}`;

function Card({ title, testId, children, foot }: { title: string; testId: string; children: React.ReactNode; foot: React.ReactNode }) {
  return <article className="pos-card" data-testid={testId}><h4>{title}</h4><div className="pos-card-body">{children}</div><footer>{foot}</footer></article>;
}

function Cards({ leg }: { leg: Leg }) {
  if (leg.latest.status !== "AVAILABLE") return <div className="pos-cards"><Missing reason={leg.latest.reason}/></div>;
  const o = leg.latest.observation, d = o.derived, oi = o.measures.open_interest, f = d.funding;
  const prov = <>Source <code>{o.provenance.source}</code>{o.provenance.mapping_id && <> · mapping <code>{o.provenance.mapping_id}</code></>}</>;
  const fresh = <span className={"pos-fresh pos-fresh-" + o.freshness.status}>{o.freshness.status === "FRESH" ? "Récente" : o.freshness.status === "STALE" ? "Périmée" : "Horloge incohérente"} · âge {Math.round(o.freshness.age_ms / 1000)} s</span>;
  const foot = <>{fresh}<br/>{o.time_basis === "SOURCE" ? "Heure source " + time(o.source_time_utc) : "Heure de réception (source absente)"}<br/>{prov}</>;
  return <div className="pos-cards">
    <Card title="Open interest" testId="pos-card-oi" foot={foot}>
      {oi.status === "AVAILABLE" ? <><p className="pos-value">{oi.value} <span>{OI_UNIT[oi.unit!] ?? oi.unit}</span></p>
        {oi.contract_size_base && <p className="pos-sub">Taille de contrat {oi.contract_size_base} {o.base_currency ?? "base"}</p>}
        <p className="pos-sub">{d.open_interest_notional.notional_quote !== null ? <>Notionnel {d.open_interest_notional.notional_quote} {o.quote_currency} (prix de marque)</> : <>Notionnel indisponible · {positioningReason(d.open_interest_notional.reason)}</>}</p></>
        : <Missing reason={oi.reason}/>}
    </Card>
    <Card title="Variation de l’OI" testId="pos-card-oi-change" foot={<>Cadence déclarée {leg.cadence_s ?? "inconnue"} s · tolérance {leg.tolerance_ms ?? "—"} ms<br/>Seuls des points de même unité, taille et base temporelle sont comparés.</>}>
      <ul className="pos-windows">{leg.oi_change.map((w: OiWindow) => <li key={w.window_s} data-testid="pos-oi-window"><strong>{windowLabel(w.window_s)}</strong>{" "}
        {w.status === "AVAILABLE" ? <>{w.change_pct} %<small>{w.start!.value} → {w.end!.value} {OI_UNIT[w.unit!] ?? w.unit} · couverture {w.coverage!.points}/{w.coverage!.expected}</small></>
          : <span className="pos-missing">— {positioningReason(w.reason)} <code>{w.reason}</code>{w.coverage && <small>couverture {w.coverage.points}/{w.coverage.expected}</small>}</span>}</li>)}</ul>
    </Card>
    <Card title="Funding" testId="pos-card-funding" foot={foot}>
      {f.status === "AVAILABLE" ? <><p className="pos-value">{f.rate} <span>par {f.interval_s! / 3600} h</span></p>
        <p className="pos-sub">Équivalent 8 h {f.rate_8h_equivalent} · annualisé simple {f.annualized_simple_pct} % (conversion linéaire, affichage seulement)</p>
        <p className="pos-sub">Prochain funding {time(f.next_funding_utc)}</p></> : <Missing reason={f.reason}/>}
    </Card>
    <Card title="Prime et basis" testId="pos-card-premium-basis" foot={foot}>
      <p className="pos-sub"><strong>Prime vs indice</strong> (marque − indice) / indice</p>
      {d.premium_to_index.status === "AVAILABLE" ? <p className="pos-value">{d.premium_to_index.bps} <span>bp</span></p> : <Missing reason={d.premium_to_index.reason}/>}
      <p className="pos-sub"><strong>Basis dérivé / spot</strong> (marque − spot qualifié) / spot</p>
      {d.basis_vs_spot.status === "AVAILABLE" ? <p className="pos-value">{d.basis_vs_spot.bps} <span>bp · contre {venueName(d.basis_vs_spot.against!.venue)} {d.basis_vs_spot.against!.native_symbol}</span></p> : <Missing reason={d.basis_vs_spot.reason}/>}
    </Card>
    {o.unavailable_fields.length > 0 && <p className="pos-sub pos-unavailable-list" data-testid="pos-unavailable">Champs indisponibles : {o.unavailable_fields.map(u => `${FIELD[u.field] ?? u.field} (${positioningReason(u.reason)})`).join(" · ")}</p>}
  </div>;
}

function Chart({ s, window_s }: { s: Series; window_s: number }) {
  // Two stacked bands, one per measure: price and OI never share a vertical scale.
  const W = 360, BAND = 96, GAP = 18, P = 28, H = 2 * BAND + GAP + 8;
  const ts = s.points.map(p => Date.parse(p.t)), price = s.points.map(p => Number(p.price)), oi = s.points.map(p => Number(p.oi));
  const t0 = Math.min(...ts), t1 = Math.max(...ts);
  const x = (t: number) => P + (t1 === t0 ? 0.5 : (t - t0) / (t1 - t0)) * (W - 2 * P);
  const band = (vals: number[], top: number) => { const lo = Math.min(...vals), hi = Math.max(...vals); return (v: number) => top + BAND - 6 - (hi === lo ? 0.5 : (v - lo) / (hi - lo)) * (BAND - 12); };
  const line = (vals: number[], top: number) => { const y = band(vals, top); return vals.map((v, i) => (i ? "L" : "M") + x(ts[i]).toFixed(1) + " " + y(v).toFixed(1)).join(" "); };
  const first = s.points[0], last = s.points[s.points.length - 1];
  const oiUnit = `${OI_UNIT[s.oi_unit!] ?? s.oi_unit}${s.contract_size_base ? ` × ${s.contract_size_base}` : ""}`;
  return <figure className="pos-chart" data-testid="pos-chart">
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Prix de marque et open interest sur ${windowLabel(window_s)}, deux bandes et deux échelles séparées`}>
      <text x={P} y={11} className="pos-band-label pos-band-price">Prix</text>
      <line x1={P} x2={W - P} y1={BAND} y2={BAND} className="pos-axis"/>
      <path d={line(price, 0)} className="pos-line-price" data-testid="pos-line-price"/>
      <text x={P} y={BAND + GAP + 11} className="pos-band-label pos-band-oi">OI</text>
      <line x1={P} x2={W - P} y1={2 * BAND + GAP} y2={2 * BAND + GAP} className="pos-axis"/>
      <path d={line(oi, BAND + GAP)} className="pos-line-oi" data-testid="pos-line-oi"/>
    </svg>
    <figcaption><span className="pos-key-price">Prix de marque ({s.price_unit}) : {first.price} → {last.price}</span>
      <span className="pos-key-oi">OI ({oiUnit}) : {first.oi} → {last.oi}</span>
      <span>Valeurs exactes du premier et du dernier point · {s.points.length} points · cadence {s.cadence_s} s · couverture {s.coverage} · échelles min–max par bande</span></figcaption>
  </figure>;
}

function ChartBlock({ doc, legId }: { doc: Positioning; legId: string }) {
  const s = doc.chart.series.find(x => x.leg_id === legId)!;
  return <section className="pos-chart-block" aria-label="Graphique prix et open interest">
    <h4>Prix + OI · {windowLabel(doc.chart.window_s)}</h4>
    {s.status === "AVAILABLE" && s.points.length > 1 ? <Chart s={s} window_s={doc.chart.window_s}/> :
      <div data-testid="pos-chart-unavailable"><p>Aucune série affichée : l’historique n’est pas comparable ou pas aligné dans le temps.</p><Missing reason={s.reason ?? "NO_OBSERVATION"}/></div>}
    <p className="pos-sub">Séries exclues : {doc.chart.series.filter(x => x.status !== "AVAILABLE").map(x => `${x.leg_id.split(":")[0]} (${positioningReason(x.reason)})`).join(" · ") || "aucune"}.</p>
  </section>;
}

function Pairs({ doc }: { doc: Positioning }) {
  const name = (id: string) => { const [v, s] = id.split(":"); return `${venueName(v)} ${s}`; };
  return <details className="pos-pairs"><summary>Comparaisons entre plateformes ({doc.pairs.length})</summary>
    <ul>{doc.pairs.map((p, i) => <li key={i} data-testid="pos-pair">{name(p.a)} ↔ {name(p.b)} · OI : {p.open_interest.status === "AVAILABLE" ? "comparable (même unité)" : <>indisponible, {positioningReason(p.open_interest.reason)} <code>{p.open_interest.reason}</code></>}
      {" "}· funding : {p.funding.status === "AVAILABLE" ? "même intervalle" : <>indisponible, {positioningReason(p.funding.reason)} <code>{p.funding.reason}</code></>}</li>)}</ul>
    <p className="pos-sub">Les valeurs restent natives. Aucune conversion entre unités, tailles de contrat ou intervalles n’est faite pour comparer.</p>
  </details>;
}

export const DerivativesPositioningPanel: React.FC = () => {
  const state = useDerivativesPositioning();
  const [legId, setLegId] = useState("");
  if (state.status === "loading") return <section className="market-panel venue-panel pos-panel" data-testid="positioning-panel" role="status">Chargement du positionnement des dérivés…</section>;
  if (state.status === "unavailable") return <section className="market-panel venue-panel pos-panel" data-testid="positioning-panel">
    <h3>Positionnement des dérivés</h3><p role="status">Aucune lecture de positionnement disponible.</p>
    {marketSourceSetup(state.errorCode) && <MarketSourceNotice source="Positionnement des dérivés" setup={marketSourceSetup(state.errorCode)!} code={state.errorCode!} httpStatus={state.httpStatus}/>}
    <details><summary>Source et diagnostic</summary><p>{state.diagnostic}</p></details>
  </section>;
  const doc = state.doc;
  const leg = doc.legs.find(l => l.leg_id === legId) ?? doc.legs[0];
  return <section className="market-panel venue-panel pos-panel" data-testid="positioning-panel">
    <h3>Positionnement des dérivés</h3>
    {doc.evidence_kind === "SYNTHETIC" && <p className="venue-evidence" data-testid="pos-synthetic">Exemple synthétique · aucune connexion attestée</p>}
    <p className="pos-sub">Lecture de l’historique local au {time(doc.generated_at_utc)}. Aucun score ni signal ; aucune autorité de trading.</p>
    <label className="pos-select">Plateforme et contrat<select aria-label="Plateforme et contrat" value={leg.leg_id} onChange={e => setLegId(e.target.value)}>
      {doc.legs.map(l => <option key={l.leg_id} value={l.leg_id}>{legName(l)}{l.latest.status !== "AVAILABLE" ? " · sans observation" : ""}</option>)}
    </select><span className="pos-sub" data-testid="pos-leg-kind">{legName(leg)} · {marketKindLabel[leg.contract_type] ?? leg.contract_type}</span></label>
    <Cards leg={leg}/>
    <ChartBlock doc={doc} legId={leg.leg_id}/>
    <Pairs doc={doc}/>
  </section>;
};
