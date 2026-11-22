// M1-C1 (EO-022) — addressable Market navigation.
// LOCAL TEST FIXTURES ONLY: every response below is either a committed test
// fixture replayed unchanged (spotRadar-*.json, intradayS1.json,
// microstructureFixture()) or a 503 carrying the explicit marker
// M1C1_LOCAL_TEST_FIXTURE_NOT_CONFIGURED. Nothing here is runtime evidence.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import scanner from "./fixtures/spotRadar-scanner.json";
import ohlcv from "./fixtures/spotRadar-ohlcv.json";
import intraday from "./fixtures/intradayS1.json";
import { microstructureFixture } from "./marketMicrostructureFixtures";
import { marketProduct } from "../views/MarketView";

const MARKER = "M1C1_LOCAL_TEST_FIXTURE_NOT_CONFIGURED";
const RADAR = "/paper-live/market/radar";
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const serve = (url: string): Response => {
  if (url.startsWith("/api/operator/v1/spot-radar/scanner")) return json(scanner);
  if (url.startsWith("/api/operator/v1/spot-radar/ohlcv")) return json(ohlcv);
  if (url.startsWith("/api/operator/v1/intraday/")) {
    const kind = url.slice("/api/operator/v1/intraday/".length).split("?")[0] as keyof typeof intraday;
    if (kind in intraday) return json(intraday[kind]);
  }
  if (url === "/api/operator/v1/market-microstructure") return json(microstructureFixture());
  return json({ error_code: MARKER }, 503);
};

