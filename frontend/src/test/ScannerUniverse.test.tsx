// Scanner V1 — common MEXC × Kraken universe in Marché → Scanner.
// LOCAL TEST FIXTURES ONLY: spotRadar-scanner.json replayed unchanged plus the
// synthetic universe of scannerUniverseFixtures.ts. Nothing here is runtime evidence.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import scanner from "./fixtures/spotRadar-scanner.json";
import bbo from "./fixtures/bboCompositeHistory-synthetic.json";
import { universeFixture } from "./scannerUniverseFixtures";
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
    ["Classement du jour", ""],
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

  it("shows only live admitted pairs in the Terminal live", async () => {
    open("?product=live");
    const table = await screen.findByRole("table", { name: "Paires live" });
    expect(within(table).getAllByRole("rowheader").map(h => h.textContent)).toEqual(["BTC/USDT"]);
    expect(screen.getByText(/● LIVE · 1 paire/)).toBeInTheDocument();
    expect(screen.queryByText("DOGE/USDT")).toBeNull();
  });

  it("shows no live row when the universe is empty or the feed is not live", async () => {
    universe = () => json(universeFixture([]));
    open("?product=live");
    await screen.findByText("Univers commun vide vérifié : aucune ligne n’est affichée.");
    expect(screen.queryByRole("table", { name: "Paires live" })).toBeNull();
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
    fireEvent.click(screen.getByRole("button", { name: "Classement du jour" }));
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
});
