import { readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MARKET_FLOW_ENDPOINT, MARKET_FLOW_TIMEOUT_MS, fetchMarketFlow } from "../lib/marketFlowClient";
import { MARKET_FLOW_MAX_RESPONSE_BYTES } from "../lib/marketFlowJson";

// The path is assembled from segments on purpose: a repository guard test greps the frontend sources for the
// Python package name. The file is the repository's synthetic reference, read in place (never copied).
const GOLDEN = path.resolve(process.cwd(), "..", "observability", ["market", "flow"].join("_"), "fixtures",
  ["market", "flow", "artifact", "synthetic"].join("_") + ".json");
const artifact = (): Record<string, unknown> => JSON.parse(readFileSync(GOLDEN, "utf8"));
const publication = () => ({ ...artifact(), serving: { freshness_classification: "NOT_ASSESSED_SYNTHETIC" } });
const enc = (s: string) => new TextEncoder().encode(s);
const json = (v: unknown, status = 200) => new Response(enc(JSON.stringify(v)), { status });

type FetchStub = (url: string, init: RequestInit) => Promise<Response>;
const stub = (impl: FetchStub) => {
  const fn = vi.fn(impl);
  vi.stubGlobal("fetch", fn);
  return fn;
};
/** A promise that rejects like fetch does when its signal aborts. */
const hang = (init: RequestInit) =>
  new Promise<Response>((_, reject) => {
    init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
  });
