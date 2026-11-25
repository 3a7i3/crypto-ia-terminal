// CAT SCANNER-UI — Mission S2 : tableau de bord mobile de l'univers des marchés.
// LOCAL TEST FIXTURES ONLY: synthetic publications from scannerUniverseFixtures.ts
// and the replayed spotRadar-scanner.json. Nothing here is runtime evidence.
// The page layout checks at 360/384/412 px (no horizontal scroll, touch targets)
// need a real browser: scripts/capture_scanner_dashboard_s2.mjs.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import scanner from "./fixtures/spotRadar-scanner.json";
import bbo from "./fixtures/bboCompositeHistory-synthetic.json";
import { assetUniverseFixture, universeFixture, withSourceAge } from "./scannerUniverseFixtures";
import { ScannerUniverse, SOURCE_ORDER, ageLabel } from "../views/ScannerUniverse";
import { MARKET_LABEL, UNIVERSE_ENDPOINT, universeView, type ScannerUniverse as Universe } from "../lib/scannerUniverseClient";

const RADAR = "/paper-live/market/radar";
const NOW = Number(scanner.server_time_ms);
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
let universe: () => Response | Promise<Response>;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  vi.spyOn(Date, "now").mockReturnValue(NOW);
  universe = () => json(universeFixture([["BTC", "USDT"]]));
  fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === UNIVERSE_ENDPOINT) return universe();
    if (url.startsWith("/api/operator/v1/spot-radar/scanner")) return json(scanner);
    if (url === "/api/operator/v1/bbo-composite-history") return json({ ...structuredClone(bbo), serving: { freshness_classification: "HISTORICAL_NOT_LIVE" } });
    return json({ error_code: "LOCAL_TEST_FIXTURE_NOT_CONFIGURED" }, 503);
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
const open = (search = "") => { window.history.replaceState({}, "", RADAR + search); render(<App />); };
const dashboard = () => screen.getByRole("region", { name: "Scanner scientifique" });
const settled = async () => waitFor(() => expect(dashboard()).not.toHaveAttribute("data-state", "LOADING"));
const card = (market: keyof typeof MARKET_LABEL) => within(screen.getByRole("list", { name: "État des quatre sources" })).getByRole("listitem", { name: new RegExp(`^${MARKET_LABEL[market]} :`) });
const universeCalls = () => fetchMock.mock.calls.filter(([u]) => String(u) === UNIVERSE_ENDPOINT).length;
const pill = () => dashboard().querySelector(".su-pill")!;

