// CryptoRadar Flux — GET client (lot 3A). A pure function: no hook, no timer,
// no fetch at import, no polling, no retry, no cache of a previous value.
//
// One endpoint, one method. Only HTTP 200 whose raw body passes the strict
// JSON reader AND the deep publication validator is a success. Every other
// outcome is a typed error; none is dressed up as an empty population, as a
// stale success, or as a server code the server never published.

import { MARKET_FLOW_MAX_RESPONSE_BYTES, readStrictJson } from "./marketFlowJson";
import { checkMarketFlowPublication } from "./marketFlowValidation";
import type { MarketFlowPublication } from "./marketFlowTypes";

export const MARKET_FLOW_ENDPOINT = "/api/operator/v1/market-flow";
/** Covers the response headers AND the whole body. */
export const MARKET_FLOW_TIMEOUT_MS = 5_000;
/** Error bodies are tiny ({"error_code": ...}); a larger one is not exploitable, its status still is. */
export const MARKET_FLOW_MAX_ERROR_BODY_BYTES = 65_536;

export type MarketFlowTransportReason =
  | "NETWORK"
  | "TIMEOUT"
  | "ABORTED"
  | "BODY_TOO_LARGE"
  | "INVALID_UTF8"
  | "INVALID_JSON"
  | "CONTRACT_INVALID";

export type MarketFlowFetchResult =
  | { readonly status: "success"; readonly publication: MarketFlowPublication }
  | { readonly status: "api_error"; readonly httpStatus: number; readonly errorCode: string | null }
  | {
      readonly status: "transport_error";
      readonly reason: MarketFlowTransportReason;
      /** Strict-reader code, or "<contract code>:<path>" for CONTRACT_INVALID. Diagnostic only. */
      readonly detail: string | null;
    };

/** State type a future consumer may hold; this slice ships no consumer. */
export type MarketFlowState = { readonly status: "loading" } | MarketFlowFetchResult;

export interface MarketFlowFetchOptions {
  /** External cancellation. */
  readonly signal?: AbortSignal;
}

type BodyRead =
  | { readonly ok: true; readonly bytes: Uint8Array }
  | { readonly ok: false; readonly reason: "TOO_LARGE" | "INTERRUPTED" };

const transport = (reason: MarketFlowTransportReason, detail: string | null = null): MarketFlowFetchResult =>
  ({ status: "transport_error", reason, detail });

/** Reads at most `limit` bytes of what is actually received; Content-Length is only an early hint. */
async function readBounded(response: Response, limit: number): Promise<BodyRead> {
  const declared = response.headers.get("content-length");
  if (declared !== null && /^[0-9]{1,16}$/.test(declared) && Number(declared) > limit) {
    try { await response.body?.cancel(); } catch { /* the refusal stands */ }
    return { ok: false, reason: "TOO_LARGE" };
  }
  if (response.body === null) return { ok: true, bytes: new Uint8Array(0) };
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.length;
      if (total > limit) {
        try { await reader.cancel(); } catch { /* the refusal stands */ }
        return { ok: false, reason: "TOO_LARGE" };
      }
      chunks.push(value);
    }
  } catch {
    return { ok: false, reason: "INTERRUPTED" };
  }
  const bytes = new Uint8Array(total);
  let at = 0;
  for (const c of chunks) { bytes.set(c, at); at += c.length; }
  return { ok: true, bytes };
}

/** The published code of an error body, only when the body is exactly {"error_code": "<CODE>"}. */
function nativeErrorCode(bytes: Uint8Array): string | null {
  const parsed = readStrictJson(bytes, MARKET_FLOW_MAX_ERROR_BODY_BYTES);
  if (!parsed.ok) return null;
  const v = parsed.value;
  if (typeof v !== "object" || v === null || Array.isArray(v)) return null;
  const keys = Object.keys(v);
  const code = (v as Record<string, unknown>).error_code;
  if (keys.length !== 1 || keys[0] !== "error_code" || typeof code !== "string") return null;
  return /^[A-Z][A-Z0-9_]{0,63}$/.test(code) ? code : null;
}

export async function fetchMarketFlow(options: MarketFlowFetchOptions = {}): Promise<MarketFlowFetchResult> {
  const external = options.signal;
  if (external?.aborted) return transport("ABORTED");
  const controller = new AbortController();
  let cause: "ABORTED" | "TIMEOUT" | null = null;
  const onExternalAbort = () => { cause ??= "ABORTED"; controller.abort(); };
  external?.addEventListener("abort", onExternalAbort, { once: true });
  const timer = setTimeout(() => { cause ??= "TIMEOUT"; controller.abort(); }, MARKET_FLOW_TIMEOUT_MS);
  const interrupted = (): MarketFlowFetchResult => transport(cause ?? "NETWORK");

  try {
    let response: Response;
    try {
      response = await fetch(MARKET_FLOW_ENDPOINT, {
        method: "GET",
        cache: "no-store",
        redirect: "error",
        signal: controller.signal,
        headers: { Accept: "application/json" },
      });
    } catch {
      return interrupted();
    }

    if (response.status !== 200) {
      const body = await readBounded(response, MARKET_FLOW_MAX_ERROR_BODY_BYTES);
      if (cause === "ABORTED") return transport("ABORTED");
      // The HTTP status is known whatever happened to the body: keep it.
      return {
        status: "api_error",
        httpStatus: response.status,
        errorCode: body.ok ? nativeErrorCode(body.bytes) : null,
      };
    }

    const body = await readBounded(response, MARKET_FLOW_MAX_RESPONSE_BYTES);
    if (!body.ok) return body.reason === "TOO_LARGE" ? transport("BODY_TOO_LARGE") : interrupted();
    const parsed = readStrictJson(body.bytes);
    if (!parsed.ok) {
      return parsed.code === "INVALID_UTF8" ? transport("INVALID_UTF8") : transport("INVALID_JSON", parsed.code);
    }
    const verdict = checkMarketFlowPublication(parsed.value);
    if (!verdict.ok) return transport("CONTRACT_INVALID", verdict.code + ":" + verdict.path);
    return { status: "success", publication: parsed.value as MarketFlowPublication };
  } finally {
    clearTimeout(timer);
    external?.removeEventListener("abort", onExternalAbort);
  }
}