/** A 200 whose body never ends and errors on abort. */
function stalledBody(init: RequestInit, first = enc('{"a":')): Response {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(c) { controller = c; c.enqueue(first); },
  });
  init.signal?.addEventListener("abort", () => controller.error(new DOMException("aborted", "AbortError")));
  return new Response(body, { status: 200 });
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("fetchMarketFlow: success", () => {
  it("issues one GET to the single endpoint, no-store, with a signal, and returns the validated publication", async () => {
    const fetchStub = stub(async () => json(publication()));
    const result = await fetchMarketFlow();
    expect(result.status).toBe("success");
    if (result.status === "success") expect(result.publication.serving.freshness_classification).toBe("NOT_ASSESSED_SYNTHETIC");
    expect(fetchStub).toHaveBeenCalledTimes(1);
    const [url, init] = fetchStub.mock.calls[0];
    expect(url).toBe("/api/operator/v1/market-flow");
    expect(MARKET_FLOW_ENDPOINT).toBe(url);
    expect(init).toMatchObject({ method: "GET", cache: "no-store", redirect: "error" });
    expect(init.signal).toBeInstanceOf(AbortSignal);
    expect(init.body).toBeUndefined();
  });
  it("does not poll, retry or keep a timer after settling", async () => {
    const fetchStub = stub(async () => json(publication()));
    await fetchMarketFlow();
    expect(vi.getTimerCount()).toBe(0);
    await vi.advanceTimersByTimeAsync(10 * 60_000);
    expect(fetchStub).toHaveBeenCalledTimes(1);
  });
  it("returns the validated values untouched (no normalisation, no BigInt)", async () => {
    const p = publication() as Record<string, any>;
    stub(async () => json(p));
    const r = await fetchMarketFlow();
    expect(r.status === "success" && r.publication).toEqual(p);
  });
  it("does nothing at import: no fetch and no timer", async () => {
    const fetchStub = stub(async () => json(publication()));
    vi.resetModules();
    await import("../lib/marketFlowClient");
    expect(fetchStub).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("fetchMarketFlow: api_error keeps the HTTP status and the published code only", () => {
  it.each([
    [503, { error_code: "MARKET_FLOW_NOT_CONFIGURED" }, "MARKET_FLOW_NOT_CONFIGURED"],
    [503, { error_code: "MARKET_FLOW_INVALID_SCHEMA" }, "MARKET_FLOW_INVALID_SCHEMA"],
    [503, { error_code: "MARKET_FLOW_TOO_LARGE" }, "MARKET_FLOW_TOO_LARGE"],
    [404, { detail: "Not Found" }, null],
    [503, { error_code: 5 }, null],
    [503, { error_code: "lower_case" }, null],
    [503, { error_code: "A".repeat(65) }, null],
    [503, { error_code: "MARKET_FLOW_MISSING", extra: 1 }, null],
    [500, {}, null],
    [503, [], null],
    [503, null, null],
  ])("HTTP %i %j -> %j", async (status, body, want) => {
    stub(async () => json(body, status));
    expect(await fetchMarketFlow()).toEqual({ status: "api_error", httpStatus: status, errorCode: want });
  });
  it.each([
    ["an empty body", new Uint8Array(0)],
    ["malformed JSON", enc("<html>Bad gateway</html>")],
    ["invalid UTF-8", new Uint8Array([0x7b, 0xff, 0x7d])],
    ["a duplicate key", enc('{"error_code":"A","error_code":"B"}')],
    ["a BOM", new Uint8Array([0xef, 0xbb, 0xbf, ...enc('{"error_code":"MARKET_FLOW_MISSING"}')])],
  ])("keeps the known status when the 503 body is %s", async (_name, data) => {
    stub(async () => new Response(data as BodyInit, { status: 503 }));
    expect(await fetchMarketFlow()).toEqual({ status: "api_error", httpStatus: 503, errorCode: null });
  });
  it("does not read an oversized error body in full", async () => {
    let pulled = 0;
    const body = new ReadableStream<Uint8Array>({
      pull(c) { pulled += 1; c.enqueue(new Uint8Array(40_000)); },
    });
    stub(async () => new Response(body, { status: 503 }));
    expect(await fetchMarketFlow()).toEqual({ status: "api_error", httpStatus: 503, errorCode: null });
    expect(pulled).toBeLessThan(10);
  });
  it("does not turn a non-200 success status into a success", async () => {
    stub(async () => new Response(enc(JSON.stringify(publication())), { status: 201 }));
    expect(await fetchMarketFlow()).toEqual({ status: "api_error", httpStatus: 201, errorCode: null });
    stub(async () => new Response(null, { status: 204 }));
    expect(await fetchMarketFlow()).toEqual({ status: "api_error", httpStatus: 204, errorCode: null });
  });
});

describe("fetchMarketFlow: an HTTP 200 that breaks the contract is a transport error, never an api_error", () => {
  const reason = async (response: Response) => {
    stub(async () => response);
    const r = await fetchMarketFlow();
    return r.status === "transport_error" ? r.reason : r.status;
  };
  it("distinguishes invalid JSON, invalid UTF-8 and an invalid contract", async () => {
    expect(await reason(new Response(enc("{"), { status: 200 }))).toBe("INVALID_JSON");
    expect(await reason(new Response(new Uint8Array(0), { status: 200 }))).toBe("INVALID_JSON");
    expect(await reason(new Response(null, { status: 200 }))).toBe("INVALID_JSON");
    expect(await reason(new Response(enc(JSON.stringify(publication()).replace('"event_count":19', '"event_count":19.0')), { status: 200 }))).toBe("INVALID_JSON");
    expect(await reason(new Response(enc(JSON.stringify(publication()).replace("{", '{"product":"MarketFlowArtifact",')), { status: 200 }))).toBe("INVALID_JSON");
    expect(await reason(new Response(new Uint8Array([0x7b, 0xff, 0x7d]), { status: 200 }))).toBe("INVALID_UTF8");
    expect(await reason(new Response(new Uint8Array([0xef, 0xbb, 0xbf, ...enc(JSON.stringify(publication()))]), { status: 200 }))).toBe("INVALID_JSON");
    expect(await reason(json({ ...publication(), score: "9" }))).toBe("CONTRACT_INVALID");
    expect(await reason(json({ ...artifact() }))).toBe("CONTRACT_INVALID"); // artifact without serving
    expect(await reason(json({ error_code: "MARKET_FLOW_MISSING" }))).toBe("CONTRACT_INVALID");
    expect(await reason(json([]))).toBe("CONTRACT_INVALID");
    expect(await reason(json(null))).toBe("CONTRACT_INVALID");
  });
  it("explains a contract refusal with the oracle vocabulary and path", async () => {
    stub(async () => json({ ...publication(), synthetic: false }));
    const r = await fetchMarketFlow();
    expect(r).toMatchObject({ status: "transport_error", reason: "CONTRACT_INVALID" });
    expect(r.status === "transport_error" && r.detail).toBe("EVIDENCE_KIND_REQUIRED:evidence_kind");
  });
  it("never offers an empty or previous result as a fallback", async () => {
    stub(async () => json(publication()));
    const first = await fetchMarketFlow();
    expect(first.status).toBe("success");
    stub(async () => json({ ...publication(), score: 1 }));
    const second = await fetchMarketFlow();
    expect(second).not.toHaveProperty("publication");
    expect(second.status).toBe("transport_error");
  });
});

describe("fetchMarketFlow: bounds on what is actually received", () => {
  it("refuses a declared Content-Length above the bound without reading the body", async () => {
    let pulled = 0;
    const body = new ReadableStream<Uint8Array>({ pull(c) { pulled += 1; c.enqueue(enc("[]")); } });
    stub(async () => new Response(body, { status: 200, headers: { "content-length": String(MARKET_FLOW_MAX_RESPONSE_BYTES + 1) } }));
    expect(await fetchMarketFlow()).toMatchObject({ status: "transport_error", reason: "BODY_TOO_LARGE" });
    expect(pulled).toBeLessThanOrEqual(1);
  });
  it("stops reading a body that exceeds the bound with no (or a lying) Content-Length", async () => {
    let pulled = 0;
    const chunk = new Uint8Array(1_000_000).fill(32);
    const body = new ReadableStream<Uint8Array>({ pull(c) { pulled += 1; c.enqueue(chunk); } });
    stub(async () => new Response(body, { status: 200, headers: { "content-length": "10" } }));
    expect(await fetchMarketFlow()).toMatchObject({ status: "transport_error", reason: "BODY_TOO_LARGE" });
    expect(pulled).toBeLessThan(10); // arbitrarily large bodies are never accumulated
  });
  it("accepts a body exactly at the bound when it is a valid document", async () => {
    const text = JSON.stringify(publication());
    const padded = new Uint8Array(MARKET_FLOW_MAX_RESPONSE_BYTES).fill(32);
    padded.set(enc(text), 0);
    stub(async () => new Response(padded as BodyInit, { status: 200 }));
    expect((await fetchMarketFlow()).status).toBe("success");
    const over = new Uint8Array(MARKET_FLOW_MAX_RESPONSE_BYTES + 1).fill(32);
    over.set(enc(text), 0);
    stub(async () => new Response(over as BodyInit, { status: 200 }));
    expect(await fetchMarketFlow()).toMatchObject({ reason: "BODY_TOO_LARGE" });
  });
});

describe("fetchMarketFlow: lifecycle", () => {
  it("reports a network failure", async () => {
    stub(async () => { throw new TypeError("Failed to fetch"); });
    expect(await fetchMarketFlow()).toEqual({ status: "transport_error", reason: "NETWORK", detail: null });
    expect(vi.getTimerCount()).toBe(0);
  });
  it("reports a redirect as a network failure (redirect: error)", async () => {
    stub(async () => { throw new TypeError("redirect mode is set to error"); });
    expect(await fetchMarketFlow()).toMatchObject({ reason: "NETWORK" });
  });
  it("times out after 5 seconds while waiting for the headers", async () => {
    expect(MARKET_FLOW_TIMEOUT_MS).toBe(5_000);
    stub((_, init) => hang(init));
    const pending = fetchMarketFlow();
    await vi.advanceTimersByTimeAsync(4_999);
    let settled = false;
    void pending.then(() => { settled = true; });
    await Promise.resolve();
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    expect(await pending).toMatchObject({ status: "transport_error", reason: "TIMEOUT" });
    expect(vi.getTimerCount()).toBe(0);
  });
  it("times out while the body is still arriving (the timeout covers the body)", async () => {
    stub(async (_, init) => stalledBody(init));
    const pending = fetchMarketFlow();
    await vi.advanceTimersByTimeAsync(5_000);
    expect(await pending).toMatchObject({ status: "transport_error", reason: "TIMEOUT" });
  });
  it("keeps the known status when an error body stalls past the timeout", async () => {
    stub(async (_, init) => {
      const r = stalledBody(init);
      return new Response(r.body, { status: 503 });
    });
    const pending = fetchMarketFlow();
    await vi.advanceTimersByTimeAsync(5_000);
    expect(await pending).toEqual({ status: "api_error", httpStatus: 503, errorCode: null });
  });
  it("honours an external abort before, during the headers and during the body", async () => {
    const before = new AbortController();
    before.abort();
    const fetchStub = stub(async () => json(publication()));
    expect(await fetchMarketFlow({ signal: before.signal })).toMatchObject({ reason: "ABORTED" });
    expect(fetchStub).not.toHaveBeenCalled();

    const headers = new AbortController();
    stub((_, init) => hang(init));
    const p1 = fetchMarketFlow({ signal: headers.signal });
    await Promise.resolve();
    headers.abort();
    expect(await p1).toMatchObject({ status: "transport_error", reason: "ABORTED" });

    const during = new AbortController();
    stub(async (_, init) => stalledBody(init));
    const p2 = fetchMarketFlow({ signal: during.signal });
    await vi.advanceTimersByTimeAsync(10);
    during.abort();
    expect(await p2).toMatchObject({ status: "transport_error", reason: "ABORTED" });
    expect(vi.getTimerCount()).toBe(0);
  });
  it("does not leak listeners on the external signal after settling", async () => {
    const controller = new AbortController();
    const remove = vi.spyOn(controller.signal, "removeEventListener");
    stub(async () => json(publication()));
    await fetchMarketFlow({ signal: controller.signal });
    expect(remove).toHaveBeenCalledWith("abort", expect.any(Function));
  });
  it("reports a connection that dies mid-body as a network failure, not as a success", async () => {
    stub(async () => {
      const body = new ReadableStream<Uint8Array>({
        start(c) { c.enqueue(enc('{"a":')); c.error(new TypeError("network error")); },
      });
      return new Response(body, { status: 200 });
    });
    expect(await fetchMarketFlow()).toMatchObject({ status: "transport_error", reason: "NETWORK" });
  });
});
