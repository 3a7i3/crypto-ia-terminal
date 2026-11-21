import { useEffect, useState } from "react";
import { validatePositioning, type Positioning } from "./derivativesPositioning";
export const POSITIONING_ENDPOINT = "/api/operator/v1/derivatives-positioning";
export type PositioningState = { status: "loading" } | { status: "success"; doc: Positioning } | { status: "unavailable"; diagnostic: string; httpStatus?: number; errorCode?: string };

/** GET-only, one request per 60 s; a failure is shown as unavailable, never as an empty market. */
export function useDerivativesPositioning(): PositioningState {
  const [state, setState] = useState<PositioningState>({ status: "loading" });
  useEffect(() => {
    let alive = true;
    let poll: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();
    const load = async () => {
      let next: PositioningState;
      try {
        const response = await fetch(POSITIONING_ENDPOINT, { method: "GET", cache: "no-store", signal: controller.signal });
        const body: unknown = await response.json();
        if (!response.ok) {
          const errorCode = typeof body === "object" && body && "error_code" in body ? String(body.error_code) : "SOURCE_UNAVAILABLE";
          next = { status: "unavailable", diagnostic: "HTTP " + response.status + " · " + errorCode, httpStatus: response.status, errorCode };
        } else next = validatePositioning(body) ? { status: "success", doc: body } : { status: "unavailable", diagnostic: "Contrat de lecture invalide" };
      } catch { next = { status: "unavailable", diagnostic: "Lecture du positionnement impossible" }; }
      if (alive) { setState(next); poll = setTimeout(load, 60_000); }
    };
    void load();
    return () => { alive = false; controller.abort(); if (poll) clearTimeout(poll); };
  }, []);
  return state;
}
