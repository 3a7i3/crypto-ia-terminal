// ── snapshotClient — the ONE application-level polling source ───────────────
//
// Every panel in the cockpit is fed from a single GET to
// /api/operator/v1/snapshot, polled on one shared interval. There is no
// per-panel polling and no mixing of domains from different snapshots: a
// single fetch's response is the sole coherent view for that render cycle.
//
// A failed fetch is NEVER converted into an empty "healthy" snapshot, and a
// previously-successful snapshot is never silently kept presented as
// "current" once a subsequent fetch fails — the state machine below always
// distinguishes the two.

import { useEffect, useRef, useState } from "react";
import type { ApiStructuredError, OperatorSnapshot } from "../types";

export const SNAPSHOT_ENDPOINT = "/api/operator/v1/snapshot";
export const DEFAULT_POLL_INTERVAL_MS = 20_000;

export interface LastSuccess {
  snapshot: OperatorSnapshot;
  fetchedAt: number;
}

export type SnapshotState =
  | { status: "loading"; lastSuccess: null }
  | { status: "success"; snapshot: OperatorSnapshot; fetchedAt: number; lastSuccess: LastSuccess }
  | { status: "api_error"; error: ApiStructuredError; httpStatus: number; lastSuccess: LastSuccess | null }
  | { status: "transport_error"; message: string; lastSuccess: LastSuccess | null };

function isPlainObject(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

/** Minimal shape guard — the reader/API already validate the envelope; this
 * only rules out a response so malformed it cannot be a snapshot at all. */
function looksLikeSnapshot(x: unknown): x is OperatorSnapshot {
  if (!isPlainObject(x)) return false;
  return (
    "snapshot_id" in x &&
    "cycle" in x &&
    "portfolio" in x &&
    "decision_pipeline" in x &&
    "system_health" in x
  );
}

export function useOperatorSnapshot(intervalMs: number = DEFAULT_POLL_INTERVAL_MS): SnapshotState {
  const [state, setState] = useState<SnapshotState>({ status: "loading", lastSuccess: null });
  const lastSuccessRef = useRef<LastSuccess | null>(null);

  useEffect(() => {
    let alive = true;

    const load = async () => {
      let response: Response;
      try {
        response = await fetch(SNAPSHOT_ENDPOINT, { method: "GET" });
      } catch (err) {
        if (!alive) return;
        setState({
          status: "transport_error",
          message: err instanceof Error ? err.message : "Network request failed",
          lastSuccess: lastSuccessRef.current,
        });
        return;
      }

      let body: unknown;
      try {
        body = await response.json();
      } catch {
        if (!alive) return;
        setState({
          status: "transport_error",
          message: `Response body was not valid JSON (HTTP ${response.status})`,
          lastSuccess: lastSuccessRef.current,
        });
        return;
      }

      if (!alive) return;

      if (!response.ok) {
        const error: ApiStructuredError = isPlainObject(body) ? body : {};
        setState({
          status: "api_error",
          error,
          httpStatus: response.status,
          lastSuccess: lastSuccessRef.current,
        });
        return;
      }

      if (!looksLikeSnapshot(body)) {
        setState({
          status: "transport_error",
          message: "HTTP 200 response did not carry a usable operator snapshot envelope.",
          lastSuccess: lastSuccessRef.current,
        });
        return;
      }

      const success: LastSuccess = { snapshot: body, fetchedAt: Date.now() };
      lastSuccessRef.current = success;
      setState({ status: "success", snapshot: body, fetchedAt: success.fetchedAt, lastSuccess: success });
    };

    load();
    const id = setInterval(load, intervalMs);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [intervalMs]);

  return state;
}
