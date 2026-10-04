import React, { useState } from "react";
import { useMarketMicrostructure } from "../lib/marketMicrostructureClient";
import type { MicrostructureRow } from "../lib/marketMicrostructureTypes";

import { detailLabels, type DetailName } from "../lib/marketMicrostructureDetail";

const value = (v: number | null, suffix = "") => v === null ? "NOT_AVAILABLE" : `${v.toLocaleString("fr-FR", { maximumSignificantDigits: 10 })}${suffix}`;
const Metrics: React.FC<{ row: MicrostructureRow }> = ({ row }) => <dl className="microstructure-metrics">
  <div><dt>Confiance état · 0–1</dt><dd>{value(row.state_confidence)}</dd></div>
  <div><dt>Prix observé</dt><dd>{value(row.price)}</dd></div>
  <div><dt>Variation prix · bps</dt><dd>{value(row.price_change_bps)}</dd></div>
  <div><dt>Pression achat / vente</dt><dd>{value(row.buy_pressure_pct, "%")} / {value(row.sell_pressure_pct, "%")}</dd></div>
  <div><dt>Fenêtre flux · ms</dt><dd>{value(row.flow_window_ms)}</dd></div>
  <div><dt>Flux achat · USD</dt><dd>{value(row.buy_flow_usd)}</dd></div>
  <div><dt>Flux vente · USD</dt><dd>{value(row.sell_flow_usd)}</dd></div>
  <div><dt>Flux total · USD</dt><dd>{value(row.total_flow_usd)}</dd></div>
  <div><dt>Résistance · USD/bps</dt><dd>{value(row.resistance)}</dd></div>
  <div><dt>Fragilité · 0–1</dt><dd>{value(row.fragility)}</dd></div>
</dl>;

const LmiDetail: React.FC<{ row: MicrostructureRow }> = ({ row }) => {
  if (row.detail === undefined) return <p>Détail non publié · schéma 1.0</p>;
  if (row.detail === null) return <p>Détail NOT_AVAILABLE</p>;
  const titles = { flow: "Flux agressif", liquidity: "Liquidité CryptoRadar", resistance: "Résistance du marché", state_components: "Composantes de l’état publié" };
  return <details className="market-provenance-details" data-testid="lmi-detail">
    <summary>Détail LMI · {row.symbol}</summary>
    <p>Valeurs exactes publiées par la source ; aucun recalcul d’état. Unités USD soumises à la provenance contractSize ci-dessus.</p>
    {(Object.keys(detailLabels) as DetailName[]).map((name) => {
      const group = row.detail![name];
      const time = group && "observed_at_utc" in group ? group : null;
      return <section key={name} data-testid={`lmi-detail-${name}`}>
        <h3>{titles[name]}</h3>
        {name === "liquidity" && <p>Valeurs source uniquement : le producteur peut publier des zéros avant la première observation du carnet. L’observation effective du carnet n’est pas attestée. Profondeur et intervalle de comparaison non publiés.</p>}
        {name === "state_components" && <p>Composantes rattachées à l’état du symbole ; aucune date indépendante publiée.</p>}
        {time && <p>{time.freshness_classification} · observation {time.observed_at_utc ?? "NOT_AVAILABLE"} · âge {time.observation_age_s === null ? "UNKNOWN" : `${String(time.observation_age_s)}s`}</p>}
        {group === null ? <p>NOT_AVAILABLE · groupe non publié</p> : <dl className="microstructure-metrics">{Object.entries(detailLabels[name]).map(([key, label]) => {
          const v = (group as unknown as Record<string, unknown>)[key];
          return <div key={key}><dt>{label}</dt><dd>{v === null ? "NOT_AVAILABLE" : String(v)}</dd></div>;
        })}</dl>}
      </section>;
    })}
  </details>;
};

