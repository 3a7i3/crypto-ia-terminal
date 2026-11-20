// MarketDerivativesStress v1.0.0 — closed presentation contract. Values are published
// decimal strings; nothing is recomputed here. A missing value is null, never zero.
export type Status = "AVAILABLE" | "NOT_AVAILABLE";
export type Sign = "UP" | "DOWN" | "FLAT";
export interface StressInstrument { base_asset_id: string; quote_asset_id: string; market_kind: string; settlement_asset_id: string; contract_identity: string }
interface Block { status: Status; reason: string | null }
export interface Premium extends Block { bps: string | null }
export interface Basis extends Block { bps: string | null; annualized_pct: string | null; against_venue: string | null }
export interface Funding extends Block { rate: string | null; interval_s: number | null; next_funding_utc: string | null; rate_8h_equivalent: string | null; annualized_simple_pct: string | null }
export interface OpenInterest extends Block { value: string | null; unit: "BASE" | "QUOTE" | "CONTRACTS" | null; notional_quote: string | null }
export interface StressWindow extends Block { window_s: number; sample_gap_ms: number | null; price_change_bps: string | null; price_sign: Sign | null; oi_change_pct: string | null; oi_sign: Sign | null }
export interface ScanRow { period_s: number; radius_ms: number; expected_share: string; boundary_events: number; boundary_count_share: string; boundary_count_lift: string; boundary_volume_share: string; boundary_volume_lift: string; placebo_events: number; placebo_count_share: string; placebo_count_lift: string; placebo_volume_share: string; placebo_volume_lift: string }
export interface Timing extends Block { events: number | null; volume_base: string | null; histogram: { period_s: number; bin_ms: number; counts: number[] } | null; scan: ScanRow[] | null }
export interface StressLeg {
  venue: string; native_symbol: string; instrument_id: string; instrument: StressInstrument; status: Status; reason: string | null;
  observed_at_utc: string | null; received_at_utc: string | null; observer_clock_id: string | null; timestamp_kind: string; event_age_ms: string | null;
  price_kind: string | null; price: string | null; index_price: string | null;
  premium_to_index: Premium; basis_vs_spot: Basis; funding: Funding; open_interest: OpenInterest; windows: StressWindow[]; timing: Timing;
  source: { mapping_id: string; mapping_sha256: string; payload_sha256: string | null; tape_sha256: string | null };
}
export interface StressPair { instrument_id: string; reference_venue: string; other_venue: string; status: Status; reason: string | null; event_skew_ms: string | null; price_gap_bps: string | null; funding_8h_difference: string | null }
export interface OpenInterestTotal extends Block { notional_quote: string | null; coverage: { expected: number; available: number; missing: string[] } }
export interface Underlying { underlying_id: string; base_asset_id: string; quote_asset_id: string; legs: StressLeg[]; pairs: StressPair[]; open_interest_total: OpenInterestTotal }
export interface StressPublication {
  schema_version: "1.0.0"; product: "MarketDerivativesStress"; authority: "OBSERVATIONAL_TELEMETRY"; evidence_kind: "OBSERVATION" | "SYNTHETIC";
  generated_at_utc: string; valid_until_utc: string | null; execution_authority: false; costs_funding_fx_included: false;
  quality_policy: { max_age_ms: number; max_skew_ms: number; history_tolerance_ms: number };
  parameters: { windows_s: number[]; timing_scan: { period_s: number; radius_ms: number }[]; timing_min_events: number; histogram: { period_s: number; bin_ms: number }; funding_reference_interval_s: number; annualization: "SIMPLE_LINEAR_365D" };
  source_counts: { expected: number; supplied: number; available: number };
  underlyings: Underlying[];
  publication_age_ms: number; freshness_classification: "FRESH" | "STALE" | "UNRESOLVED";
}

