// engine.js — moteur pur de lecture de la microstructure (aucun DOM, aucun flux branché).
//
// Entrée : des transactions {ts, price, qty, side}. `side` est le côté AGRESSEUR :
//   'buy'  = achat agressif (frappe l'Ask)  -> colonne Ask
//   'sell' = vente agressive (frappe le Bid) -> colonne Bid
//   null   = côté inconnu. Il n'est JAMAIS deviné : le volume est compté à part.
//
// Sortie : des bougies footprint (Bid × Ask par niveau), imbalances diagonales,
// Volume / Delta / DeltaChg / DltaDay, et profils Delta / Volume.

export const CHANNELS = Object.freeze([
  { id: 'trades',    label: "Transactions (avec côté agresseur)", required: true,  status: 'disconnected' },
  { id: 'orderbook', label: "Carnet d'ordres (DOM)",              required: false, status: 'disconnected' },
]);

// status : 'engine' = calculé et testé dans ce moteur ; 'todo' = à définir ; 'needs-book' = attend le carnet.
export const INDICATORS = Object.freeze([
  { id: 'footprint',  label: 'Footprint Bid × Ask par niveau',          status: 'engine' },
  { id: 'imbalance',  label: 'Imbalances diagonales (IMB %, IMB MIN)',  status: 'engine' },
  { id: 'stacked',    label: 'Stacked imbalances',                      status: 'engine' },
  { id: 'volume',     label: 'Volume de bougie',                        status: 'engine' },
  { id: 'delta',      label: 'Delta de bougie',                         status: 'engine' },
  { id: 'deltachg',   label: 'DeltaChg (variation du Delta)',           status: 'engine' },
  { id: 'dltaday',    label: 'DltaDay (Delta cumulatif de session)',    status: 'engine' },
  { id: 'deltaprof',  label: 'Delta Profile',                           status: 'engine' },
  { id: 'volprof',    label: 'Volume Profile et POC',                   status: 'engine' },
  { id: 'levels',     label: 'Niveaux horizontaux (violet / jaune / bleu)', status: 'todo' },
  { id: 'dom',        label: "Heatmap / DOM",                           status: 'needs-book' },
]);

export type AggressorSide = 'buy' | 'sell' | null;
export interface FootprintTrade {
  ts: number;
  price: number;
  qty: number;
  side: AggressorSide;
}

type RejectReason = 'not_object' | 'bad_ts' | 'bad_price' | 'bad_qty' | 'bad_side';
type SessionKey = (timestamp: number) => number | string;
export interface FootprintOptions {
  tickSize: number;
  tfMs: number;
  sessionKey?: SessionKey;
}

interface Quantities {
  bid: number;
  ask: number;
  unc: number;
}

interface Level extends Quantities {
  idx: number;
  price: number;
  buyImb?: boolean;
  sellImb?: boolean;
  stackedBuy?: boolean;
  stackedSell?: boolean;
}

interface PendingBar {
  levels: Map<number, Quantities>;
  openKey: [number, number] | null;
  closeKey: [number, number] | null;
  openIdx: number;
  closeIdx: number;
  hiIdx: number;
  loIdx: number;
}

const r9 = (v: number) => Math.round(v * 1e9) / 1e9;

// Retourne null si la transaction est valide, sinon le code du rejet.
export function validateTrade(input: unknown): RejectReason | null {
  if (!input || typeof input !== 'object') return 'not_object';
  const t = input as Partial<Record<keyof FootprintTrade, unknown>>;
  if (!Number.isSafeInteger(t.ts) || typeof t.ts !== 'number' || t.ts <= 0) return 'bad_ts';
  if (!Number.isFinite(t.price) || typeof t.price !== 'number' || t.price <= 0) return 'bad_price';
  if (!Number.isFinite(t.qty) || typeof t.qty !== 'number' || t.qty <= 0) return 'bad_qty';
  if (t.side != null && t.side !== 'buy' && t.side !== 'sell') return 'bad_side';
  return null;
}

// Clé de session : la journée UTC décalée de `startHourUTC` (ex. 18 pour une session qui ouvre à 18:00 UTC).
export const utcSessionKey = (startHourUTC = 0) => (ts: number) => Math.floor((ts - startHourUTC * 3600000) / 86400000);

