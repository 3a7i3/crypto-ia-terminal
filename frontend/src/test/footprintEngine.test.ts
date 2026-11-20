import { test } from 'vitest';
import assert from 'node:assert/strict';
import { FootprintBuilder, validateTrade, profileOf, utcSessionKey, INDICATORS, CHANNELS } from '../lib/footprintEngine';

const MIN = 60000;
const BASE = Date.UTC(2026, 0, 5, 10, 0, 0); // 10:00 UTC, jour fixe
const tr = (ts: number, price: number, qty: number, side: unknown) => ({ ts, price, qty, side });
const build = (trades: unknown[], opts: Partial<ConstructorParameters<typeof FootprintBuilder>[0]> = {}) => {
  const b = new FootprintBuilder({ tickSize: 1, tfMs: 5 * MIN, ...opts });
  for (const t of trades) b.push(t);
  return b;
};

test('validateTrade rejette les transactions invalides avec un code précis', () => {
  assert.equal(validateTrade(tr(BASE, 10, 1, 'buy')), null);
  assert.equal(validateTrade(tr(BASE, 10, 1, null)), null);
  assert.equal(validateTrade(null), 'not_object');
  assert.equal(validateTrade(tr(1.5, 10, 1, 'buy')), 'bad_ts');
  assert.equal(validateTrade(tr(BASE, 0, 1, 'buy')), 'bad_price');
  assert.equal(validateTrade(tr(BASE, 10, -1, 'buy')), 'bad_qty');
  assert.equal(validateTrade(tr(BASE, 10, 1, 'long')), 'bad_side');
  assert.equal(validateTrade(tr(BASE, NaN, 1, 'buy')), 'bad_price');
});

test('les rejets sont comptés et ne modifient aucune bougie', () => {
  const b = build([tr(BASE, 10, 1, 'buy'), tr(BASE, -1, 1, 'buy'), tr(BASE, 10, 0, 'sell')]);
  const s = b.snapshot();
  assert.equal(s.quality.accepted, 1);
  assert.deepEqual(s.quality.rejected, { bad_price: 1, bad_qty: 1 });
  assert.equal(s.bars[0].volume, 1);
});

test('achat agressif -> Ask, vente agressive -> Bid, côté inconnu jamais deviné', () => {
  const s = build([tr(BASE, 10, 5, 'buy'), tr(BASE, 10, 3, 'sell'), tr(BASE, 10, 2, null)]).snapshot();
  const l = s.bars[0].levels[0];
  assert.equal(l.ask, 5);
  assert.equal(l.bid, 3);
  assert.equal(l.unc, 2);
  assert.equal(s.bars[0].delta, 2);          // le non classifié n'entre pas dans le Delta
  assert.equal(s.bars[0].volume, 10);        // mais il entre dans le volume
  assert.equal(s.quality.unclassifiedRatio, 0.2);
});

test('les transactions sont rangées par période et par niveau', () => {
  const s = build([tr(BASE, 10, 1, 'buy'), tr(BASE + 4 * MIN, 11, 1, 'buy'), tr(BASE + 5 * MIN, 10, 1, 'sell')]).snapshot();
  assert.equal(s.bars.length, 2);
  assert.deepEqual(s.bars[0].levels.map((l) => l.idx), [10, 11]);
  assert.equal(s.bars[1].t0, BASE + 5 * MIN);
});

test('ouverture et clôture suivent l horodatage, pas l ordre d arrivée', () => {
  const trades = [tr(BASE + 1000, 10, 1, 'buy'), tr(BASE + 2000, 12, 1, 'buy'), tr(BASE + 3000, 11, 1, 'sell')];
  const a = build(trades).snapshot().bars[0];
  const b = build([...trades].reverse()).snapshot().bars[0];
  assert.equal(a.open, 10);
  assert.equal(a.close, 11);
  assert.equal(a.high, 12);
  assert.equal(a.low, 10);
  assert.deepEqual([b.open, b.close, b.high, b.low], [a.open, a.close, a.high, a.low]);
});

test('un prix hors pas de cotation est accepté mais signalé', () => {
  const b = new FootprintBuilder({ tickSize: 0.5, tfMs: 5 * MIN });
  b.push(tr(BASE, 10.5, 1, 'buy'));
  b.push(tr(BASE, 10.7, 1, 'buy'));
  assert.equal(b.snapshot().quality.offTick, 1);
});

test('imbalance diagonale : Ask du niveau p contre Bid du niveau p-1', () => {
  const s = build([
    tr(BASE, 10, 100, 'sell'), tr(BASE, 10, 20, 'buy'),
    tr(BASE, 11, 30, 'sell'), tr(BASE, 11, 400, 'buy'),
  ]).snapshot({ imbPct: 150, imbMin: 50 });
  const [l10, l11] = s.bars[0].levels;
  assert.equal(l11.buyImb, true);    // 400 contre 100 (niveau du dessous)
  assert.equal(l10.sellImb, false);  // 100 contre 400 (niveau du dessus)
  assert.equal(l10.buyImb, false);   // pas de niveau en dessous : aucune comparaison
  assert.equal(l11.sellImb, false);  // pas de niveau au-dessus : aucune comparaison
});

test('la comparaison est diagonale, pas sur la même ligne', () => {
  // Niveau 11 : 30 × 400 sur la même ligne serait un déséquilibre, mais en diagonale (400 contre 350) non.
  const s = build([
    tr(BASE, 10, 350, 'sell'),
    tr(BASE, 11, 30, 'sell'), tr(BASE, 11, 400, 'buy'),
  ]).snapshot({ imbPct: 150, imbMin: 50 });
  assert.equal(s.bars[0].levels[1].buyImb, false);
});

