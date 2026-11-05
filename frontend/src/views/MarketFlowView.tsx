import { useEffect, useRef, useState } from "react";
import { fetchMarketFlow, type MarketFlowState } from "../lib/marketFlowClient";
import { decAdd, decCompare, parseDecimal, type ExactDecimal } from "../lib/marketFlowExact";
import type { HeatmapColumn, MarketFlowHeatmap, MarketFlowPublication } from "../lib/marketFlowTypes";
import "./market-flow.css";

const PAGE = 16;
const unavailable = "Non disponible";

function WindowControls({ label, start, end, total, move }: { label: string; start: number; end: number; total: number; move: (step: number) => void }) {
  return <div className="flux-window" role="group" aria-label={label}>
    <button type="button" disabled={start === 0} onClick={() => move(-PAGE)}>Précédents</button>
    <span role="status">{label} · affichés {end - start}/{total} · {total ? start + 1 : 0}–{end}</span>
    <button type="button" disabled={end >= total} onClick={() => move(PAGE)}>Suivants</button>
  </div>;
}

const units = (value: string) => {
  const d = parseDecimal(value, true)!;
  return d.units * 10n ** BigInt(125 - d.scale);
};

function Series({ data }: { data: MarketFlowPublication }) {
  const [start, setStart] = useState(0);
  const bars = data.bars.slice(start, start + PAGE);
  const marks = bars.flatMap((bar, i) => bar.cvd_base_bounds === null ? [] : [{
    i, lo: units(bar.cvd_base_bounds[0]), hi: units(bar.cvd_base_bounds[1]),
  }]);
  const values = marks.flatMap(mark => [mark.lo, mark.hi]);
  const lo = values.reduce((a, b) => a < b ? a : b, values[0] ?? 0n);
  const hi = values.reduce((a, b) => a > b ? a : b, lo);
  const y = (v: bigint) => hi === lo ? 50 : 90 - Number((v - lo) * 80n / (hi - lo));
  return <section aria-label="Barres de prix et CVD">
    <p>CVD en {data.flow.base} · points et intervalles par barre, avec segments indiqués dans le tableau.</p>
    {marks.length > 0 && <svg className="flux-chart" viewBox={`0 0 ${PAGE * 20} 100`} role="img" aria-label="CVD par barre, valeurs exactes dans le tableau">
      {marks.map(({ i, lo, hi }) => lo === hi
        ? <circle key={i} cx={10 + i * 20} cy={y(lo)} r="3" fill="currentColor"/>
        : <line key={i} x1={10 + i * 20} x2={10 + i * 20} y1={y(lo)} y2={y(hi)} stroke="currentColor" strokeWidth="3"/>)}
    </svg>}
    <WindowControls start={start} end={start + bars.length} label="Barres" total={data.bars.length} move={step => setStart(start + step)}/>
    <div className="flux-scroll" tabIndex={0} role="region" aria-label="Valeurs exactes des barres">
      <table><thead><tr><th>Intervalle (ns)</th><th>Couverture et segment</th><th>OHLC ({data.flow.quote})</th><th>Volumes achat / vente / inconnu ({data.flow.base})</th><th>Delta ({data.flow.base})</th><th>CVD ({data.flow.base})</th></tr></thead>
        <tbody>{bars.map(bar => <tr key={bar.index}>
          <th scope="row">{bar.start_ns} – {bar.end_ns}</th>
          <td>{bar.status} · segment {bar.segment ?? unavailable} · {bar.delta_status}</td>
          <td>{bar.status === "NOT_COVERED" ? unavailable : [bar.open, bar.high, bar.low, bar.close].map(v => v ?? unavailable).join(" / ")}</td>
          <td>{bar.status === "NOT_COVERED" ? unavailable : [bar.buy_volume, bar.sell_volume, bar.unknown_volume].join(" / ")}</td>
          <td>{bar.delta_base ?? bar.delta_base_bounds?.join(" à ") ?? unavailable}</td>
          <td>{bar.cvd_base ?? bar.cvd_base_bounds?.join(" à ") ?? unavailable}</td>
        </tr>)}</tbody>
      </table>
    </div>
    <details><summary>Fenêtres de delta publiées</summary><ul>{Object.entries(data.rolling_delta).map(([ns, value]) =>
      <li key={ns}>{ns} ns · {value.status} · {"reason" in value ? value.reason : value.delta_base ?? value.delta_base_bounds.join(" à ")}</li>)}</ul></details>
  </section>;
}

