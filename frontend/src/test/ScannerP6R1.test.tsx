// CAT P6-R1 — stabilisation mobile du Scanner (F1–F4).
// LOCAL TEST FIXTURES ONLY: synthetic publications from scannerUniverseFixtures.ts
// and the replayed spotRadar-scanner.json. Nothing here is runtime evidence.
// jsdom has no layout engine: widths, page scroll and dialog sizes are measured
// under Chromium by scripts/capture_scanner_p6r1.mjs; here we pin the behaviour
// (fold state, unknown counts) and the stylesheet contract.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import scanner from "./fixtures/spotRadar-scanner.json";
import { assetUniverseFixture } from "./scannerUniverseFixtures";
import { ScannerUniverse } from "../views/ScannerUniverse";
import { UNIVERSE_ENDPOINT, admissionKnown, universeView, type ScannerGate } from "../lib/scannerUniverseClient";

const RADAR = "/paper-live/market/radar";
const NOW = Number(scanner.server_time_ms);
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
let universe: () => Promise<Response> | Response;
beforeEach(() => {
  vi.spyOn(Date, "now").mockReturnValue(NOW);
  universe = () => json(assetUniverseFixture({ now: NOW }));
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === UNIVERSE_ENDPOINT) return universe();
    if (url.startsWith("/api/operator/v1/spot-radar/scanner")) return json(scanner);
    return json({ error_code: "LOCAL_TEST_FIXTURE_NOT_CONFIGURED" }, 503);
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); window.history.replaceState(null, "", "/"); });

const openApp = (search = "") => { window.history.pushState(null, "", RADAR + search); return render(<App />); };
const fold = () => screen.getByTestId("asset-list-fold") as HTMLDetailsElement;
const summary = () => fold().querySelector("summary")!;

describe("P6-R1 · F3 catalogue repliable", () => {
  it("est replié par défaut et son résumé donne l'état, puis le compte publié", async () => {
    openApp();
    expect(fold().open).toBe(false);
    expect(summary()).toHaveTextContent("Actifs publiésen chargement");
    await waitFor(() => expect(summary()).toHaveTextContent("Actifs publiés4 lignes publiées"));
    expect(fold().open).toBe(false);
    // Folded, the list rows stay in the document (tests) but are not shown by the browser.
    expect(fold().querySelector(".su-assets-body")).not.toBeNull();
  });

  it.each([["?q=BTC"], ["?cov=3"], ["?q=ET&cov=4&product=spot-radar"]])("s'ouvre seul quand l'URL porte une recherche (%s)", async (search) => {
    openApp(search);
    expect(fold().open).toBe(true);
    await waitFor(() => expect(screen.getByTestId("asset-results")).toBeInTheDocument());
    expect(fold().open).toBe(true);
  });

  it("s'ouvre si une recherche arrive après coup, et la recherche reste dans l'URL", async () => {
    openApp();
    await waitFor(() => expect(summary()).toHaveTextContent("4 lignes publiées"));
    fold().open = true; fireEvent(fold(), new Event("toggle"));
    fireEvent.change(screen.getByRole("searchbox", { name: "Actif ou symbole" }), { target: { value: "eth" } });
    await waitFor(() => expect(window.location.search).toContain("q=ETH"));
    expect(fold().open).toBe(true);
  });

  it("garde le choix de l'opérateur pendant un rafraîchissement de la publication", () => {
    const doc = assetUniverseFixture({ now: NOW });
    const { rerender } = render(<ScannerUniverse view={universeView(doc, null, NOW, NOW)} />);
    fold().open = true; fireEvent(fold(), new Event("toggle"));
    rerender(<ScannerUniverse view={universeView({ ...doc, computed_ms: doc.computed_ms + 1 }, null, NOW, NOW)} />);
    expect(fold().open).toBe(true);
    // The other way round: folded stays folded across a new read.
    fold().open = false; fireEvent(fold(), new Event("toggle"));
    rerender(<ScannerUniverse view={universeView({ ...doc, computed_ms: doc.computed_ms + 2 }, null, NOW, NOW)} />);
    expect(fold().open).toBe(false);
  });

  it("ne présente aucun compte inventé dans le résumé replié", () => {
    render(<ScannerUniverse view={universeView(null, "HTTP_503", NOW, NOW)} />);
    expect(summary()).toHaveTextContent("Actifs publiésindisponible");
    expect(summary().textContent).not.toMatch(/\d/);
  });

  it("le résumé est un élément natif atteignable au clavier", () => {
    render(<ScannerUniverse view={universeView(assetUniverseFixture({ now: NOW }), null, NOW, NOW)} />);
    expect(summary().tagName).toBe("SUMMARY");
    expect(within(summary()).getByRole("heading", { name: "Actifs publiés" })).toBeInTheDocument();
  });
});

