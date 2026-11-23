/** Radar de signaux — PROTOTYPE sur le schéma BROUILLON cat.signals.indicators.v1-draft.
 *  Affiche, par symbole, les indicateurs publiés par le module de signaux pour chaque
 *  marché (MX·S, MX·P, KR·S, KR·P) et les écarts calculés par le producteur.
 *  L'écran filtre et formate seulement : aucun indicateur, écart ni score n'est
 *  recalculé ici. Une valeur absente reste visible avec son motif, jamais 0. */
import { useState } from "react";
import "./signals-radar.css";

export const SIGNAL_MARKETS = ["mexc_spot", "mexc_perp", "kraken_spot", "kraken_perp"] as const;
export type SignalMarket = typeof SIGNAL_MARKETS[number];
const SHORT: Record<SignalMarket, string> = { mexc_spot: "MX·S", mexc_perp: "MX·P", kraken_spot: "KR·S", kraken_perp: "KR·P" };
const LONG: Record<SignalMarket, string> = { mexc_spot: "MEXC Spot", mexc_perp: "MEXC Perpétuel", kraken_spot: "Kraken Spot", kraken_perp: "Kraken Perpétuel" };
type Value = { closed?: string; provisional?: string } | { snapshot: string; at: string } | { state: string; reason: string; missing?: number };
type MarketBlock = { instrument: string; quote: string; check: string; reason?: string; checked_at?: string; values?: Record<string, Value> };
type Gap = { spot_vs_perp?: Record<string, string | Value>; mexc_vs_kraken?: Record<string, string | Value>; dispersion?: { value: string; markets_used: number } };
export type SignalSymbol = { base: string; timeframe: string; bar_open: string; markets: Record<SignalMarket, MarketBlock>; gaps: Record<string, Gap> };
export type SignalsDoc = { schema: string; fixture?: string; generated_at: string; status: string; symbols: SignalSymbol[] };

const LABEL: Record<string, string> = {
  adx_14: "ADX 14", di_plus_14: "DI+ 14", di_minus_14: "DI− 14", rsi_14: "RSI 14", vwap_dist_pct: "Écart VWAP %",
  ema20_dist_pct: "Écart EMA 20 %", ema50_dist_pct: "Écart EMA 50 %", atr14_pct: "ATR 14 %", volume_rel_20: "Volume relatif 20",
  delta_pct_volume: "Delta % volume", imb_top10: "IMB 10 niveaux", spread_bps: "Spread pb", oi_change_pct: "Variation OI %",
  funding: "Funding", basis_pct: "Base %",
};
const ORDER = Object.keys(LABEL);
const CHECK: Record<string, string> = { VERIFIED: "vérifié", REJECTED: "rejeté", NOT_LISTED: "non coté", UNRESOLVED: "non résolu" };

function cell(v: Value | undefined): { text: string; title?: string; state: "ok" | "na" } {
  if (!v) return { text: "—", title: "non publié pour ce marché", state: "na" };
  if ("state" in v) return { text: "n.d.", title: `${v.state} · ${v.reason}${v.missing ? ` · ${v.missing} bougies manquantes` : ""}`, state: "na" };
  if ("snapshot" in v) return { text: v.snapshot, title: `instantané ${v.at}`, state: "ok" };
  return { text: v.closed ?? "—", title: v.provisional !== undefined ? `bougie en cours : ${v.provisional}` : undefined, state: "ok" };
}

export function SignalsRadar({ doc }: { doc: SignalsDoc }) {
  const [shown, setShown] = useState<ReadonlySet<SignalMarket>>(new Set(SIGNAL_MARKETS));
  const [base, setBase] = useState(doc.symbols[0]?.base ?? "");
  const symbol = doc.symbols.find(s => s.base === base);
  const markets = SIGNAL_MARKETS.filter(m => shown.has(m));
  const toggle = (m: SignalMarket) => setShown(prev => { const next = new Set(prev); if (next.has(m)) { if (next.size > 1) next.delete(m); } else next.add(m); return next; });
  const indicators = symbol ? ORDER.filter(k => SIGNAL_MARKETS.some(m => symbol.markets[m]?.values?.[k])) : [];
  return <section className="signals-radar" aria-label="Radar de signaux">
    <header><h2>Radar de signaux</h2>
      <p>Indicateurs publiés par le module de signaux, par marché. Lecture seule, aucun score.</p>
      {doc.fixture === "SYNTHETIC" && <p className="signals-draft" role="note">◆ Prototype · données SYNTHÉTIQUES · schéma brouillon {doc.schema}</p>}
    </header>
    <div className="signals-tools">
      <label>Symbole<select value={base} onChange={e => setBase(e.target.value)}>{doc.symbols.map(s => <option key={s.base} value={s.base}>{s.base}</option>)}</select></label>
      <div role="group" aria-label="Marchés affichés" className="signals-chips">{SIGNAL_MARKETS.map(m =>
        <button key={m} type="button" aria-pressed={shown.has(m)} title={LONG[m]} onClick={() => toggle(m)}>{SHORT[m]}</button>)}</div>
    </div>
    {symbol && <>
      <ul className="signals-checks" aria-label="Vérification des marchés">{markets.map(m => {
        const b = symbol.markets[m];
        return <li key={m} className={b?.check === "VERIFIED" ? "ok" : "ko"}><strong>{SHORT[m]}</strong> {b?.instrument ?? "—"} · {CHECK[b?.check ?? ""] ?? b?.check ?? "absent"}{b?.reason ? ` (${b.reason})` : ""}</li>;
      })}</ul>
      <p className="signals-meta">Unité {symbol.timeframe} · bougie ouverte {symbol.bar_open.replace("T", " ").replace("Z", " UTC")} · valeur de bougie close, la bougie en cours au survol</p>
      {indicators.length === 0 ? <p role="status">Aucun indicateur publié pour {symbol.base} : aucun marché vérifié.</p> :
      <div className="signals-scroll"><table className="signals-table" aria-label={`Indicateurs ${symbol.base}`}>
        <thead><tr><th scope="col">Indicateur</th>{markets.map(m => <th key={m} scope="col" title={LONG[m]}>{SHORT[m]}</th>)}<th scope="col" title="Dispersion publiée par le producteur, tous marchés vérifiés">Écart</th></tr></thead>
        <tbody>{indicators.map(k => <tr key={k}><th scope="row">{LABEL[k]}</th>
          {markets.map(m => { const c = cell(symbol.markets[m]?.check === "VERIFIED" ? symbol.markets[m]?.values?.[k] : undefined); return <td key={m} className={c.state} title={c.title}>{c.text}</td>; })}
          <td className="gap" title={symbol.gaps[k]?.dispersion ? `dispersion sur ${symbol.gaps[k].dispersion!.markets_used} marchés` : "pas d’écart publié"}>{symbol.gaps[k]?.dispersion?.value ?? "—"}</td></tr>)}</tbody>
      </table></div>}
    </>}
    <p className="signals-foot">Publication {doc.generated_at.replace("T", " ").replace("Z", " UTC")} · état {doc.status} · « n.d. » = non disponible, motif au survol · « — » = non publié pour ce marché.</p>
  </section>;
}
