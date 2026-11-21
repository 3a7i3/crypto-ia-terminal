import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FootprintPanel, autoStepMultiplier } from "../components/FootprintPanel";
import { FOOTPRINT_REPLAY_URL } from "../lib/footprintReplay";
import { MarketMicrostructureView } from "../views/MarketMicrostructureView";
import { syntheticReplay } from "./footprintReplayFixture";

const resp = (body: string | Uint8Array, status = 200, type = "application/json") => new Response(body as BodyInit, { status, headers: { "content-type": type } });
const sha = (body: string | Uint8Array) => createHash("sha256").update(body).digest("hex");
const FIXTURE = JSON.stringify(syntheticReplay());
const FIXTURE_SHA = sha(FIXTURE);
const pending = () => vi.fn(() => new Promise<Response>(() => undefined));
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("panneau Footprint · vue unique BTC_USDT", () => {
  it("ouvre directement le tableau à partir de la capture figée, sans commande de mode", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(resp(FIXTURE));
    render(<FootprintPanel fetchImpl={fetchImpl} expectedSha256={FIXTURE_SHA} />);
    expect(screen.getByTestId("footprint-capture-loading")).toHaveTextContent("Chargement de la capture BTC_USDT");
    const table = await screen.findByTestId("footprint-table");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(fetchImpl).toHaveBeenCalledWith(FOOTPRINT_REPLAY_URL, expect.objectContaining({ cache: "no-store" }));
    expect(screen.getAllByRole("table")).toHaveLength(1);
    expect(screen.queryByRole("radio", { name: /Temps réel/ })).toBeNull();
    for (const gone of [/Démo historique/, /Panneau non alimenté/]) expect(screen.queryByText(gone)).toBeNull();
    expect(screen.queryByRole("radio")).toBeNull();
    expect(screen.getByTestId("footprint-mention")).toHaveTextContent("Capture figée · Couverture partielle");
    expect(screen.getByTestId("footprint-coverage")).toHaveTextContent(
      "MEXC · BTC_USDT perpétuel · quantités en contrats · 2026-01-05T10:00:00Z → 2026-01-05T10:20:00Z (20 min) · 6 transactions");
    expect(screen.getByTestId("footprint-provenance")).toHaveTextContent("FIXTURE SYNTHÉTIQUE DE TEST");
    expect(screen.getByTestId("footprint-provenance")).toHaveTextContent("6 acceptées · 0 rejetées · 0 hors pas");
    expect(screen.getByTestId("footprint-sha256")).toHaveTextContent(`${FIXTURE_SHA} · ${new TextEncoder().encode(FIXTURE).length} octets · vérifiée`);
    // V3 : « partiel » qualifie la fenêtre de la bougie (couverture ou lacune), pas la session.
    // La fixture couvre 10:00 → 10:20 : les trois bougies de 5 min sont entières ; DltaDay reste partiel (*).
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Prix", "10:00", "10:05", "10:10", "Profil vol."]);
    expect(screen.getByText("Valeurs exactes").closest("details")).toContainElement(table);
    expect(screen.getByTestId("footprint-chart")).toBeInTheDocument();
    // Temps réel : indisponibilité affichée, sans connexion ; provenance du côté agresseur.
    expect(screen.getByTestId("footprint-live-status")).toHaveTextContent("Temps réel indisponible");
    expect(screen.getByTestId("footprint-aggressor-origin")).toHaveTextContent("Publié par MEXC avec chaque transaction");
    expect(screen.getByTestId("footprint-coverage")).toHaveTextContent("côté agresseur publié par MEXC");
    expect(screen.getByTestId("footprint-row-Delta")).toHaveTextContent(/\+400.*-50.*-70/);
    expect(screen.getByTestId("footprint-row-DltaDay")).toHaveTextContent(/\+400 \*.*\+350 \*.*\+280 \*/);
    expect(screen.getByTestId("footprint-profile-summary")).toHaveTextContent("DltaDay partiel");
    // Réglages compacts : période, pas, nombre de bougies et profil dans une même rangée.
    const controls = screen.getByRole("group", { name: "Réglages du tableau" });
    expect(within(controls).getAllByRole("combobox")).toHaveLength(4);
    // Le profil du graphique est piloté depuis cette rangée (aucun menu en double dans le graphique).
    expect(within(screen.getByTestId("footprint-chart")).queryByRole("combobox")).toBeNull();
    fireEvent.change(within(controls).getByRole("combobox", { name: "Profil" }), { target: { value: "volume" } });
    expect(screen.getByTestId("footprint-chart").querySelector(".fp-head[data-profile]")).toHaveTextContent("Volume");
    fireEvent.change(within(controls).getByRole("combobox", { name: "Profil" }), { target: { value: "delta" } });
    fireEvent.change(screen.getByLabelText("Pas des niveaux"), { target: { value: "10" } });
    expect(screen.getByTestId("footprint-row-Delta")).toHaveTextContent(/\+400.*-50.*-70/);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("refuse un fichier dont l'empreinte SHA-256 n'est pas celle de la capture livrée", async () => {
    render(<FootprintPanel fetchImpl={vi.fn().mockResolvedValue(resp(FIXTURE))} />);
    const notice = await screen.findByTestId("footprint-capture-unavailable");
    expect(notice).toHaveTextContent("Capture indisponible");
    expect(notice).toHaveTextContent("empreinte SHA-256");
    expect(notice).toHaveAttribute("data-reason", "invalid");
    expect(screen.queryByTestId("footprint-table")).toBeNull();
  });

  it("affiche « Capture indisponible » sans donnée de remplacement si le fichier est absent ou invalide", async () => {
    const absent = render(<FootprintPanel fetchImpl={vi.fn().mockResolvedValue(resp("<!doctype html>", 200, "text/html"))} />);
    const a = await screen.findByTestId("footprint-capture-unavailable");
    expect(a).toHaveTextContent("Capture indisponible");
    expect(a).toHaveAttribute("data-reason", "absent");
    expect(screen.queryByTestId("footprint-table")).toBeNull();
    absent.unmount();
    const bad = syntheticReplay(); bad.provenance.symbol = "ETH_USDT"; const badBody = JSON.stringify(bad);
    render(<FootprintPanel fetchImpl={vi.fn().mockResolvedValue(resp(badBody))} expectedSha256={sha(badBody)} />);
    const b = await screen.findByTestId("footprint-capture-unavailable");
    expect(b).toHaveTextContent("BTC_USDT perpétuel MEXC");
    expect(b).toHaveAttribute("data-reason", "invalid");
    expect(screen.queryByTestId("footprint-table")).toBeNull();
  });

  it("signale une panne de lecture comme telle et permet de réessayer", async () => {
    const fetchImpl = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(resp(FIXTURE));
    render(<FootprintPanel fetchImpl={fetchImpl} expectedSha256={FIXTURE_SHA} />);
    const notice = await screen.findByTestId("footprint-capture-unavailable");
    expect(notice).toHaveTextContent("Capture indisponible");
    expect(notice).toHaveTextContent("pas une absence de transactions");
    fireEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(await screen.findByTestId("footprint-table")).toBeInTheDocument();
  });

  it("propose un menu « Thème » Clair / Sombre, clair par défaut", () => {
    render(<FootprintPanel fetchImpl={pending()} />);
    const panel = screen.getByTestId("footprint-panel");
    const select = screen.getByRole("combobox", { name: "Thème" });
    expect(panel).toHaveAttribute("data-footprint-theme", "light");
    expect(select).toHaveValue("light");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Clair", "Sombre"]);
    expect(screen.queryByRole("button", { name: /Thème/ })).not.toBeInTheDocument();
    fireEvent.change(select, { target: { value: "dark" } });
    expect(panel).toHaveAttribute("data-footprint-theme", "dark");
    fireEvent.change(select, { target: { value: "light" } });
    expect(panel).toHaveAttribute("data-footprint-theme", "light");
  });

  it("garde le même tableau en clair, en sombre et en plein écran, sans relire la capture", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(resp(FIXTURE));
    Object.defineProperty(HTMLElement.prototype, "requestFullscreen", { configurable: true, value: undefined });
    render(<FootprintPanel fetchImpl={fetchImpl} expectedSha256={FIXTURE_SHA} />);
    const panel = screen.getByTestId("footprint-panel");
    const table = await screen.findByTestId("footprint-table");
    const html = table.innerHTML;
    const select = screen.getByRole("combobox", { name: "Thème" });
    fireEvent.change(select, { target: { value: "dark" } });
    expect(screen.getByTestId("footprint-table").innerHTML).toBe(html);
    fireEvent.click(screen.getByRole("button", { name: "Plein écran" }));
    expect(panel).toHaveClass("footprint-fullscreen");
    expect(panel).toHaveAttribute("data-footprint-theme", "dark");
    expect(screen.getAllByRole("table")).toHaveLength(1);
    expect(screen.getByTestId("footprint-table").innerHTML).toBe(html);
    fireEvent.click(screen.getByRole("button", { name: "Quitter le plein écran" }));
    fireEvent.change(select, { target: { value: "light" } });
    expect(panel).toHaveAttribute("data-footprint-theme", "light");
    expect(screen.getByTestId("footprint-table").innerHTML).toBe(html);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("passe en plein écran par l'API Fullscreen, avec repli CSS", () => {
    const request = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(HTMLElement.prototype, "requestFullscreen", { configurable: true, value: request });
    render(<FootprintPanel fetchImpl={pending()} />);
    const panel = screen.getByTestId("footprint-panel");
    fireEvent.click(screen.getByRole("button", { name: "Plein écran" }));
    expect(request).toHaveBeenCalledTimes(1);
    expect(panel).toHaveClass("footprint-fullscreen");
    fireEvent.click(screen.getByRole("button", { name: "Quitter le plein écran" }));
    expect(panel).not.toHaveClass("footprint-fullscreen");
    delete (HTMLElement.prototype as { requestFullscreen?: unknown }).requestFullscreen;
    fireEvent.click(screen.getByRole("button", { name: "Plein écran" }));
    expect(panel).toHaveClass("footprint-fullscreen");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(panel).not.toHaveClass("footprint-fullscreen");
  });

  it("choisit un pas d'affichage qui borne le nombre de niveaux", () => {
    expect(autoStepMultiplier(0.1, 90000, 90002)).toBe(1);
    expect(autoStepMultiplier(0.1, 90000, 90500)).toBe(100);
    expect(autoStepMultiplier(0.1, 90000, 90000)).toBe(1);
  });

  it("affiche la capture MEXC réelle dans Microstructure, indépendamment de la source LMI indisponible", async () => {
    const real = new Uint8Array(readFileSync(resolve(__dirname, "../../public/observations/footprint/mexc-btc_usdt-perp-replay-v1.json")));
    const fetchMock = vi.fn((input: RequestInfo | URL) => String(input).includes(FOOTPRINT_REPLAY_URL)
      ? Promise.resolve(resp(real))
      : Promise.resolve({ ok: false, status: 503, json: async () => ({ error_code: "MICROSTRUCTURE_MISSING" }) } as Response));
    vi.stubGlobal("fetch", fetchMock);
    render(<MarketMicrostructureView />);
    expect(await screen.findByTestId("footprint-table")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("microstructure-status")).toHaveTextContent("INCONNU"));
    expect(screen.getByTestId("footprint-mention")).toHaveTextContent("Capture figée · Couverture partielle");
    expect(screen.getByTestId("footprint-coverage")).toHaveTextContent(/MEXC · BTC_USDT perpétuel · quantités en contrats · .* \(15 s\) · 100 transactions/);
    expect(fetchMock.mock.calls.filter(([u]) => String(u).includes(FOOTPRINT_REPLAY_URL))).toHaveLength(1);
  });
});
