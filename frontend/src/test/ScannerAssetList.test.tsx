// CAT SCANNER-UI — S3 : liste des actifs publiés, recherche, filtres et détail par instrument.
// LOCAL TEST FIXTURES ONLY: synthetic publications from scannerUniverseFixtures.ts
// and the replayed spotRadar-scanner.json. Nothing here is runtime evidence.
// A1–A14 refer to the S3 acceptance criteria approved by the operator on 2026-11-25.
// A10 (360/384/412 px, light/dark) needs a real browser: scripts/capture_scanner_assets_s3.mjs.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import scanner from "./fixtures/spotRadar-scanner.json";
import { assetUniverseFixture, inverseAssetFixture, manyAssetsFixture, universeFixture, withSourceAge } from "./scannerUniverseFixtures";
import { ScannerUniverse } from "../views/ScannerUniverse";
import { UNIVERSE_ENDPOINT, universeView, type ScannerUniverse as Universe } from "../lib/scannerUniverseClient";
import { chipCounts, filterAssets, matchAsset, normalizeQuery, parseCoverage, withAssetSearch } from "../lib/scannerAssetSearch";

const RADAR = "/paper-live/market/radar";
const NOW = Number(scanner.server_time_ms);
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
let universe: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  vi.spyOn(Date, "now").mockReturnValue(NOW);
  universe = () => json(assetUniverseFixture());
  fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === UNIVERSE_ENDPOINT) return universe();
    if (url.startsWith("/api/operator/v1/spot-radar/scanner")) return json(scanner);
    return json({ error_code: "LOCAL_TEST_FIXTURE_NOT_CONFIGURED" }, 503);
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

const view = (doc: Universe | null, error: string | null = null) => universeView(doc, error, NOW, NOW);
const show = (doc: Universe | null, error: string | null = null) => render(<ScannerUniverse view={view(doc, error)} />);
const list = () => screen.getByRole("region", { name: "Actifs publiés" });
const rows = () => within(list()).queryAllByRole("button", { name: /ouvrir les instruments$/ });
const bases = () => rows().map(r => r.querySelector("strong")!.textContent);
const chip = (name: RegExp) => within(screen.getByRole("group", { name: "Filtrer par couverture" })).getByRole("button", { name });
const search = () => screen.getByRole("searchbox", { name: "Actif ou symbole" });
const type = (text: string) => fireEvent.change(search(), { target: { value: text } });
const tile = (n: number) => Number(screen.getByTestId(`coverage-tier-${n}`).querySelector(".su-count")!.textContent);