describe("S2 · en-tête et quatre sources", () => {
  it("1 · univers vérifié : statut, horodatage, nature des données, quatre sources fraîches dans l'ordre demandé", async () => {
    open();
    await settled();
    expect(screen.getByRole("heading", { level: 2, name: "Scanner scientifique" })).toBeInTheDocument();
    expect(pill()).toHaveTextContent("Vérifié");
    expect(dashboard().querySelector(".su-checked")).toHaveTextContent(/^Dernier relevé vérifié : \d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC · il y a 0 s$/);
    expect(dashboard().querySelector(".su-nature")).toHaveTextContent("Catalogues d’instruments");
    expect(dashboard().querySelector(".su-nature")).toHaveTextContent("Fraîcheur des catalogues, pas des prix : aucune cotation LIVE.");
    const items = within(screen.getByRole("list", { name: "État des quatre sources" })).getAllByRole("listitem");
    expect(items.map(li => li.getAttribute("aria-label"))).toEqual(SOURCE_ORDER.map(m => `${MARKET_LABEL[m]} : Disponible`));
    expect(SOURCE_ORDER).toEqual(["KRAKEN_SPOT", "KRAKEN_PERPETUAL", "MEXC_SPOT", "MEXC_PERPETUAL"]);
    for (const li of items) expect(li).toHaveTextContent(/^.+DisponibleRelevé il y a 1 min · \d\d:\d\d UTC$/);
    expect(screen.getByText("Détail des sources et de la publication").closest("details")).toHaveTextContent("100 instruments · 90 admissibles");
    // Strict pairs are published; asset groups are not part of schema 1.0.0 (never a zero).
    expect(screen.getByTestId("coverage-strict")).toHaveTextContent(/1$/);
    for (const n of [4, 3, 2]) expect(screen.getByTestId(`coverage-tier-${n}`)).toHaveTextContent(`Sur ${n} marchésNon publié`);
    expect(screen.getByText(/1 paire vérifiée/)).toBeInTheDocument();
  });

  it("2 · 1.1.0 : zéro paire stricte et des actifs multi-marchés sont deux faits séparés", async () => {
    universe = () => json(assetUniverseFixture());
    open();
    await settled();
    expect(pill()).toHaveTextContent("Vérifié · strict vide");
    for (const [n, v] of [[4, 1], [3, 1], [2, 1]]) expect(screen.getByTestId(`coverage-tier-${n}`)).toHaveTextContent(`Sur ${n} marchés${v}`);
    expect(screen.getByTestId("coverage-strict")).toHaveTextContent(/0$/);
    const why = screen.getByText("Aucune paire stricte").closest("p")!;
    expect(why).toHaveTextContent("aucune paire n’a la même devise de cotation sur les quatre marchés");
    expect(why).toHaveTextContent("Les actifs multi-marchés sont comptés à part");
    expect(screen.getByText(/crypto-actifs au total/)).toHaveTextContent("3 crypto-actifs au total · 1 devise et stablecoin non compté.");
    expect(screen.queryByText(/Univers vide vérifié/)).toBeNull();
    expect(screen.queryByText(/Univers indisponible/)).toBeNull();
  });

  it("3 · une source indisponible : motif sur sa carte, comptes indisponibles et jamais zéro", async () => {
    universe = () => json(assetUniverseFixture({ status: "UNVERIFIABLE" }));
    open();
    await settled();
    expect(pill()).toHaveTextContent("Indisponible");
    expect(card("KRAKEN_PERPETUAL")).toHaveAttribute("aria-label", "Kraken Perpétuel : Indisponible");
    expect(card("KRAKEN_PERPETUAL")).toHaveTextContent("catalogue inaccessible (HTTP_503)");
    expect(card("KRAKEN_PERPETUAL")).toHaveTextContent("Relevé : non disponible");
    for (const m of ["KRAKEN_SPOT", "MEXC_SPOT", "MEXC_PERPETUAL"] as const) expect(card(m)).toHaveAttribute("aria-label", `${MARKET_LABEL[m]} : Disponible`);
    expect(screen.getByRole("alert")).toHaveTextContent("Univers indisponible · Kraken Perpétuel : catalogue inaccessible (HTTP_503). Aucune paire n’est présentée comme courante.");
    for (const n of [4, 3, 2]) expect(screen.getByTestId(`coverage-tier-${n}`)).toHaveTextContent(`Sur ${n} marchésIndisponible`);
    expect(screen.getByTestId("coverage-strict")).toHaveTextContent(/Indisponible$/);
    expect(screen.queryByText(/^0$/)).toBeNull();
    expect(dashboard().querySelector(".su-checked")).toHaveTextContent(/Dernier relevé vérifié : .* UTC · non courant/);
  });

  it("4 · une source périmée : carte « Périmée », statut global et liste retirée", async () => {
    universe = () => json(withSourceAge(universeFixture([["BTC", "USDT"]]), "MEXC_PERPETUAL", 2_200_000));
    open();
    await settled();
    expect(pill()).toHaveTextContent("Source périmée");
    expect(card("MEXC_PERPETUAL")).toHaveAttribute("aria-label", "MEXC Perpétuel : Périmée");
    expect(card("MEXC_PERPETUAL")).toHaveTextContent("Relevé il y a 36 min");
    expect(card("MEXC_PERPETUAL")).toHaveTextContent("relevé plus vieux que la limite (35 min)");
    expect(card("KRAKEN_SPOT")).toHaveAttribute("aria-label", "Kraken Spot : Disponible");
    expect(screen.getByRole("alert")).toHaveTextContent("Univers indisponible · MEXC Perpétuel : relevé périmé.");
    expect(screen.getByTestId("coverage-strict")).toHaveTextContent(/Indisponible$/);
    expect(screen.queryByRole("list", { name: "Paires vérifiées sur quatre marchés" })).toBeNull();
    expect(dashboard().querySelector(".su-checked")).toHaveTextContent(/UTC · plus courant$/);
  });

  it("4b · une publication fraîche devient périmée avec le temps, sans nouvelle requête", () => {
    const doc = withSourceAge(universeFixture([["BTC", "USDT"]], { now: NOW }), "KRAKEN_SPOT", 2_050_000);
    const { rerender } = render(<ScannerUniverse view={universeView(doc, null, NOW, NOW)} />);
    expect(card("KRAKEN_SPOT")).toHaveAttribute("aria-label", "Kraken Spot : Disponible");
    rerender(<ScannerUniverse view={universeView(doc, null, NOW, NOW + 60_000)} />);
    expect(card("KRAKEN_SPOT")).toHaveAttribute("aria-label", "Kraken Spot : Périmée");
    expect(pill()).toHaveTextContent("Source périmée");
    rerender(<ScannerUniverse view={universeView(universeFixture([["BTC", "USDT"]], { now: NOW }), null, NOW, NOW + 181_000)} />);
    expect(pill()).toHaveTextContent("Publication trop ancienne");
    expect(card("KRAKEN_SPOT")).toHaveAttribute("aria-label", "Kraken Spot : Non confirmée");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("5 · publication invalide : refusée, sources inconnues, aucun compte affiché", async () => {
    const bad = universeFixture([["BTC", "USDT"]]) as unknown as { pairs: { proofs: Record<string, unknown> }[] };
    delete bad.pairs[0].proofs.KRAKEN_SPOT;
    universe = () => json(bad);
    open();
    await settled();
    expect(pill()).toHaveTextContent("Publication invalide");
    expect(screen.getByRole("alert")).toHaveTextContent("Univers indisponible · publication invalide (contrat scanner-universe non respecté).");
    for (const m of SOURCE_ORDER) expect(card(m)).toHaveAttribute("aria-label", `${MARKET_LABEL[m]} : Inconnue`);
    for (const n of [4, 3, 2]) expect(screen.getByTestId(`coverage-tier-${n}`)).toHaveTextContent("Indisponible");
    expect(screen.getByTestId("coverage-strict")).toHaveTextContent(/Indisponible$/);
    expect(screen.queryByRole("button", { name: /^BTC\/USDT/ })).toBeNull();
    expect(dashboard().querySelector(".su-checked")).toHaveTextContent("Dernier relevé vérifié : aucun relevé courant");
  });

  it("chargement : sources inconnues et comptes « En chargement », jamais zéro", async () => {
    universe = () => new Promise<Response>(() => undefined);
    open();
    expect(await screen.findByText("Chargement de l’univers commun…")).toBeInTheDocument();
    expect(pill()).toHaveTextContent("Chargement");
    for (const m of SOURCE_ORDER) expect(card(m)).toHaveTextContent("publication en cours de lecture");
    expect(screen.getByTestId("coverage-strict")).toHaveTextContent(/En chargement$/);
  });
});

describe("S2 · changement de publication", () => {
  it("6 · le sondage suivant remplace comptes, horodatages et sources sans mélanger les publications", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    universe = () => json(assetUniverseFixture());
    open();
    await settled();
    expect(screen.getByTestId("coverage-tier-4")).toHaveTextContent("Sur 4 marchés1");
    const before = dashboard().querySelector(".su-checked")!.textContent;
    // Next publication: computed 15 min later, with one strict pair and no asset group (1.0.0).
    const next = universeFixture([["SOL", "USDT"]], { now: NOW + 900_000 });
    universe = () => json(next);
    await act(async () => { vi.advanceTimersByTime(60_000); });
    await waitFor(() => expect(pill()).toHaveTextContent("Vérifié"));
    await waitFor(() => expect(screen.getByTestId("coverage-strict")).toHaveTextContent(/1$/));
    expect(screen.getByTestId("coverage-tier-4")).toHaveTextContent("Non publié");
    expect(dashboard().querySelector(".su-checked")!.textContent).not.toBe(before);
    expect(screen.getByRole("list", { name: "Paires vérifiées sur quatre marchés" })).toHaveTextContent("SOL/USDT");
    expect(screen.queryByRole("list", { name: "Actifs sur les quatre marchés" })).toBeNull();
    expect(universeCalls()).toBe(2);
  });

  it("6b · un détail ouvert se ferme si son actif disparaît de la nouvelle publication", () => {
    const first = assetUniverseFixture({ now: NOW });
    const { rerender } = render(<ScannerUniverse view={universeView(first, null, NOW, NOW)} />);
    fireEvent.click(screen.getByRole("button", { name: /^BTC · 4 marchés/ }));
    expect(screen.getByRole("dialog", { name: "Instruments BTC" })).toBeInTheDocument();
    const second = { ...first, assets: first.assets!.filter(a => a.base !== "BTC"), asset_count: 3, universe_sha256: "d".repeat(64) } as Universe;
    rerender(<ScannerUniverse view={universeView(second, null, NOW, NOW)} />);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByTestId("coverage-tier-4")).toHaveTextContent("Sur 4 marchés0");
    expect(screen.getByText("d".repeat(64))).toBeInTheDocument();
  });
});

