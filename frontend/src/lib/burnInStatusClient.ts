import { useEffect, useState } from "react";
import type { ApiStructuredError } from "../types";
import type { BurnInStatusSnapshot } from "./burnInStatusTypes";
import { validateBurnInStatusSnapshot } from "./burnInStatusValidation";

export const BURN_IN_ENDPOINT = "/api/operator/v1/burn-in";
export const BURN_IN_POLL_INTERVAL_MS = 20_000;

export type BurnInState =
  | { status: "loading" }
  | { status: "success"; snapshot: BurnInStatusSnapshot; fetchedAt: number }
  | { status: "api_error"; error: ApiStructuredError; httpStatus: number }
  | { status: "transport_error"; message: string };

function plain(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

export function useBurnInStatus(intervalMs: number = BURN_IN_POLL_INTERVAL_MS): BurnInState {
  const [state, setState] = useState<BurnInState>({ status: "loading" });

  useEffect(() => {
    let alive = true;
    let timerId: ReturnType<typeof setTimeout> | undefined;
    let latestSeq = 0;
    const schedule = () => {
      if (alive) timerId = setTimeout(load, intervalMs);
    };
    const settle = (next: BurnInState, seq: number) => {
      if (alive && seq === latestSeq) setState(next);
    };
    const load = async () => {
      if (!alive) return;
      const seq = ++latestSeq;
      let response: Response;
      try {
        response = await fetch(BURN_IN_ENDPOINT, { method: "GET" });
      } catch (err) {
        settle({ status: "transport_error", message: err instanceof Error ? err.message : "Network request failed" }, seq);
        schedule();
        return;
      }

      let body: unknown;
      try {
        body = await response.json();
      } catch {
        settle({ status: "transport_error", message: `Response body was not valid JSON (HTTP ${response.status})` }, seq);
        schedule();
        return;
      }

      if (!response.ok) {
        settle({ status: "api_error", error: plain(body) ? body : {}, httpStatus: response.status }, seq);
        schedule();
        return;
      }
      if (!validateBurnInStatusSnapshot(body)) {
        settle({ status: "transport_error", message: "HTTP 200 response did not satisfy the APP-UNIFY U2 BurnInStatusSnapshot contract." }, seq);
        schedule();
        return;
      }

      settle({ status: "success", snapshot: body, fetchedAt: Date.now() }, seq);
      schedule();
    };

    load();
    return () => {
      alive = false;
      if (timerId !== undefined) clearTimeout(timerId);
    };
  }, [intervalMs]);

  return state;
}
