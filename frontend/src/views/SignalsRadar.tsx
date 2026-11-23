/** Radar de signaux — écran de la publication cat.signals.indicators.v1 (module de
 *  signaux). Par symbole : chaque indicateur sur chaque marché (MX·S, MX·P, KR·S,
 *  KR·P) et l'écart (dispersion) publié par le producteur. L'écran filtre et formate
 *  seulement : aucun indicateur, écart ni score n'est recalculé ici. Une valeur
 *  absente reste visible avec son motif, jamais 0 ; rien n'est affiché sous un
 *  marché dont la vérification n'est pas VERIFIED. Non branché tant que la route
 *  GET /api/operator/v1/signals-indicators n'existe pas. */
import { useState } from "react";
import "./signals-radar.css";

export const SIGNAL_MARKETS = ["mexc_spot", "mexc_perp", "kraken_spot", "kraken_perp"] as const;
export type SignalMarket = typeof SIGNAL_MARKETS[number];
const SHORT: Record<SignalMarket, string> = { mexc_spot: "MX·S", mexc_perp: "MX·P", kraken_spot: "KR·S", kraken_perp: "KR·P" };
const LONG: Record<SignalMarket, string> = { mexc_spot: "MEXC Spot", mexc_perp: "MEXC Perpétuel", kraken_spot: "Kraken Spot", kraken_perp: "Kraken Perpétuel" };
type Cell = { state: "OK"; value: string } | { state: "NOT_AVAILABLE"; reason: string; missing?: number };
type Value = { closed?: Cell; provisional?: Cell; snapshot?: Cell; at?: string };
type Check = { check: string; reason?: string; at?: string };
type MarketBlock = Check & { instrument: string; quote: string; book?: Check; values?: Record<string, Value> };
type Gap = { dispersion?: Cell & { markets_used?: number }; spot_vs_perp?: Record<string, Cell> };
export type SignalSymbol = { base: string; timeframe: string; markets: Record<SignalMarket, MarketBlock>; gaps: Record<string, Gap>; not_compared?: string[] };
export type SignalsDoc = { schema: string; as_of: string; status: string; provenance?: { fixture?: string }; symbols: SignalSymbol[] };

const LABEL: Record<string, string> = {
  adx_14: "ADX 14", di_plus_14: "DI+ 14", di_minus_14: "DI− 14", rsi_14: "RSI 14",
  vwap_session_dist_pct: "Écart VWAP séance %", ema20_dist_pct: "Écart EMA 20 %", ema20_slope_pct: "Pente EMA 20 %",
  ema50_dist_pct: "Écart EMA 50 %", ema50_slope_pct: "Pente EMA 50 %", atr14_pct: "ATR 14 %",
  volume_rel_20: "Volume relatif 20", delta_pct_volume: "Delta % volume", cvd_session: "CVD séance",
  imb_top10: "IMB 10 niveaux", spread_bps: "Spread pb", oi_change_pct: "Variation OI %", funding_rate: "Funding", funding_rate_hourly: "Funding horaire",
};
const ORDER = Object.keys(LABEL);
const CHECK: Record<string, string> = { VERIFIED: "vérifié", REJECTED: "rejeté", NOT_LISTED: "non coté", UNRESOLVED: "non résolu" };
const num = (v: string) => v.replace(/(\.\d*?[1-9])0+$|\.0+$/, "$1");
/** Affichage abrégé (4 décimales, 3 chiffres significatifs sous 0,01) (formatage seul) ; la valeur exacte publiée reste au survol. */
const short = (v: string) => {
  const n = Number(v);
  if (!Number.isFinite(n) || !/\.\d{5,}/.test(v)) return num(v);
  // une petite valeur non nulle ne s'affiche jamais « 0 » : 3 chiffres significatifs
  return num(n !== 0 && Math.abs(n) < 0.01 ? n.toPrecision(3) : n.toFixed(4));
};
const utc = (iso: string) => iso.replace("T", " ").replace(/\.\d+Z$|Z$/, " UTC");

function show(c: Cell | undefined, extra?: string): { text: string; title?: string; na: boolean } {
  if (!c) return { text: "—", title: "non publié pour ce marché", na: true };
  if (c.state !== "OK") return { text: "n.d.", title: `${c.reason}${c.missing ? ` · ${c.missing} bougies manquantes` : ""}`, na: true };
  const exact = short(c.value) !== num(c.value) ? `valeur exacte ${num(c.value)}` : undefined;
  return { text: short(c.value), title: [exact, extra].filter(Boolean).join(" · ") || undefined, na: false };
}
function value(v: Value | undefined) {
  if (!v) return show(undefined);
  if (v.snapshot) return show(v.snapshot, v.at ? `instantané ${utc(v.at)}` : undefined);
  const p = v.provisional?.state === "OK" ? `bougie en cours : ${num(v.provisional.value)}` : undefined;
  return show(v.closed, p);
}

