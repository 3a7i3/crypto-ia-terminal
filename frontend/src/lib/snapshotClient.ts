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
//
// O-02W-D2-R1 Correction C: polling is serialized. The next poll is only
// scheduled once the current request has fully settled (success or
// failure) — `setInterval` is never used, so a slow request can never
// overlap with the next tick. Each request also carries a monotonic
// sequence token; a response whose token is not the latest issued is
// discarded rather than allowed to roll the UI back to an older snapshot
// (e.g. a fetch retried out of order, or a dev-tools throttled response
// racing a later one under React StrictMode's double-invoke). Cycle
// numbers are never used for this purpose — a producer restart can reset
// `cycle`, so recency is tracked purely by issue order, not by domain data.

import { useEffect, useRef, useState } from "react";
import type { ApiStructuredError, OperatorSnapshot } from "../types";
import { validateOperatorSnapshot } from "./snapshotValidation";

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

export function useOperatorSnapshot(intervalMs: number = DEFAULT_POLL_INTERVAL_MS): SnapshotState {
  const [state, setState] = useState<SnapshotState>({ status: "loading", lastSuccess: null });
  const lastSuccessRef = useRef<LastSuccess | null>(null);

  useEffect(() => {
    let alive = true;
    let timerId: ReturnType<typeof setTimeout> | undefined;
    // Monotonic sequence token — only the response matching the latest
    // issued request is allowed to update state (Correction C).
    let latestSeq = 0;

    const settle = (next: SnapshotState, seq: number) => {
      if (!alive) return; // unmounted — never update state after unmount
      if (seq !== latestSeq) return; // superseded by a newer request
      setState(next);
    };

    const scheduleNext = () => {
      if (!alive) return;
      timerId = setTimeout(load, intervalMs);
    };

    const load = async () => {
      if (!alive) return;
      const seq = ++latestSeq; // exactly one in-flight request is "current"

      let response: Response;
      try {
        response = await fetch(SNAPSHOT_ENDPOINT, { method: "GET" });
      } catch (err) {
        settle(
          {
            status: "transport_error",
            message: err instanceof Error ? err.message : "Network request failed",
            lastSuccess: lastSuccessRef.current,
          },
          seq,
        );
        scheduleNext();
        return;
      }

      let body: unknown;
      try {
        body = await response.json();
      } catch {
        settle(
          {
            status: "transport_error",
            message: `Response body was not valid JSON (HTTP ${response.status})`,
            lastSuccess: lastSuccessRef.current,
          },
          seq,
        );
        scheduleNext();
        return;
      }

      if (!response.ok) {
        const error: ApiStructuredError = isPlainObject(body) ? body : {};
        settle(
          { status: "api_error", error, httpStatus: response.status, lastSuccess: lastSuccessRef.current },
          seq,
        );
        scheduleNext();
        return;
      }

      if (!validateOperatorSnapshot(body)) {
        settle(
          {
            status: "transport_error",
            message: "HTTP 200 response did not carry a structurally valid operator snapshot envelope.",
            lastSuccess: lastSuccessRef.current,
          },
          seq,
        );
        scheduleNext();
        return;
      }

      const success: LastSuccess = { snapshot: body, fetchedAt: Date.now() };
      // Only accepted if this response is still the latest issued request —
      // an older, slower response can never roll a newer accepted result
      // back (Correction C invariant: no out-of-order overwrite).
      if (alive && seq === latestSeq) {
        lastSuccessRef.current = success;
      }
      settle({ status: "success", snapshot: body, fetchedAt: success.fetchedAt, lastSuccess: success }, seq);
      scheduleNext();
    };

    load();
    return () => {
      alive = false;
      if (timerId !== undefined) clearTimeout(timerId);
    };
  }, [intervalMs]);

  return state;
}