type Obj = Record<string, unknown>;
const object = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const own = (v: Obj, k: string) => Object.prototype.hasOwnProperty.call(v, k);
const keys = (v: unknown, names: string[]): v is Obj => object(v) && Object.keys(v).length === names.length && names.every(k => own(v, k));
const text = (v: unknown): v is string => typeof v === "string" && /^[A-Za-z0-9@.:/_=-]{1,120}$/.test(v);
const code = (v: unknown): boolean => typeof v === "string" && /^[A-Z][A-Z0-9_]{1,79}$/.test(v);
const integer = (v: unknown, low = 0): v is number => typeof v === "number" && Number.isSafeInteger(v) && v >= low;
const stamp = (v: unknown): boolean => typeof v === "string" && v.length <= 40 && v.endsWith("Z") && Number.isFinite(Date.parse(v));
const decimal = (v: unknown, signed = false): v is string => typeof v === "string" && v.length <= 90 && (signed ? /^-?\d+(?:\.\d+)?$/ : /^\d+(?:\.\d+)?$/).test(v);
const signed = (v: unknown) => decimal(v, true);
const positive = (v: unknown) => decimal(v) && !/^0+(?:\.0+)?$/.test(String(v));
const nullable = (v: unknown, check: (x: unknown) => boolean) => v === null || check(v);
const hash = (v: unknown) => typeof v === "string" && /^[a-f0-9]{64}$/.test(v);
const venueId = (v: unknown) => typeof v === "string" && /^[a-z][a-z0-9_]{1,30}$/.test(v);
const sign = (v: unknown) => v === "UP" || v === "DOWN" || v === "FLAT";
const KINDS = ["SPOT", "PERPETUAL_LINEAR", "PERPETUAL_INVERSE", "FUTURE_LINEAR", "FUTURE_INVERSE"];
const DERIVATIVES = KINDS.slice(1);
const INSTRUMENT = ["base_asset_id", "quote_asset_id", "market_kind", "settlement_asset_id", "contract_identity"];
const WINDOWS_S = [3600, 14400, 86400];
const SCAN: [number, number][] = [[60, 1000], [300, 1000], [900, 500], [900, 1000], [900, 2000], [900, 5000], [3600, 1000]];
const SCAN_COUNTS = ["boundary_events", "placebo_events"];
const SCAN_SHARES = ["boundary_count_share", "boundary_volume_share", "placebo_count_share", "placebo_volume_share"];
const SCAN_LIFTS = ["boundary_count_lift", "boundary_volume_lift", "placebo_count_lift", "placebo_volume_lift"];
const HIST_BINS = 900;

type Spec = Record<string, (v: unknown) => boolean>;
// A block is closed: either AVAILABLE, or NOT_AVAILABLE with a typed reason and every value null.
function block(b: unknown, spec: Spec, keep: string[] = []): b is Obj {
  if (!keys(b, ["status", "reason", ...Object.keys(spec)])) return false;
  if (!Object.entries(spec).every(([k, check]) => nullable(b[k], check))) return false;
  if (b.status === "AVAILABLE") return b.reason === null || code(b.reason);
  return b.status === "NOT_AVAILABLE" && code(b.reason) && Object.keys(spec).every(k => keep.includes(k) || b[k] === null);
}
const PREMIUM: Spec = { bps: signed };
const BASIS: Spec = { bps: signed, annualized_pct: signed, against_venue: venueId };
const FUNDING: Spec = { rate: signed, interval_s: v => integer(v, 60) && (v as number) <= 86400, next_funding_utc: stamp, rate_8h_equivalent: signed, annualized_simple_pct: signed };
const OI: Spec = { value: decimal, unit: v => v === "BASE" || v === "QUOTE" || v === "CONTRACTS", notional_quote: decimal };
const WINDOW: Spec = { window_s: integer, sample_gap_ms: integer, price_change_bps: signed, price_sign: sign, oi_change_pct: signed, oi_sign: sign };

