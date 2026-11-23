// LOCAL TEST FIXTURES ONLY (Scanner V1). Invented native statuses and times;
// nothing here is runtime evidence. Times are relative to Date.now() at call
// time so the publication is fresh in tests that mock the clock.
import type { ScannerUniverse, UniverseMarket } from "../lib/scannerUniverseClient";

const MARKETS: UniverseMarket[] = ["MEXC_SPOT", "MEXC_PERPETUAL", "KRAKEN_SPOT", "KRAKEN_PERPETUAL"];
const proof = (m: UniverseMarket, base: string, quote: string, at: number) => ({
  exchange: m.startsWith("MEXC") ? "mexc" : "kraken", market_type: m.endsWith("SPOT") ? "SPOT" : "PERPETUAL",
  native_symbol: { MEXC_SPOT: base + quote, MEXC_PERPETUAL: `${base}_${quote}`, KRAKEN_SPOT: (base === "BTC" ? "XBT" : base) + quote, KRAKEN_PERPETUAL: `PF_${base}${quote}` }[m],
  base, quote, native_base: base, native_quote: quote, status: "fixture=tradable",
  contract_type: m.endsWith("SPOT") ? "SPOT" : "LINEAR_PERPETUAL", settlement_asset: m.endsWith("SPOT") ? null : quote,
  settlement_basis: m.endsWith("SPOT") ? "NOT_APPLICABLE_SPOT" : "SOURCE_FIELD_settleCoin", collected_ms: at, exclusion: null,
});

export function universeFixture(pairs: [string, string][], opts: { status?: "VERIFIED" | "VERIFIED_EMPTY" | "UNVERIFIABLE"; now?: number; blocked?: UniverseMarket; ageMs?: number } = {}): ScannerUniverse {
  const now = opts.now ?? Date.now();
  const at = now - (opts.ageMs ?? 60_000);
  const status = opts.status ?? (pairs.length ? "VERIFIED" : "VERIFIED_EMPTY");
  const blocked = status === "UNVERIFIABLE" ? opts.blocked ?? "KRAKEN_PERPETUAL" : null;
  const listed = status === "VERIFIED" ? pairs : [];
  return {
    schema_version: "scanner-universe/1.0.0", product: "ScannerCommonUniverse", status,
    computed_ms: now, served_ms: now, freshness_max_age_ms: 2_100_000, cadence_ms: 900_000,
    blocking_sources: blocked ? [{ market: blocked, reason: "UNAVAILABLE:HTTP_503" }] : [],
    sources: MARKETS.map(m => ({
      market: m, state: m === blocked ? "UNAVAILABLE" : "COMPLETE", catalogue_state: m === blocked ? "UNAVAILABLE" : "COMPLETE",
      reason: m === blocked ? "UNAVAILABLE:HTTP_503" : null, collected_ms: m === blocked ? null : at, age_ms: m === blocked ? null : now - at,
      current: m !== blocked, instruments: m === blocked ? 0 : 100, admissible: m === blocked ? 0 : 90, excluded: {}, raw_sha256: {},
    })),
    pairs: listed.map(([base, quote]) => ({ key: `${base}/${quote}`, base, quote, proofs: Object.fromEntries(MARKETS.map(m => [m, proof(m, base, quote, at)])) as never })),
    pair_count: listed.length,
    exclusions: [{ key: "ETH/USDT", reasons: { MEXC_SPOT: null, MEXC_PERPETUAL: null, KRAKEN_SPOT: null, KRAKEN_PERPETUAL: "ABSENT" }, native_symbols: { MEXC_SPOT: ["ETHUSDT"] } }],
    exclusions_truncated: false,
    reference: blocked ? { universe_sha256: "f".repeat(64), status: "VERIFIED", computed_ms: now - 900_000, keys: ["BTC/USDT"], current: false } : null,
    universe_sha256: "e".repeat(64),
  } as ScannerUniverse;
}
