import { useEffect, useState } from "react";
import { validateVenuePublication, type VenuePublication } from "./venueComparison";
export const VENUE_ENDPOINT = "/api/operator/v1/venue-comparison";
export type VenueState = { status: "loading" } | { status: "success"; publication: VenuePublication } | { status: "unavailable"; diagnostic: string };

// Only presentation age/expiry is projected. Prices, source order and metrics retain their published values.
export function elapsedVenuePublication(publication: VenuePublication, elapsedMs: number): VenuePublication | undefined {
  if (!Number.isFinite(elapsedMs) || elapsedMs < 0) return undefined;
  const age = publication.publication_age_ms + elapsedMs;
  if (!Number.isFinite(age)) return undefined;
  const lifetime = publication.valid_until_utc === null ? null :
    Date.parse(publication.valid_until_utc) - Date.parse(publication.generated_at_utc) - 1;
  const freshness = publication.freshness_classification === "FRESH" && lifetime !== null && age >= lifetime ?
    "STALE" : publication.freshness_classification;
  return { ...publication, publication_age_ms: age, freshness_classification: freshness };
}

export function displayElapsed(startMono: number, startWall: number, nowMono: number, nowWall: number): number | undefined {
  const mono = nowMono - startMono, wall = nowWall - startWall;
  if (![mono, wall].every(Number.isFinite) || mono < 0 || wall < -1000) return undefined;
  return Math.max(mono, wall, 0);
}

export function useVenueComparison(): VenueState {
  const [state, setState] = useState<VenueState>({ status: "loading" });
  useEffect(() => {
    let alive = true;
    let poll: ReturnType<typeof setTimeout> | undefined;
    let expiry: ReturnType<typeof setTimeout> | undefined;
    let current: { publication: VenuePublication; mono: number; wall: number; elapsed: number; clockRefused: boolean } | undefined;
    const controller = new AbortController();
    const refreshAge = () => {
      if (expiry) clearTimeout(expiry);
      if (!alive || !current) return;
      const sampled = displayElapsed(current.mono, current.wall, performance.now(), Date.now());
      if (sampled === undefined) current.clockRefused = true;
      current.elapsed = Math.max(current.elapsed, sampled ?? 0);
      const publication = current.clockRefused ? undefined : elapsedVenuePublication(current.publication, current.elapsed);
      if (!publication) {
        setState({ status: "unavailable", diagnostic: "Horloge d’affichage non qualifiée" });
        return;
      }
      setState({ status: "success", publication });
      if (publication.freshness_classification === "FRESH" && publication.valid_until_utc !== null) {
        const remaining = Date.parse(publication.valid_until_utc) - Date.parse(publication.generated_at_utc) - publication.publication_age_ms - 1;
        expiry = setTimeout(refreshAge, Math.max(1, Math.min(remaining, 2_147_483_647)));
      }
    };
    const load = async () => {
      const mono = performance.now(), wall = Date.now(); // Count the whole request transit conservatively.
      let next: VenueState;
      try {
        const response = await fetch(VENUE_ENDPOINT, { method: "GET", cache: "no-store", signal: controller.signal });
        const body: unknown = await response.json();
        if (!response.ok) {
          const code = typeof body === "object" && body && "error_code" in body ? String(body.error_code) : "SOURCE_UNAVAILABLE";
          next = { status: "unavailable", diagnostic: "HTTP " + response.status + " · " + code };
        } else if (validateVenuePublication(body)) {
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