function timing(t: unknown): boolean {
  if (!keys(t, ["status", "reason", "events", "volume_base", "histogram", "scan"])) return false;
  if (t.status === "NOT_AVAILABLE") return code(t.reason) && t.events === null && t.volume_base === null && t.histogram === null && t.scan === null;
  if (t.status !== "AVAILABLE" || t.reason !== null || !integer(t.events, 1000) || t.events > 500_000 || !positive(t.volume_base)) return false;
  const h = t.histogram;
  if (!keys(h, ["period_s", "bin_ms", "counts"]) || h.period_s !== 900 || h.bin_ms !== 1000 || !Array.isArray(h.counts) || h.counts.length !== HIST_BINS || !h.counts.every(c => integer(c)) || (h.counts as number[]).reduce((a, b) => a + b, 0) !== t.events) return false;
  if (!Array.isArray(t.scan) || t.scan.length !== SCAN.length) return false;
  return t.scan.every((row, i) => keys(row, ["period_s", "radius_ms", "expected_share", ...SCAN_COUNTS, ...SCAN_SHARES, ...SCAN_LIFTS])
    && row.period_s === SCAN[i][0] && row.radius_ms === SCAN[i][1] && positive(row.expected_share) && Number(row.expected_share) <= 1
    && SCAN_COUNTS.every(k => integer(row[k]) && (row[k] as number) <= (t.events as number))
    && SCAN_SHARES.every(k => decimal(row[k]) && Number(row[k]) <= 1) && SCAN_LIFTS.every(k => decimal(row[k])));
}

function leg(l: unknown, u: Obj, v: Obj, generated: number): l is Obj {
  const names = ["venue", "native_symbol", "instrument_id", "instrument", "status", "reason", "observed_at_utc", "received_at_utc", "observer_clock_id", "timestamp_kind", "event_age_ms", "price_kind", "price", "index_price", "premium_to_index", "basis_vs_spot", "funding", "open_interest", "windows", "timing", "source"];
  if (!keys(l, names) || !keys(l.instrument, INSTRUMENT) || !keys(l.source, ["mapping_id", "mapping_sha256", "payload_sha256", "tape_sha256"])) return false;
  const ins = l.instrument as Obj, src = l.source as Obj;
  if (!Object.values(ins).every(x => text(x) && !["UNKNOWN", "UNRESOLVED", "NOT_AVAILABLE"].includes(x.toUpperCase())) || !KINDS.includes(String(ins.market_kind))) return false;
  if (ins.market_kind === "SPOT" && ins.contract_identity !== "SPOT") return false;
  if (ins.base_asset_id !== u.base_asset_id || ins.quote_asset_id !== u.quote_asset_id) return false;
  if (typeof l.instrument_id !== "string" || !/^[a-f0-9]{24}$/.test(l.instrument_id) || !venueId(l.venue) || !text(l.native_symbol)) return false;
  if (!text(src.mapping_id) || !hash(src.mapping_sha256) || !nullable(src.payload_sha256, hash) || !nullable(src.tape_sha256, hash)) return false;
  if (!["UNRESOLVED", "MATCHING_ENGINE", "BOOK_PUBLICATION", "TICKER_PUBLICATION"].includes(String(l.timestamp_kind)) || !nullable(l.price_kind, x => ["BOOK_MID", "LAST_TRADE", "MARK"].includes(String(x)))) return false;
  if (!nullable(l.observed_at_utc, stamp) || !nullable(l.received_at_utc, stamp) || !nullable(l.observer_clock_id, text) || !nullable(l.event_age_ms, decimal) || !nullable(l.price, positive) || !nullable(l.index_price, positive)) return false;
  if (!block(l.premium_to_index, PREMIUM) || !block(l.basis_vs_spot, BASIS, ["against_venue"]) || !block(l.funding, FUNDING) || !block(l.open_interest, OI)) return false;
  if (!Array.isArray(l.windows) || l.windows.length !== WINDOWS_S.length) return false;
  for (let i = 0; i < WINDOWS_S.length; i++) {
    const w = l.windows[i];
    if (!block(w, WINDOW, ["window_s"]) || w.window_s !== WINDOWS_S[i]) return false;
    if ((w.price_change_bps === null) !== (w.price_sign === null) || (w.oi_change_pct === null) !== (w.oi_sign === null)) return false;
    if (w.status === "AVAILABLE" && w.price_change_bps === null && w.oi_change_pct === null) return false;
  }
  if (!timing(l.timing)) return false;
  const derivative = DERIVATIVES.includes(String(ins.market_kind));
  const st = (name: string) => (l[name] as Obj).status;
  if (!derivative && ["premium_to_index", "basis_vs_spot", "funding", "open_interest"].some(n => st(n) !== "NOT_AVAILABLE")) return false;
  if (!String(ins.market_kind).startsWith("PERPETUAL") && st("funding") !== "NOT_AVAILABLE") return false;
  if (!String(ins.market_kind).startsWith("FUTURE") && (l.basis_vs_spot as Obj).annualized_pct !== null) return false;
  if (l.status === "AVAILABLE") {
    if (l.reason !== null || ["observed_at_utc", "received_at_utc", "observer_clock_id", "event_age_ms", "price_kind"].some(k => l[k] === null) || l.timestamp_kind === "UNRESOLVED") return false;
    if (Date.parse(String(l.observed_at_utc)) > Date.parse(String(l.received_at_utc)) || Date.parse(String(l.received_at_utc)) > generated) return false;
    return Number(l.event_age_ms) <= Number((v.quality_policy as Obj).max_age_ms);
  }
  if (l.status !== "NOT_AVAILABLE" || !code(l.reason) || l.price !== null || l.index_price !== null) return false;
  return ["premium_to_index", "basis_vs_spot", "funding", "open_interest"].every(n => st(n) === "NOT_AVAILABLE") && l.windows.every(w => (w as Obj).status === "NOT_AVAILABLE");
}

