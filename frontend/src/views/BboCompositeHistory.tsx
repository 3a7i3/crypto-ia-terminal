/** Historical preview of the MEXC + Kraken Spot book-mid composite (M5).
 *  Read-only: the publication is served by the GET-only Operator API and displayed as is.
 *  Nothing here is LIVE, no value is recomputed, and no candle is drawn for an incomplete window. */
import React, { useEffect, useState } from "react";
import { RadarCandles } from "../components/RadarCandles";
import type { Bar } from "../lib/spotRadarClient";
import {
  fetchBboHistory, BboHistoryError, BBO_HISTORY_LABEL, BBO_VENUES, BBO_SOURCE_STATES, BBO_SENS_L, BBO_SENS_G,
  type BboHistory, type BboPair, type BboWindow, type BboCandle, type BboVenue,
} from "../lib/bboHistoryClient";
import { gateNotice, type ScannerGate } from "../lib/scannerUniverseClient";
import "../intraday.css";
import "../spot-radar.css";

const VENUE: Record<BboVenue, string> = { mexc: "MEXC", kraken: "Kraken" };
const CATEGORY: Record<string, string> = {
  COMPOSITE: "composite", SINGLE_SOURCE: "une seule source", SOURCE_EXCLUDED: "source exclue",
  EXCESSIVE_GAP: "écart excessif", NOT_EVALUATED: "non évalué",
};
const LIMIT: Record<string, string> = {
  NOT_LIVE: "Historique : aucune donnée n’est actuelle ni LIVE.",
  SAMPLED_BOOK_MIDS_NOT_TRADES: "Bougies de milieux de carnet échantillonnés, pas de transactions ni de volumes.",
  SINGLE_SHORT_SESSION_PER_PAIR: "Une seule session courte par paire : aucune généralisation.",
  MEXC_MARGIN_ESTIMATE_ONLY: "La marge MEXC reste une estimation.",
  NO_SIGNAL_NO_DECISION: "Aucun signal, score ni décision de trading.",
};
export const utcMs = (ms: number) => new Date(ms).toISOString().slice(0, 16).replace("T", " ") + " UTC";
const hm = (ms: number) => new Date(ms).toISOString().slice(11, 16);

const toBar = (w: BboWindow): Bar => ({
  open_ms: String(w.start_ms), source_close_ms: null, close_boundary_ms: String(w.end_ms),
  open: w.candle.open!, high: w.candle.high!, low: w.candle.low!, close: w.candle.close!,
  base_volume: "0", quote_volume: "0", closed: true, raw_sha256: "", received_ms: "",
} as unknown as Bar);

const Ohlc: React.FC<{ c: BboCandle; ppw: number }> = ({ c, ppw }) => c.status === "COMPLETE"
  ? <span className="bbo-ohlc">O {c.open} · H {c.high} · L {c.low} · C {c.close}</span>
  : <span className="bbo-ohlc">Incomplète · {c.points} / {ppw} points · aucune valeur OHLC</span>;

const WindowCard: React.FC<{ w: BboWindow; p: BboPair }> = ({ w, p }) => {
  const ppw = p.thresholds.points_per_window;
  const excluded = Object.entries(w.by_category).filter(([k, n]) => k !== "COMPOSITE" && n > 0);
  return <article className="bbo-window" aria-label={`Fenêtre ${w.index + 1} · ${utcMs(w.start_ms)}`}>
    <h4>Fenêtre {w.index + 1} · {utcMs(w.start_ms).slice(0, 10)} {hm(w.start_ms)}–{hm(w.end_ms)} UTC
      <span className={w.candle.status === "COMPLETE" ? "bbo-tag bbo-complete" : "bbo-tag bbo-incomplete"}>{w.candle.status === "COMPLETE" ? "Complète" : "Incomplète"}</span></h4>
    <p><Ohlc c={w.candle} ppw={ppw} /></p>
    <dl>
      <dt>Points composites</dt><dd>{w.composite} / {w.planned} prévus · {w.evaluated} évalués</dd>
      <dt>Exclusions</dt><dd>{excluded.length ? excluded.map(([k, n]) => `${n} ${CATEGORY[k]}`).join(" · ") : "Aucune"}</dd>
      {BBO_VENUES.map(v => {
        const s = w.by_source_state[v];
        const other = BBO_SOURCE_STATES.filter(k => k !== "VALID" && k !== "UNCHANGED_VERIFIED" && s[k] > 0);
        return <React.Fragment key={v}><dt>{VENUE[v]}</dt><dd>VALID {s.VALID} · UNCHANGED_VERIFIED {s.UNCHANGED_VERIFIED}{other.map(k => ` · ${k} ${s[k]}`).join("")}</dd></React.Fragment>;
      })}
    </dl>
    <details className="radar-detail-facts"><summary>Bougies par plateforme (même fenêtre)</summary>
      <dl>{BBO_VENUES.map(v => <React.Fragment key={v}><dt>{VENUE[v]}</dt><dd><Ohlc c={w.venue_candles[v]} ppw={ppw} /></dd></React.Fragment>)}</dl>
    </details>
  </article>;
};

