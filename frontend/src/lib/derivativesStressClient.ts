import { useEffect, useState } from "react";
import { displayElapsed } from "./venueComparisonClient";
import { validateStressPublication, type StressPublication } from "./derivativesStress";
export const STRESS_ENDPOINT = "/api/operator/v1/derivatives-stress";
export type StressState = { status: "loading" } | { status: "success"; publication: StressPublication } | { status: "unavailable"; diagnostic: string; httpStatus?: number; errorCode?: string };

// Only presentation age/expiry is projected; every published value keeps its published text.
export function elapsedStressPublication(publication: StressPublication, elapsedMs: number): StressPublication | undefined {
  if (!Number.isFinite(elapsedMs) || elapsedMs < 0) return undefined;
  const age = publication.publication_age_ms + elapsedMs;
  if (!Number.isFinite(age)) return undefined;
  const lifetime = publication.valid_until_utc === null ? null : Date.parse(publication.valid_until_utc) - Date.parse(publication.generated_at_utc) - 1;
  const freshness = publication.freshness_classification === "FRESH" && lifetime !== null && age >= lifetime ? "STALE" : publication.freshness_classification;
  return { ...publication, publication_age_ms: age, freshness_classification: freshness };
}

/** GET-only reader of the explicitly configured publication; one 20 s poll, no retry storm. */
export function useDerivativesStress(): StressState {
  const [state, setState] = useState<StressState>({ status: "loading" });
  useEffect(() => {
    let alive = true;
    let poll: ReturnType<typeof setTimeout> | undefined;
    let expiry: ReturnType<typeof setTimeout> | undefined;
    let current: { publication: StressPublication; mono: number; wall: number; elapsed: number; clockRefused: boolean } | undefined;
    const controller = new AbortController();
    const refreshAge = () => {
      if (expiry) clearTimeout(expiry);
      if (!alive || !current) return;
      const sampled = displayElapsed(current.mono, current.wall, performance.now(), Date.now());
      if (sampled === undefined) current.clockRefused = true;
      current.elapsed = Math.max(current.elapsed, sampled ?? 0);
      const publication = current.clockRefused ? undefined : elapsedStressPublication(current.publication, current.elapsed);
      if (!publication) { setState({ status: "unavailable", diagnostic: "Horloge d’affichage non qualifiée" }); return; }
      setState({ status: "success", publication });
      if (publication.freshness_classification === "FRESH" && publication.valid_until_utc !== null) {
        const remaining = Date.parse(publication.valid_until_utc) - Date.parse(publication.generated_at_utc) - publication.publication_age_ms - 1;
        expiry = setTimeout(refreshAge, Math.max(1, Math.min(remaining, 2_147_483_647)));
      }
    };
    const load = async () => {
      const mono = performance.now(), wall = Date.now();
      let next: StressState;
      try {
        const response = await fetch(STRESS_ENDPOINT, { method: "GET", cache: "no-store", signal: controller.signal });
        const body: unknown = await response.json();
        if (!response.ok) {
          const errorCode = typeof body === "object" && body && "error_code" in body ? String(body.error_code) : "SOURCE_UNAVAILABLE";
          next = { status: "unavailable", diagnostic: "HTTP " + response.status + " · " + errorCode, httpStatus: response.status, errorCode };
        } else if (validateStressPublication(body)) {
          if (!alive) return;
          current = { publication: body, mono, wall, elapsed: 0, clockRefused: false };
          refreshAge();
          poll = setTimeout(load, 20_000);
          return;
        } else next = { status: "unavailable", diagnostic: "Contrat de publication invalide" };
      } catch { next = { status: "unavailable", diagnostic: "Lecture de la publication impossible" }; }
      if (alive) {
        current = undefined;
        if (expiry) clearTimeout(expiry);
        setState(next);
        poll = setTimeout(load, 20_000);
      }
    };
    document.addEventListener("visibilitychange", refreshAge);
    void load();
    return () => {
      alive = false; current = undefined; controller.abort();
      if (poll) clearTimeout(poll);
      if (expiry) clearTimeout(expiry);
      document.removeEventListener("visibilitychange", refreshAge);
    };
  }, []);
  return state;
}
