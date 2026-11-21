import React, { useState } from "react";
import { useDerivativesPositioning } from "../lib/derivativesPositioningClient";
import type { Leg, Positioning, Series } from "../lib/derivativesPositioning";
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

const compact = (value: string | number, digits = 4) =>
  Number(value).toLocaleString("fr-FR", { maximumFractionDigits: digits });

function Cards({ leg, period }: { leg: Leg; period: number }) {
  if (leg.latest.status !== "AVAILABLE") return <Missing reason={leg.latest.reason}/>;
  const o = leg.latest.observation;
  const d = o.derived, oi = o.measures.open_interest, f = d.funding;
  const w = leg.oi_change.find(row => row.window_s === period);
  const basis = d.basis_vs_spot.status === "AVAILABLE";
  const premium = basis ? d.basis_vs_spot : d.premium_to_index;
  const cards = [
    { id: "oi", title: "Open interest", value: oi.status === "AVAILABLE" ? compact(oi.value, 6) : null,
      detail: oi.status === "AVAILABLE" ? OI_UNIT[oi.unit!] ?? oi.unit : positioningReason(oi.reason) },
    { id: "oi-change", title: "Variation OI", value: w?.status === "AVAILABLE" && w.change_pct !== null ? compact(w.change_pct) + " %" : null,
      detail: w?.status === "AVAILABLE" ? windowLabel(period) : positioningReason(w?.reason ?? null) },
    { id: "funding", title: "Funding", value: f.status === "AVAILABLE" && f.rate !== null ? compact(Number(f.rate) * 100, 8) + " %" : null,
      detail: f.status === "AVAILABLE" ? "Par " + f.interval_s! / 3600 + " h" : positioningReason(f.reason) },
    { id: "premium-basis", title: basis ? "Basis" : "Prime futures", value: premium.bps === null ? null : compact(premium.bps) + " pb",
      detail: premium.status === "AVAILABLE" ? (basis ? "Référence spot" : "Référence indice") : positioningReason(premium.reason) },
  ];
  return <div className="pos-cards">
    {cards.map(c => <article key={c.id} className="pos-card" data-testid={"pos-card-" + c.id}>
      <h4>{c.title}</h4><p className="pos-value">{c.value ?? "—"}</p><p className="pos-sub">{c.detail}</p>
    </article>)}
  </div>;
}

