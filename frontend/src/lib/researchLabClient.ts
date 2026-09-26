import { useEffect, useState } from "react";
import type { ApiStructuredError } from "../types";
import type { ResearchLabSnapshot } from "./researchLabTypes";
import { validateResearchLabSnapshot } from "./researchLabValidation";

export const RESEARCH_LAB_ENDPOINT = "/api/operator/v1/research-lab";
export const RESEARCH_LAB_POLL_INTERVAL_MS = 60_000;

export type ResearchLabState =
  | { status: "loading" }
  | { status: "success"; snapshot: ResearchLabSnapshot; fetchedAt: number }
  | { status: "api_error"; error: ApiStructuredError; httpStatus: number }
  | { status: "transport_error"; message: string };

function isPlainObject(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

export function useResearchLabSnapshot(
  intervalMs: number = RESEARCH_LAB_POLL_INTERVAL_MS,
): ResearchLabState {
  const [state, setState] = useState<ResearchLabState>({ status: "loading" });

  useEffect(() => {
    let alive = true;
    let timerId: ReturnType<typeof setTimeout> | undefined;
    let latestSeq = 0;

    const scheduleNext = () => {
      if (alive) timerId = setTimeout(load, intervalMs);
    };

    const settle = (next: ResearchLabState, seq: number) => {
      if (!alive || seq !== latestSeq) return;
      setState(next);
    };

    const load = async () => {
      if (!alive) return;
      const seq = ++latestSeq;
      let response: Response;
      try {
        response = await fetch(RESEARCH_LAB_ENDPOINT, { method: "GET" });
      } catch (err) {
        settle(
          {
            status: "transport_error",
            message: err instanceof Error ? err.message : "Network request failed",
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
          },
          seq,
        );
        scheduleNext();
        return;
      }

      if (!response.ok) {
        const error: ApiStructuredError = isPlainObject(body) ? body : {};
        settle({ status: "api_error", error, httpStatus: response.status }, seq);
        scheduleNext();
        return;
      }

      if (!validateResearchLabSnapshot(body)) {
        settle(
          {
            status: "transport_error",
            message: "HTTP 200 response did not satisfy the WEB-RL Research Lab contract.",
          },
          seq,
        );
        scheduleNext();
        return;
      }

      settle({ status: "success", snapshot: body, fetchedAt: Date.now() }, seq);
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
