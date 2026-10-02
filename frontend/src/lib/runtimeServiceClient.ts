import { useEffect, useState } from "react";
import type { RuntimeServiceSnapshot } from "./runtimeServiceTypes";
import { validateRuntimeServiceSnapshot } from "./runtimeServiceValidation";

export const RUNTIME_SERVICE_ENDPOINT = "/api/operator/v1/runtime-service";
export type RuntimeServiceState =
  | { status: "loading" }
  | { status: "success"; snapshot: RuntimeServiceSnapshot }
  | { status: "api_error"; errorCode: string; httpStatus: number }
  | { status: "transport_error"; message: string };

export function useRuntimeService(intervalMs = 20_000): RuntimeServiceState {
  const [state, setState] = useState<RuntimeServiceState>({ status: "loading" });
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();
    async function load() {
      let next: RuntimeServiceState;
      try {
        const response = await fetch(RUNTIME_SERVICE_ENDPOINT, { method: "GET", signal: controller.signal });
        const body: unknown = await response.json();
        if (!response.ok) {
          const code = typeof body === "object" && body !== null && "error_code" in body && typeof body.error_code === "string" ? body.error_code : "RUNTIME_SERVICE_SOURCE_ERROR";
          next = { status: "api_error", errorCode: code, httpStatus: response.status };
        } else if (!validateRuntimeServiceSnapshot(body)) {
          next = { status: "transport_error", message: "HTTP 200 invalide pour RuntimeServiceSnapshot." };
        } else next = { status: "success", snapshot: body };
      } catch {
        next = { status: "transport_error", message: "Source host indisponible ou réponse JSON invalide." };
      }
      if (alive) {
        setState(next);
        // Serialized polling: a slow request never overlaps the next one.
        timer = setTimeout(load, intervalMs);
      }
    }
    load();
    return () => { alive = false; controller.abort(); if (timer !== undefined) clearTimeout(timer); };
  }, [intervalMs]);
  return state;
}