const Sensitivity: React.FC<{ p: BboPair }> = ({ p }) => {
  const planned = p.coverage.planned, primaryL = p.thresholds.liveness_max_ms / 1000;
  const at10 = p.sensitivity_composite_totals[`L${primaryL}s_G10bps`];
  return <section className="bbo-sensitivity" aria-label={`Sensibilité ${p.display_symbol}`}>
    <h5>Sensibilité des seuils (points composites sur {planned})</h5>
    {at10 !== undefined && <p className="bbo-highlight">À 10 bps (fraîcheur {primaryL} s) : <strong>{at10} / {planned}</strong> points composites. Seuil enregistré : {p.thresholds.gap_max_bps} bps → {p.coverage.composite} / {planned}.</p>}
    <div className="radar-bars"><table>
      <caption>Lignes : fraîcheur maximale · colonnes : écart maximal</caption>
      <thead><tr><th scope="col">Fraîcheur</th>{BBO_SENS_G.map(g => <th scope="col" key={g} className={g === 10 ? "bbo-col10" : undefined}>{g} bps</th>)}</tr></thead>
      <tbody>{BBO_SENS_L.map(l => <tr key={l}><th scope="row">{l} s</th>{BBO_SENS_G.map(g => <td key={g} className={g === 10 ? "bbo-col10" : undefined}>{p.sensitivity_composite_totals[`L${l}s_G${g}bps`]}</td>)}</tr>)}</tbody>
    </table></div>
    <p>Par fenêtre à 10 bps (fraîcheur {primaryL} s) : {p.windows.map(w => w.sensitivity_composite[`L${primaryL}s_G10bps`]).join(" · ")}.</p>
  </section>;
};