function priceText(price: ExactDecimal) {
  if (!price.scale) return price.units.toString();
  const digits = price.units.toString().padStart(price.scale + 1, "0");
  return digits.slice(0, -price.scale) + "." + digits.slice(-price.scale);
}

function Heatmap({ grid, base }: { grid: MarketFlowHeatmap; base: string }) {
  const [row, setRow] = useState(0);
  const [start, setStart] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const cols = grid.columns.slice(start, start + PAGE);
  const priceLo = parseDecimal(grid.price_lo)!;
  const tick = parseDecimal(grid.tick)!;
  const priceHi = parseDecimal(grid.price_hi)!;
  const rows = Array.from({ length: Math.min(PAGE, grid.rows - row) }, (_, i) => {
    const lo = decAdd(priceLo, { units: tick.units * BigInt(row + i), scale: tick.scale });
    const end = decAdd(lo, tick);
    return { lo, hi: decCompare(end, priceHi) < 0 ? end : priceHi };
  });
  const sample = selected === null ? undefined : grid.columns[selected];
  const intervalStart = sample && BigInt(grid.t0_ns) + BigInt(sample.bucket) * BigInt(grid.bucket_ns);
  return <section aria-label="Carte de liquidité affichée">
    <p>Quantité affichée en {base}, dernier instantané retenu par intervalle de {grid.bucket_ns} ns. Pas de mesure continue.</p>
    <p>Grille de {grid.price_lo} à {grid.price_hi} · pas {grid.tick} · origine {grid.t0_ns} ns</p>
    <WindowControls start={start} end={start + cols.length} label="Intervalles" total={grid.columns.length} move={step => setStart(start + step)}/>
    <WindowControls start={row} end={row + rows.length} label="Prix" total={grid.rows} move={step => setRow(row + step)}/>
    {sample && <p role="status">Intervalle {sample.bucket} · [{String(intervalStart)}, {String(intervalStart! + BigInt(grid.bucket_ns))}[ ns · {sample.status} · réception {sample.sample_receipt_ns ?? unavailable} ns</p>}
    {(["bids", "asks"] as const).map(side => {
      const caption = side === "bids" ? "Achats" : "Ventes";
      const columns = cols.map(c => ({ c, cells: c.status === "LIVE" ? new Map(c[side].filter(([index]) => index >= row && index < row + PAGE)) : null }));
      let max = 0n;
      for (const { cells } of columns) {
        for (const value of cells?.values() ?? []) {
          const n = units(value);
          if (n > max) max = n;
        }
      }
      return <div className="flux-scroll" key={side} tabIndex={0} role="region" aria-label={caption}>
        <table><caption>{caption} · intensité relative à la fenêtre affichée</caption><thead><tr><th>Prix</th>{cols.map(c => <th key={c.bucket}>
          <button type="button" aria-pressed={selected === c.bucket} onClick={() => setSelected(c.bucket)}>#{c.bucket}</button>
          <div>{c.status === "LIVE" ? "Échantillon" : c.status}</div>
        </th>)}</tr></thead><tbody>
          {rows.map(({lo, hi}, i) => <tr key={row + i}><th scope="row">[{priceText(lo)}, {priceText(hi)}[</th>
            {columns.map(({c, cells}) => {
              const quantity = cells?.get(row + i);
              const covered = c.status === "LIVE" && wholeCellCovered(c, side, lo, hi);
              const shade = quantity !== undefined && max > 0n ? Number(units(quantity) * 25n / max) + 8 : null;
              return <td key={c.bucket} style={shade === null ? undefined : { background: `color-mix(in srgb, currentColor ${shade}%, transparent)` }} data-flux-cell={quantity !== undefined ? "observed" : covered ? "zero" : "unknown"}>
                {quantity ?? (covered ? "0 observé" : "Inconnu")}
              </td>;
            })}
          </tr>)}
        </tbody></table>
      </div>;
    })}
  </section>;
}

export function wholeCellCovered(column: Extract<HeatmapColumn, { status: "LIVE" }>, side: "bids" | "asks", lo: ExactDecimal, hi: ExactDecimal) {
  const bound = side === "bids" ? column.bid_cover_floor : column.ask_cover_ceiling;
  if (bound === null) return true;
  const edge = parseDecimal(bound)!;
  return side === "bids" ? decCompare(lo, edge) >= 0 : decCompare(hi, edge) <= 0;
}

function Publication({ data }: { data: MarketFlowPublication }) {
  const { flow, book } = data;
  const [eventStart, setEventStart] = useState(0);
  const events = data.level_events.items.slice(eventStart, eventStart + PAGE);
  return <>
    <p><strong>{flow.instrument} · {flow.market_kind} · {flow.venue} (candidat)</strong></p>
    <p>{data.evidence_kind === "HISTORICAL" ? "Variante historique de démonstration" : "Démonstration synthétique"} · {data.serving.freshness_classification}</p>
    <p>Convention maker/taker {flow.side_convention.attested ? "attestée" : "non attestée"} · Ancrage {data.anchor_ns} ns · Coupe {data.as_of_receipt_ns} ns</p>
    <p>{data.bars.length} barres publiées · {data.trades.accepted} observations acceptées · {data.trades.duplicates} doublons · {data.trades.conflicts.length} conflits</p>
    <details><summary>Provenance, exclusions et limites</summary>
      <p>Référence de convention {flow.side_convention.evidence_ref}</p>
      <p>Empreinte des événements {data.inputs.events_sha256}</p>
      <dl>{Object.entries(data.trades.refused).map(([reason, count]) => <div key={reason}><dt>{reason}</dt><dd>{count}</dd></div>)}
      {Object.entries(data.trades.excluded).map(([reason, count]) => <div key={reason}><dt>{reason}</dt><dd>{count}</dd></div>)}</dl>
      <p>Après la coupe {data.inputs.events_after_as_of_not_read} · chevauchement {data.inputs.events_straddling_as_of_not_read} · L2 interrompu après chevauchement {data.inputs.l2_events_not_read_after_straddle}</p>
      <ul>{[...data.assumptions, ...data.limits].map((value, i) => <li key={i}>{value}</li>)}</ul>
    </details>
    <details><summary>Prix, delta et CVD</summary><Series data={data}/></details>
    <details><summary>Carnet · meilleurs prix</summary>
      <p>Reconstruction interne {book.state.join(" · ")} · {book.bbo.qualification}</p>
      {book.bbo.status === "OBSERVED_UNQUALIFIED" ? <dl>
        <dt>Meilleur achat</dt><dd>{book.bbo.bid.price} {flow.quote} · {book.bbo.bid.size} {flow.base}</dd>
        <dt>Meilleure vente</dt><dd>{book.bbo.ask.price} {flow.quote} · {book.bbo.ask.size} {flow.base}</dd>
      </dl> : <p>{unavailable} · {book.bbo.reason}</p>}
      {book.freshness ? <p>{book.freshness.freshness} · silence {book.freshness.connection_silence_status} · âge {book.freshness.state_age_status} · {book.freshness.unresolved.join(", ")}</p> : <p>Temporalité {unavailable.toLowerCase()}</p>}
    </details>
    <details><summary>Heatmap des quantités affichées</summary><Heatmap grid={data.heatmap} base={flow.base}/></details>
    <details><summary>Événements de niveau</summary>
      <p>Cause des disparitions indéterminée. {data.level_events.truncated && "Publication tronquée."}</p>
      <WindowControls start={eventStart} end={eventStart + events.length} label="Événements" total={data.level_events.items.length} move={step => setEventStart(eventStart + step)}/>
      <ul>{events.map((event, i) => <li key={eventStart + i}>{event.kind} · {event.side} · {event.price} {flow.quote} · {"qty" in event ? event.qty : event.last_qty} {flow.base} · {event.interval_ns.join(" à ")} ns · {event.cause}</li>)}</ul>
    </details>
  </>;
}

export function MarketFlowView() {
  const [state, setState] = useState<MarketFlowState>({ status: "loading" });
  const [request, setRequest] = useState(0);
  const current = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    current.current = controller;
    void fetchMarketFlow({ signal: controller.signal }).then(result => {
      if (current.current !== controller || controller.signal.aborted) return;
      setState(result);
    });
    return () => {
      controller.abort();
      current.current = null;
    };
  }, [request]);
  return <section className="market-panel flux-view" aria-label="Flux">
    <h2>Flux · démonstration synthétique</h2>
    <button type="button" onClick={() => {
      current.current?.abort();
      setState({ status: "loading" });
      setRequest(value => value + 1);
    }}>Rafraîchir Flux</button>
    {state.status === "loading" && <p role="status">Chargement de Flux…</p>}
    {state.status === "api_error" && <p role="alert">Flux indisponible · HTTP {state.httpStatus}{state.errorCode && ` · ${state.errorCode}`}</p>}
    {state.status === "transport_error" && state.reason !== "ABORTED" && <p role="alert">Lecture de Flux impossible · {state.reason}{state.detail && ` · ${state.detail}`}</p>}
    {state.status === "success" && <Publication key={request} data={state.publication}/>}
  </section>;
}