let fetchMock: ReturnType<typeof vi.fn>;
const urls = () => fetchMock.mock.calls.map((call) => String(call[0]));
// La capture Footprint figée (fichier statique de Microstructure) est nommée à part.
const families = () => [...new Set(urls().map((u) => u.replace(/^\/observations\/footprint\/.*/, "footprint-capture").replace(/^\/api\/operator\/v1\//, "").replace(/^\//, "").replace(/[/?].*$/, "")))].sort();
const at = (path: string) => window.history.replaceState({}, "", path);
const where = () => window.location.pathname + window.location.search;
const tab = (name: string) => screen.getByRole("tab", { name });
const panel = () => screen.getByTestId("market-panel");

beforeEach(() => {
  fetchMock = vi.fn(async (input: RequestInfo | URL) => serve(String(input)));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("M1-C1 deep Market routes", () => {
  const views = [
    ["radar", "Scanner", ["spot-radar"]],
    ["lmi", "Microstructure", ["footprint-capture", "market-microstructure"]],
  ] as const;

  it.each(views)("opens /paper-live/market/%s directly and only that view requests its source", async (slug, label, family) => {
    at("/paper-live/market/" + slug);
    render(<App />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(panel()).toHaveAttribute("data-market-view", slug);
    expect(tab(label)).toHaveAttribute("aria-selected", "true");
    expect(tab(label)).toHaveAttribute("aria-current", "page");
    expect(screen.getAllByRole("tab").filter((t) => t.getAttribute("aria-selected") === "true")).toHaveLength(1);
    expect(screen.getAllByRole("tabpanel")).toHaveLength(1);
    expect(window.location.pathname).toBe("/paper-live/market/" + slug);
    expect(families()).toEqual([...family]);
    expect(urls().some((u) => u.includes("/burn-in"))).toBe(false);
    expect(screen.getByText("Scanner et microstructure")).toBeInTheDocument();
  });

  it.each(["/", "/direction", "/paper-live", "/paper-live/overview", "/paper-live/market", "/paper-live/market/"])(
    "redirects %s to the canonical Radar route without an extra history entry", async (from) => {
      at(from);
      const before = window.history.length;
      render(<App />);
      await waitFor(() => expect(window.location.pathname).toBe(RADAR));
      expect(window.history.length).toBe(before);
      expect(await screen.findByRole("heading", { name: "Scanner classé" })).toBeInTheDocument();
      expect(urls().some((u) => u.includes("/burn-in"))).toBe(false);
    });

  it("keeps /direction/travaux and the other modules on their own routes", async () => {
    at("/paper-live/decisions");
    render(<App />);
    await screen.findByTestId("paper-live-shell");
    expect(window.location.pathname).toBe("/paper-live/decisions");
    expect(screen.queryByTestId("market-workspace")).toBeNull();
    cleanup();
    at("/direction/travaux");
    render(<App />);
    await waitFor(() => expect(window.location.pathname).toBe("/direction/travaux"));
    expect(screen.queryByTestId("market-workspace")).toBeNull();
  });

  it("shows an explicit unknown Market view that loads nothing", async () => {
    at("/paper-live/market/inconnue");
    render(<App />);
    expect(await screen.findByTestId("market-unknown-view")).toHaveTextContent("/paper-live/market/inconnue");
    expect(panel()).toHaveAttribute("data-market-view", "unknown");
    expect(screen.queryByRole("tabpanel")).toBeNull();
    expect(screen.getAllByRole("tab").every((t) => t.getAttribute("aria-selected") === "false")).toBe(true);
    expect(tab("Scanner")).toHaveAttribute("tabindex", "0");
    await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
    expect(urls().filter((u) => u.startsWith("/api/"))).toEqual([]);
  });
});

describe("M1-C1 browser history", () => {
  it("moves between Scanner and Microstructure with browser history, without mounting retired views", async () => {
    at(RADAR);
    render(<App />);
    await screen.findByRole("heading", { name: "Scanner classé" });
    const start = window.history.length;
    fetchMock.mockClear();
    fireEvent.click(tab("Microstructure"));
    await waitFor(() => expect(panel()).toHaveAttribute("data-market-view", "lmi"));
    expect(window.history.length).toBe(start + 1);
    await waitFor(() => expect(families()).toEqual(["footprint-capture", "market-microstructure"]));
    act(() => window.history.back());
    await waitFor(() => expect(panel()).toHaveAttribute("data-market-view", "radar"));
    act(() => window.history.forward());
    await waitFor(() => expect(panel()).toHaveAttribute("data-market-view", "lmi"));
  });

  it.each(["venues", "flow"])("redirects the retired %s bookmark without requesting its sources", async (slug) => {
    at("/paper-live/market/" + slug);
    const before = window.history.length;
    render(<App />);
    await waitFor(() => expect(window.location.pathname).toBe(RADAR));
    expect(window.history.length).toBe(before);
    await screen.findByRole("heading", { name: "Scanner classé" });
    expect(families()).toEqual(["spot-radar"]);
    expect(screen.queryByRole("tab", { name: /Flux|Comparaison des plateformes/ })).toBeNull();
  });
});

describe("M1-C1 historical bookmarks and Radar sub-views", () => {
  // M1-C3 (EO-024): CryptoRadar historique is withdrawn from the Market UI.
  // Was: radar=0 -> "historical" and the three bookmarks below stayed on it.
  // Now: radar=0 is obsolete; it opens Radar Spot (Intraday if intraday=1 too),
  // the parameter is dropped with replace and /api/operator/v1/market is not read.
  it("documents the parameter priority after M1-C3 (intraday=1 / product=intraday > Radar Spot)", () => {
    const p = (q: string) => marketProduct(new URLSearchParams(q));
    expect(p("")).toBe("spot");
    expect(p("radar=0")).toBe("spot");
    expect(p("intraday=1")).toBe("intraday");
    expect(p("radar=0&intraday=1")).toBe("intraday");
    expect(p("product=intraday")).toBe("intraday");
    expect(p("radar=0&product=intraday")).toBe("intraday");
    expect(p("radar=1")).toBe("spot");
    expect(p("product=autre")).toBe("spot");
  });

  it.each(["/paper-live/market?radar=0", "/?radar=0", "/direction?radar=0", RADAR + "?radar=0"])(
    "opens Radar Spot from the old %s bookmark, without history entry or historical source", async (from) => {
      at(from);
      const before = window.history.length;
      render(<App />);
      await waitFor(() => expect(where()).toBe(RADAR));
      expect(window.history.length).toBe(before);
      expect(screen.queryByRole("button", { name: "CryptoRadar historique" })).toBeNull();
      expect(screen.getByRole("button", { name: "Scanner classé" })).toHaveAttribute("aria-pressed", "true");
      await screen.findByRole("heading", { name: "Scanner classé" });
      await waitFor(() => expect(families()).toEqual(["spot-radar"]));
    });

  it.each(["/paper-live/market?intraday=1", RADAR + "?product=intraday", "/paper-live/market?radar=0&intraday=1"])(
    "opens Intraday from %s", async (from) => {
      at(from);
      render(<App />);
      await waitFor(() => expect(window.location.pathname).toBe(RADAR));
      expect(screen.getByRole("button", { name: "Bulles Intraday" })).toHaveAttribute("aria-pressed", "true");
      await waitFor(() => expect(families()).toEqual(["spot-radar"]));
      expect(new URLSearchParams(window.location.search).get("radar") ?? "").not.toBe("1");
    });

  it("offers ranked, intraday and Radar Spot views, keeps the choice across views, without new history entries", async () => {
    at(RADAR);
    render(<App />);
    await screen.findByRole("heading", { name: "Scanner classé" });
    expect(within(screen.getByRole("group", { name: "Produit du scanner" })).getAllByRole("button").map((b) => b.textContent)).toEqual(["Scanner classé", "Bulles Intraday", "Radar Spot"]);
    const before = window.history.length;
    fireEvent.click(screen.getByRole("button", { name: "Bulles Intraday" }));
    await waitFor(() => expect(where()).toBe(RADAR + "?product=intraday"));
    expect(window.history.length).toBe(before);
    await waitFor(() => expect(families()).toEqual(["spot-radar"]));
    fireEvent.click(tab("Microstructure"));
    await waitFor(() => expect(window.location.pathname).toBe("/paper-live/market/lmi"));
    expect(tab("Scanner")).toHaveAttribute("href", RADAR + "?product=intraday");
    fireEvent.click(tab("Scanner"));
    await waitFor(() => expect(where()).toBe(RADAR + "?product=intraday"));
    fireEvent.click(screen.getByRole("button", { name: "Scanner classé" }));
    await waitFor(() => expect(where()).toBe(RADAR));
    expect(families()).not.toContain("market");
  });

  it("keeps the Radar detail dialog without history entry, closes it with Escape and restores focus", async () => {
    at(RADAR);
    render(<App />);
    const bubble = await screen.findByRole("button", { name: /^BTC\/USDT$/ });
    const before = window.history.length;
    bubble.focus();
    fireEvent.click(bubble);
    const dialog = await screen.findByRole("dialog");
    expect(window.history.length).toBe(before);
    expect(where()).toBe(RADAR);
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(bubble);
  });

  it("keeps the Intraday detail dialog working inside the Radar route", async () => {
    at(RADAR + "?product=intraday");
    render(<App />);
    const trigger = await screen.findByRole("button", { name: /^DOGE\/USDT/ });
    const before = window.history.length;
    trigger.focus();
    fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog");
    expect(window.history.length).toBe(before);
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});

describe("M1-C1 keyboard and links", () => {
  it("moves with arrows, Home and End, keeps one focusable tab and returns focus to the chosen tab", async () => {
    at(RADAR);
    render(<App />);
    await screen.findByRole("heading", { name: "Scanner classé" });
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["Scanner", "Microstructure"]);
    expect(tabs.map((t) => t.getAttribute("tabindex"))).toEqual(["0", "-1"]);
    expect(screen.getByRole("tablist", { name: "Vues du marché" })).toBeInTheDocument();
    tab("Scanner").focus();
    fireEvent.keyDown(tab("Scanner"), { key: "ArrowRight" });
    await waitFor(() => expect(window.location.pathname).toBe("/paper-live/market/lmi"));
    await waitFor(() => expect(tab("Microstructure")).toHaveFocus());
    expect(tab("Microstructure")).toHaveAttribute("tabindex", "0");
    fireEvent.keyDown(tab("Microstructure"), { key: "End" });
    await waitFor(() => expect(window.location.pathname).toBe("/paper-live/market/lmi"));
    await waitFor(() => expect(tab("Microstructure")).toHaveFocus());
    fireEvent.keyDown(tab("Microstructure"), { key: "ArrowRight" });
    await waitFor(() => expect(window.location.pathname).toBe(RADAR));
    await waitFor(() => expect(tab("Scanner")).toHaveFocus());
    fireEvent.keyDown(tab("Scanner"), { key: "ArrowLeft" });
    await waitFor(() => expect(tab("Microstructure")).toHaveFocus());
    fireEvent.keyDown(tab("Microstructure"), { key: "Home" });
    await waitFor(() => expect(window.location.pathname).toBe(RADAR));
    await waitFor(() => expect(tab("Scanner")).toHaveFocus());
    const before = window.history.length;
    fireEvent.keyDown(tab("Scanner"), { key: "Home" });
    fireEvent.keyDown(tab("Scanner"), { key: " " });
    expect(window.history.length).toBe(before);
    expect(tab("Scanner")).toHaveFocus();
  });

  it("points Accueil and the brand at the canonical Radar route; Marché keeps the active state", async () => {
    at("/paper-live/market/lmi");
    render(<App />);
    await waitFor(() => expect(panel()).toHaveAttribute("data-market-view", "lmi"));
    const nav = screen.getByRole("navigation", { name: "Modules de la machine" });
    const home = within(nav).getByRole("link", { name: "Accueil" });
    expect(home).toHaveAttribute("href", RADAR);
    expect(screen.getByRole("link", { name: /Crypto AI Terminal/ })).toHaveAttribute("href", RADAR);
    expect(screen.getByTestId("tab-market")).toHaveAttribute("aria-current", "page");
    fireEvent.click(home);
    await waitFor(() => expect(window.location.pathname).toBe(RADAR));
    expect(home).not.toHaveAttribute("aria-current", "page");
    expect(home.className).not.toContain("is-active");
    expect(screen.getByTestId("tab-market")).toHaveAttribute("aria-current", "page");
    fireEvent.click(screen.getByTestId("tab-decisions"));
    await waitFor(() => expect(window.location.pathname).toBe("/paper-live/decisions"));
    fireEvent.click(screen.getByRole("link", { name: /Crypto AI Terminal/ }));
    await waitFor(() => expect(window.location.pathname).toBe(RADAR));
    expect(urls().some((u) => u.includes("/burn-in"))).toBe(false);
  });
});
