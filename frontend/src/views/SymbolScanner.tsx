import { useEffect, useRef, useState } from "react";
import { decimalCompare } from "../lib/intradayClient";
import { fetchRadar, RadarError, type RadarScanner, type RadarRow } from "../lib/spotRadarClient";
import { MarketSourceNotice } from "../components/MarketSourceNotice";
import { marketSourceSetup } from "../lib/marketSourceSetup";
import { MARKET_RADAR_PATH } from "../lib/moduleNavigation";
import { gateNotice, type ScannerGate } from "../lib/scannerUniverseClient";
import "./symbol-scanner.css";

type Qualification = {
  instrumentId: string;
  burnInPassed: boolean;
  chartHref?: string;
};
const noQualifications: readonly Qualification[] = [];

export function SymbolScanner({ bubbles, selection, onSelect, qualifications = noQualifications, gate }: {
  bubbles: boolean;
  /** Scanner V1 common universe: only admitted MEXC Spot rows are shown. */
  gate?: ScannerGate;
  selection: readonly string[];
  onSelect: (id: string) => void;
  qualifications?: readonly Qualification[];
}) {
  const [snapshot, setSnapshot] = useState<{ data: RadarScanner; received: number }>();
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [now, setNow] = useState(Date.now);
  const [query, setQuery] = useState("");
  const [list, setList] = useState(false);
  const [selectedOnly, setSelectedOnly] = useState(false);
  const [active, setActive] = useState<string>();
  const trigger = useRef<HTMLButtonElement | null>(null);
  const close = () => { setActive(undefined); trigger.current?.focus(); };
  useEffect(() => {
    const poll = setInterval(() => setRefresh(value => value + 1), 15_000);
    const tick = setInterval(() => setNow(Date.now()), 1_000);
    return () => { clearInterval(poll); clearInterval(tick); };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    fetchRadar("scanner", {}, controller.signal).then(data => {
      if (controller.signal.aborted) return;
      const received = Date.now();
      setSnapshot({ data, received });
      setNow(received);
      setError("");
    }).catch(reason => {
      if (!controller.signal.aborted) setError(reason instanceof RadarError ? reason.code : "Erreur de transport");
    });
    return () => controller.abort();
  }, [refresh]);

  const data = snapshot?.data;
  const setup = error && !data ? marketSourceSetup(error) : null;
  const elapsed = snapshot ? Math.max(0, now - snapshot.received) : 0;
  const freshness = (row: RadarRow) => {
    if (data?.evidence_kind === "SYNTHETIC") return "Démonstration";
    if (!data || error || data.collector.state !== "RUNNING" || elapsed > 45_000
        || Number(data.server_time_ms) + elapsed > Number(data.collector.expires_ms)) return "Déconnectée";
    if (row.freshness.state === "LIVE" && row.freshness.age_ms !== null) {
      return row.freshness.age_ms + elapsed <= 45_000 ? "Fraîche" : "Ancienne";
    }
    return { LIVE: "Non qualifiée", STALE: "Ancienne", DISCONNECTED: "Déconnectée", UNRESOLVED: "Indisponible", SYNTHETIC: "Démonstration" }[row.freshness.state];
  };
  const instruments = (data?.rows ?? []).filter(row => !gate || gate.admitted.has(row.identity.native_symbol));
  const ranked = instruments.filter(row => row.ticker.volume_qualified && freshness(row) === "Fraîche")
    .sort((a, b) => decimalCompare(b.ticker.quote_volume_24h, a.ticker.quote_volume_24h)
      || a.instrument_id.localeCompare(b.instrument_id));
  const ranks = new Map(ranked.map((row, index) => [row.instrument_id, index + 1]));
  const needle = query.trim().toUpperCase();
  const ordered = bubbles ? [...instruments].sort((a, b) => a.instrument_id.localeCompare(b.instrument_id))
    : [...ranked, ...instruments.filter(row => !ranks.has(row.instrument_id))];
  const rows = ordered
    .filter(row => (row.display_symbol.toUpperCase().includes(needle) || row.identity.native_symbol.toUpperCase().includes(needle))
      && (!selectedOnly || selection.includes(row.instrument_id)));
  const detail = instruments.find(row => row.instrument_id === active);
  const evidence = qualifications.find(item => item.instrumentId === detail?.instrument_id);
  const chartHref = evidence?.burnInPassed && evidence.chartHref?.startsWith(`${MARKET_RADAR_PATH}/`)
    ? evidence.chartHref : undefined;
  const change = (row: RadarRow) => row.ticker.change_qualified ? row.ticker.change_pct_24h : null;
  const pct = (row: RadarRow) => {
    const value = change(row);
    return value === null ? "Indisponible" : `${decimalCompare(value, "0") > 0 ? "+" : ""}${value} %`;
  };
  const spread = (row: RadarRow) => {
    const bid = Number(row.book.bid);
    const ask = Number(row.book.ask);
    return bid > 0 && ask >= bid ? `${((ask - bid) / ((ask + bid) / 2) * 10_000).toFixed(1)} pb` : "Indisponible";
  };

  return <section className="symbol-scanner" aria-label={bubbles ? "Bulles Intraday" : "Scanner classé"}>
    <header><h2>{bubbles ? "Bulles Intraday" : "Scanner classé"}</h2>
      <p>MEXC Spot · USDT · {bubbles ? "Variation publiée sur 24 h" : "Rang par volume 24 h qualifié"}</p></header>
    <div className="symbol-tools">
      <label>Rechercher un symbole<input type="search" value={query} onChange={event => setQuery(event.target.value)} /></label>
      {bubbles ? <button type="button" aria-pressed={list} onClick={() => setList(!list)}>{list ? "Afficher les bulles" : "Afficher la liste"}</button>
        : <button type="button" aria-pressed={selectedOnly} onClick={() => setSelectedOnly(!selectedOnly)}>Sélection ({selection.length})</button>}
      <button type="button" onClick={() => setRefresh(value => value + 1)}>Actualiser</button>
    </div>
    {setup ? <MarketSourceNotice source="Radar Spot" setup={setup} code={error} />
      : error && <p role="alert">Source indisponible · {error}{data ? " · Dernière publication affichée" : ""}</p>}
    {!data && !error && <p role="status">Chargement des observations…</p>}
    {data && gate && instruments.length === 0 && <p role="status" className="scanner-gate-notice">{gateNotice(gate.state)}</p>}
    {data && <p className="symbol-summary">{rows.length} / {data.selected_instruments} instruments{gate ? ` · ${instruments.length} admis par l’univers commun` : ""} · {data.evidence_kind === "SYNTHETIC" ? "Démonstration" : `Collecteur ${data.collector.state}`}</p>}
    {data && rows.length === 0 && (instruments.length > 0 || !gate) && <p role="status">Aucun symbole pour cette recherche.</p>}
    {rows.length > 0 && (bubbles && !list ? <div className="symbol-bubbles">
      {rows.map(row => {
        const value = change(row);
        const numeric = value === null ? 0 : Number(value);
        const size = 66 + Math.min(30, Math.abs(numeric) * 2);
        return <button key={row.instrument_id} type="button" className={numeric > 0 ? "up" : numeric < 0 ? "down" : "neutral"}
          style={{ width: size, height: size }} onClick={event => { trigger.current = event.currentTarget; setActive(row.instrument_id); }}>
          <strong>{row.display_symbol}</strong><span>{pct(row)}</span>{freshness(row) !== "Fraîche" && <small>{freshness(row)}</small>}
        </button>;
      })}</div> : <table className="symbol-table">
      <thead><tr><th scope="col">Rang</th><th scope="col">Paire</th><th scope="col">{bubbles ? "Variation" : "Volume 24 h"}</th><th scope="col">Spread</th></tr></thead>
      <tbody>{rows.map(row => {
        const rank = ranks.get(row.instrument_id);
        return <tr key={row.instrument_id}><td><span className={rank && rank <= 25 ? rank <= 3 ? "gold" : rank <= 10 ? "silver" : "bronze" : undefined}>{rank ?? "—"}</span></td>
          <td><button type="button" onClick={event => { trigger.current = event.currentTarget; setActive(row.instrument_id); }}>{row.display_symbol}</button><small>{freshness(row)}</small></td>
          <td>{bubbles ? pct(row) : row.ticker.volume_qualified ? `${Intl.NumberFormat("fr-FR", { notation: "compact" }).format(Number(row.ticker.quote_volume_24h))} USDT` : "—"}</td>
          <td>{spread(row)}</td></tr>;
      })}</tbody>
    </table>)}
    {detail && <dialog className="symbol-detail" ref={node => { if (node && !node.open) node.showModal?.(); }}
      aria-label={`Fiche ${detail.display_symbol}`} open={typeof HTMLDialogElement.prototype.showModal !== "function" || undefined} onClose={close}
      onKeyDown={event => { if (event.key === "Escape") { event.preventDefault(); event.currentTarget.close?.(); close(); } }}>
      <form method="dialog"><button type="button" onClick={event => { event.currentTarget.closest("dialog")?.close?.(); close(); }}>Fermer</button></form>
      <h3>{detail.display_symbol} · Spot</h3>
      <p>{ranks.has(detail.instrument_id) ? `Rang ${ranks.get(detail.instrument_id)}` : "Non classée"} · {freshness(detail)}</p>
      <dl><dt>Plateforme documentée</dt><dd>MEXC · {detail.identity.native_symbol}</dd>
        <dt>Variation 24 h</dt><dd>{pct(detail)}</dd>
        <dt>Dernier prix publié</dt><dd>{detail.ticker.last_price} USDT</dd>
        <dt>Volume publié</dt><dd>{detail.ticker.volume_qualified ? `${detail.ticker.quote_volume_24h} USDT` : "Indisponible"}</dd>
        <dt>Bid / Ask</dt><dd>{detail.book.bid ?? "—"} / {detail.book.ask ?? "—"} USDT</dd>
        <dt>Réception du ticker (UTC)</dt><dd>{new Date(Number(detail.ticker.received_ms)).toISOString()}</dd>
        <dt>Qualification multi-exchange</dt><dd>{chartHref ? "Qualifiée" : evidence?.burnInPassed ? "Graphique indisponible" : "Flux à qualifier"}</dd></dl>
      <button type="button" onClick={() => onSelect(detail.instrument_id)}>{selection.includes(detail.instrument_id) ? "Retirer de la sélection" : "Ajouter à la sélection"}</button>
      {chartHref && <a href={chartHref}>Ouvrir le graphique unifié</a>}
    </dialog>}
  </section>;
}