test('IMB MIN écarte les volumes insignifiants, et un côté nul compte comme déséquilibre total', () => {
  const small = build([tr(BASE, 10, 1, 'sell'), tr(BASE, 11, 30, 'buy')]).snapshot({ imbPct: 150, imbMin: 50 });
  assert.equal(small.bars[0].levels[1].buyImb, false);        // 30 < IMB MIN
  const zero = build([tr(BASE, 10, 1, 'buy'), tr(BASE, 11, 80, 'buy')]).snapshot({ imbPct: 150, imbMin: 50 });
  assert.equal(zero.bars[0].levels[1].buyImb, true);          // Bid du dessous = 0
});

test('stacked imbalances : au moins N niveaux consécutifs du même côté', () => {
  const t = [tr(BASE, 10, 10, 'sell')];
  for (const p of [11, 12, 13]) t.push(tr(BASE, p, 200, 'buy'), tr(BASE, p, 10, 'sell'));
  const s = build(t).snapshot({ imbPct: 150, imbMin: 50, stackN: 3 });
  const lv = s.bars[0].levels;
  assert.deepEqual(lv.map((l) => l.buyImb), [false, true, true, true]);
  assert.deepEqual(lv.map((l) => l.stackedBuy), [false, true, true, true]);
  const two = build(t.slice(0, 5)).snapshot({ imbPct: 150, imbMin: 50, stackN: 3 });
  assert.equal(two.bars[0].levels.some((l) => l.stackedBuy), false); // seulement 2 niveaux consécutifs
});

test('reproduit les chiffres de la capture : Delta, DeltaChg, DltaDay, Volume', () => {
  // Bougies 10:00 (cumul 9992), 10:05 (Δ+430), 10:10 (Δ-3197, vol 20009), 10:15 (Δ-778, vol 10284)
  const bar = (k: number, buy: number, sell: number) => [tr(BASE + k * 5 * MIN, 100, buy, 'buy'), tr(BASE + k * 5 * MIN + 1, 100, sell, 'sell')];
  const s = build([...bar(0, 9997, 5), ...bar(1, 1000, 570), ...bar(2, 8406, 11603), ...bar(3, 4753, 5531)]).snapshot();
  const [, b1, c, d] = s.bars;
  assert.equal(b1.delta, 430);
  assert.equal(b1.dltaDay, 10422);
  assert.equal(c.volume, 20009);
  assert.equal(c.delta, -3197);
  assert.equal(c.deltaChg, -3627);
  assert.equal(c.dltaDay, 7225);
  assert.equal(d.delta, -778);
  assert.equal(d.deltaChg, 2419);   // Delta encore négatif, mais DeltaChg positif : la pression vendeuse diminue
  assert.equal(d.dltaDay, 6447);
  assert.equal(d.volume, 10284);
  assert.equal(s.bars[0].deltaChg, null); // pas de bougie précédente
});

test('DltaDay est remis à zéro à chaque changement de session', () => {
  const day2 = BASE + 24 * 3600000;
  const s = build([tr(BASE, 10, 100, 'buy'), tr(day2, 10, 40, 'buy')]).snapshot();
  assert.equal(s.bars[0].dltaDay, 100);
  assert.equal(s.bars[1].dltaDay, 40);
  // Session qui ouvre à 18:00 UTC : 10:00 et 17:59 appartiennent à la même session, 18:00 à la suivante.
  const k = utcSessionKey(18);
  assert.equal(k(Date.UTC(2026, 0, 5, 10)), k(Date.UTC(2026, 0, 5, 17, 59)));
  assert.notEqual(k(Date.UTC(2026, 0, 5, 17, 59)), k(Date.UTC(2026, 0, 5, 18)));
});

test('POC en volume et niveau de Delta extrême peuvent être deux prix différents', () => {
  const s = build([
    tr(BASE, 1, 1500, 'buy'), tr(BASE, 1, 1500, 'sell'),   // volume 3000, delta 0
    tr(BASE, 2, 1000, 'buy'), tr(BASE, 2, 1400, 'sell'),   // volume 2400, delta -400
  ]).snapshot();
  const p = profileOf(s.bars);
  assert.equal(p.pocVolume?.idx, 1);
  assert.equal(p.pocDelta?.idx, 2);
  assert.equal(p.pocDelta?.delta, -400);
  assert.equal(p.totalDelta, -400);
});

test('changer la période reconstruit les bougies à partir des mêmes transactions', () => {
  const trades = [tr(BASE, 10, 1, 'buy'), tr(BASE + 6 * MIN, 10, 1, 'sell'), tr(BASE + 11 * MIN, 10, 1, 'buy')];
  assert.equal(build(trades, { tfMs: 5 * MIN }).snapshot().bars.length, 3);
  assert.equal(build(trades, { tfMs: 15 * MIN }).snapshot().bars.length, 1);
});

test('contrat : paramètres invalides refusés, canaux déconnectés par défaut', () => {
  assert.throws(() => new FootprintBuilder({ tickSize: 0, tfMs: 1000 }));
  assert.throws(() => new FootprintBuilder({ tickSize: 1, tfMs: 1.5 }));
  assert.ok(CHANNELS.every((c) => c.status === 'disconnected'));
  assert.ok(INDICATORS.some((i) => i.status === 'todo'));
});
