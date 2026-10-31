import { useEffect, useState } from "react";
import { validateVenuePublication, type VenuePublication } from "./venueComparison";
export const VENUE_ENDPOINT = "/api/operator/v1/venue-comparison";
export type VenueState = { status: "loading" } | { status: "success"; publication: VenuePublication } | { status: "unavailable"; diagnostic: string };
export function useVenueComparison(): VenueState {
  const [state, setState] = useState<VenueState>({ status: "loading" });
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      let next: VenueState;
      try {
        const response = await fetch(VENUE_ENDPOINT, { method: "GET", cache: "no-store" });
        const body: unknown = await response.json();
        if (!response.ok) {
          const code = typeof body === "object" && body && "error_code" in body ? String(body.error_code) : "SOURCE_UNAVAILABLE";
          next = { status: "unavailable", diagnostic: "HTTP " + response.status + " · " + code };
        } else if (validateVenuePublication(body)) next = { status: "success", publication: body };
        else next = { status: "unavailable", diagnostic: "Contrat de publication invalide" };
      } catch { next = { status: "unavailable", diagnostic: "Lecture de la publication impossible" }; }
      if (alive) { setState(next); timer = setTimeout(load, 20_000); }
    };
    void load();
    return () => { alive = false; if (timer) clearTimeout(timer); };
  }, []);
  return state;
}
