// SYNTHETIC — FIXTURE DE TEST UNIQUEMENT. Ces transactions ne proviennent d'aucune source
// réelle et ne sont jamais servies par le build. Elles servent à vérifier les espacements
// et les alignements du graphique Footprint sur 20 bougies M1 (tests et banc visuel local).
import { FOOTPRINT_REPLAY_SCHEMA, type FootprintReplay } from "../lib/footprintReplay";

export const SYNTHETIC_T0 = Date.UTC(2026, 0, 6, 9, 0, 0);
export function syntheticTwentyBars(): FootprintReplay {
  const trades: FootprintReplay["trades"] = [];
  let seed = 7;
  const rnd = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
  let price = 60000;
  for (let bar = 0; bar < 20; bar += 1) {
    const t0 = SYNTHETIC_T0 + bar * 60_000;
    for (let k = 0; k < 24; k += 1) {
      price = Math.round((price + (rnd() - 0.48) * 4) * 10) / 10;
      const side = rnd() < 0.5 ? "buy" as const : "sell" as const;
      trades.push({ ts: t0 + 1_000 + k * 2_000, price, qty: Math.round(1 + rnd() * (k % 7 === 0 ? 900 : 120)), side });
    }
  }
  return {
    schema: FOOTPRINT_REPLAY_SCHEMA,
    provenance: {
      venue: "MEXC", market_type: "perpetual", symbol: "BTC_USDT",
      source: "SYNTHETIC — FIXTURE DE TEST (aucune source réelle)", collected_at_utc: "2026-01-06T09:30:00Z",
      coverage_from_utc: "2026-01-06T09:00:00Z", coverage_to_utc: "2026-01-06T09:20:00Z",
      qty_unit: "contracts", side_semantics: "aggressor", gaps: [],
    },
    tick_size: 0.1,
    trades,
  };
}
