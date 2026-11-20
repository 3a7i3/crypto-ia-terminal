import { describe, it, expect, vi, afterEach } from "vitest";
import { validateBboHistory, fetchBboHistory, BboHistoryError, BBO_HISTORY_LABEL } from "../lib/bboHistoryClient";
import raw from "./fixtures/bboCompositeHistory-synthetic.json";

const served = () => ({ ...structuredClone(raw), serving: { freshness_classification: "HISTORICAL_NOT_LIVE" } }) as any;
const respond = (body: string, status = 200, headers: Record<string, string> = {}) =>
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(body, { status, headers }));
afterEach(() => vi.restoreAllMocks());

describe("BBO composite history contract", () => {
  it("accepts the synthetic publication unchanged", () => {
    const d = served();
    expect(validateBboHistory(d)).toBe(d);
    expect(d.label).toBe(BBO_HISTORY_LABEL);
    expect(d.pairs.map((p: any) => p.pair)).toEqual(["BTC", "ATOM"]);
  });
  const cases: Record<string, (d: any) => void> = {
    serving_missing: d => { delete d.serving; },
    live_claimed: d => { d.serving.freshness_classification = "LIVE"; },
    label: d => { d.label = "Live"; },
    count: d => { d.pairs[0].coverage.composite = 60; },
    category: d => { d.pairs[0].windows[0].by_category.COMPOSITE = 31; },
    candle_bounds: d => { d.pairs[0].windows[0].candle.high = "1"; },
    invented_ohlc: d => { Object.assign(d.pairs[0].windows[1].candle, { open: "1", high: "1", low: "1", close: "1" }); },
    numeric_price: d => { d.pairs[0].windows[0].candle.open = 62024.79; },
    a_order: d => { d.pairs[1].hypotheses.A_ORDER.majority_unchanged_verified = false; },
    sensitivity: d => { d.pairs[1].sensitivity_composite_totals.L2s_G10bps = 79; },
    extra_field: d => { d.pairs[0].score = 1; },
    provenance: d => { d.pairs[0].provenance.archive_sha256 = "x"; },
    order: d => { d.pairs[0].windows.reverse(); },
    duplicate_pair: d => { d.pairs[1].pair = "BTC"; },
  };
  for (const [name, mutate] of Object.entries(cases)) it(`refuses ${name}`, () => {
    const d = served(); mutate(d);
    expect(() => validateBboHistory(d)).toThrow(BboHistoryError);
  });
});

describe("fetchBboHistory", () => {
  it("returns a valid publication through a bounded GET", async () => {
    const spy = respond(JSON.stringify(served()));
    const d = await fetchBboHistory();
    expect(d.pairs[1].coverage.composite).toBe(61);
    expect(spy).toHaveBeenCalledWith("/api/operator/v1/bbo-composite-history", expect.objectContaining({ method: "GET", cache: "no-store" }));
  });
  it("surfaces the typed 503 error code", async () => {
    respond('{"error_code":"BBO_HISTORY_NOT_CONFIGURED"}', 503);
    await expect(fetchBboHistory()).rejects.toMatchObject({ code: "BBO_HISTORY_NOT_CONFIGURED", status: 503 });
  });
  it("refuses malformed, duplicate-key, oversized and invalid bodies", async () => {
    respond("{not json"); await expect(fetchBboHistory()).rejects.toMatchObject({ code: "INVALID_JSON" });
    respond('{"a":1,"a":2}'); await expect(fetchBboHistory()).rejects.toMatchObject({ code: "INVALID_JSON" });
    respond("{}", 200, { "content-length": "200001" }); await expect(fetchBboHistory()).rejects.toMatchObject({ code: "RESPONSE_LIMIT" });
    const d = served(); d.pairs[0].coverage.planned = 61;
    respond(JSON.stringify(d)); await expect(fetchBboHistory()).rejects.toMatchObject({ code: "INVALID_BBO_HISTORY_COVERAGE_SUM" });
  });
  it("reports transport failure without inventing a population", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("offline"));
    await expect(fetchBboHistory()).rejects.toMatchObject({ code: "TRANSPORT_ERROR" });
  });
});
