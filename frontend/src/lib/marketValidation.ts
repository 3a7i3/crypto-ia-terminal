import type { MarketOpportunity, MarketRadarSnapshot } from "./marketTypes";

function isPlainObject(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

function exactKeys(x: Record<string, unknown>, expected: readonly string[]): boolean {
  const actual = Object.keys(x).sort();
  const wanted = [...expected].sort();
  return actual.length === wanted.length && actual.every((key, i) => key === wanted[i]);
}

function isFiniteNumber(x: unknown): x is number {
  return typeof x === "number" && Number.isFinite(x);
}

function isNonNegativeInteger(x: unknown): x is number {
  return Number.isSafeInteger(x) && (x as number) >= 0;
}

const TOP_LEVEL_KEYS = [
  "schema_version",
  "product",
  "domain",
  "authority",
  "mode",
  "generated_at_utc",
  "source_updated_at_utc",
  "window_hours",
  "min_confidence",
  "packets_observed",
  "market_regime",
  "universe_size",
  "actionable_count",
  "watchlist_count",
  "top_opportunities",
  "snapshot_age_s",
  "freshness_classification",
] as const;

const ROW_KEYS = [
  "symbol",
  "avg_confidence",
  "max_confidence",
  "n_signals",
  "dominant_side",
  "dominance_pct",
  "regime",
] as const;

const FORBIDDEN_EXECUTION_KEYS = new Set([
  "entry",
  "entry_price",
  "sl",
  "stop_loss",
  "tp",
  "take_profit",
  "r_multiple",
  "trade_allowed",
  "is_actionable",
  "order",
  "position",
]);

function isMarketOpportunity(x: unknown): x is MarketOpportunity {
  if (!isPlainObject(x)) return false;
  if (!exactKeys(x, ROW_KEYS)) return false;
  for (const key of Object.keys(x)) {
    if (FORBIDDEN_EXECUTION_KEYS.has(key)) return false;
  }
  if (typeof x.symbol !== "string" || !x.symbol.trim()) return false;
  if (!isFiniteNumber(x.avg_confidence)) return false;
  if (!isFiniteNumber(x.max_confidence)) return false;
  if (!isNonNegativeInteger(x.n_signals)) return false;
  if (x.dominant_side !== "LONG" && x.dominant_side !== "SHORT" && x.dominant_side !== "MIXED") return false;
  if (!isFiniteNumber(x.dominance_pct) || x.dominance_pct < 0 || x.dominance_pct > 100) return false;
  if (typeof x.regime !== "string") return false;
  return true;
}


function validCatalogue(doc: Record<string, unknown>): boolean {
  const c = doc.catalogue;
  if (!isPlainObject(c) || !exactKeys(c, ["population", "rows", "qualified_rows", "coverage"])) return false;
  if (c.population !== "ALL_OBSERVED_PACKETS") return false;
  if (!Array.isArray(c.rows) || !c.rows.every(isMarketOpportunity)) return false;
  if (!Array.isArray(c.qualified_rows) || !c.qualified_rows.every(isMarketOpportunity)) return false;
  const rows = c.rows, qualified = c.qualified_rows;
  if (rows.length !== doc.universe_size || qualified.length !== doc.actionable_count) return false;
  const counts = new Map(rows.map((r) => [r.symbol, r.n_signals]));
  if (counts.size !== rows.length || new Set(qualified.map((r) => r.symbol)).size !== qualified.length) return false;
  if (rows.some((r) => r.n_signals <= 0) || qualified.some((r) => r.n_signals <= 0 || !counts.has(r.symbol) || r.n_signals > counts.get(r.symbol)!)) return false;
  const top = doc.top_opportunities as MarketOpportunity[];
  if (!top.every((r, i) => qualified[i] && ROW_KEYS.every((k) => r[k] === qualified[i][k]))) return false;
  if (rows.reduce((n, r) => n + r.n_signals, 0) !== doc.packets_observed) return false;
  const cv = c.coverage;
  const countKeys = ["input_packets", "included_packets", "outside_window_packets", "future_packets", "unresolved_timestamp_packets"] as const;
  if (!isPlainObject(cv) || !exactKeys(cv, ["start_at_utc", "end_at_utc", ...countKeys])) return false;
  if (!countKeys.every((k) => isNonNegativeInteger(cv[k]))) return false;
  if (cv.included_packets !== doc.packets_observed) return false;
  if (cv.input_packets !== countKeys.filter((k) => k !== "input_packets").reduce((sum, k) => sum + (cv[k] as number), 0)) return false;
  const instant = (v: unknown): number => typeof v === "string" && /(Z|[+-]\d{2}:\d{2})$/.test(v) ? Date.parse(v) : NaN;
  const start = instant(cv.start_at_utc), end = instant(cv.end_at_utc), generated = instant(doc.generated_at_utc);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end - start !== (doc.window_hours as number) * 3_600_000 || end !== generated) return false;
  const source = instant(doc.source_updated_at_utc);
  return rows.length === 0 ? doc.source_updated_at_utc === null : Number.isFinite(source) && start <= source && source <= end;
}

export function validateMarketRadarSnapshot(x: unknown): x is MarketRadarSnapshot {
  if (!isPlainObject(x)) return false;
  if (x.schema_version !== "1.0.0" && x.schema_version !== "1.1.0") return false;
  if (!exactKeys(x, x.schema_version === "1.1.0" ? [...TOP_LEVEL_KEYS, "catalogue"] : TOP_LEVEL_KEYS)) return false;
  if (x.product !== "CryptoRadar") return false;
  if (x.domain !== "market") return false;
  if (x.authority !== "OBSERVATIONAL_TELEMETRY") return false;
  if (x.mode !== "OBSERVATION") return false;
  if (typeof x.generated_at_utc !== "string" || !x.generated_at_utc.trim()) return false;
  if (x.source_updated_at_utc !== null && typeof x.source_updated_at_utc !== "string") return false;
  if (!isNonNegativeInteger(x.window_hours) || x.window_hours <= 0) return false;
  if (!isFiniteNumber(x.min_confidence)) return false;
  if (!isNonNegativeInteger(x.packets_observed)) return false;
  if (x.market_regime !== null && typeof x.market_regime !== "string") return false;
  if (!isNonNegativeInteger(x.universe_size)) return false;
  if (!isNonNegativeInteger(x.actionable_count)) return false;
  if (!isNonNegativeInteger(x.watchlist_count)) return false;
  if (!Array.isArray(x.top_opportunities) || !x.top_opportunities.every(isMarketOpportunity)) return false;
  if (x.top_opportunities.length > x.actionable_count || x.actionable_count > x.universe_size) return false;
  if (new Set(x.top_opportunities.map((row) => row.symbol)).size !== x.top_opportunities.length) return false;
  if (!isFiniteNumber(x.snapshot_age_s) || x.snapshot_age_s < 0) return false;
  if (x.freshness_classification !== "FRESH" && x.freshness_classification !== "STALE") return false;
  return x.schema_version === "1.1.0" ? validCatalogue(x) : true;
}