function Chart({ s, window_s }: { s: Series; window_s: number }) {
  const [active, setActive] = useState<number | null>(null);
  const points = s.points;
  const times = points.map(p => Date.parse(p.t));
  const price = points.map(p => Number(p.price)), oi = points.map(p => Number(p.oi));
  const width = 360, height = 190, left = 54, right = 306, top = 15, bottom = 157;
  const begin = times[0], end = times[times.length - 1];
  const x = (t: number) => left + (t - begin) / Math.max(1, end - begin) * (right - left);
  const scale = (v: number[]) => {
    const min = Math.min(...v), max = Math.max(...v);
    const pad = (max - min || Math.abs(max) || 1) * .08;
    return { low: min - pad, high: max + pad };
  };
  const a = scale(price), b = scale(oi);
  const y = (v: number, axis: typeof a) => bottom - (v - axis.low) / (axis.high - axis.low) * (bottom - top);
  const line = (vals: number[], axis: typeof a) => vals.map((v, i) => {
    const gap = i > 0 && s.cadence_s !== null && times[i] - times[i - 1] > s.cadence_s * 1000;
    return `${i === 0 || gap ? "M" : "L"}${x(times[i])} ${y(v, axis)}`;
  }).join(" ");
  const selected = active === null ? null : points[active];
  const stamp = (t: number) => new Date(t).toISOString().slice(11, 16);
  const axisLabel = (v: number) => v.toLocaleString("fr-FR", { notation: "compact", maximumFractionDigits: 2 });
  const oiUnit = OI_UNIT[s.oi_unit!] ?? s.oi_unit;
  return <figure className="pos-chart" data-testid="pos-chart">
    <figcaption><span className="pos-key-price">Prix ({s.price_unit})</span><span className="pos-key-oi">OI ({oiUnit})</span></figcaption>
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Prix et open interest sur ${windowLabel(window_s)}, axes séparés`}
      onPointerDown={e => {
        const box = e.currentTarget.getBoundingClientRect();
        const cursor = (e.clientX - box.left) / box.width * width;
        setActive(times.reduce((best, t, i) => Math.abs(x(t) - cursor) < Math.abs(x(times[best]) - cursor) ? i : best, 0));
      }}>
      {[0, .25, .5, .75, 1].map(f => {
        const row = top + f * (bottom - top);
        return <g key={f}><line x1={left} x2={right} y1={row} y2={row} className="pos-axis"/>
          <text x={left - 5} y={row + 4} textAnchor="end" className="pos-band-price">{axisLabel(a.high - f * (a.high - a.low))}</text>
          <text x={right + 5} y={row + 4} className="pos-band-oi">{axisLabel(b.high - f * (b.high - b.low))}</text></g>;
      })}
      {[0, .25, .5, .75, 1].map(f => <text key={f} x={left + f * (right - left)} y={179} textAnchor="middle">{stamp(begin + f * (end - begin))}</text>)}
      <path d={line(price, a)} className="pos-line-price" data-testid="pos-line-price"/>
      <path d={line(oi, b)} className="pos-line-oi" data-testid="pos-line-oi"/>
      {active !== null && <line x1={x(times[active])} x2={x(times[active])} y1={top} y2={bottom} className="pos-cursor"/>}
    </svg>
    {selected && <output className="pos-readout">{stamp(times[active!])} UTC · Prix {selected.price} {s.price_unit} · OI {selected.oi} {oiUnit}</output>}
    <input className="pos-chart-slider" type="range" min={0} max={points.length - 1} value={active ?? points.length - 1}
      aria-label="Parcourir les observations du graphique" onChange={e => setActive(Number(e.target.value))}/>
  </figure>;
}

function ChartBlock({ doc, legId, period }: { doc: Positioning; legId: string; period: number }) {
  const source = doc.chart.series.find(x => x.leg_id === legId)!;
  const cutoff = Date.parse(doc.chart.end_utc) - period * 1000;
  const s = { ...source, points: source.points.filter(p => Date.parse(p.t) >= cutoff) };
  return <section className="pos-chart-block" aria-label="Graphique prix et open interest">
    <h4>Prix + OI · {windowLabel(period)}</h4>
    {s.status === "AVAILABLE" && s.points.length > 1 ? <Chart key={legId + period} s={s} window_s={period}/> :
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
  const [period, setPeriod] = useState(86400);
  const [instrument, setInstrument] = useState("");
  if (state.status === "loading") return <section className="market-panel venue-panel pos-panel" data-testid="positioning-panel" role="status">Chargement du positionnement des dérivés…</section>;
  if (state.status === "unavailable") return <section className="market-panel venue-panel pos-panel" data-testid="positioning-panel">
    <h1>Plateformes & levier</h1><p role="status">Aucune lecture de positionnement disponible.</p>
    {marketSourceSetup(state.errorCode) && <MarketSourceNotice source="Positionnement des dérivés" setup={marketSourceSetup(state.errorCode)!} code={state.errorCode!} httpStatus={state.httpStatus}/>}
    <details><summary>Source et diagnostic</summary><p>{state.diagnostic}</p></details>
  </section>;
  const doc = state.doc;
  const instrumentOf = (l: Leg) => l.latest.observation?.base_currency ?? l.native_symbol;
  const instruments = [...new Set(doc.legs.map(instrumentOf))];
  const chosen = instruments.includes(instrument) ? instrument : instruments[0];
  const eligible = doc.legs.filter(l => instrumentOf(l) === chosen);
  const leg = eligible.find(l => l.leg_id === legId) ?? eligible[0];
  const observation = leg.latest.observation;
  const window = leg.oi_change.find(w => w.window_s === period);
  return <section className="market-panel venue-panel pos-panel" data-testid="positioning-panel">
    <header className="pos-heading"><h1>Plateformes & levier</h1><p>Positionnement des dérivés</p></header>
    <div className="pos-filters">
      <label className="pos-select">Instrument<select value={chosen} onChange={e => { setInstrument(e.target.value); setLegId(""); }}>
        {instruments.map(name => <option key={name}>{name}</option>)}</select></label>
      <label className="pos-select">Plateforme<select aria-label="Plateforme et contrat" value={leg.leg_id} onChange={e => setLegId(e.target.value)}>
        {eligible.map(l => <option key={l.leg_id} value={l.leg_id}>{legName(l)}</option>)}</select></label>
      <label className="pos-select">Période<select value={period} onChange={e => setPeriod(Number(e.target.value))}>
        {[3600,14400,86400].map(seconds => <option key={seconds} value={seconds}>{windowLabel(seconds)}</option>)}</select></label>
    </div>
    <p className="pos-quality" data-testid={doc.evidence_kind === "SYNTHETIC" ? "pos-synthetic" : undefined}>
      {doc.evidence_kind === "SYNTHETIC" && "Exemple synthétique · "}
      {observation ? (observation.freshness.status === "FRESH" ? "Récente" : observation.freshness.status === "STALE" ? "Périmée" : "Horloge incohérente") : "Aucune observation"}
      {window?.coverage && ` · couverture ${window.coverage.points}/${window.coverage.expected}`}
    </p>
    <p className="pos-sub" data-testid="pos-leg-kind">{legName(leg)} · {marketKindLabel[leg.contract_type] ?? leg.contract_type}</p>
    <Cards leg={leg} period={period}/>
    <ChartBlock doc={doc} legId={leg.leg_id} period={period}/>
    <details className="pos-details"><summary>Qualité et provenance</summary>
      <p>Lecture de l’historique local au {time(doc.generated_at_utc)}</p>
      {observation && <><p>Source <code>{observation.provenance.source}</code> · {observation.provenance.mapping_id}</p>
      <p>Horodatage {time(observation.effective_time_utc)} · cotation {observation.quote_currency}</p>
      {observation.units.contract_size_base && <p>Taille du contrat · {observation.units.contract_size_base} {observation.base_currency}</p>}
      {observation.derived.open_interest_notional.notional_quote !== null && <p>OI notionnel · {observation.derived.open_interest_notional.notional_quote} {observation.quote_currency}</p>}
      <ul className="pos-windows">{leg.oi_change.map(w => <li key={w.window_s} data-testid="pos-oi-window">
        {windowLabel(w.window_s)} · {w.change_pct === null ? positioningReason(w.reason) : w.change_pct + " %"}
        {w.coverage && ` · couverture ${w.coverage.points}/${w.coverage.expected}`}
      </li>)}</ul>
      {observation.unavailable_fields.length > 0 && <div data-testid="pos-unavailable">{observation.unavailable_fields.map(u => <p key={u.field}>{FIELD[u.field] ?? u.field} · {positioningReason(u.reason)}</p>)}</div>}</>}
      <Pairs doc={doc}/>
    </details>
  </section>;
};