describe("S3 · liste, comptes et filtres", () => {
  it("A1 · la liste contient exactement les actifs publiés et vérifiés, dans l'ordre de la publication", () => {
    const doc = assetUniverseFixture({ now: NOW });
    show(doc);
    expect(bases()).toEqual(doc.assets!.map(a => a.base));
    expect(within(screen.getByRole("list", { name: "Crypto-actifs" })).getAllByRole("button").map(b => b.querySelector("strong")!.textContent)).toEqual(["BTC", "ETH", "DOGE"]);
  });

  it("A2 · « Tous » compte toutes les lignes ; 4/4, 3/4, 2/4 égalent les tuiles ; le nombre filtré est affiché à part", () => {
    show(assetUniverseFixture({ now: NOW }));
    expect(chip(/^Tous,/)).toHaveAccessibleName("Tous, 4 lignes publiées");
    for (const n of [4, 3, 2]) expect(chip(new RegExp(`^${n} marchés sur 4`)).querySelector(".su-chip-count")!.textContent).toBe(String(tile(n)));
    expect(screen.getByTestId("asset-results")).toHaveTextContent("4 résultats · 4 lignes publiées");
    type("eth");
    // Counts come from the verified publication: search changes the result count, not the chips.
    expect(chip(/^Tous,/)).toHaveAccessibleName("Tous, 4 lignes publiées");
    expect(chip(/^3 marchés sur 4/)).toHaveAccessibleName("3 marchés sur 4, 1 crypto-actif");
    expect(screen.getByTestId("asset-results")).toHaveTextContent("1 résultat · 4 lignes publiées");
    type("");
    fireEvent.click(chip(/^4 marchés sur 4/));
    expect(chip(/^4 marchés sur 4/)).toHaveAttribute("aria-pressed", "true");
    expect(bases()).toEqual(["BTC"]);
    // Currencies and stablecoins appear only under « Tous ».
    expect(screen.queryByText(/non comptés dans la couverture/)).toBeNull();
    fireEvent.click(chip(/^2 marchés sur 4/));
    expect(bases()).toEqual(["DOGE"]);
    fireEvent.click(chip(/^Tous,/));
    expect(screen.getByRole("list", { name: "Devises et stablecoins · non comptés dans la couverture" })).toHaveTextContent("USDC");
    expect(chipCounts(assetUniverseFixture().assets!)).toEqual({ all: 4, 4: 1, 3: 1, 2: 1 });
  });

  it("A3 · recherche par base (préfixe) et par symbole natif publié, sans alias inventé ni correspondance approximative", () => {
    const assets = inverseAssetFixture().assets!;
    const [btc, eth] = assets;
    expect(normalizeQuery("  xbt ")).toBe("XBT");
    expect(matchAsset(btc, "BT")).toEqual({ asset: btc, via: null });
    expect(matchAsset(btc, "XBT")).toEqual({ asset: btc, via: "XBTUSD" });
    expect(matchAsset(eth, "PF_ETHUSD")).toEqual({ asset: eth, via: "PF_ETHUSD" });
    expect(matchAsset(btc, "PI_XBT")).toEqual({ asset: btc, via: "PI_XBTUSD" });
    // XDG is a Kraken alias of DOGE in the producer, but no published DOGE symbol contains it.
    expect(filterAssets(assets, "XDG", null)).toEqual({ crypto: [], others: [] });
    expect(filterAssets(assets, "BTX", null).crypto).toEqual([]);
    expect(filterAssets(assets, "TC", null).crypto.map(m => m.asset.base)).toEqual(["BTC"]); // via BTCUSDT, not via the base
    show(inverseAssetFixture({ now: NOW }));
    type("xbt");
    expect(search()).toHaveValue("XBT");
    expect(rows()).toHaveLength(1);
    expect(rows()[0]).toHaveTextContent("via XBTUSD");
    expect(rows()[0]).toHaveAccessibleName("BTC, 4 marchés sur 4, devises USD et USDT, trouvé via XBTUSD, ouvrir les instruments");
  });

  it("A4 · aucun résultat : message explicite, jamais une liste vide muette", () => {
    show(assetUniverseFixture({ now: NOW }));
    type("zzz");
    expect(rows()).toHaveLength(0);
    expect(screen.getByTestId("asset-list-message")).toHaveTextContent("Aucun actif publié ne correspond à « ZZZ ».");
    expect(screen.getByTestId("asset-results")).toHaveTextContent("0 résultat · 4 lignes publiées");
  });
});

describe("S3 · détail par instrument", () => {
  it("A5 · tous les instruments natifs publiés, un par ligne ; USD et USDT séparés ; inverse étiqueté ; marché absent « non négocié »", () => {
    const doc = inverseAssetFixture({ now: NOW });
    show(doc);
    fireEvent.click(screen.getByRole("button", { name: /^BTC, 4 marchés sur 4/ }));
    const dialog = screen.getByRole("dialog", { name: "Instruments BTC" });
    const btc = doc.assets![0];
    const published = Object.values(btc.markets).flat().length;
    expect(within(dialog).getAllByRole("listitem")).toHaveLength(published);
    for (const text of [
      "BTCUSDT · BTC / USDT · Spot · règlement sans objet (Spot)",
      "BTC_USDT · BTC / USDT · Perpétuel linéaire · règlement USDT",
      "XBTUSD · BTC / USD · Spot · règlement sans objet (Spot)",
      "XBTUSDT · BTC / USDT · Spot · règlement sans objet (Spot)",
      "PF_XBTUSD · BTC / USD · Perpétuel linéaire · règlement USD",
      "PI_XBTUSD · BTC / USD · Perpétuel inverse · règlement BTC",
    ]) expect(dialog).toHaveTextContent(text);
    expect(dialog.querySelector('[data-market="KRAKEN_SPOT"]')).toHaveTextContent("Kraken Spot · 2 instruments");
    fireEvent.click(within(dialog).getByRole("button", { name: "Fermer" }));
    fireEvent.click(screen.getByRole("button", { name: /^ETH, 3 marchés sur 4/ }));
    expect(screen.getByRole("dialog", { name: "Instruments ETH" }).querySelector('[data-market="KRAKEN_SPOT"]')).toHaveTextContent("non négocié");
  });
});

