import { useEffect, useState } from "react";
import "../market-venues.css";

const instruments = ["BTC", "ATOM"] as const;
const venues = ["MEXC", "Kraken"] as const;
const columns = {
  comparison: ["Plateforme", "Symbole natif", "Bid (USDT)", "Ask (USDT)", "Spread (pb)", "Cotation UTC"],
  flow: ["Plateforme", "Points éligibles", "Carnet inchangé vérifié", "Ruptures non résolues", "Reconnexions"],
};
type Instrument = typeof instruments[number];
type Venue = typeof venues[number];
type Mode = keyof typeof columns;
interface Observation {
  time: string;
  gap: string;
  comparable: number;
  planned: number;
  sources: Record<Venue, {
    symbol: string; bid: string; ask: string; spread: string; quoteTime: string;
    eligible: number; evaluated: number; unchanged: number; breaks: number; reconnects: number;
  }>;
}

export function MarketBookObservation({ mode }: { mode: Mode }) {
  const [asset, setAsset] = useState<Instrument>("BTC");
  const [venue, setVenue] = useState<"all" | Venue>("all");
  const [publication, setPublication] = useState<Partial<Record<Instrument, Observation>>>();
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/observations/btc-atom-book-v1.json", { signal: controller.signal, cache: "no-store" })
      .then(async response => {
        if (!response.ok || !response.headers.get("content-type")?.includes("application/json")) return;
        const data = await response.json();
        if (data?.kind === "HISTORICAL_BBO_OBSERVATION" && !controller.signal.aborted) setPublication(data.instruments);
      })
      .catch(() => undefined)
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);
  const observation = publication?.[asset];
  const displayedVenues = venues.filter(source => venue === "all" || source === venue);
  return <section className="market-panel venue-panel">
    <h2>{mode === "flow" ? "Flux de carnet · historique" : "Comparaison Spot · historique"}</h2>
    <div className="venue-controls">
      <label>Instrument de la capture<select value={asset} onChange={event => setAsset(event.target.value as Instrument)}>
        {instruments.map(instrument => <option key={instrument}>{instrument}</option>)}
      </select></label>
      <label>Plateformes de la capture<select value={venue} onChange={event => setVenue(event.target.value as "all" | Venue)}>
        <option value="all">MEXC Spot et Kraken Spot</option>
        {venues.map(source => <option key={source} value={source}>{source} Spot</option>)}
      </select></label>
    </div>
    {observation ? <p>Capture historique · {asset}/USDT · dernier point comparable à <time dateTime={observation.time}>{observation.time}</time></p>
      : <p role="status">{loading ? "Chargement de la capture…" : "Capture historique indisponible."}</p>}
    <div className="venue-table-wrap" role="region" aria-label="Observations par plateforme" tabIndex={0}>
      <table className="market-table">
        <thead><tr>{columns[mode].map(title => <th scope="col" key={title}>{title}</th>)}</tr></thead>
        <tbody>{displayedVenues.map(source => {
          const row = observation?.sources[source];
          const cells = mode === "comparison"
            ? [row?.symbol, row?.bid, row?.ask, row?.spread, row?.quoteTime]
            : [row && `${row.eligible} / ${row.evaluated}`, row?.unchanged, row?.breaks, row?.reconnects];
          return <tr key={source}><th scope="row">{source} Spot</th>{cells.map((value, i) => <td key={i}>{value ?? "—"}</td>)}</tr>;
        })}</tbody>
      </table>
    </div>
    {mode === "comparison" && observation && venue === "all" && <p>Écart signé des milieux de carnet, Kraken par rapport à MEXC · {observation.gap} pb.</p>}
    {mode === "flow" && observation && <>
      <p>Points comparables · {observation.comparable} sur {observation.planned} instants prévus.</p>
      {asset === "ATOM" && <p>La couverture ATOM dépend en majorité des carnets inchangés vérifiés selon l’hypothèse de continuité A-ORDER.</p>}
    </>}
  </section>;
}
