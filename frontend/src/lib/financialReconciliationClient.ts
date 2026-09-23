import { useEffect, useState } from "react";
import type { ApiStructuredError } from "../types";
import type { FinancialReconciliationSnapshot } from "./financialReconciliationTypes";
import { validateFinancialReconciliationSnapshot } from "./financialReconciliationValidation";

export const FINANCIAL_RECONCILIATION_ENDPOINT =
  "/api/operator/v1/financial-reconciliation";
export const FINANCIAL_RECONCILIATION_POLL_INTERVAL_MS = 20_000;

export type FinancialReconciliationState =
  | { status: "loading" }
  | { status: "success"; snapshot: FinancialReconciliationSnapshot; fetchedAt: number }
  | { status: "api_error"; error: ApiStructuredError; httpStatus: number }
  | { status: "transport_error"; message: string };

function isPlainObject(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

export function useFinancialReconciliation(
  intervalMs: number = FINANCIAL_RECONCILIATION_POLL_INTERVAL_MS,
): FinancialReconciliationState {
  const [state, setState] = useState<FinancialReconciliationState>({ status: "loading" });

  useEffect(() => {
    let alive = true;
    let timerId: ReturnType<typeof setTimeout> | undefined;
    let latestSeq = 0;

    const scheduleNext = () => {
      if (alive) timerId = setTimeout(load, intervalMs);
    };

    const settle = (next: FinancialReconciliationState, seq: number) => {
      if (!alive || seq !== latestSeq) return;
      setState(next);
    };

    const load = async () => {
      if (!alive) return;
      const seq = ++latestSeq;
      let response: Response;

      try {
        response = await fetch(FINANCIAL_RECONCILIATION_ENDPOINT, { method: "GET" });
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
            message: "Response body was not valid JSON (HTTP " + response.status + ")",
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

      if (!validateFinancialReconciliationSnapshot(body)) {
        settle(
          {
            status: "transport_error",
            message: "HTTP 200 response did not satisfy the FIN-02 financial reconciliation contract.",
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
