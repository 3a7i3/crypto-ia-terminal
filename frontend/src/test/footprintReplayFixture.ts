// FIXTURE SYNTHÉTIQUE DE TEST : ces transactions ne proviennent d'aucune source réelle.
import { FOOTPRINT_REPLAY_SCHEMA } from "../lib/footprintReplay";

export const T0 = Date.UTC(2026, 0, 5, 10, 0, 0);
const MIN = 60_000;
export function syntheticReplay() {
  return {
    schema: FOOTPRINT_REPLAY_SCHEMA,
    provenance: {
      venue: "MEXC", market_type: "perpetual", symbol: "BTC_USDT",
      source: "FIXTURE SYNTHÉTIQUE DE TEST", collected_at_utc: "2026-01-05T11:00:00Z",
      coverage_from_utc: "2026-01-05T10:00:00Z", coverage_to_utc: "2026-01-05T10:20:00Z",
      qty_unit: "contracts", side_semantics: "aggressor", gaps: [] as { from_utc: string; to_utc: string }[],
    } as Record<string, unknown>,
    tick_size: 0.1,
    trades: [
      { ts: T0 + 1_000, price: 90000.1, qty: 120, side: "buy" },
      { ts: T0 + 2_000, price: 90000.0, qty: 20, side: "sell" },
      { ts: T0 + 3_000, price: 90001.0, qty: 300, side: "buy" },
      { ts: T0 + 6 * MIN, price: 90002.0, qty: 50, side: "sell" },
      { ts: T0 + 6 * MIN + 1, price: 90002.0, qty: 10, side: null },
      { ts: T0 + 11 * MIN, price: 89999.9, qty: 70, side: "sell" },
    ] as Record<string, unknown>[],
  };
}
