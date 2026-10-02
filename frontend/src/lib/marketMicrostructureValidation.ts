import type { MarketMicrostructureSnapshot } from "./marketMicrostructureTypes";
const states = ["accumulation", "distribution", "absorption_buy", "absorption_sell", "fragility_up", "fragility_down", "compression", "expansion", "exhaustion_buy", "exhaustion_sell", "vacuum_up", "vacuum_down", "conflict", "quiet"];
const metrics = ["state_confidence", "price", "price_change_bps", "buy_pressure_pct", "sell_pressure_pct", "buy_flow_usd", "sell_flow_usd", "total_flow_usd", "resistance", "fragility"];
const rowKeys = ["symbol", "stream_requested", "availability", "unavailable_reason", "observed_at_utc", "state", ...metrics, "flow_window_ms", "notable", "observation_age_s", "freshness_classification"];
function exact(x: unknown, keys: string[]): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x) && Object.keys(x).length === keys.length && keys.every((key) => Object.prototype.hasOwnProperty.call(x, key));
}
function member(x: unknown, values: string[]): boolean { return typeof x === "string" && values.includes(x); }
function finite(x: unknown): x is number { return typeof x === "number" && Number.isFinite(x); }
function unsigned(x: unknown): x is number { return finite(x) && Number.isSafeInteger(x) && x >= 0; }
function utc(x: unknown): number | null {
  if (typeof x !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(x)) return null;
  const ms = Date.parse(x);
  return Number.isFinite(ms) && new Date(ms).toISOString() === x ? ms / 1000 : null;
}
function close(a: number, b: number): boolean { return Math.abs(a - b) <= Math.max(1e-6, Math.abs(b) * 1e-12); }

export function validateMarketMicrostructureSnapshot(x: unknown): x is MarketMicrostructureSnapshot {
  if (!exact(x, ["schema_version", "product", "domain", "authority", "mode", "generated_at_utc", "source_updated_at_utc", "source_artifact_sha256", "exchange", "unit_contract_source", "unit_contract_degraded", "pressure_field_count", "coverage", "rows", "read_at_utc", "source_age_s", "freshness_classification"])) return false;
  if (x.schema_version !== "1.0.0" || x.product !== "MarketMicrostructureSnapshot" || x.domain !== "market_microstructure" || x.authority !== "OBSERVATIONAL_TELEMETRY" || x.mode !== "READ_ONLY") return false;
  const source = utc(x.source_updated_at_utc), generated = utc(x.generated_at_utc), read = utc(x.read_at_utc);
  if (source === null || generated === null || read === null || source < 0 || source > generated || generated > read) return false;
  if (!finite(x.source_age_s) || !close(x.source_age_s, read - source) || x.freshness_classification !== (x.source_age_s > 15 ? "STALE" : "FRESH")) return false;
  if (typeof x.source_artifact_sha256 !== "string" || !/^[0-9a-f]{64}$/.test(x.source_artifact_sha256) || !member(x.exchange, ["mexc", "binance"])) return false;
  if (!member(x.unit_contract_source, ["api", "fallback", "mixed", "unknown"]) || (x.unit_contract_degraded !== null && typeof x.unit_contract_degraded !== "boolean")) return false;
  if (x.pressure_field_count !== null && !unsigned(x.pressure_field_count)) return false;
  const c = x.coverage;
  if (!exact(c, ["requested", "streamable", "observed", "unavailable"]) || !Object.values(c).every(unsigned) || !unsigned(c.requested) || !unsigned(c.observed) || !unsigned(c.unavailable) || !Array.isArray(x.rows) || x.rows.length > 100 || c.requested !== x.rows.length || c.observed + c.unavailable !== c.requested) return false;
  const symbols = new Set<string>();
  let observed = 0, streamable = 0;
  for (const row of x.rows) {
    if (!exact(row, rowKeys) || typeof row.symbol !== "string" || !/^[A-Z0-9][A-Z0-9_/-]{0,63}$/.test(row.symbol) || symbols.has(row.symbol) || typeof row.stream_requested !== "boolean") return false;
    symbols.add(row.symbol); streamable += Number(row.stream_requested);
    if (row.availability === "UNAVAILABLE") {
      if (!member(row.unavailable_reason, ["SOURCE_UNAVAILABLE", "NO_OBSERVATION"]) || rowKeys.filter((key) => !["symbol", "stream_requested", "availability", "unavailable_reason", "freshness_classification"].includes(key)).some((key) => row[key] !== null) || row.freshness_classification !== "NOT_AVAILABLE") return false;
    } else if (row.availability === "OBSERVED") {
      observed += 1;
      if (!row.stream_requested || row.unavailable_reason !== null || (row.state !== null && !member(row.state, states))) return false;
      const stamp = utc(row.observed_at_utc);
      if (row.observed_at_utc !== null && (stamp === null || stamp < 0 || stamp > source)) return false;
      if (row.flow_window_ms !== null && !unsigned(row.flow_window_ms)) return false;
      for (const key of metrics) {
        const value = row[key];
        if (value === null) continue;
        if (!finite(value) || (key !== "price_change_bps" && value < 0) || (["buy_pressure_pct", "sell_pressure_pct"].includes(key) && value > 100) || (["state_confidence", "fragility"].includes(key) && value > 1)) return false;
      }
      const buy = row.buy_pressure_pct, sell = row.sell_pressure_pct;
      if ((buy === null) !== (sell === null) || (finite(buy) && finite(sell) && Math.abs(buy + sell - 100) > 1e-8)) return false;
      const b = row.buy_flow_usd, s = row.sell_flow_usd, total = row.total_flow_usd;
      if (b === null || s === null) { if (total !== null) return false; }
      else if (!finite(b) || !finite(s) || !finite(total) || Math.abs(total - (b + s)) > Math.max(1e-8, Math.abs(b + s) * 1e-12)) return false;
      const expectedNotable = row.state === null || row.state_confidence === null ? null : row.state !== "quiet" && finite(row.state_confidence) && row.state_confidence >= 0.6;
      if (row.notable !== expectedNotable) return false;
      if (stamp === null) { if (row.observation_age_s !== null || row.freshness_classification !== "UNKNOWN") return false; }
      else {
        if (!finite(row.observation_age_s) || !close(row.observation_age_s, read - stamp)) return false;
        if (row.freshness_classification !== (row.observation_age_s > 15 || read - source > 15 ? "STALE" : "FRESH")) return false;
      }
    } else return false;
  }
  return observed === c.observed && streamable === c.streamable;
}