export const MarketMicrostructureView: React.FC = () => {
  const state = useMarketMicrostructure();
  const [query, setQuery] = useState("");
  const [notableOnly, setNotableOnly] = useState(false);
  if (state.status !== "success") return <section className="market-panel microstructure-panel" data-testid="microstructure-view">
    <h2>Microstructure · LMI</h2>
    <p data-testid="microstructure-status">ÉTAT ACTUEL · INCONNU</p>
    <p>{state.status === "loading" ? "Chargement de la source indépendante…" : state.status === "api_error" ? `SOURCE INDISPONIBLE · HTTP ${state.httpStatus} · ${state.errorCode}` : `ERREUR TRANSPORT / CONTRAT · ${state.message}`}</p>
    <p>Observation passive · aucune autorité d’exécution.</p>
  </section>;
  const m = state.snapshot;
  const stale = m.freshness_classification === "STALE";
  const rows = m.rows.filter((r) => r.symbol.toUpperCase().includes(query.trim().toUpperCase()) && (!notableOnly || r.notable === true));
  return <section className="market-panel microstructure-panel" data-testid="microstructure-view">
    <div className="market-summary-row"><div><div className="market-eyebrow">SOURCE INDÉPENDANTE · OBSERVATION PASSIVE</div><h2>Microstructure · LMI</h2></div>
      <span className={`market-freshness ${stale ? "market-freshness-stale" : "market-freshness-fresh"}`} data-testid="microstructure-status">{m.freshness_classification} · source {value(m.source_age_s, "s")}</span></div>
    <p>{stale ? "ÉTAT ACTUEL · INCONNU · source périmée, mesures historiques." : "Capture source récente ; chaque symbole conserve sa propre fraîcheur. Aucune preuve de santé du service."}</p>
    <div className="microstructure-coverage" data-testid="microstructure-coverage">
      Demandés {m.coverage.requested} · Streamables {m.coverage.streamable} · Observés {m.coverage.observed} · Indisponibles {m.coverage.unavailable}
    </div>
    <p data-testid="microstructure-units">Unités contractSize : {m.unit_contract_source} · {m.unit_contract_degraded === null ? "qualité INCONNUE" : m.unit_contract_degraded ? "DÉGRADÉES" : "aucune dégradation déclarée"}. Flux et liquidité USD à lire avec cette provenance.</p>
    <details className="market-provenance-details"><summary>Provenance LMI et fenêtre des mesures</summary>
      <p>{m.authority} · {m.exchange} · source {m.source_updated_at_utc} · publication {m.generated_at_utc} · lecture {m.read_at_utc}</p>
      <p className="microstructure-hash">Artifact source SHA256 : {m.source_artifact_sha256}</p>
      <p>PressureFields cumulés à la capture : {m.pressure_field_count === null ? "NOT_AVAILABLE" : m.pressure_field_count}. Aucun historique d’événements WS. Fenêtres définies par le producteur LMI ; aucun recalcul dans l’app.</p>
    </details>
    <div className="market-scanner-controls">
      <label>Recherche LMI<input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="BTCUSDT…" /></label>
      <label className="microstructure-toggle"><input type="checkbox" checked={notableOnly} onChange={(e) => setNotableOnly(e.target.checked)} />Observations notables à la capture</label>
      <button type="button" onClick={() => { setQuery(""); setNotableOnly(false); }}>Réinitialiser LMI</button>
    </div>
    <p role="status">{rows.length} résultat(s) sur {m.coverage.requested} demandé(s). Notable : état non quiet et confiance ≥ 0,6, selon la projection. Ce filtre inclut les observations historiques signalées comme telles.</p>
    {rows.length === 0 && <p data-testid="microstructure-empty">{m.rows.length === 0 ? "Watchlist explicitement vide dans la source." : "Aucune observation correspondant aux filtres dans cette capture."}</p>}
    <div className="microstructure-card-list">
      {rows.map((r) => <article className="microstructure-card" key={r.symbol} data-testid="microstructure-row">
        <div className="market-summary-row"><strong>{r.symbol}</strong><span>{r.freshness_classification}</span></div>
        <p>{r.availability === "UNAVAILABLE" ? `NOT_AVAILABLE · ${r.unavailable_reason}` : `${r.state ?? "UNKNOWN"} · ${r.freshness_classification === "FRESH" ? "état observé" : "état actuel INCONNU"}`}</p>
        <p>Stream demandé : {r.stream_requested ? "oui" : "non"} · observation {r.observed_at_utc ?? "NOT_AVAILABLE"} · âge {value(r.observation_age_s, "s")}</p>
        {r.availability === "OBSERVED" && <><Metrics row={r} /><LmiDetail row={r} /><span>Notable à la capture : {r.notable === null ? "UNKNOWN" : r.notable ? "oui" : "non"}</span></>}
      </article>)}
    </div>
    <p>Microstructure non autoritaire · aucun signal d’entrée, aucun ordre, aucune permission de trading. Scanner et LMI sont deux captures indépendantes.</p>
  </section>;
};
