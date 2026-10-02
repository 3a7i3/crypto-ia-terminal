import { describe, expect, it } from "vitest";
import { validateMarketMicrostructureSnapshot } from "../lib/marketMicrostructureValidation";
import { microstructureFixture } from "./marketMicrostructureFixtures";

describe("U3b strict transport contract", () => {
  it("admits the complete observational shape", () => expect(validateMarketMicrostructureSnapshot(microstructureFixture())).toBe(true));
  it.each([
    (d: any) => { d.entry = 1; },
    (d: any) => { d.rows[0].risk_pct = 1; },
    (d: any) => { d.coverage.observed = 0; },
    (d: any) => { d.rows[1].symbol = d.rows[0].symbol; },
    (d: any) => { d.rows[0].price = true; },
    (d: any) => { d.rows[0].price = Infinity; },
    (d: any) => { d.rows[0].notable = false; },
    (d: any) => { d.rows[0].state = "buy_now"; },
    (d: any) => { d.rows[0].total_flow_usd = 0; },
    (d: any) => { d.rows[0].sell_pressure_pct = 100; },
    (d: any) => { d.rows[0].fragility = 1.1; },
    (d: any) => { d.rows[0].flow_window_ms = true; },
    (d: any) => { d.rows[2].price = 0; },
    (d: any) => { d.rows[1].freshness_classification = "FRESH"; },
    (d: any) => { d.source_age_s = 0; },
    (d: any) => { d.rows[0].observation_age_s = 0; },
    (d: any) => { d.source_updated_at_utc = "2026-02-30T20:00:00.000Z"; },
    (d: any) => { d.read_at_utc = "2026-09-14T19:00:00.000Z"; },
    (d: any) => { d.source_artifact_sha256 = "bad"; },
  ])("rejects corruption without coercion", (mutate) => {
    const doc = microstructureFixture(); mutate(doc);
    expect(validateMarketMicrostructureSnapshot(doc)).toBe(false);
  });
});