describe("S2 · navigation mobile, réseau et anciennes vues", () => {
  it("7 · l'essentiel précède les détails ; détails et preuves s'ouvrent au toucher et rendent le focus", async () => {
    universe = () => json(assetUniverseFixture());
    open();
    await settled();
    const order = [".su-head", ".su-sources", ".su-coverage", ".su-details"].map(sel => dashboard().querySelector(sel)!);
    for (let i = 1; i < order.length; i++) expect(order[i - 1].compareDocumentPosition(order[i]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // The universe dashboard comes before the sub-view switch and its long lists.
    const choice = screen.getByRole("group", { name: "Produit du scanner" });
    expect(dashboard().compareDocumentPosition(choice) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    for (const d of dashboard().querySelectorAll("details")) expect(d.open).toBe(false);
    const sources = screen.getByText("Détail des sources et de la publication");
    fireEvent.click(sources);
    const detail = sources.closest("details")!;
    expect(detail).toHaveTextContent("Kraken Perpétuel");
    expect(detail).toHaveTextContent("scanner-universe/1.1.0 · statut publié VERIFIED_EMPTY");
    expect(detail).toHaveTextContent(/Relevé \d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC · âge 1 min/);
    const doge = screen.getByRole("button", { name: /DOGE/ });
    fireEvent.click(doge);
    const dialog = screen.getByRole("dialog", { name: "Instruments DOGE" });
    expect(dialog).toHaveTextContent("DOGEUSDT · USDT");
    fireEvent.click(within(dialog).getByRole("button", { name: "Fermer" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(doge).toHaveFocus();
  });

  it("8 · aucune requête réseau supplémentaire : une lecture de l'univers, rien au toucher", async () => {
    universe = () => json(assetUniverseFixture());
    open();
    await settled();
    await screen.findByRole("table");
    const before = fetchMock.mock.calls.map(([u]) => String(u));
    expect(before.filter(u => u === UNIVERSE_ENDPOINT)).toHaveLength(1);
    expect(new Set(before.map(u => u.split("?")[0]))).toEqual(new Set([UNIVERSE_ENDPOINT, "/api/operator/v1/spot-radar/scanner"]));
    for (const s of dashboard().querySelectorAll("summary")) fireEvent.click(s);
    fireEvent.click(screen.getByRole("button", { name: /^BTC · 4 marchés/ }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Fermer" }));
    expect(fetchMock.mock.calls.map(([u]) => String(u))).toEqual(before);
  });

  it.each([
    ["Moniteur de marché", "", "table"],
    ["Radar Spot", "?product=spot-radar", null],
    ["Radar de signaux · Démo", "?product=signals-demo", "region"],
  ])("9 · %s reste sous le tableau de bord, une seule fois", async (_label, search, role) => {
    open(search);
    await settled();
    expect(screen.getAllByRole("region", { name: "Scanner scientifique" })).toHaveLength(1);
    expect(screen.getByRole("button", { name: _label })).toHaveAttribute("aria-pressed", "true");
    if (role) expect(await screen.findAllByRole(role)).not.toHaveLength(0);
    expect(universeCalls()).toBe(1);
  });

  it("9b · schéma 1.0.0 : exclusions et preuves natives restent accessibles", async () => {
    open();
    await settled();
    expect(screen.getByText(/paire présente sur trois marchés au moins, exclue/)).toBeInTheDocument();
    expect(screen.getByText("ETH/USDT").closest("li")).toHaveTextContent("Kraken Perpétuel : absente du catalogue");
    fireEvent.click(screen.getByRole("button", { name: /^BTC\/USDT · vérifiée/ }));
    expect(screen.getByRole("dialog", { name: "Preuves BTC/USDT" })).toHaveTextContent("PF_BTCUSDT");
  });

  it("formate les âges sans arrondi vers le haut", () => {
    expect([59_999, 60_000, 2_159_999, 3_600_000, 172_800_000].map(ageLabel)).toEqual(["59 s", "1 min", "35 min", "1 h", "2 j"]);
  });
});