export function SignalsRadar({ doc, demo = false }: { doc: SignalsDoc; demo?: boolean }) {
  const [shown, setShown] = useState<ReadonlySet<SignalMarket>>(new Set(SIGNAL_MARKETS));
  const [base, setBase] = useState(doc.symbols[0]?.base ?? "");
  const symbol = doc.symbols.find(s => s.base === base);
  const markets = SIGNAL_MARKETS.filter(m => shown.has(m));
  const toggle = (m: SignalMarket) => setShown(prev => { const next = new Set(prev); if (next.has(m)) { if (next.size > 1) next.delete(m); } else next.add(m); return next; });
  const verified = (m: SignalMarket) => symbol?.markets[m]?.check === "VERIFIED";
  const indicators = symbol ? ORDER.filter(k => SIGNAL_MARKETS.some(m => verified(m) && symbol.markets[m]?.values?.[k])) : [];
  const basis = symbol?.gaps.basis_pct?.spot_vs_perp;
  return <section className="signals-radar" aria-label="Radar de signaux">
    <header><h2>Radar de signaux{demo ? " · Démo" : ""}</h2>
      <p>Indicateurs publiés par le module de signaux, par marché. Lecture seule, aucun score.</p>
      {doc.provenance?.fixture === "SYNTHETIC" && <p className="signals-draft" role="note">◆ Données SYNTHÉTIQUES · {doc.schema}{demo ? " · démonstration, aucune donnée de marché réelle" : ""}</p>}
    </header>
    <div className="signals-tools">
      <label>Symbole<select value={base} onChange={e => setBase(e.target.value)}>{doc.symbols.map(s => <option key={s.base} value={s.base}>{s.base}</option>)}</select></label>
      <div role="group" aria-label="Marchés affichés" className="signals-chips">{SIGNAL_MARKETS.map(m =>
        <button key={m} type="button" aria-pressed={shown.has(m)} title={LONG[m]} onClick={() => toggle(m)}>{SHORT[m]}</button>)}</div>
    </div>
    {symbol && <>
      <ul className="signals-checks" aria-label="Vérification des marchés">{markets.map(m => {
        const b = symbol.markets[m];
        const book = b?.book && b.book.check !== "VERIFIED" ? ` · carnet ${CHECK[b.book.check] ?? b.book.check}${b.book.reason ? ` (${b.book.reason})` : ""}` : "";
        return <li key={m} className={b?.check === "VERIFIED" ? (book ? "warn" : "ok") : "ko"}><strong>{SHORT[m]}</strong> {b?.instrument ?? "—"} · {CHECK[b?.check ?? ""] ?? b?.check ?? "absent"}{b?.reason ? ` (${b.reason})` : ""}{book}</li>;
      })}</ul>
      {basis && <p className="signals-basis" aria-label="Base Spot–Perpétuel">Base Spot–Perpétuel : MEXC {show(basis.mexc).text}{basis.mexc?.state === "OK" ? " %" : ""} · Kraken {show(basis.kraken).text}{basis.kraken?.state === "OK" ? " %" : ""}</p>}
      <p className="signals-meta">Unité {symbol.timeframe} · valeur de la dernière bougie close, bougie en cours et motifs au survol · « Écart global » = dispersion publiée par le producteur sur ses marchés utilisables, inchangée par le filtre</p>
      {indicators.length === 0 ? <p role="status">Aucun indicateur publié pour {symbol.base} : aucun marché vérifié.</p> :
      <div className="signals-scroll"><table className="signals-table" aria-label={`Indicateurs ${symbol.base}`}>
        <thead><tr><th scope="col">Indicateur</th>{markets.map(m => <th key={m} scope="col" title={LONG[m]}>{SHORT[m]}</th>)}<th scope="col" title="Dispersion publiée par le producteur sur tous ses marchés utilisables ; le filtre ne la recalcule pas">Écart global</th></tr></thead>
        <tbody>{indicators.map(k => {
          const d = symbol.gaps[k]?.dispersion;
          const gap = symbol.not_compared?.includes(k) ? { text: "n.c.", title: "non comparé entre marchés", na: true }
            : d ? show(d, d.markets_used !== undefined ? `dispersion sur ${d.markets_used} marchés` : undefined) : show(undefined);
          return <tr key={k}><th scope="row">{LABEL[k]}</th>
            {markets.map(m => { const c = verified(m) ? value(symbol.markets[m]?.values?.[k]) : show(undefined); return <td key={m} className={c.na ? "na" : undefined} title={c.title}>{c.text}</td>; })}
            <td className={"gap" + (gap.na ? " na" : "")} title={gap.title}>{gap.text}</td></tr>;
        })}</tbody>
      </table></div>}
    </>}
    <p className="signals-foot">Publication {utc(doc.as_of)} · état {doc.status} · « n.d. » non disponible · « — » non publié pour ce marché · « n.c. » non comparé.</p>
  </section>;
}