// Imbalance : le côté dominant `a` doit atteindre `pct` % de l'autre côté `b` (150 → au moins 1,5 × b)
// et au moins `min` unités. Si b vaut 0, le déséquilibre est total.
// Hypothèse à confirmer avec la plateforme de référence : la lecture exacte de « IMB % ».
const dominates = (a: number, b: number, pct: number, min: number) => a > 0 && a >= min && (b === 0 || a * 100 >= b * pct);

function flagImbalances(levels: Level[], pct: number, min: number, stackN: number) {
  const byIdx = new Map(levels.map((l) => [l.idx, l]));
  for (const l of levels) {
    const below = byIdx.get(l.idx - 1);
    const above = byIdx.get(l.idx + 1);
    // Comparaison diagonale : Ask du niveau p contre Bid du niveau p-1, Bid de p contre Ask de p+1.
    // Sans niveau voisin dans la bougie, aucune comparaison n'est faite.
    l.buyImb = !!below && dominates(l.ask, below.bid, pct, min);
    l.sellImb = !!above && dominates(l.bid, above.ask, pct, min);
    l.stackedBuy = false;
    l.stackedSell = false;
  }
  for (const [flag, stack] of [['buyImb', 'stackedBuy'], ['sellImb', 'stackedSell']] as const) {
    let run: Level[] = [];
    const flush = () => { if (run.length >= stackN) run.forEach((l) => { l[stack] = true; }); run = []; };
    for (const l of levels) {
      if (l[flag] && (run.length === 0 || run[run.length - 1].idx === l.idx - 1)) run.push(l);
      else { flush(); if (l[flag]) run = [l]; }
    }
    flush();
  }
}

export class FootprintBuilder {
  readonly tickSize: number;
  readonly tfMs: number;
  private readonly sessionKey: SessionKey;
  private readonly bars = new Map<number, PendingBar>();
  private readonly rejected: Partial<Record<RejectReason, number>> = {};
  private accepted = 0;
  private offTick = 0;
  private seq = 0;

  constructor(options?: FootprintOptions) {
    const tickSize = options?.tickSize ?? 0;
    const tfMs = options?.tfMs ?? 0;
    if (!(tickSize > 0)) throw new Error('tickSize doit être > 0');
    if (!Number.isInteger(tfMs) || tfMs <= 0) throw new Error('tfMs doit être un entier > 0 (ms)');
    this.tickSize = tickSize;
    this.tfMs = tfMs;
    this.sessionKey = options?.sessionKey || utcSessionKey(0);
  }

  push(input: unknown) {
    const reason = validateTrade(input);
    if (reason) { this.rejected[reason] = (this.rejected[reason] || 0) + 1; return false; }
    const t = input as FootprintTrade;
    const ratio = t.price / this.tickSize;
    const idx = Math.round(ratio);
    if (Math.abs(ratio - idx) > 1e-6) this.offTick += 1; // accepté, mais signalé dans la qualité
    const t0 = Math.floor(t.ts / this.tfMs) * this.tfMs;
    let bar = this.bars.get(t0);
    if (!bar) {
      bar = { levels: new Map(), openKey: null, closeKey: null, openIdx: idx, closeIdx: idx, hiIdx: idx, loIdx: idx };
      this.bars.set(t0, bar);
    }
    const seq = (this.seq += 1);
    // Ouverture et clôture suivent l'horodatage de la transaction, pas l'ordre d'arrivée.
    if (!bar.openKey || t.ts < bar.openKey[0] || (t.ts === bar.openKey[0] && seq < bar.openKey[1])) { bar.openKey = [t.ts, seq]; bar.openIdx = idx; }
    if (!bar.closeKey || t.ts > bar.closeKey[0] || (t.ts === bar.closeKey[0] && seq > bar.closeKey[1])) { bar.closeKey = [t.ts, seq]; bar.closeIdx = idx; }
    bar.hiIdx = Math.max(bar.hiIdx, idx);
    bar.loIdx = Math.min(bar.loIdx, idx);
    let lvl = bar.levels.get(idx);
    if (!lvl) { lvl = { bid: 0, ask: 0, unc: 0 }; bar.levels.set(idx, lvl); }
    if (t.side === 'buy') lvl.ask += t.qty;
    else if (t.side === 'sell') lvl.bid += t.qty;
    else lvl.unc += t.qty;
    this.accepted += 1;
    return true;
  }