const Provenance: React.FC<{ p: BboPair; doc: BboHistory }> = ({ p, doc }) => {
  const pv = p.provenance, a = p.hypotheses.A_ORDER;
  return <details className="intraday-provenance bbo-provenance"><summary>Provenance, hypothèse A-ORDER et sensibilité</summary>
    <section className="bbo-aorder" aria-label="Hypothèse A-ORDER">
      <h5>Hypothèse A-ORDER</h5>
      <p>{a.statement}</p>
      <p><strong>{a.majority_unchanged_verified ? "Majorité de la couverture fondée sur UNCHANGED_VERIFIED : oui." : "Majorité de la couverture fondée sur UNCHANGED_VERIFIED : non."}</strong></p>
      <dl>{BBO_VENUES.map(v => { const f = p.flux[v]; return <React.Fragment key={v}><dt>{VENUE[v]}</dt><dd>{f.eligible} éligibles dont {f.unchanged_verified} UNCHANGED_VERIFIED · {f.evaluated} évalués · {f.unresolved_breaks} ruptures non résolues · {f.verdict}</dd></React.Fragment>; })}</dl>
    </section>
    <Sensitivity p={p} />
    <dl>
      <dt>Seuils</dt><dd>Fraîcheur ≤ {p.thresholds.liveness_max_ms} ms · écart {p.thresholds.gap_boundary} {p.thresholds.gap_max_bps} bps · pas {p.thresholds.step_ms} ms · {p.thresholds.points_per_window} points par fenêtre · pondération {p.thresholds.weights} · référence {p.thresholds.reference_venue}</dd>
      <dt>Plateformes</dt><dd>{p.venues.map(v => `${VENUE[v.venue]} ${v.native_symbol} (${v.feed})`).join(" · ")}</dd>
      <dt>Preuve</dt><dd>{p.evidence_kind} · {pv.pilot} · commit {pv.collection_commit} · hôte {pv.host}</dd>
      <dt>Session</dt><dd>{utcMs(pv.started_utc_ms)} → {utcMs(pv.ended_utc_ms)} · {pv.run_status} · code {pv.exit_code}</dd>
      <dt>Volume capté</dt><dd>{pv.frames} trames · {pv.events} événements · REST {Object.entries(pv.rest_used).map(([k, n]) => `${k} ${n}`).join(", ")} · reconnexions {BBO_VENUES.map(v => `${VENUE[v]} ${pv.reconnects[v]}`).join(", ")} · resyncs {BBO_VENUES.map(v => `${VENUE[v]} ${pv.resyncs[v]}`).join(", ")}</dd>
      <dt>Checksums Kraken</dt><dd>{p.kraken_checksums.match} concordants · {p.kraken_checksums.mismatch} discordants</dd>
      <dt>Archive</dt><dd>{pv.archive_name}<br /><code>{pv.archive_sha256}</code></dd>
      <dt>Événements / trames</dt><dd><code>{pv.events_sha256}</code><br /><code>{pv.frames_sha256}</code></dd>
      <dt>Résumé rejoué</dt><dd><code>{pv.summary_sha256}</code> · {pv.replay}</dd>
      <dt>Fenêtres rejouées</dt><dd>{pv.window_sha256.map((h, i) => <React.Fragment key={h + i}><code>{h}</code><br /></React.Fragment>)}</dd>
      <dt>Publication</dt><dd>{doc.schema_version} · générée {doc.generated_at_utc} · rapport {doc.report} · {doc.serving.freshness_classification}</dd>
    </dl>
    <ul className="bbo-limits">{doc.limits.map(l => <li key={l}>{LIMIT[l] ?? l}</li>)}</ul>
  </details>;
};