describe("S3 · états de la publication", () => {
  it.each([
    ["LOADING", null, null, "Liste en chargement."],
    ["UNAVAILABLE", assetUniverseFixture({ now: NOW, status: "UNVERIFIABLE" }), null, "Liste indisponible : aucun actif n’est présenté comme courant."],
    ["1.0.0 sans assets", universeFixture([["BTC", "USDT"]], { now: NOW }), null, "Non publié par scanner-universe/1.0.0"],
    ["1.1.0 assets vide", { ...assetUniverseFixture({ now: NOW }), assets: [], asset_count: 0 } as Universe, null, "Aucun actif publié sur au moins un Spot et un Perpétuel."],
  ])("A6 · %s : message, aucune ligne, aucun zéro", (_label, doc, error, message) => {
    show(doc as Universe | null, error);
    expect(screen.getByTestId("asset-list-message")).toHaveTextContent(message);
    expect(rows()).toHaveLength(0);
    expect(search()).toBeDisabled();
    for (const c of within(screen.getByRole("group", { name: "Filtrer par couverture" })).getAllByRole("button")) {
      expect(c).toBeDisabled();
      expect(c.querySelector(".su-chip-count")!.textContent).toBe("—");
      expect(c).toHaveAccessibleName(/compte indisponible/);
    }
    expect(screen.queryByTestId("asset-results")).toBeNull();
  });

  it("A6b · une publication qui devient indisponible retire toutes les lignes affichées et ferme le détail", () => {
    const doc = assetUniverseFixture({ now: NOW });
    const { rerender } = render(<ScannerUniverse view={view(doc)} />);
    fireEvent.click(screen.getByRole("button", { name: /^DOGE, 2 marchés sur 4/ }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    rerender(<ScannerUniverse view={view(withSourceAge(doc, "MEXC_SPOT", 3_000_000))} />);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(rows()).toHaveLength(0);
    expect(list()).not.toHaveTextContent("DOGE");
    expect(screen.getByTestId("asset-list-message")).toHaveTextContent("Liste indisponible");
  });

  it("A7 · changement de publication : liste recalculée, recherche conservée, détail fermé si l'actif disparaît", () => {
    const first = assetUniverseFixture({ now: NOW });
    const { rerender } = render(<ScannerUniverse view={view(first)} />);
    type("et");
    expect(bases()).toEqual(["ETH"]);
    fireEvent.click(screen.getByRole("button", { name: /^ETH, 3 marchés sur 4/ }));
    const second = { ...first, assets: [first.assets![0], { ...first.assets![2], base: "ETC", markets: {
      MEXC_SPOT: [{ native_symbol: "ETCUSDT", quote: "USDT", contract_type: "SPOT", settlement_asset: null }],
      MEXC_PERPETUAL: [{ native_symbol: "ETC_USDT", quote: "USDT", contract_type: "LINEAR_PERPETUAL", settlement_asset: "USDT" }] } }], asset_count: 2, universe_sha256: "d".repeat(64) } as Universe;
    rerender(<ScannerUniverse view={view(second)} />);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(search()).toHaveValue("ET");
    expect(bases()).toEqual(["ETC"]);
    expect(chip(/^Tous,/)).toHaveAccessibleName("Tous, 2 lignes publiées");
  });

  it("A9 · plus de 50 actifs : 50 lignes, puis 50 de plus à la demande ; compte total visible", () => {
    show(manyAssetsFixture(120, { now: NOW }));
    expect(screen.getByTestId("asset-results")).toHaveTextContent("120 résultats · 120 lignes publiées");
    expect(rows()).toHaveLength(50);
    fireEvent.click(screen.getByRole("button", { name: "Afficher 50 de plus (70 restants)" }));
    expect(rows()).toHaveLength(100);
    fireEvent.click(screen.getByRole("button", { name: "Afficher 20 de plus (20 restants)" }));
    expect(rows()).toHaveLength(120);
    expect(screen.queryByRole("button", { name: /^Afficher/ })).toBeNull();
    type("SYN1");
    expect(rows()).toHaveLength(21); // bases SYN100–SYN120 (prefix); the page size restarts at 50
  });
});

describe("S3 · accessibilité, réseau, URL et limites", () => {
  it("A11 · puces en groupe avec aria-pressed, lignes en boutons nommés, focus rendu à la ligne", () => {
    show(assetUniverseFixture({ now: NOW }));
    const chips = within(screen.getByRole("group", { name: "Filtrer par couverture" })).getAllByRole("button");
    expect(chips.map(c => c.getAttribute("aria-pressed"))).toEqual(["true", "false", "false", "false"]);
    expect(rows().map(r => r.getAttribute("aria-label"))).toEqual([
      "BTC, 4 marchés sur 4, devises USD et USDT, ouvrir les instruments",
      "ETH, 3 marchés sur 4, devises USD et USDT, ouvrir les instruments",
      "DOGE, 2 marchés sur 4, devise USDT, ouvrir les instruments",
      "USDC, stablecoin, 2 marchés sur 4, devise USDT, ouvrir les instruments",
    ]);
    const eth = rows()[1];
    fireEvent.click(eth);
    fireEvent.click(within(screen.getByRole("dialog", { name: "Instruments ETH" })).getByRole("button", { name: "Fermer" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(eth).toHaveFocus();
  });

  it("A8 · aucune requête réseau en cherchant, filtrant, paginant ou ouvrant un détail", async () => {
    universe = () => json(manyAssetsFixture(60));
    window.history.replaceState({}, "", RADAR);
    render(<App />);
    await waitFor(() => expect(rows()).toHaveLength(50));
    const before = fetchMock.mock.calls.map(([u]) => String(u));
    expect(before.filter(u => u === UNIVERSE_ENDPOINT)).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: /^Afficher 10 de plus/ }));
    type("syn05");
    fireEvent.click(chip(/^2 marchés sur 4/));
    fireEvent.click(rows()[0]);
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Fermer" }));
    expect(fetchMock.mock.calls.map(([u]) => String(u))).toEqual(before);
  });

  it("A13 · q et cov dans l'URL avec replace, product conservé, valeurs bornées et validées", async () => {
    expect(normalizeQuery("<script>alert(1)</script>")).toBe("SCRIPTALERT1/SCRIPT");
    expect(normalizeQuery("a".repeat(50))).toHaveLength(32);
    expect(normalizeQuery("pf_xbt usd")).toBe("PF_XBTUSD");
    expect(normalizeQuery(null)).toBe("");
    expect(["4", "3", "2", "1", "5", "4/4", "", null].map(parseCoverage)).toEqual([4, 3, 2, null, null, null, null, null]);
    expect(withAssetSearch(new URLSearchParams("product=spot-radar&x=1"), "eth", 3).toString()).toBe("product=spot-radar&x=1&q=ETH&cov=3");

    window.history.replaceState({}, "", `${RADAR}?product=spot-radar&q=${encodeURIComponent("xbt usd<>")}&cov=9`);
    const length = window.history.length;
    render(<App />);
    await waitFor(() => expect(rows()).toHaveLength(1));
    await waitFor(() => expect(window.location.search).toBe("?product=spot-radar&q=XBTUSD"));
    expect(search()).toHaveValue("XBTUSD");
    expect(chip(/^Tous,/)).toHaveAttribute("aria-pressed", "true");
    type("e");
    fireEvent.click(chip(/^3 marchés sur 4/));
    await waitFor(() => expect(window.location.search).toBe("?product=spot-radar&q=E&cov=3"));
    expect(bases()).toEqual(["ETH"]);
    type("");
    fireEvent.click(chip(/^Tous,/));
    await waitFor(() => expect(window.location.search).toBe("?product=spot-radar"));
    expect(screen.getByRole("button", { name: "Radar Spot" })).toHaveAttribute("aria-pressed", "true");
    expect(window.history.length).toBe(length);

    cleanup();
    window.history.replaceState({}, "", `${RADAR}?q=${"B".repeat(80)}&cov=2`);
    render(<App />);
    await waitFor(() => expect(window.location.search).toBe(`?q=${"B".repeat(32)}&cov=2`));
  });

  it("A14 · aucune admissibilité, éligibilité, priorité ni score tirés de market_count ; aucun bouton de sélection", () => {
    show(inverseAssetFixture({ now: NOW }));
    const forbidden = /admissib|éligib|eligib|priorit|score|sélectionn|selection|recommand/i;
    expect(list().textContent).not.toMatch(forbidden);
    for (const b of within(list()).getAllByRole("button")) expect(b.getAttribute("aria-label") ?? b.textContent).not.toMatch(forbidden);
    fireEvent.click(rows()[0]);
    const dialog = screen.getByRole("dialog");
    expect(dialog.textContent).not.toMatch(/admissib|éligib|priorit|score|sélectionn/i);
    expect(within(dialog).getAllByRole("button").map(b => b.textContent)).toEqual(["Fermer"]);
    act(() => { fireEvent.click(within(dialog).getByRole("button", { name: "Fermer" })); });
  });
});
