// Scanner V1 — common MEXC × Kraken universe in Marché → Scanner.
// LOCAL TEST FIXTURES ONLY: spotRadar-scanner.json replayed unchanged plus the
// synthetic universe of scannerUniverseFixtures.ts. Nothing here is runtime evidence.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import scanner from "./fixtures/spotRadar-scanner.json";
import bbo from "./fixtures/bboCompositeHistory-synthetic.json";
import { assetUniverseFixture, universeFixture } from "./scannerUniverseFixtures";
import { validateUniverse, universeView, admittedMexcSpot, UniverseError } from "../lib/scannerUniverseClient";

const RADAR = "/paper-live/market/radar";
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
let universe: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  vi.spyOn(Date, "now").mockReturnValue(Number(scanner.server_time_ms));
  universe = () => json(universeFixture([["BTC", "USDT"]]));
  fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/operator/v1/scanner-universe") return universe();
    if (url.startsWith("/api/operator/v1/spot-radar/scanner")) return json(scanner);
    if (url === "/api/operator/v1/bbo-composite-history") return json({ ...structuredClone(bbo), serving: { freshness_classification: "HISTORICAL_NOT_LIVE" } });
    return json({ error_code: "LOCAL_TEST_FIXTURE_NOT_CONFIGURED" }, 503);
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
const openHistory = (summary: HTMLElement) => { const d = summary.closest("details")!; act(() => { d.open = true; d.dispatchEvent(new Event("toggle")); }); };
const open = (search = "") => { window.history.replaceState({}, "", RADAR + search); render(<App />); };

describe("client contract", () => {
  it("accepts a verified, an empty and an unverifiable publication", () => {
    expect(validateUniverse(JSON.parse(JSON.stringify(universeFixture([["BTC", "USDT"]])))).status).toBe("VERIFIED");
    expect(validateUniverse(JSON.parse(JSON.stringify(universeFixture([])))).status).toBe("VERIFIED_EMPTY");
    expect(validateUniverse(JSON.parse(JSON.stringify(universeFixture([], { status: "UNVERIFIABLE" })))).pairs).toEqual([]);
  });
  it("refuses a pair with three proofs, a mixed quote or an empty universe with a missing source", () => {
    const three = universeFixture([["BTC", "USDT"]]) as unknown as { pairs: { proofs: Record<string, unknown> }[] };
    delete three.pairs[0].proofs.KRAKEN_PERPETUAL;
    expect(() => validateUniverse(three)).toThrow(UniverseError);
    const mixed = universeFixture([["BTC", "USDT"]]);
    (mixed.pairs[0].proofs.KRAKEN_PERPETUAL as { quote: string }).quote = "USD";
    expect(() => validateUniverse(mixed)).toThrow(UniverseError);
    const fakeEmpty = { ...universeFixture([], { status: "UNVERIFIABLE" }), status: "VERIFIED_EMPTY" };
    expect(() => validateUniverse(fakeEmpty)).toThrow(UniverseError);
  });
  it("withdraws the current list once a source exceeds the published bound or the read is too old", () => {
    const now = 1_000_000_000_000;
    const doc = universeFixture([["BTC", "USDT"]], { now, ageMs: 2_000_000 });
    expect(universeView(doc, null, now, now).state).toBe("VERIFIED");
    const later = universeView(doc, null, now, now + 100_001);
    expect(later.state).toBe("UNAVAILABLE");
    expect(admittedMexcSpot(later).size).toBe(0);
    expect(universeView(universeFixture([["BTC", "USDT"]], { now }), null, now, now + 181_000).state).toBe("UNAVAILABLE");
    expect(universeView(doc, "HTTP_503", now, now).state).toBe("UNAVAILABLE");
  });
});

