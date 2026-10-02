import { useEffect, useState } from "react";
import { validateResearchStrategyBoard } from "./researchStrategyValidation";
import type { ResearchStrategyBoard } from "./researchStrategyTypes";
export type StrategyBoardState =
  | { status: "loading" }
  | { status: "success"; snapshot: ResearchStrategyBoard }
  | { status: "error"; code: string };
export function useResearchStrategyBoard(
  intervalMs = 60_000,
): StrategyBoardState {
  const [state, setState] = useState<StrategyBoardState>({ status: "loading" });
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController | undefined;
    async function load() {
      controller = new AbortController();
      timeout = setTimeout(() => controller?.abort(), 5_000);
      let next: StrategyBoardState;
      try {
        const response = await fetch("/api/operator/v1/research-strategies", {
          method: "GET",
          signal: controller.signal,
        });
        const body: unknown = await response.json();
        if (!response.ok) {
          const code =
            typeof body === "object" &&
            body !== null &&
            "error_code" in body &&
            typeof body.error_code === "string"
              ? body.error_code
              : "RESEARCH_STRATEGY_SOURCE_ERROR";
          next = { status: "error", code };
        } else if (!validateResearchStrategyBoard(body))
          next = { status: "error", code: "RESEARCH_STRATEGY_CONTRACT_ERROR" };
        else next = { status: "success", snapshot: body };
      } catch {
        next = {
          status: "error",
          code: "RESEARCH_STRATEGY_NETWORK_OR_TIMEOUT",
        };
      } finally {
        if (timeout !== undefined) clearTimeout(timeout);
      }
      if (alive) {
        setState(next);
        timer = setTimeout(load, intervalMs);
      }
    }
    load();
    return () => {
      alive = false;
      controller?.abort();
      if (timer !== undefined) clearTimeout(timer);
      if (timeout !== undefined) clearTimeout(timeout);
    };
  }, [intervalMs]);
  return state;
}
