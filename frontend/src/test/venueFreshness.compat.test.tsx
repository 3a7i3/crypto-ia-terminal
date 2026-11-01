import { readFileSync } from "node:fs";
import path from "node:path";
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { displayElapsed, elapsedVenuePublication, useVenueComparison } from "../lib/venueComparisonClient";
import { validateVenuePublication, type VenuePublication } from "../lib/venueComparison";
const dir = process.env.CROSS_STACK_FIXTURES_DIR;
const suite = dir ? describe : describe.skip;
const fixture = () => JSON.parse(readFileSync(path.join(dir!, "S_market_venues.json"), "utf8")).body as VenuePublication;
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });
describe("Expiry presentation independently of a new fetch", () => {
  const published = { generated_at_utc: "2026-10-31T12:00:00Z", valid_until_utc: "2026-10-31T12:00:05Z", publication_age_ms: 100,
    freshness_classification: "FRESH", groups: [{ price: "123456789.123456789123" }] } as unknown as VenuePublication;
  it("expires between polls and never changes exact prices or nested producer fields", () => {
    expect(elapsedVenuePublication(published, 4000)?.freshness_classification).toBe("FRESH");
    const aged = elapsedVenuePublication(published, 5000)!;
    expect(aged.freshness_classification).toBe("STALE");
    expect(aged.groups).toBe(published.groups);
    expect(published.freshness_classification).toBe("FRESH");
  });
  it("never makes a stale or unresolved publication fresh again", () => {
    expect(elapsedVenuePublication({ ...published, freshness_classification: "STALE" }, 0)?.freshness_classification).toBe("STALE");
    expect(elapsedVenuePublication({ ...published, valid_until_utc: null, freshness_classification: "UNRESOLVED" }, 5000)?.freshness_classification).toBe("UNRESOLVED");
  });
  it.each([-1, NaN, Infinity])("refuses an invalid elapsed clock %s", value => expect(elapsedVenuePublication(published, value)).toBeUndefined());
  it("uses the larger elapsed clock and refuses a backward jump", () => {
    expect(displayElapsed(10, 10000, 20, 15000)).toBe(5000);
    expect(displayElapsed(10, 10000, 20, 9900)).toBe(10);
    expect(displayElapsed(10, 10000, 20, 8000)).toBeUndefined();
    expect(displayElapsed(10, 10000, 9, 10020)).toBeUndefined();
  });
});
suite("Real producer fixture expiry in the React client", () => {
  it("admits the bounded pilot through capture, reader and GET route", () => {
    const body = JSON.parse(readFileSync(path.join(dir!, "T_market_pilot.json"), "utf8")).body;
    expect(validateVenuePublication(body)).toBe(true);
    expect(body.evidence_kind).toBe("SYNTHETIC");
    expect(body.source_counts).toEqual({ expected: 4, supplied: 4, available: 4 });
    expect(body.groups).toHaveLength(2);
    expect(elapsedVenuePublication(body, 6000)?.freshness_classification).toBe("STALE");
  });
  const fakeTimers = () => vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date", "performance"] });
  it("turns stale without a second API response while preserving the original exact metrics", async () => {
    fakeTimers(); const body = fixture();
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => body });
    vi.stubGlobal("fetch", fetch);
    const { result, unmount } = renderHook(() => useVenueComparison());
    await act(async () => { await Promise.resolve(); });
    expect(result.current.status).toBe("success");
    if (result.current.status === "success") expect(result.current.publication.freshness_classification).toBe("FRESH");
    await act(async () => { vi.advanceTimersByTime(6000); });
    expect(fetch).toHaveBeenCalledTimes(1);
    if (result.current.status !== "success") throw Error("expected retained dated publication");
    expect(result.current.publication.freshness_classification).toBe("STALE");
    expect(result.current.publication.groups).toBe(body.groups);
    expect(body.freshness_classification).toBe("FRESH");
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
  it("counts request transit, so an expired response is never rendered as fresh", async () => {
    fakeTimers(); let resolve: (v: unknown) => void = () => {};
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => new Promise(r => { resolve = r; })));
    const { result, unmount } = renderHook(() => useVenueComparison());
    await act(async () => { vi.advanceTimersByTime(6000); resolve({ ok: true, json: async () => fixture() }); });
    if (result.current.status !== "success") throw Error("expected dated publication");
    expect(result.current.publication.freshness_classification).toBe("STALE");
    unmount();
  });
  it("rechecks age on visibility changes without inventing a fresh response", async () => {
    fakeTimers(); vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => fixture() }));
    const { result, unmount } = renderHook(() => useVenueComparison());
    await act(async () => { await Promise.resolve(); });
    await act(async () => { vi.setSystemTime(Date.now() + 6000); document.dispatchEvent(new Event("visibilitychange")); });
    if (result.current.status !== "success") throw Error("expected dated publication");
    expect(result.current.publication.freshness_classification).toBe("STALE");
    unmount();
  });
  it("never rejuvenates a publication after the browser wall clock returns from a forward jump", async () => {
    fakeTimers(); vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => fixture() }));
    const { result, unmount } = renderHook(() => useVenueComparison());
    await act(async () => { await Promise.resolve(); });
    const original = Date.now();
    await act(async () => { vi.setSystemTime(original + 6000); document.dispatchEvent(new Event("visibilitychange")); });
    if (result.current.status !== "success") throw Error("expected expired publication");
    expect(result.current.publication.freshness_classification).toBe("STALE");
    await act(async () => { vi.setSystemTime(original); document.dispatchEvent(new Event("visibilitychange")); });
    if (result.current.status !== "success") throw Error("expected retained publication");
    expect(result.current.publication.freshness_classification).toBe("STALE");
    unmount();
  });
  it("keeps an unqualified display clock unavailable until a new API response", async () => {
    fakeTimers(); vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => fixture() }));
    const { result, unmount } = renderHook(() => useVenueComparison());
    await act(async () => { await Promise.resolve(); });
    const original = Date.now();
    await act(async () => { vi.setSystemTime(original - 6000); document.dispatchEvent(new Event("visibilitychange")); });
    expect(result.current.status).toBe("unavailable");
    await act(async () => { vi.setSystemTime(original); document.dispatchEvent(new Event("visibilitychange")); });
    expect(result.current.status).toBe("unavailable");
    unmount();
  });
  it("does not resurrect old prices when the next fetch is unavailable", async () => {
    fakeTimers(); const fetch = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => fixture() }).mockResolvedValue({ ok: false, status: 503, json: async () => ({ error_code: "MISSING" }) });
    vi.stubGlobal("fetch", fetch);
    const { result, unmount } = renderHook(() => useVenueComparison());
    await act(async () => { await Promise.resolve(); });
    await act(async () => { vi.advanceTimersByTime(20000); await Promise.resolve(); });
    expect(result.current.status).toBe("unavailable");
    await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
    expect(result.current.status).toBe("unavailable");
    unmount();
  });
});
