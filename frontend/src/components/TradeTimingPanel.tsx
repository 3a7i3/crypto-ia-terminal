import React, { useState } from "react";
import { useDerivativesStress } from "../lib/derivativesStressClient";
import type { ScanRow, StressLeg } from "../lib/derivativesStress";
import { PublicationStamp } from "./PublicationStamp";
import { MarketSourceNotice } from "./MarketSourceNotice";
import { marketSourceSetup } from "../lib/marketSourceSetup";
import { legLabel, periodLabel, reasonLabel } from "../lib/stressLabels";
import "../market-stress.css";

const HALF = 30; // seconds shown on each side of the boundary; a view choice, not a statistic

// Fold the 900 published one-second phase bins into [-30 s, +30 s) around the boundary.
const fold = (counts: number[]) => [...counts.slice(counts.length - HALF), ...counts.slice(0, HALF)];

function Histogram({ counts, events }: { counts: number[]; events: number }) {
  const bars = fold(counts), max = Math.max(1, ...bars);
  return <>
    <svg className="stress-hist" viewBox={`0 0 ${HALF * 2 * 10} 110`} role="img" aria-label={`Transactions par seconde autour de la frontière, ${events} transactions au total ; valeurs exactes dans le détail`}>
      <line className="stress-hist-axis" x1="0" x2={HALF * 2 * 10} y1="100" y2="100"/>
      <line className="stress-hist-mark" x1={HALF * 10} x2={HALF * 10} y1="0" y2="100"/>
      {bars.map((c, i) => <rect key={i} x={i * 10 + 1} width="8" y={100 - (c * 98) / max} height={(c * 98) / max} fill="currentColor"><title>{i < HALF ? "−" + (HALF - i) : "+" + (i - HALF)} s : {c}</title></rect>)}
    </svg>
    <details><summary>Valeurs exactes par seconde (±{HALF} s)</summary>
      <ul>{bars.map((c, i) => <li key={i}>{i < HALF ? "−" + (HALF - i) : "+" + (i - HALF)} s : {c}</li>)}</ul></details>
  </>;
}

function ScanTable({ scan }: { scan: ScanRow[] }) {
  return <><p>Part des transactions à moins de ± rayon d’une frontière, face à sa part attendue si le temps était réparti uniformément.</p>
  <div className="flux-scroll" role="region" aria-label="Concentration aux frontières · défilement horizontal" tabIndex={0}>
    <table className="stress-scan"><caption>Concentration aux frontières</caption>
      <thead><tr><th>Période</th><th>Rayon</th><th>Attendue (uniforme)</th><th>Frontières · transactions</th><th>Facteur</th><th>Placebo · facteur</th><th>Frontières · volume</th><th>Facteur volume</th></tr></thead>
      <tbody>{scan.map(r => <tr key={r.period_s + "-" + r.radius_ms} data-testid="timing-scan-row">
        <th scope="row">{periodLabel(r.period_s)}</th><td>± {r.radius_ms} ms</td><td>{r.expected_share}</td>
        <td>{r.boundary_count_share} ({r.boundary_events})</td><td>× {r.boundary_count_lift}</td><td>{r.placebo_count_share} · × {r.placebo_count_lift}</td>
        <td>{r.boundary_volume_share}</td><td>× {r.boundary_volume_lift}</td></tr>)}</tbody></table></div></>;
}

export const TradeTimingPanel: React.FC = () => {
  const state = useDerivativesStress();
  const [chosen, setChosen] = useState("");
  const title = <h3>Périodicité temporelle des transactions</h3>;
  if (state.status === "loading") return <section className="stress-panel" data-testid="timing-panel" role="status">Chargement de la périodicité…</section>;
  if (state.status === "unavailable") return <section className="stress-panel" data-testid="timing-panel">{title}
    <p role="status">Aucune publication de périodicité disponible.</p>
    {marketSourceSetup(state.errorCode) && <MarketSourceNotice source="Périodicité des transactions" setup={marketSourceSetup(state.errorCode)!} code={state.errorCode!} httpStatus={state.httpStatus}/>}
    <p>Aucune concentration n’est déclarée absente : la mesure est INCONNUE.</p>
    <details><summary>Source et diagnostic</summary><p>{state.diagnostic}</p></details></section>;
  const pub = state.publication;
  const legs: StressLeg[] = pub.underlyings.flatMap(u => u.legs);
  const leg = legs.find(l => l.instrument_id + "|" + l.venue === chosen) ?? legs.find(l => l.timing.status === "AVAILABLE") ?? legs[0];
  const t = leg.timing;
  return <section className="stress-panel" data-testid="timing-panel" aria-label="Périodicité temporelle">
    {title}
    <PublicationStamp source="Périodicité · publication" generatedAt={pub.generated_at_utc} freshness={pub.freshness_classification} age={pub.publication_age_ms / 1000}/>
    {pub.evidence_kind === "SYNTHETIC" && <p data-testid="timing-synthetic">Exemple synthétique · aucune connexion attestée</p>}
    <p>Des concentrations d’activité aux frontières temporelles (quarts d’heure) ont été observées dans la littérature sur des perpétuels crypto. Piste expérimentale : ce signal ne doit pas être négocié sans validation et n’est ici qu’une mesure descriptive.</p>
    <label>Marché observé <select aria-label="Marché observé" value={leg.instrument_id + "|" + leg.venue} onChange={e => setChosen(e.target.value)}>
      {legs.map(l => <option key={l.instrument_id + "|" + l.venue} value={l.instrument_id + "|" + l.venue}>{legLabel(l)}</option>)}</select></label>
    {t.status !== "AVAILABLE" ? <p role="status" data-testid="timing-unavailable">Mesure indisponible · {reasonLabel(t.reason)} · <code>{t.reason}</code>. Aucune concentration n’est déclarée absente.</p> : <>
      <p>{t.events} transactions · volume {t.volume_base} {leg.instrument.base_asset_id} · heure moteur d’appariement uniquement · seuil de {pub.parameters.timing_min_events} transactions.</p>
      <Histogram counts={t.histogram!.counts} events={t.events!}/>
      <ScanTable scan={t.scan!}/>
    </>}
    <details><summary>Lire la mesure et ses limites</summary>
      <p>Les frontières sont les multiples de la période depuis l’époque UTC (:00, :15, :30, :45 pour 15 min). La part attendue est celle qu’obtiendrait une répartition uniforme sur la grille d’horodatage déclarée ; le placebo utilise des frontières décalées d’une demi-période. Un facteur proche de × 1 pour la frontière comme pour le placebo ne montre aucune concentration ; un facteur élevé aux frontières seulement est une piste à valider.</p>
      <p>Les rafales d’exécution rompent l’indépendance des transactions : aucune p-valeur n’est publiée. Les périodes de 1 min et 5 min contiennent les frontières du quart d’heure ; leur facteur est donc lié. Une validation sur plusieurs jours séparés, plateformes et fenêtres reste nécessaire avant toute hypothèse.</p>
      <p>Source de la série : {leg.source.tape_sha256 ?? "empreinte non disponible"}</p>
    </details>
  </section>;
};