  snapshot({ imbPct = 150, imbMin = 50, stackN = 3 } = {}) {
    const bars = [];
    let prevDelta: number | null = null;
    let day = 0;
    let prevKey: ReturnType<SessionKey> | null = null;
    let totalVolume = 0;
    let uncVolume = 0;
    for (const [t0, b] of [...this.bars.entries()].sort(([a], [b]) => a - b)) {
      const levels: Level[] = [...b.levels.entries()]
        .sort((x, y) => x[0] - y[0])
        .map(([idx, v]) => ({ idx, price: r9(idx * this.tickSize), bid: r9(v.bid), ask: r9(v.ask), unc: r9(v.unc) }));
      flagImbalances(levels, imbPct, imbMin, stackN);
      let bid = 0; let ask = 0; let unc = 0;
      for (const l of levels) { bid += l.bid; ask += l.ask; unc += l.unc; }
      const delta = r9(ask - bid);
      const volume = r9(bid + ask + unc);
      const key = this.sessionKey(t0);
      if (key !== prevKey) { day = 0; prevKey = key; }
      day = r9(day + delta);
      totalVolume += volume;
      uncVolume += unc;
      bars.push({
        t0, levels,
        openIdx: b.openIdx, closeIdx: b.closeIdx, hiIdx: b.hiIdx, loIdx: b.loIdx,
        open: r9(b.openIdx * this.tickSize), close: r9(b.closeIdx * this.tickSize),
        high: r9(b.hiIdx * this.tickSize), low: r9(b.loIdx * this.tickSize),
        bid: r9(bid), ask: r9(ask), unclassified: r9(unc),
        volume, delta,
        deltaChg: prevDelta === null ? null : r9(delta - prevDelta),
        dltaDay: day,
      });
      prevDelta = delta;
    }
    return {
      bars,
      params: { imbPct, imbMin, stackN, tickSize: this.tickSize, tfMs: this.tfMs },
      quality: {
        accepted: this.accepted,
        rejected: { ...this.rejected },
        offTick: this.offTick,
        totalVolume: r9(totalVolume),
        unclassifiedVolume: r9(uncVolume),
        unclassifiedRatio: totalVolume > 0 ? uncVolume / totalVolume : 0,
      },
    };
  }
}

// Profil agrégé d'un ensemble de bougies. Le POC en volume et le niveau de Delta extrême
// sont deux informations distinctes et peuvent désigner deux prix différents.
export function profileOf(bars: readonly { levels: readonly Level[] }[]) {
  const m = new Map<number, Level>();
  for (const b of bars) {
    for (const l of b.levels) {
      let a = m.get(l.idx);
      if (!a) { a = { idx: l.idx, price: l.price, bid: 0, ask: 0, unc: 0 }; m.set(l.idx, a); }
      a.bid += l.bid; a.ask += l.ask; a.unc += l.unc;
    }
  }
  const levels = [...m.values()].sort((a, b) => a.idx - b.idx).map((a) => ({
    idx: a.idx, price: a.price, bid: r9(a.bid), ask: r9(a.ask), unc: r9(a.unc),
    volume: r9(a.bid + a.ask + a.unc), delta: r9(a.ask - a.bid),
  }));
  let pocVolume: (typeof levels)[number] | null = null;
  let pocDelta: (typeof levels)[number] | null = null;
  let totalDelta = 0;
  for (const l of levels) {
    if (!pocVolume || l.volume > pocVolume.volume) pocVolume = l;
    if (!pocDelta || Math.abs(l.delta) > Math.abs(pocDelta.delta)) pocDelta = l;
    totalDelta += l.delta;
  }
  return { levels, pocVolume, pocDelta, totalDelta: r9(totalDelta) };
}
