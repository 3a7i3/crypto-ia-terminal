import { useEffect, useRef, useState } from "react";
import { decimalCompare } from "../lib/intradayClient";
import { fetchRadar, RadarError, type RadarScanner, type RadarRow } from "../lib/spotRadarClient";
import { MarketSourceNotice } from "../components/MarketSourceNotice";
import { marketSourceSetup } from "../lib/marketSourceSetup";
import { MARKET_RADAR_PATH } from "../lib/moduleNavigation";
import { admissionKnown, admissionPending, gateNotice, marketBadge, type ScannerGate } from "../lib/scannerUniverseClient";
import { CADENCES, signalOf, useRefreshSchedule } from "../lib/refreshSchedule";
import "./symbol-scanner.css";

export const LIVE_MAX_AGE_MS = 45_000;
type SortKey = "volume" | "change" | "spread";
const clock = (ms: number) => new Date(ms).toISOString().slice(11, 19) + " UTC";

type Qualification = {
  instrumentId: string;
  burnInPassed: boolean;
  chartHref?: string;
};
const noQualifications: readonly Qualification[] = [];

/** Moniteur de marché (ex-Classement du jour + Terminal live, 2026-11-23) : paires
 *  MEXC Spot observées, rang par volume 24 h qualifié, âge de chaque ligne, filtre
 *  « Live seulement » et programmateur de lecture (Live 5 s, 1m, 5m, Off) avec voyant.
 *  Affichage seulement : aucun score, aucun signal, aucun ordre. */
