/** Terminal live: only the pairs whose public MEXC Spot ticker is LIVE qualified
 *  right now (source age, plus time since reception, within 45 s, collector
 *  RUNNING and not expired). Nothing is computed beyond display formatting:
 *  no score, no signal, no ranking. A demonstration fixture is never "live". */
import { useEffect, useState } from "react";
import { decimalCompare } from "../lib/intradayClient";
import { fetchRadar, RadarError, type RadarScanner, type RadarRow } from "../lib/spotRadarClient";
import { MarketSourceNotice } from "../components/MarketSourceNotice";
import { marketSourceSetup } from "../lib/marketSourceSetup";
import { gateNotice, type ScannerGate } from "../lib/scannerUniverseClient";
import "./live-terminal.css";

export const LIVE_MAX_AGE_MS = 45_000;
const clock = (ms: number) => new Date(ms).toISOString().slice(11, 19) + " UTC";

export function LiveTerminal({ gate }: { gate?: ScannerGate }) {
  const [snapshot, setSnapshot] = useState<{ data: RadarScanner; received: number }>();
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [now, setNow] = useState(Date.now);
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
      setSnapshot({ data, received }); setNow(received); setError("");
    }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof RadarError ? reason.code : "TRANSPORT_ERROR"); });
    return () => controller.abort();
  }, [refresh]);

  const data = snapshot?.data;
  const elapsed = snapshot ? Math.max(0, now - snapshot.received) : 0;
  const feedLive = !!data && !error && data.evidence_kind === "PUBLIC_OBSERVED" && data.collector.state === "RUNNING"
    && elapsed <= LIVE_MAX_AGE_MS && Number(data.server_time_ms) + elapsed <= Number(data.collector.expires_ms);
  const age = (row: RadarRow) => row.freshness.age_ms === null ? null : row.freshness.age_ms + elapsed;
  const isLive = (row: RadarRow) => feedLive && row.freshness.state === "LIVE" && age(row) !== null && age(row)! <= LIVE_MAX_AGE_MS;
  const admitted = (data?.rows ?? []).filter(row => !gate || gate.admitted.has(row.identity.native_symbol));
  const live = admitted.filter(isLive).sort((a, b) => decimalCompare(b.ticker.quote_volume_24h, a.ticker.quote_volume_24h) || a.instrument_id.localeCompare(b.instrument_id));
  const setup = error && !data ? marketSourceSetup(error) : null;
  const change = (row: RadarRow) => row.ticker.change_qualified ? row.ticker.change_pct_24h : null;
  const spread = (row: RadarRow) => {
    const bid = Number(row.book.bid), ask = Number(row.book.ask);
    return bid > 0 && ask >= bid ? ((ask - bid) / ((ask + bid) / 2) * 10_000).toFixed(1) : "—";
  };

  return <section className="live-terminal" aria-label="Terminal live">
    <header>
      <h2>Terminal live</h2>
      <p className={feedLive ? "live-on" : "live-off"} role="status">
        {feedLive ? `● LIVE · ${live.length} paire${live.length > 1 ? "s" : ""} · reçu ${clock(snapshot!.received)}`
          : data?.evidence_kind === "SYNTHETIC" ? "◆ Démonstration · aucune paire n’est présentée comme live"
          : data ? `○ Flux non live (${error || data.collector.state}) · aucune paire affichée`
          : error ? "○ Source indisponible" : "Connexion…"}
      </p>
    </header>
    {setup ? <MarketSourceNotice source="Radar Spot" setup={setup} code={error} />
      : error && <p role="alert" className="live-alert">Source indisponible · {error}</p>}
    {data && gate && admitted.length === 0 && <p role="status" className="scanner-gate-notice">{gateNotice(gate.state)}</p>}
    {feedLive && admitted.length > 0 && live.length === 0 && <p role="status" className="live-empty">Aucune paire LIVE en ce moment.</p>}
    {live.length > 0 && <table className="live-table" aria-label="Paires live">
      <thead><tr><th scope="col">Paire</th><th scope="col">Prix</th><th scope="col">24 h</th><th scope="col">Spread pb</th><th scope="col">Âge</th></tr></thead>
      <tbody>{live.map(row => {
        const value = change(row), sign = value === null ? 0 : decimalCompare(value, "0");
        return <tr key={row.instrument_id}>
          <th scope="row">{row.display_symbol}</th>
          <td>{row.ticker.last_price}</td>
          <td className={sign > 0 ? "up" : sign < 0 ? "down" : undefined}>{value === null ? "—" : `${sign > 0 ? "+" : ""}${value} %`}</td>
          <td>{spread(row)}</td>
          <td>{Math.round(age(row)! / 1000)} s</td>
        </tr>;
      })}</tbody>
    </table>}
    <p className="live-foot">MEXC Spot · ticker public · LIVE = âge ≤ 45 s · actualisation 15 s · observation uniquement, aucun signal.</p>
  </section>;
}