describe("Marché → Scanner", () => {
  it("lists a verified pair with its four markets and its native proofs", async () => {
    open();
    const list = await screen.findByRole("list", { name: "Paires vérifiées sur quatre marchés" });
    const row = within(list).getByRole("button", { name: /^BTC\/USDT · vérifiée sur MEXC Spot, MEXC Perpétuel, Kraken Spot, Kraken Perpétuel/ });
    expect(row).toHaveTextContent("✓ MX·S✓ MX·P✓ KR·S✓ KR·P");
    fireEvent.click(row);
    const dialog = await screen.findByRole("dialog", { name: "Preuves BTC/USDT" });
    for (const native of ["BTCUSDT", "BTC_USDT", "XBTUSDT", "PF_BTCUSDT"]) expect(dialog).toHaveTextContent(native);
    expect(dialog).toHaveTextContent(/Relevé \d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC/);
  });

  it.each([
    ["Moniteur de marché", ""],
    ["Radar Spot", "?product=spot-radar"],
  ])("keeps a three-market pair out of %s", async (_label, search) => {
    open(search);
    await screen.findByText(/1 paire vérifiée/);
    await waitFor(() => expect(screen.getAllByRole("button", { name: /^BTC\/USDT/ }).length).toBeGreaterThan(1));
    // DOGE, ATOM… are observed by Radar Spot but not admitted by the four-market universe.
    expect(screen.queryByRole("button", { name: /^DOGE\/USDT/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /^ATOM\/USDT/ })).toBeNull();
    expect(screen.queryByText("DOGE/USDT")).toBeNull();
  });

  it("shows only live admitted pairs with « Live seulement »", async () => {
    open();
    const table = await screen.findByRole("table", { name: "Paires du moniteur" });
    fireEvent.click(screen.getByRole("button", { name: "Live seulement" }));
    expect(within(table).getAllByRole("button").map(b => b.textContent)).toEqual(["BTC/USDT"]);
    expect(within(table).getByRole("button", { name: "BTC/USDT" }).closest("td")).toHaveTextContent(/Fraîche · \d+ s/);
    expect(screen.queryByText("DOGE/USDT")).toBeNull();
  });

  it("shows no live row when the universe is empty or the feed is not live", async () => {
    universe = () => json(universeFixture([]));
    open();
    await screen.findByText("Univers commun vide vérifié : aucune ligne n’est affichée.");
    expect(screen.queryByRole("table", { name: "Paires du moniteur" })).toBeNull();
  });

  it("keeps a non-admitted pair out of the historical composite tab", async () => {
    open("?product=spot-radar");
    await screen.findByText(/1 paire vérifiée/);
    openHistory(await screen.findByText("Composite historique · aperçu hors live"));
    const group = await screen.findByRole("group", { name: "Paire historique" });
    expect(within(group).getByRole("button", { name: "BTC/USDT" })).toBeInTheDocument();
    expect(within(group).queryByRole("button", { name: /ATOM/ })).toBeNull();
  });

  it("hides the historical composite entirely when the universe is unavailable", async () => {
    universe = () => json(universeFixture([], { status: "UNVERIFIABLE" }));
    open("?product=spot-radar");
    await screen.findByText(/Univers indisponible/);
    openHistory(await screen.findByText("Composite historique · aperçu hors live"));
    await screen.findByText("Composite de milieux de carnet · Spot · Historique");
    expect(screen.queryByRole("group", { name: "Paire historique" })).toBeNull();
  });

  it("names the failed source and withdraws every current row", async () => {
    universe = () => json(universeFixture([], { status: "UNVERIFIABLE", blocked: "KRAKEN_PERPETUAL" }));
    open();
    const alert = await screen.findByText(/Univers indisponible/);
    expect(alert.closest("p")).toHaveTextContent("Kraken Perpétuel : catalogue inaccessible (HTTP_503)");
    expect(screen.getByText(/Dernière liste vérifiée, /)).toHaveTextContent("non courante");
    await screen.findByText("Univers commun indisponible : aucune ligne n’est présentée comme courante.");
    expect(screen.queryByRole("button", { name: /^BTC\/USDT/ })).toBeNull();
    expect(screen.queryByRole("list", { name: "Paires vérifiées sur quatre marchés" })).toBeNull();
  });

  it("shows a verified empty universe apart from an unavailable one", async () => {
    universe = () => json(universeFixture([]));
    open();
    expect(await screen.findByText(/Univers vide vérifié/)).toBeInTheDocument();
    expect(screen.queryByText(/Univers indisponible/)).toBeNull();
    await screen.findByText("Univers commun vide vérifié : aucune ligne n’est affichée.");
    expect(screen.queryByRole("button", { name: /^BTC\/USDT/ })).toBeNull();
  });

  it("keeps the synthetic signals demo apart from a verified empty strict universe, without any signals request", async () => {
    universe = () => json(universeFixture([]));
    open("?product=signals-demo");
    expect(await screen.findByText(/Univers vide vérifié/)).toBeInTheDocument();
    const demo = screen.getByRole("region", { name: "Radar de signaux" });
    expect(within(demo).getByRole("note")).toHaveTextContent("Données SYNTHÉTIQUES · cat.signals.indicators.v1");
    expect(within(demo).getByRole("table", { name: "Indicateurs BTC" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Moniteur de marché" }));
    await screen.findByText("Univers commun vide vérifié : aucune ligne n’est affichée.");
    expect(screen.queryByRole("button", { name: /^BTC\/USDT/ })).toBeNull();
    expect(screen.queryByRole("region", { name: "Radar de signaux" })).toBeNull();
    expect(fetchMock.mock.calls.map(([u]) => String(u)).filter(u => /signal/i.test(u))).toEqual([]);
  });

  it("treats an unconfigured or failing universe source as unavailable, never as empty", async () => {
    universe = () => json({ error_code: "SCANNER_UNIVERSE_NOT_CONFIGURED" }, 503);
    open();
    expect(await screen.findByText(/Univers indisponible/)).toBeInTheDocument();
    expect(screen.queryByText(/Univers vide vérifié/)).toBeNull();
    expect(screen.queryByRole("button", { name: /^BTC\/USDT/ })).toBeNull();
  });

  describe("by base asset (scanner-universe/1.1.0)", () => {
    it("validates the asset groups and refuses merged or premature ones", () => {
      const doc = JSON.parse(JSON.stringify(assetUniverseFixture()));
      expect(validateUniverse(doc).assets).toHaveLength(4);
      const spotOnly = JSON.parse(JSON.stringify(doc)); spotOnly.assets[2].markets = { MEXC_SPOT: spotOnly.assets[2].markets.MEXC_SPOT }; spotOnly.assets[2].market_count = 1;
      expect(() => validateUniverse(spotOnly)).toThrow(UniverseError);
      const merged = JSON.parse(JSON.stringify(doc)); merged.assets[0].quotes = ["USDT"];
      expect(() => validateUniverse(merged)).toThrow(UniverseError);
      const premature = { ...JSON.parse(JSON.stringify(assetUniverseFixture({ status: "UNVERIFIABLE" }))), assets: doc.assets, asset_count: 4 };
      expect(() => validateUniverse(premature)).toThrow(UniverseError);
    });

    it("counts assets per number of markets and keeps the strict pair count apart", async () => {
      universe = () => json(assetUniverseFixture());
      open();
      expect((await screen.findByText(/1 crypto-actif sur les 4 marchés/)).closest("p")).toHaveTextContent("1 crypto-actif sur les 4 marchés · 1 sur 3 · 1 sur 2");
      expect(screen.getByText(/devise et stablecoin|devises et stablecoins/)).toHaveTextContent("1 devise et stablecoin, non comptés");
      expect(screen.getByText(/Paires strictes/)).toHaveTextContent("Paires strictes (même devise sur les 4 marchés) : 0.");
      expect(screen.queryByText(/Univers vide vérifié/)).toBeNull();
      fireEvent.click(within(screen.getByRole("list", { name: "Actifs sur les quatre marchés" })).getByRole("button", { name: /^BTC · 4 marchés · devises USD, USDT/ }));
      const dialog = await screen.findByRole("dialog", { name: "Instruments BTC" });
      for (const text of ["BTCUSDT · USDT", "BTC_USDT · USDT", "XBTUSD · USD", "XBTUSDT · USDT", "PF_XBTUSD · USD"]) expect(dialog).toHaveTextContent(text);
    });

    it("shows observed MEXC Spot rows of published assets with their market count, and nothing else", async () => {
      universe = () => json(assetUniverseFixture());
      open();
      await screen.findByText(/admis par actif/);
      const table = await screen.findByRole("table");
      const btc = within(table).getByRole("button", { name: "BTC/USDT" }).closest("td")!;
      expect(btc).toHaveTextContent("4/4");
      expect(within(table).getByRole("button", { name: "DOGE/USDT" }).closest("td")).toHaveTextContent("2/4");
      expect(within(table).getByRole("button", { name: "USDC/USDT" }).closest("td")).toHaveTextContent("stablecoin · 2/4");
      expect(within(table).queryByRole("button", { name: "ATOM/USDT" })).toBeNull();
    });

    it("withdraws every asset row when a source is unavailable", async () => {
      universe = () => json(assetUniverseFixture({ status: "UNVERIFIABLE" }));
      open();
      await screen.findByText(/Univers indisponible/);
      await screen.findByText("Univers commun indisponible : aucune ligne n’est présentée comme courante.");
      expect(screen.queryByRole("table", { name: "Paires du moniteur" })).toBeNull();
    });
  });
});
