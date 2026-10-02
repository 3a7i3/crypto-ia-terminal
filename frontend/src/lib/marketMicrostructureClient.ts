import { useEffect, useState } from "react";
import type { MarketMicrostructureSnapshot } from "./marketMicrostructureTypes";
import { validateMarketMicrostructureSnapshot } from "./marketMicrostructureValidation";

export const MARKET_MICROSTRUCTURE_ENDPOINT = "/api/operator/v1/market-microstructure";
export type MarketMicrostructureState =
  | { status: "loading" }
  | { status: "success"; snapshot: MarketMicrostructureSnapshot }
  | { status: "api_error"; errorCode: string; httpStatus: number }
  | { status: "transport_error"; message: string };

export function useMarketMicrostructure(intervalMs = 5_000): MarketMicrostructureState {
  const [state, setState] = useState<MarketMicrostructureState>({ status: "loading" });
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController | undefined;
    async function load() {
      controller = new AbortController();
      timeout = setTimeout(() => controller?.abort(), 5_000);
      let next: MarketMicrostructureState;
      try {
        const response = await fetch(MARKET_MICROSTRUCTURE_ENDPOINT, { method: "GET", signal: controller.signal });
        const body: unknown = await response.json();
        if (!response.ok) {
          const code = typeof body === "object" && body !== null && "error_code" in body && typeof body.error_code === "string" ? body.error_code : "MICROSTRUCTURE_SOURCE_ERROR";
          next = { status: "api_error", errorCode: code, httpStatus: response.status };
        } else if (!validateMarketMicrostructureSnapshot(body)) {
          next = { status: "transport_error", message: "HTTP 200 invalide pour MarketMicrostructureSnapshot." };
        } else next = { status: "success", snapshot: body };
      } catch {
        next = { status: "transport_error", message: "Source LMI indisponible, délai dépassé ou réponse JSON invalide." };
      } finally { if (timeout !== undefined) clearTimeout(timeout); }
      if (alive) {
        setState(next);
        // Serialized polling: next request only after current body has settled.
        timer = setTimeout(load, intervalMs);
      }
    }
    load();
    return () => { alive = false; controller?.abort(); if (timer !== undefined) clearTimeout(timer); if (timeout !== undefined) clearTimeout(timeout); };
  }, [intervalMs]);
  return state;
}
