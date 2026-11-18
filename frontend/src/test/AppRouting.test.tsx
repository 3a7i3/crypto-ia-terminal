import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { baseSnapshot } from "./fixtures";
const response = (body: unknown, status = 200) =>
  ({ ok: status === 200, status, json: async () => body }) as Response;
describe("Module workspace routing", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue(response(baseSnapshot()));
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());
  // M1-C1 reconciliation (EO-022). Was: "/" opened the six-domain Direction home
  // (ModuleHome, six cards). Decision D-C5: Market stays the home during M1 and
  // the Direction home is not promoted (ModuleHome stays in the sources, unrouted).
  // Preserved: one home, one primary navigation, no scores or burn-in surface.
  it("opens one home with six modules and one primary navigation", async () => {
    render(<App />);
    await screen.findByTestId("market-workspace");
    expect(window.location.pathname).toBe("/paper-live/market/radar");
    expect(screen.queryByTestId("module-home")).toBeNull();
    const primary = screen.getAllByRole("navigation", { name: "Modules de la machine" });
    expect(primary).toHaveLength(1);
    // Six modules plus the Accueil shortcut, which opens the Market home itself.
    expect(within(primary[0]).getAllByRole("link")).toHaveLength(7);
    expect(screen.queryByText("Ordres & Burn-in")).toBeNull();
    expect(screen.queryByTestId("tab-scores")).toBeNull();
  });
  it("preserves Decisions deep links and its single validated source", async () => {
    window.history.replaceState({}, "", "/paper-live/decisions");
    render(<App />);
    await screen.findByTestId("decisions-view");
    expect(screen.getByTestId("paper-live-shell")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/operator/v1/snapshot", {
      method: "GET",
    });
  });
  // M1-C1 reconciliation (EO-022). Was: the Direction home read five sources
  // (snapshot, market, finance, research-lab, runtime-service). Decision D-C5: the
  // home is Market Radar, which owns one source (Spot Radar). Preserved: the home
  // reads only the sources it owns, never Advisor, finance or capital, never burn-in.
  it("home reads five sources, shares canonical metadata and never requests burn-in", async () => {
    render(<App />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 20));
    const urls = fetchMock.mock.calls.map((call) => String(call[0]));
    expect(urls.length).toBeGreaterThan(0);
    expect(urls.every((url) => url.startsWith("/api/operator/v1/spot-radar/"))).toBe(true);
    expect(urls).not.toContain("/api/operator/v1/burn-in");
    expect(urls).not.toContain("/api/operator/v1/snapshot");
    expect(urls).not.toContain("/api/operator/v1/market");
    expect(screen.getByTestId("market-workspace")).not.toHaveTextContent(
      "Capital disponible",
    );
  });
  // M1-C1 reconciliation (EO-022). Was: ten requests for five owners under StrictMode.
  // Decision D-C5: one owner (Spot Radar) on the Market home. Preserved: StrictMode's
  // repeated mount effects add no new source and at most one repeat per request.
  it("keeps five source owners when StrictMode repeats development mount effects", async () => {
    const { StrictMode } = await import("react");
    render(<StrictMode><App /></StrictMode>);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 20));
    const urls = fetchMock.mock.calls.map(call => String(call[0]));
    expect(new Set(urls)).toEqual(new Set(["/api/operator/v1/spot-radar/scanner"]));
    expect(urls.length).toBeLessThanOrEqual(2);
  });

  // M1-C1 reconciliation (EO-022). Was: a "Décisions" card of the Direction home.
  // Decision D-C5: no Direction home during M1; the home reaches each owned source
  // through the single primary navigation. Preserved: Décisions opens its own route.
  it("opens the owned source from a home card", async () => {
    render(<App />);
    await screen.findByTestId("market-workspace");
    fireEvent.click(
      within(
        screen.getByRole("navigation", { name: "Modules de la machine" }),
      ).getByRole("link", { name: "Décisions" }),
    );
    await screen.findByTestId("decisions-view");
    expect(window.location.pathname).toBe("/paper-live/decisions");
  });
  // M1-C1 reconciliation (EO-022). Was: obsolete /paper-live and /paper-live/overview
  // -> /direction. Decisions D-C1/D-C5: they land on the canonical Market Radar route.
  // Preserved: obsolete routes redirect and never request burn-in.
  it.each([
    ["/paper-live", "/paper-live/market/radar"],
    ["/paper-live/overview", "/paper-live/market/radar"],
    ["/paper-live/burn-in", "/paper-live/portfolio"],
    ["/paper-live/scores", "/paper-live/system"],
  ])("redirects obsolete %s to %s", async (from, to) => {
    window.history.replaceState({}, "", from);
    render(<App />);
    await waitFor(() => expect(window.location.pathname).toBe(to));
    expect(
      fetchMock.mock.calls.some((call) => String(call[0]).includes("/burn-in")),
    ).toBe(false);
  });
  it("keeps Research non-authoritative and independent", async () => {
    window.history.replaceState({}, "", "/research");
    render(<App />);
    expect(
      screen.getByTestId("research-header-domain-badge"),
    ).toHaveTextContent("RECHERCHE NON AUTORITAIRE");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock).toHaveBeenCalledWith("/api/operator/v1/research-lab", {
      method: "GET",
    });
    expect(screen.queryByTestId("paper-live-shell")).toBeNull();
  });
  it("unknown routes show their path and never fetch data", () => {
    window.history.replaceState({}, "", "/route-inconnue");
    render(<App />);
    expect(screen.getByTestId("not-found-path")).toHaveTextContent(
      "/route-inconnue",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