export const BboCompositeHistory: React.FC<{ gate?: ScannerGate }> = ({ gate }) => {
  const [doc, setDoc] = useState<BboHistory | null>(null), [error, setError] = useState<string | null>(null);
  const [pair, setPair] = useState<string | null>(null), [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    fetchBboHistory(controller.signal)
      .then(d => { if (!controller.signal.aborted) { setDoc(d); setPair(x => x && d.pairs.some(p => p.pair === x) ? x : d.pairs[0].pair); } })
      .catch(e => { if (!controller.signal.aborted) { setDoc(null); setError(e instanceof BboHistoryError ? e.code : "TRANSPORT_ERROR"); } });
    return () => controller.abort();
  }, [attempt]);
  // Scanner V1: inside the Scanner, a historical pair is listed only when the
  // current common universe admits the same BASE/QUOTE on all four markets.
  const pairs = doc ? doc.pairs.filter(x => !gate || gate.keys.has(x.display_symbol)) : [];
  const p = pairs.find(x => x.pair === pair) ?? pairs[0] ?? null;
  const complete = p ? p.windows.filter(w => w.candle.status === "COMPLETE") : [];
  const incomplete = p ? p.windows.length - complete.length : 0;
  const invalid = error?.startsWith("INVALID_BBO_HISTORY") || error === "BBO_HISTORY_INVALID_SCHEMA" || error === "BBO_HISTORY_MALFORMED_JSON" || error === "INVALID_JSON";
  const absent = error === "BBO_HISTORY_NOT_CONFIGURED" || error === "BBO_HISTORY_MISSING";
  return <section className="intraday-desk spot-radar bbo-history" aria-label="Composite historique BBO Spot">
    <header className="intraday-heading"><div><p className="intraday-eyebrow">CAT / MARKET INTELLIGENCE · APERÇU</p><h2>{BBO_HISTORY_LABEL}</h2>
      <p className="intraday-lead">MEXC + Kraken. Bougies M5 de milieux de carnet échantillonnés, rejouées depuis des preuves scellées.</p></div>
      <span className="intraday-proof">{doc?.evidence_kind === "SYNTHETIC" ? "◆ SYNTHETIC" : "◇ HISTORIQUE"}<small>{doc?.evidence_kind === "SYNTHETIC" ? "Fixture isolée · données fictives" : "Non LIVE · lecture seule"}</small></span>
    </header>
    <p className="intraday-disclaimer">Aperçu historique en lecture seule. Ce ne sont pas des transactions : aucun volume, aucun signal, aucune donnée actuelle.</p>
    {!doc && !error && <div role="status" className="intraday-loading"><span className="intraday-skeleton" />Lecture de la publication historique…</div>}
    {error && <div role="alert" className="intraday-error">
      {absent ? "Aperçu historique absent" : invalid ? "Publication historique invalide" : "Aperçu historique indisponible"} · {error}. Aucune bougie n’est présentée.
      <button type="button" className="intraday-refresh" onClick={() => setAttempt(n => n + 1)}>Réessayer</button></div>}
    {doc && gate && !pairs.length && <p role="status" className="scanner-gate-notice">{gateNotice(gate.state)}</p>}
    {doc && p && <>
      <div className="intraday-switch bbo-pairs" role="group" aria-label="Paire historique">{pairs.map(x =>
        <button key={x.pair} type="button" aria-pressed={x.pair === pair} onClick={() => setPair(x.pair)}>{x.display_symbol}</button>)}</div>
      <p className="bbo-window-utc"><strong>{p.display_symbol}</strong> · Spot · {p.venues.map(v => `${VENUE[v.venue]} ${v.native_symbol}`).join(" + ")}<br />
        Fenêtre UTC : {utcMs(p.window_utc.start_ms)} → {utcMs(p.window_utc.end_ms)}</p>
      <div className="intraday-metrics" aria-label={`Couverture ${p.display_symbol}`}>
        <div><strong>{p.coverage.composite} / {p.coverage.planned}</strong><span>Points composites / prévus</span></div>
        <div><strong>{p.coverage.complete_composite_candles} / {p.coverage.candles}</strong><span>Bougies M5 complètes / fenêtres</span></div>
        <div><strong>{p.coverage.evaluated}</strong><span>Points évalués</span></div>
        <div><strong>{p.coverage.verdict_pre_registered}</strong><span>Verdict pré-enregistré</span></div>
      </div>
      {p.hypotheses.A_ORDER.majority_unchanged_verified && <p className="bbo-notice" role="note">Couverture majoritairement fondée sur UNCHANGED_VERIFIED (hypothèse A-ORDER). Détail et sensibilité 10 bps dans la provenance.</p>}
      {complete.length
        ? <RadarCandles rows={complete.map(toBar)} symbol={p.display_symbol} timeframe="M5" volume={false}
          caption={`M5 · ${complete.length} bougie${complete.length > 1 ? "s" : ""} complète${complete.length > 1 ? "s" : ""} sur ${p.windows.length} · USDT`}
          title={`${p.display_symbol} M5 — ${BBO_HISTORY_LABEL}`}
          label={`${BBO_HISTORY_LABEL} ${p.display_symbol} M5, ${complete.length} bougies complètes ; milieux de carnet échantillonnés, sans volume`}
          note={`Milieux de carnet échantillonnés (pas ${p.thresholds.step_ms / 1000} s), pas de transactions ni de volumes. ${incomplete ? `${incomplete} fenêtre${incomplete > 1 ? "s" : ""} incomplète${incomplete > 1 ? "s" : ""} non tracée${incomplete > 1 ? "s" : ""}.` : "Aucune fenêtre incomplète."} Valeurs exactes ci-dessous.`} />
        : <p role="status" className="intraday-empty">Aucune bougie complète : rien n’est tracé.</p>}
      <div className="bbo-windows">{p.windows.map(w => <WindowCard key={w.index} w={w} p={p} />)}</div>
      <Provenance p={p} doc={doc} />
    </>}
  </section>;
};
