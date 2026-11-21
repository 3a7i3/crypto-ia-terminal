// MarketDerivativesPositioning 1.0.0 — read-only projection of the local positioning store.
// Values are exact decimal strings as published; the view never recomputes them.
export type Avail = { status: "AVAILABLE" | "NOT_AVAILABLE"; reason: string | null };
export type Measure = { status: "AVAILABLE"; value: string; unit?: string; contract_size_base?: string | null; interval_s?: number; interval_attested_by?: string; next_funding_utc?: string | null; qualification?: string; venue?: string; native_symbol?: string; qualification_ref?: string } | { status: "NOT_AVAILABLE"; reason: string };
export type Observation = {
  venue: string; native_symbol: string; contract_type: string; quote_currency: string; base_currency: string | null;
  source_time_utc: string | null; received_at_utc: string; effective_time_utc: string; time_basis: "SOURCE" | "RECEIPT";
  receipt_latency_ms: number | null; lateness: "ON_TIME" | "LATE" | "UNDETERMINED";
  provenance: { source: string; payload_sha256: string | null; mapping_id: string | null; mapping_sha256: string | null; collector_run_id: string | null };
  measures: Record<"mark_price" | "index_price" | "spot_reference" | "open_interest" | "funding_rate", Measure>;
  unavailable_fields: { field: string; reason: string }[];
  units: { prices: string; open_interest: string | null; contract_size_base: string | null; funding_interval_s: number | null; funding_rate: string | null };
  freshness: { as_of_utc: string; age_ms: number; status: "FRESH" | "STALE" | "FUTURE_OR_INCONSISTENT_CLOCK"; max_age_ms: number };
  derived: {
    premium_to_index: Avail & { bps: string | null; definition: string };
    basis_vs_spot: Avail & { bps: string | null; against?: { venue: string; native_symbol: string }; definition: string };
    funding: Avail & { rate: string | null; interval_s: number | null; rate_8h_equivalent: string | null; annualized_simple_pct: string | null; next_funding_utc: string | null };
    open_interest_notional: Avail & { value: string | null; unit: string | null; notional_quote: string | null };
  };
};
export type OiWindow = Avail & { window_s: number; unit: string | null; contract_size_base: string | null; time_basis: string | null;
  start: { at_utc: string; value: string; gap_ms: number } | null; end: { at_utc: string; value: string; gap_ms: number } | null;
  coverage: { points: number; expected: number; ratio: string } | null; change_pct: string | null };
export type Leg = { leg_id: string; venue: string; native_symbol: string; contract_type: string; cadence_s: number | null; tolerance_ms: number | null;
  latest: { status: "AVAILABLE"; reason: null; as_of_utc: string; observation: Observation } | { status: "NOT_AVAILABLE"; reason: string; as_of_utc: string; observation: null };
  oi_change: OiWindow[] };
export type PairCheck = { status: "AVAILABLE" | "NOT_AVAILABLE"; reason: string | null; units?: string[]; intervals_s?: number[]; contract_sizes_base?: string[] };
export type Pair = { a: string; b: string; open_interest: PairCheck; funding: PairCheck };
export type Series = { leg_id: string; status: "AVAILABLE" | "NOT_AVAILABLE"; reason: string | null; price_unit: string | null; oi_unit: string | null;
  contract_size_base: string | null; time_basis: string | null; cadence_s: number | null; coverage: string | null; points: { t: string; price: string; oi: string }[] };
export type Positioning = {
  product: "MarketDerivativesPositioning"; schema_version: "1.0.0"; authority: "OBSERVATIONAL_TELEMETRY"; execution_authority: false;
  evidence_kind: "OBSERVATION" | "SYNTHETIC"; generated_at_utc: string; policy: Record<string, unknown>;
  legs: Leg[]; pairs: Pair[];
  chart: { window_s: number; start_utc: string; end_utc: string; reference_leg_id: string | null; series: Series[]; note: string };
};

const DECIMAL = /^-?\d+(\.\d+)?$/;
const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const dec = (v: unknown) => typeof v === "string" && DECIMAL.test(v);
const decOrNull = (v: unknown) => v === null || dec(v);
const avail = (v: unknown) => isObj(v) && (v.status === "AVAILABLE" ? v.reason === null : v.status === "NOT_AVAILABLE" && typeof v.reason === "string");

/** Structural admission; any score, authority or non-decimal value refuses the whole publication. */
export function validatePositioning(doc: unknown): doc is Positioning {
  if (!isObj(doc)) return false;
  if (doc.product !== "MarketDerivativesPositioning" || doc.schema_version !== "1.0.0" || doc.authority !== "OBSERVATIONAL_TELEMETRY") return false;
  if (doc.execution_authority !== false || !["OBSERVATION", "SYNTHETIC"].includes(doc.evidence_kind as string)) return false;
  if ("score" in doc || "signal" in doc || typeof doc.generated_at_utc !== "string") return false;
  if (!Array.isArray(doc.legs) || doc.legs.length < 1 || doc.legs.length > 20 || !Array.isArray(doc.pairs) || !isObj(doc.chart)) return false;
  for (const leg of doc.legs as unknown[]) {
    if (!isObj(leg) || typeof leg.leg_id !== "string" || !isObj(leg.latest) || !Array.isArray(leg.oi_change)) return false;
    if (leg.oi_change.length !== 3 || !leg.oi_change.every(w => avail(w) && decOrNull((w as Record<string, unknown>).change_pct))) return false;
    const l = leg.latest;
    if (l.status === "AVAILABLE") {
      const o = l.observation;
      if (!isObj(o) || !isObj(o.measures) || !isObj(o.derived) || !isObj(o.freshness) || !isObj(o.units) || !isObj(o.provenance)) return false;
      for (const m of Object.values(o.measures)) if (!isObj(m) || (m.status === "AVAILABLE" ? !dec(m.value) : typeof m.reason !== "string")) return false;
      const d = o.derived as Record<string, Record<string, unknown>>;
      if (!["premium_to_index", "basis_vs_spot", "funding", "open_interest_notional"].every(k => avail(d[k]))) return false;
      if (!decOrNull(d.premium_to_index.bps) || !decOrNull(d.basis_vs_spot.bps) || !decOrNull(d.funding.rate_8h_equivalent)) return false;
    } else if (l.status !== "NOT_AVAILABLE" || l.observation !== null || typeof l.reason !== "string") return false;
  }
  const chart = doc.chart;
  if (!Array.isArray(chart.series)) return false;
  for (const s of chart.series as unknown[]) {
    if (!avail(s) || !Array.isArray((s as Record<string, unknown>).points)) return false;
    const pts = (s as Record<string, unknown>).points as unknown[];
    if ((s as Record<string, unknown>).status !== "AVAILABLE" && pts.length) return false;
    if (!pts.every(p => isObj(p) && typeof p.t === "string" && dec(p.price) && dec(p.oi))) return false;
  }
  return true;
}
