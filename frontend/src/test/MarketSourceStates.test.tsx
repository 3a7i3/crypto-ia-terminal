import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { marketSourceSetup } from "../lib/marketSourceSetup";
import { FOOTPRINT_REPLAY_URL } from "../lib/footprintReplay";
import { MarketFlowView } from "../views/MarketFlowView";
import { MarketVenuesView } from "../views/MarketVenuesView";
import { MarketMicrostructureView } from "../views/MarketMicrostructureView";
import { SpotRadarMap } from "../views/SpotRadarMap";
import scanner from "./fixtures/spotRadar-scanner.json";

// M1-C2 (EO-024): a source that the server does not configure or deploy is shown
// apart from read, transport and contract failures, with its exact code. LOCAL
// TEST FIXTURES only: every response below is fabricated in this file.
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
type Route = (path: string) => Response;
function stub(route: Route) {
  const calls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = new URL(String(input instanceof Request ? input.url : input), "http://127.0.0.1").pathname;
    calls.push(path);
    return route(path);
  }));
  return calls;
}
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("marketSourceSetup", () => {
  it("recognises only configuration and deployment codes", () => {
    expect(marketSourceSetup("MARKET_FLOW_NOT_CONFIGURED")).toBe("NOT_CONFIGURED");
    expect(marketSourceSetup("VENUE_COMPARISON_NOT_CONFIGURED")).toBe("NOT_CONFIGURED");
    expect(marketSourceSetup("NOT_CONFIGURED")).toBe("NOT_CONFIGURED");
    expect(marketSourceSetup("SOURCE_NOT_DEPLOYED")).toBe("NOT_DEPLOYED");
    for (const code of ["MICROSTRUCTURE_MISSING", "VENUE_COMPARISON_MISSING", "MARKET_FLOW_UNREADABLE", "HTTP_503", "TRANSPORT_ERROR", "NOT_CONFIGURED_X", "", null, undefined])
      expect(marketSourceSetup(code)).toBeNull();
  });
});

const cases: { name: string; view: () => JSX.Element; endpoint: string; also?: string[]; code: string; label: string; otherCode: string; otherText: RegExp }[] = [
  { name: "Flux", view: () => <MarketFlowView/>, endpoint: "/api/operator/v1/market-flow", code: "MARKET_FLOW_NOT_CONFIGURED", label: "Source Flux non configurée", otherCode: "MARKET_FLOW_UNREADABLE", otherText: /Flux indisponible · HTTP 503 · MARKET_FLOW_UNREADABLE/ },
  { name: "Comparaison des plateformes", view: () => <MarketVenuesView/>, endpoint: "/api/operator/v1/venue-comparison", code: "VENUE_COMPARISON_NOT_CONFIGURED", label: "Source Comparaison des plateformes non configurée", otherCode: "VENUE_COMPARISON_MISSING", otherText: /Aucune publication de comparaison disponible/ },
  { name: "Microstructure", view: () => <MarketMicrostructureView/>, endpoint: "/api/operator/v1/market-microstructure", also: [FOOTPRINT_REPLAY_URL], code: "SOURCE_NOT_DEPLOYED", label: "Source Microstructure non déployée", otherCode: "MICROSTRUCTURE_MISSING", otherText: /SOURCE INDISPONIBLE · HTTP 503 · MICROSTRUCTURE_MISSING/ },
  { name: "Radar Spot", view: () => <SpotRadarMap/>, endpoint: "/api/operator/v1/spot-radar/scanner", code: "SPOT_RADAR_NOT_CONFIGURED", label: "Source Radar Spot non configurée", otherCode: "SPOT_RADAR_MISSING", otherText: /API indisponible · SPOT_RADAR_MISSING/ },
];

describe.each(cases)("$name", ({ name, view, endpoint, also = [], code, label, otherCode, otherText }) => {
  it("shows an unconfigured source apart from a failure, with its exact code and no empty market", async () => {
    const calls = stub(() => json({ error_code: code }, 503));
    render(view());
    // Flux and Comparaison now also host the derivatives-stress source: pick this view's own notice.
    const notice = (await screen.findAllByTestId("market-source-not-configured")).find(n => n.textContent?.includes(label))!;
    expect(notice).toHaveTextContent(label);
    expect(notice).toHaveTextContent(code);
    expect(notice).toHaveTextContent("ni marché vide, ni valeur nulle");
    expect(notice).toHaveAttribute("role", "status");
    expect(screen.queryByRole("alert")).toBeNull();
    // The venue view keeps its pre-C2 sentence (asserted by venueComparison.compat).
    if (endpoint.endsWith("/venue-comparison")) expect(screen.getByText("Aucune publication de comparaison disponible.")).toBeInTheDocument();
    // Only this view's own sources are read (Footprint capture for Microstructure, derivatives stress for Flux and venues).
    const stress = name === "Flux" || name === "Comparaison des plateformes" ? ["/api/operator/v1/derivatives-stress"] : [];
    expect(new Set(calls)).toEqual(new Set([endpoint, ...also, ...stress]));
  });

  it("keeps any other error code as an unavailable source, not as unconfigured", async () => {
    stub(() => json({ error_code: otherCode }, 503));
    render(view());
    expect(await screen.findByText(otherText)).toBeInTheDocument();
    expect(screen.queryByTestId("market-source-not-configured")).toBeNull();
  });
});

it("Radar Spot keeps observed values DISCONNECTED when the source later reports not configured", async () => {
  let next: Response = json(scanner);
  vi.spyOn(Date, "now").mockReturnValue(Number(scanner.server_time_ms));
  stub(() => next);
  render(<SpotRadarMap/>);
  await screen.findByText("30 / 30");
  next = json({ error_code: "SPOT_RADAR_NOT_CONFIGURED" }, 503);
  fireEvent.click(screen.getByRole("button", { name: "Actualiser" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Dernières valeurs conservées, état DISCONNECTED.");
  expect(screen.queryByTestId("market-source-not-configured")).toBeNull();
  expect(screen.getAllByRole("button", { name: /MEXC Spot · DISCONNECTED/ })).toHaveLength(30);
});