describe("P6-R1 · F2 aucun faux zéro d'admission", () => {
  const gate = (state: ScannerGate["state"]): ScannerGate => ({ admitted: new Set(), keys: new Set(), state });
  it("admissionKnown ne vaut que pour un univers vérifié", () => {
    expect(admissionKnown(undefined)).toBe(true);
    expect(admissionKnown(gate("VERIFIED"))).toBe(true);
    expect(admissionKnown(gate("VERIFIED_EMPTY"))).toBe(true);
    expect(admissionKnown(gate("LOADING"))).toBe(false);
    expect(admissionKnown(gate("UNAVAILABLE"))).toBe(false);
  });

  it("Moniteur arrivé avant l'univers : admission en attente, jamais « 0 admis »", async () => {
    let release!: (r: Response) => void;
    universe = () => new Promise<Response>(r => { release = r; });
    openApp();
    const summaryLine = await waitFor(() => { const p = document.querySelector(".symbol-summary"); expect(p).not.toBeNull(); return p!; });
    expect(summaryLine).toHaveTextContent("30 instruments observés · admission en attente (univers commun en chargement)");
    expect(summaryLine.textContent).not.toMatch(/\b0 admis/);
    expect(summaryLine.textContent).not.toMatch(/^0 \//);
    await act(async () => release(json(assetUniverseFixture({ now: NOW }))));
    await waitFor(() => expect(document.querySelector(".symbol-summary")).toHaveTextContent(/admis par actif \(Spot et Perpétuel\)/));
  });

  it("univers indisponible : admission inconnue, jamais « 0 admis »", async () => {
    universe = () => json({ error_code: "SCANNER_UNIVERSE_NOT_CONFIGURED" }, 503);
    openApp();
    await waitFor(() => expect(document.querySelector(".symbol-summary")).toHaveTextContent("admission inconnue (univers commun indisponible)"));
    expect(document.querySelector(".symbol-summary")!.textContent).not.toMatch(/\b0 admis/);
  });

  it("Radar Spot : même règle pendant le chargement de l'univers", async () => {
    universe = () => new Promise<Response>(() => {});
    openApp("?product=spot-radar");
    await waitFor(() => expect(document.querySelector(".intraday-coverage")).toHaveTextContent(/admission en attente \(univers commun en chargement\) pour les \d+ instruments observés/));
    expect(document.querySelector(".intraday-coverage")!.textContent).not.toMatch(/\b0 instrument admis/);
  });
});

describe("P6-R1 · F1/F4 contrat des feuilles de style", () => {
  const read = (name: string) => readFileSync(fileURLToPath(new URL("../" + name, import.meta.url)), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  const rule = (css: string, selector: string) => [...css.matchAll(/([^{}@]+)\{([^{}]*)\}/g)].filter(m => m[1].split(",").map(s => s.trim()).includes(selector)).map(m => m[2]).join(";");
  const su = read("views/scanner-universe.css");
  const sym = read("views/symbol-scanner.css");

  it("F1 · la liste des devises se replie au lieu d'imposer sa largeur, sans masquer le débordement", () => {
    expect(rule(su, ".su-quotes")).not.toMatch(/nowrap/);
    expect(rule(su, ".su-quotes")).toMatch(/overflow-wrap:\s*anywhere/);
    expect(rule(su, ".su-row-meta")).toMatch(/flex-wrap:\s*wrap/);
    for (const css of [su, sym]) expect(css).not.toMatch(/overflow-x:\s*hidden/);
  });

  it("F4 · fiche du Moniteur bornée, défilement interne et bouton Fermer collé", () => {
    expect(rule(sym, ".symbol-detail")).toMatch(/max-height:/);
    expect(rule(sym, ".symbol-detail")).toMatch(/overflow-y:\s*auto/);
    expect(rule(sym, ".symbol-detail form")).toMatch(/position:\s*sticky/);
    expect(rule(sym, ".symbol-detail form button")).toMatch(/min-width:\s*44px/);
    expect(rule(su, ".universe-detail form")).toMatch(/position:\s*sticky/);
  });
});