export function SymbolScanner({ selection, onSelect, qualifications = noQualifications, gate }: {
  /** Scanner V1 common universe: only admitted MEXC Spot rows are shown. */
  gate?: ScannerGate;
  selection: readonly string[];
  onSelect: (id: string) => void;
  qualifications?: readonly Qualification[];
}) {
  const [snapshot, setSnapshot] = useState<{ data: RadarScanner; received: number }>();
  const [error, setError] = useState("");
  const schedule = useRefreshSchedule();
  const [pendingSince, setPendingSince] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now);
  const [liveOnly, setLiveOnly] = useState(false);
  const [sort, setSort] = useState<SortKey>("volume");
  const [query, setQuery] = useState("");
  const [selectedOnly, setSelectedOnly] = useState(false);
  const [active, setActive] = useState<string>();
  const trigger = useRef<HTMLButtonElement | null>(null);
  const close = () => { setActive(undefined); trigger.current?.focus(); };
  useEffect(() => {
    const tick = setInterval(() => setNow(Date.now()), 1_000);
    return () => clearInterval(tick);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setPendingSince(Date.now());
    fetchRadar("scanner", {}, controller.signal).then(data => {
      if (controller.signal.aborted) return;
      const received = Date.now();
      setSnapshot({ data, received });
      setNow(received);
      setError("");
    }).catch(reason => {
      if (!controller.signal.aborted) setError(reason instanceof RadarError ? reason.code : "Erreur de transport");
    }).finally(() => { if (!controller.signal.aborted) setPendingSince(null); });
    return () => controller.abort();
  }, [schedule.tick]);

  const data = snapshot?.data;
  const setup = error && !data ? marketSourceSetup(error) : null;
  const elapsed = snapshot ? Math.max(0, now - snapshot.received) : 0;
  const freshness = (row: RadarRow) => {
    if (data?.evidence_kind === "SYNTHETIC") return "Démonstration";
    if (!data || error || data.collector.state !== "RUNNING" || elapsed > LIVE_MAX_AGE_MS
        || Number(data.server_time_ms) + elapsed > Number(data.collector.expires_ms)) return "Déconnectée";
    if (row.freshness.state === "LIVE" && row.freshness.age_ms !== null) {
      return row.freshness.age_ms + elapsed <= LIVE_MAX_AGE_MS ? "Fraîche" : "Ancienne";
    }
    return { LIVE: "Non qualifiée", STALE: "Ancienne", DISCONNECTED: "Déconnectée", UNRESOLVED: "Indisponible", SYNTHETIC: "Démonstration" }[row.freshness.state];
  };
  const instruments = (data?.rows ?? []).filter(row => !gate || gate.admitted.has(row.identity.native_symbol));
  const ranked = instruments.filter(row => row.ticker.volume_qualified && freshness(row) === "Fraîche")
    .sort((a, b) => decimalCompare(b.ticker.quote_volume_24h, a.ticker.quote_volume_24h)
      || a.instrument_id.localeCompare(b.instrument_id));
  const ranks = new Map(ranked.map((row, index) => [row.instrument_id, index + 1]));
  const needle = query.trim().toUpperCase();
  const ordered = [...ranked, ...instruments.filter(row => !ranks.has(row.instrument_id))];
  const age = (row: RadarRow) => row.freshness.age_ms === null ? null : row.freshness.age_ms + elapsed;
  const spreadBp = (row: RadarRow) => { const bid = Number(row.book.bid), ask = Number(row.book.ask); return bid > 0 && ask >= bid ? (ask - bid) / ((ask + bid) / 2) * 10_000 : null; };
  // Tri d'affichage seulement ; une valeur indisponible va en fin de liste, jamais à 0.
  const keyOf = (row: RadarRow): number | null => sort === "change" ? (row.ticker.change_qualified ? Number(row.ticker.change_pct_24h) : null) : sort === "spread" ? spreadBp(row) : null;
  const sorted = sort === "volume" ? ordered : [...ordered].sort((a, b) => {
    const x = keyOf(a), y = keyOf(b);
    if (x === null || y === null) return x === null ? (y === null ? 0 : 1) : -1;
    return sort === "change" ? y - x : x - y;
  });
  const rows = sorted
    .filter(row => (row.display_symbol.toUpperCase().includes(needle) || row.identity.native_symbol.toUpperCase().includes(needle))
      && (!selectedOnly || selection.includes(row.instrument_id)) && (!liveOnly || freshness(row) === "Fraîche"));
  const sourceActive = !!data && (data.evidence_kind === "SYNTHETIC" || (data.collector.state === "RUNNING" && Number(data.server_time_ms) + elapsed <= Number(data.collector.expires_ms)));
  const light = signalOf({ cadence: schedule.cadence, pendingSince, lastOk: snapshot?.received ?? null, error: !!error, sourceActive, now });
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
    const value = spreadBp(row);
    return value === null ? "Indisponible" : `${value.toFixed(1)} pb`;
  };

  return <section className="symbol-scanner" aria-label="Moniteur de marché">
    <header><h2>Moniteur de marché</h2>
      <p>MEXC Spot · USDT · rang par volume 24 h qualifié · âge de chaque ligne</p></header>
    <div className="monitor-schedule">
      <div role="group" aria-label="Programmateur de lecture" className="monitor-cadence">{CADENCES.map(c =>
        <button key={c.id} type="button" aria-pressed={schedule.cadence === c.id} onClick={() => schedule.setCadence(c.id)}>{c.label}</button>)}</div>
      <p role="status" aria-label="Voyant de connexion" className={`monitor-light ${light.signal}`}><span aria-hidden="true" className="dot" />{light.label}
        {snapshot && <small> · lu {clock(snapshot.received)}</small>}</p>
    </div>
    <div className="symbol-tools">
      <label>Rechercher un symbole<input type="search" value={query} onChange={event => setQuery(event.target.value)} /></label>
      <button type="button" aria-pressed={selectedOnly} onClick={() => setSelectedOnly(!selectedOnly)}>Sélection ({selection.length})</button>
      <button type="button" aria-pressed={liveOnly} onClick={() => setLiveOnly(!liveOnly)}>Live seulement</button>
      <label className="monitor-sort">Trier<select value={sort} onChange={e => setSort(e.target.value as SortKey)}>
        <option value="volume">Volume 24 h</option><option value="change">Variation 24 h</option><option value="spread">Spread</option></select></label>
      <button type="button" onClick={schedule.readNow}>Actualiser</button>
    </div>
    {setup ? <MarketSourceNotice source="Radar Spot" setup={setup} code={error} />
      : error && <p role="alert">Source indisponible · {error}{data ? " · Dernière publication affichée" : ""}</p>}
    {!data && !error && <p role="status">Chargement des observations…</p>}
    {data && gate && instruments.length === 0 && <p role="status" className="scanner-gate-notice">{gateNotice(gate.state, gate.byAsset)}</p>}
    {data && <p className="symbol-summary">{admissionKnown(gate)
      ? `${rows.length} / ${data.selected_instruments} instruments${gate ? ` · ${instruments.length} admis ${gate.byAsset ? "par actif (Spot et Perpétuel)" : "par l’univers commun"}` : ""}`
      : `${data.selected_instruments} instruments observés · admission ${admissionPending(gate!)}`} · {data.evidence_kind === "SYNTHETIC" ? "Démonstration" : `Collecteur ${data.collector.state}`}</p>}
    {data && rows.length === 0 && (instruments.length > 0 || !gate) && <p role="status">{liveOnly ? "Aucune paire live en ce moment." : "Aucun symbole pour cette recherche."}</p>}
    {rows.length > 0 && <table className="symbol-table" aria-label="Paires du moniteur">
      <thead><tr><th scope="col">Rang</th><th scope="col">Paire</th><th scope="col">Volume 24 h</th><th scope="col">24 h</th><th scope="col">Spread</th></tr></thead>
      <tbody>{rows.map(row => {
        const rank = ranks.get(row.instrument_id);
        return <tr key={row.instrument_id}><td><span className={rank && rank <= 25 ? rank <= 3 ? "gold" : rank <= 10 ? "silver" : "bronze" : undefined}>{rank ?? "—"}</span></td>
          <td><button type="button" onClick={event => { trigger.current = event.currentTarget; setActive(row.instrument_id); }}>{row.display_symbol}</button>{(b => b && <span className="market-count-badge" title={b.title}>{b.text}</span>)(marketBadge(gate, row.identity.native_symbol))}<small>{freshness(row)}{age(row) !== null && freshness(row) !== "Démonstration" ? ` · ${Math.round(age(row)! / 1000)} s` : ""}</small></td>
          <td>{row.ticker.volume_qualified ? `${Intl.NumberFormat("fr-FR", { notation: "compact" }).format(Number(row.ticker.quote_volume_24h))} USDT` : "—"}</td>
          <td className={change(row) === null ? undefined : decimalCompare(change(row)!, "0") > 0 ? "up" : decimalCompare(change(row)!, "0") < 0 ? "down" : undefined}>{pct(row)}</td>
          <td>{spread(row)}</td></tr>;
      })}</tbody>
    </table>}
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