export function validateStressPublication(v: unknown): v is StressPublication {
  const top = ["schema_version", "product", "authority", "evidence_kind", "generated_at_utc", "valid_until_utc", "execution_authority", "costs_funding_fx_included", "quality_policy", "parameters", "source_counts", "underlyings", "publication_age_ms", "freshness_classification"];
  if (!keys(v, top) || v.schema_version !== "1.0.0" || v.product !== "MarketDerivativesStress" || v.authority !== "OBSERVATIONAL_TELEMETRY") return false;
  if (!["OBSERVATION", "SYNTHETIC"].includes(String(v.evidence_kind)) || v.execution_authority !== false || v.costs_funding_fx_included !== false) return false;
  if (!stamp(v.generated_at_utc) || !nullable(v.valid_until_utc, stamp)) return false;
  const generated = Date.parse(String(v.generated_at_utc));
  if (v.valid_until_utc !== null && Date.parse(String(v.valid_until_utc)) < generated) return false;
  if (!["FRESH", "STALE", "UNRESOLVED"].includes(String(v.freshness_classification)) || typeof v.publication_age_ms !== "number" || !Number.isFinite(v.publication_age_ms) || v.publication_age_ms < 0) return false;
  if ((v.valid_until_utc === null) !== (v.freshness_classification === "UNRESOLVED")) return false;
  if (!keys(v.quality_policy, ["max_age_ms", "max_skew_ms", "history_tolerance_ms"]) || !Object.values(v.quality_policy).every(x => integer(x))) return false;
  const p = v.parameters;
  if (!keys(p, ["windows_s", "timing_scan", "timing_min_events", "histogram", "funding_reference_interval_s", "annualization"])) return false;
  if (JSON.stringify(p.windows_s) !== JSON.stringify(WINDOWS_S) || !Array.isArray(p.timing_scan) || p.timing_scan.length !== SCAN.length || !p.timing_scan.every((r, i) => keys(r, ["period_s", "radius_ms"]) && r.period_s === SCAN[i][0] && r.radius_ms === SCAN[i][1]) || p.timing_min_events !== 1000 || !keys(p.histogram, ["period_s", "bin_ms"]) || p.histogram.period_s !== 900 || p.histogram.bin_ms !== 1000 || p.funding_reference_interval_s !== 28800 || p.annualization !== "SIMPLE_LINEAR_365D") return false;
  const sc = v.source_counts;
  if (!keys(sc, ["expected", "supplied", "available"]) || !Object.values(sc).every(x => integer(x))) return false;
  if (!Array.isArray(v.underlyings) || !v.underlyings.length || v.underlyings.length > 1000) return false;
  let total = 0, supplied = 0, available = 0;
  const ids = new Set<string>();
  for (const u of v.underlyings) {
    if (!keys(u, ["underlying_id", "base_asset_id", "quote_asset_id", "legs", "pairs", "open_interest_total"]) || typeof u.underlying_id !== "string" || !/^[a-f0-9]{24}$/.test(u.underlying_id) || ids.has(u.underlying_id) || !text(u.base_asset_id) || !text(u.quote_asset_id)) return false;
    ids.add(u.underlying_id);
    if (!Array.isArray(u.legs) || !u.legs.length || u.legs.length > 50 || !Array.isArray(u.pairs)) return false;
    const byKey = new Map<string, Obj>();
    for (const l of u.legs) {
      if (!leg(l, u, v, generated)) return false;
      const key = l.instrument_id + "|" + l.venue;
      if (byKey.has(key)) return false;
      byKey.set(key, l);
      total++; supplied += (l.source as Obj).payload_sha256 !== null ? 1 : 0; available += l.status === "AVAILABLE" ? 1 : 0;
    }
    const seen = new Set<string>();
    for (const q of u.pairs) {
      if (!keys(q, ["instrument_id", "reference_venue", "other_venue", "status", "reason", "event_skew_ms", "price_gap_bps", "funding_8h_difference"])) return false;
      const a = byKey.get(q.instrument_id + "|" + q.reference_venue), b = byKey.get(q.instrument_id + "|" + q.other_venue), k = q.instrument_id + "|" + q.reference_venue + "|" + q.other_venue;
      if (!a || !b || q.reference_venue === q.other_venue || seen.has(k) || !nullable(q.event_skew_ms, decimal) || !nullable(q.price_gap_bps, signed) || !nullable(q.funding_8h_difference, signed)) return false;
      seen.add(k);
      if (q.status === "AVAILABLE") {
        if (q.reason !== null || q.price_gap_bps === null || a.status !== "AVAILABLE" || b.status !== "AVAILABLE" || q.event_skew_ms === null || Number(q.event_skew_ms) > Number((v.quality_policy as Obj).max_skew_ms)) return false;
      } else if (q.status !== "NOT_AVAILABLE" || !code(q.reason) || q.price_gap_bps !== null || q.funding_8h_difference !== null) return false;
    }
    const t = u.open_interest_total;
    if (!keys(t, ["status", "reason", "notional_quote", "coverage"]) || !keys(t.coverage, ["expected", "available", "missing"])) return false;
    const cov = t.coverage as Obj;
    const derivs = u.legs.filter(l => DERIVATIVES.includes(String((l.instrument as Obj).market_kind)));
    const have = derivs.filter(l => (l.open_interest as Obj).notional_quote !== null);
    if (!integer(cov.expected) || !integer(cov.available) || !Array.isArray(cov.missing) || !cov.missing.every(text) || cov.expected !== derivs.length || cov.available !== have.length || cov.missing.length !== derivs.length - have.length) return false;
    if (t.status === "AVAILABLE") { if (t.reason !== null || !derivs.length || have.length !== derivs.length || !decimal(t.notional_quote)) return false; }
    else if (t.status !== "NOT_AVAILABLE" || !code(t.reason) || t.notional_quote !== null) return false;
  }
  return sc.expected === total && sc.supplied === supplied && sc.available === available;
}
