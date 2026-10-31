export interface VenueInstrument { base_asset_id: string; quote_asset_id: string; market_kind: string; settlement_asset_id: string; contract_identity: string }
export interface VenueSource { endpoint_id: string; payload_sha256: string | null; mapping_id: string; mapping_sha256: string; identity_evidence: string; native_sequence: string | null; timestamp_note: string }
export interface VenueRow { venue: string; native_symbol: string; bid: string | null; ask: string | null; bid_size_base: string | null; ask_size_base: string | null; observed_at_utc: string | null; received_at_utc: string | null; observer_clock_id: string | null; timestamp_kind: string; book_state: string; status: "AVAILABLE" | "NOT_AVAILABLE"; reason: string | null; mid: string | null; spread_bps: string | null; event_age_ms: string | null; source: VenueSource }
export interface VenuePair { reference_venue: string; other_venue: string; status: "AVAILABLE" | "NOT_AVAILABLE"; reason: string | null; event_skew_ms: string | null; mid_basis_bps: string | null; buy_reference_sell_other_gross_bps: string | null; buy_other_sell_reference_gross_bps: string | null; buy_reference_sell_other_top_size_base: string | null; buy_other_sell_reference_top_size_base: string | null }
export interface VenueGroup { instrument_id: string; instrument: VenueInstrument; default_reference: string; rows: VenueRow[]; comparisons: VenuePair[] }
export interface VenuePublication { schema_version: "1.0.0"; product: "MarketVenueComparison"; authority: "OBSERVATIONAL_TELEMETRY"; evidence_kind: "OBSERVATION" | "SYNTHETIC"; generated_at_utc: string; valid_until_utc: string | null; execution_authority: false; costs_funding_fx_included: false; quality_policy: { max_age_ms: number; max_skew_ms: number }; source_counts: { expected: number; supplied: number; available: number }; groups: VenueGroup[]; publication_age_ms: number; freshness_classification: "FRESH" | "STALE" | "UNRESOLVED" }
const TOP = ["schema_version", "product", "authority", "evidence_kind", "generated_at_utc", "valid_until_utc", "execution_authority", "costs_funding_fx_included", "quality_policy", "source_counts", "groups", "publication_age_ms", "freshness_classification"];
const ROW = ["venue", "native_symbol", "bid", "ask", "bid_size_base", "ask_size_base", "observed_at_utc", "received_at_utc", "observer_clock_id", "timestamp_kind", "book_state", "status", "reason", "mid", "spread_bps", "event_age_ms", "source"];
const SOURCE = ["endpoint_id", "payload_sha256", "mapping_id", "mapping_sha256", "identity_evidence", "native_sequence", "timestamp_note"];
const INSTRUMENT = ["base_asset_id", "quote_asset_id", "market_kind", "settlement_asset_id", "contract_identity"];
const NUMBERS = ["event_skew_ms", "mid_basis_bps", "buy_reference_sell_other_gross_bps", "buy_other_sell_reference_gross_bps", "buy_reference_sell_other_top_size_base", "buy_other_sell_reference_top_size_base"];
const PAIR = ["reference_venue", "other_venue", "status", "reason", ...NUMBERS];
const ENDPOINTS: Record<string, string> = { mexc: "spot.v3.depth", bybit: "v5.market.orderbook", okx: "v5.market.books", kraken: "spot.rest.Depth", bitfinex: "v2.book.P0", kucoin: "spot.v1.market.orderbook.level1", coinbase_exchange: "exchange.products.book.level2", hyperliquid: "info.l2Book" };
type Obj = Record<string, unknown>;
const object = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const own = (v: Obj, k: string) => Object.prototype.hasOwnProperty.call(v, k);
const keys = (v: unknown, names: string[]): v is Obj => object(v) && Object.keys(v).length === names.length && names.every(k => own(v, k));
const text = (v: unknown): v is string => typeof v === "string" && /^[A-Za-z0-9@.:/_=-]{1,120}$/.test(v);
const integer = (v: unknown): v is number => typeof v === "number" && Number.isSafeInteger(v) && v >= 0;
const stamp = (v: unknown): boolean => typeof v === "string" && v.length <= 40 && v.endsWith("Z") && Number.isFinite(Date.parse(v));
const decimal = (v: unknown, signed = false): boolean => typeof v === "string" && v.length <= 90 && (signed ? /^-?\d+(?:\.\d+)?$/ : /^\d+(?:\.\d+)?$/).test(v);
const positive = (v: unknown): boolean => decimal(v) && !/^0+(?:\.0+)?$/.test(String(v));
const compare = (a: string, b: string): number => {
  const [ai, af = ""] = a.split("."), [bi, bf = ""] = b.split(".");
  const x = ai.replace(/^0+/, "") || "0", y = bi.replace(/^0+/, "") || "0";
  if (x.length !== y.length) return x.length < y.length ? -1 : 1;
  if (x !== y) return x < y ? -1 : 1;
  const n = Math.max(af.length, bf.length), l = af.padEnd(n, "0"), r = bf.padEnd(n, "0");
  return l === r ? 0 : l < r ? -1 : 1;
};
const nullable = (v: unknown, check: (x: unknown) => boolean): boolean => v === null || check(v);
const hash = (v: unknown): boolean => typeof v === "string" && /^[a-f0-9]{64}$/.test(v);
const state = (r: Obj): boolean => r.status === "AVAILABLE" ? r.reason === null : r.status === "NOT_AVAILABLE" && typeof r.reason === "string" && /^[A-Z][A-Z0-9_]{1,79}$/.test(r.reason);
export function validateVenuePublication(v: unknown): v is VenuePublication {
  if (!keys(v, TOP) || v.schema_version !== "1.0.0" || v.product !== "MarketVenueComparison" || v.authority !== "OBSERVATIONAL_TELEMETRY") return false;
  if (!["OBSERVATION", "SYNTHETIC"].includes(String(v.evidence_kind)) || v.execution_authority !== false || v.costs_funding_fx_included !== false) return false;
  if (!stamp(v.generated_at_utc) || !nullable(v.valid_until_utc, stamp) || (v.valid_until_utc !== null && Date.parse(String(v.valid_until_utc)) < Date.parse(String(v.generated_at_utc)))) return false;
  if (!["FRESH", "STALE", "UNRESOLVED"].includes(String(v.freshness_classification)) || typeof v.publication_age_ms !== "number" || !Number.isFinite(v.publication_age_ms) || v.publication_age_ms < 0) return false;
  if ((v.valid_until_utc === null) !== (v.freshness_classification === "UNRESOLVED")) return false;
  if (!keys(v.quality_policy, ["max_age_ms", "max_skew_ms"]) || !Object.values(v.quality_policy).every(integer) || !keys(v.source_counts, ["expected", "supplied", "available"]) || !Object.values(v.source_counts).every(integer)) return false;
  if (!Array.isArray(v.groups) || !v.groups.length || v.groups.length > 1000) return false;
  let total = 0, supplied = 0, available = 0, pairCount = 0;
  const ids = new Set<string>();
  for (const group of v.groups) {
    if (!keys(group, ["instrument_id", "instrument", "default_reference", "rows", "comparisons"]) || typeof group.instrument_id !== "string" || !/^[a-f0-9]{24}$/.test(group.instrument_id) || ids.has(group.instrument_id)) return false;
    ids.add(group.instrument_id);
    if (!keys(group.instrument, INSTRUMENT) || !Object.values(group.instrument).every(x => text(x) && !["UNKNOWN", "UNRESOLVED", "NOT_AVAILABLE"].includes(x.toUpperCase()))) return false;
    if (!["SPOT", "PERPETUAL_LINEAR", "PERPETUAL_INVERSE", "FUTURE_LINEAR", "FUTURE_INVERSE"].includes(String(group.instrument.market_kind)) || (group.instrument.market_kind === "SPOT" && group.instrument.contract_identity !== "SPOT")) return false;
    if (!Array.isArray(group.rows) || !group.rows.length || group.rows.length > 50 || !Array.isArray(group.comparisons)) return false;
    const venues = new Set<string>(), statuses = new Map<string, unknown>(), rowsByVenue = new Map<string, Obj>();
    for (const row of group.rows) {
      if (!keys(row, ROW) || typeof row.venue !== "string" || !own(ENDPOINTS, row.venue) || venues.has(row.venue) || !state(row)) return false;
      venues.add(row.venue); statuses.set(row.venue, row.status); rowsByVenue.set(row.venue, row);
      if (!text(row.native_symbol) || !nullable(row.observer_clock_id, text) || !nullable(row.observed_at_utc, stamp) || !nullable(row.received_at_utc, stamp)) return false;
      if (!["UNRESOLVED", "BOOK_PUBLICATION", "MATCHING_ENGINE"].includes(String(row.timestamp_kind)) || !["UNRESOLVED", "SNAPSHOT", "SYNCHRONIZED"].includes(String(row.book_state))) return false;
      if (!["bid", "ask", "bid_size_base", "ask_size_base", "mid", "spread_bps", "event_age_ms"].every(k => nullable(row[k], decimal))) return false;
      if (!["bid", "ask", "bid_size_base", "ask_size_base", "mid"].every(k => nullable(row[k], positive))) return false;
      if (!keys(row.source, SOURCE) || row.source.endpoint_id !== ENDPOINTS[row.venue] || !hash(row.source.mapping_sha256) || !nullable(row.source.payload_sha256, hash) || !text(row.source.mapping_id) || !text(row.source.timestamp_note)) return false;
      if (!["REQUEST_CONTEXT", "NATIVE_SYMBOL_ECHO"].includes(String(row.source.identity_evidence)) || !nullable(row.source.native_sequence, x => typeof x === "string" && /^\d{1,30}$/.test(x))) return false;
      total++; supplied += row.source.payload_sha256 !== null ? 1 : 0;
      if (row.status === "AVAILABLE") {
        if (["bid", "ask", "mid", "spread_bps", "event_age_ms", "observed_at_utc", "received_at_utc", "observer_clock_id"].some(k => row[k] === null) || row.timestamp_kind === "UNRESOLVED" || row.book_state === "UNRESOLVED" || row.source.payload_sha256 === null) return false;
        if (Date.parse(String(row.observed_at_utc)) > Date.parse(String(row.received_at_utc)) || Date.parse(String(row.received_at_utc)) > Date.parse(String(v.generated_at_utc))) return false;
        if (compare(String(row.ask), String(row.bid)) < 0 || compare(String(row.event_age_ms), String(v.quality_policy.max_age_ms)) > 0) return false;
        available++;
      } else if (row.mid !== null || row.spread_bps !== null) return false;
    }
    if (typeof group.default_reference !== "string" || !venues.has(group.default_reference)) return false;
    const pairs = new Set<string>();
    for (const p of group.comparisons) {
      if (!keys(p, PAIR) || !state(p) || typeof p.reference_venue !== "string" || typeof p.other_venue !== "string" || p.reference_venue === p.other_venue || !venues.has(p.reference_venue) || !venues.has(p.other_venue)) return false;
      const key = p.reference_venue + "|" + p.other_venue;
      if (pairs.has(key) || !NUMBERS.every(k => nullable(p[k], x => decimal(x, k.endsWith("_bps"))))) return false;
      pairs.add(key);
      if (p.status === "AVAILABLE") {
        if (statuses.get(p.reference_venue) !== "AVAILABLE" || statuses.get(p.other_venue) !== "AVAILABLE" || ["event_skew_ms", "mid_basis_bps", "buy_reference_sell_other_gross_bps", "buy_other_sell_reference_gross_bps"].some(k => p[k] === null)) return false;
        const left = rowsByVenue.get(p.reference_venue)!, right = rowsByVenue.get(p.other_venue)!;
        if (left.observer_clock_id !== right.observer_clock_id || left.timestamp_kind !== right.timestamp_kind || compare(String(p.event_skew_ms), String(v.quality_policy.max_skew_ms)) > 0) return false;
      } else if (NUMBERS.filter(k => k !== "event_skew_ms").some(k => p[k] !== null)) return false;
    }
    if (pairs.size !== venues.size * (venues.size - 1)) return false;
    pairCount += pairs.size;
  }
  return (available === 0 ? v.valid_until_utc === null : stamp(v.valid_until_utc)) && total <= 1000 && pairCount <= 10000 && v.source_counts.expected === total && v.source_counts.supplied === supplied && v.source_counts.available === available;
}
