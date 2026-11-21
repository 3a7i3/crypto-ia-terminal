import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FootprintPanel, FOOTPRINT_ADMITTED_SYMBOLS, autoStepMultiplier } from "../components/FootprintPanel";
import { MarketMicrostructureView } from "../views/MarketMicrostructureView";
import { syntheticReplay } from "./footprintReplayFixture";

const resp = (body: string, status = 200, type = "application/json") => new Response(body, { status, headers: { "content-type": type } });
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("panneau Footprint", () => {
  it("reste « Panneau non alimenté » en temps réel tant que le symbole est non admis, sans aucune requête", () => {
    const fetchImpl = vi.fn();
    render(<FootprintPanel fetchImpl={fetchImpl} />);
    expect(FOOTPRINT_ADMITTED_SYMBOLS).toHaveLength(0);
    const unfed = screen.getByTestId("footprint-unfed");
    expect(unfed).toHaveTextContent("Panneau non alimenté");
    expect(unfed).toHaveTextContent("Symbole non admis : BTC_USDT · perpétuel · MEXC");
    for (const gate of ["Critères d'admission", "Réglages IMB", "Session crypto", "Contrat du flux"]) expect(unfed).toHaveTextContent(gate);
    expect(unfed).toHaveTextContent("Transactions (avec côté agresseur) · déconnecté");
    expect(fetchImpl).not.toHaveBeenCalled();
    expect(screen.getByRole("radio", { name: "Temps réel" })).toHaveAttribute("aria-checked", "true");
  });

  it("rejoue le fichier en Démo historique avec provenance et couverture partielle visibles", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(resp(JSON.stringify(syntheticReplay())));
    render(<FootprintPanel fetchImpl={fetchImpl} />);
    fireEvent.click(screen.getByRole("radio", { name: "Démo historique" }));
    const prov = await screen.findByTestId("footprint-provenance");
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(prov).toHaveTextContent("DÉMO HISTORIQUE · REJEU");
    expect(prov).toHaveTextContent("MEXC · BTC_USDT · PERPÉTUEL");
    expect(prov).toHaveTextContent("FIXTURE SYNTHÉTIQUE DE TEST");
    expect(screen.getByTestId("footprint-coverage")).toHaveTextContent("Couverture 2026-01-05T10:00:00Z → 2026-01-05T10:20:00Z · 20 min · 6 transactions · 0 lacune(s) déclarée(s)");
    expect(screen.getByTestId("footprint-partial")).toHaveTextContent("COUVERTURE PARTIELLE");
    await waitFor(() => expect(screen.getByTestId("footprint-sha256").textContent).toMatch(/^[0-9a-f]{64}/));
    expect(prov).toHaveTextContent("6 acceptées · 0 rejetées · 0 hors pas");
    const table = screen.getByTestId("footprint-table");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Prix", "10:00 · partiel", "10:05 · partiel", "10:10 · partiel", "Profil vol."]);
    expect(screen.getByTestId("footprint-row-Delta")).toHaveTextContent(/\+400.*-50.*-70/);
    expect(screen.getByTestId("footprint-row-DltaDay")).toHaveTextContent(/\+400 \*.*\+350 \*.*\+280 \*/);
    expect(screen.getByTestId("footprint-profile-summary")).toHaveTextContent("DltaDay partiel");
    // L'agrégation par pas plus grand reconstruit les niveaux à partir des mêmes transactions.
    fireEvent.change(screen.getByLabelText("Pas des niveaux"), { target: { value: "10" } });
    expect(screen.getByTestId("footprint-row-Delta")).toHaveTextContent(/\+400.*-50.*-70/);
  });

  it("n'affiche aucune donnée de remplacement si le fichier est absent ou invalide", async () => {
    const absent = render(<FootprintPanel fetchImpl={vi.fn().mockResolvedValue(resp("<!doctype html>", 200, "text/html"))} />);
    fireEvent.click(screen.getByRole("radio", { name: "Démo historique" }));
    expect(await screen.findByTestId("footprint-replay-absent")).toHaveTextContent("fichier de rejeu absent");
    expect(screen.queryByTestId("footprint-table")).toBeNull();
    absent.unmount();
    const bad = syntheticReplay(); bad.provenance.symbol = "ETH_USDT";
    render(<FootprintPanel fetchImpl={vi.fn().mockResolvedValue(resp(JSON.stringify(bad)))} />);
    fireEvent.click(screen.getByRole("radio", { name: "Démo historique" }));
    expect(await screen.findByTestId("footprint-replay-invalid")).toHaveTextContent("BTC_USDT perpétuel MEXC");
    expect(screen.queryByTestId("footprint-table")).toBeNull();
  });

  it("signale une panne de lecture comme telle et permet de réessayer", async () => {
    const fetchImpl = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(resp(JSON.stringify(syntheticReplay())));
    render(<FootprintPanel fetchImpl={fetchImpl} />);
    fireEvent.click(screen.getByRole("radio", { name: "Démo historique" }));
    expect(await screen.findByTestId("footprint-replay-error")).toHaveTextContent("pas une absence de transactions");
    fireEvent.click(screen.getByRole("button", { name: "Réessayer" }));
    expect(await screen.findByTestId("footprint-table")).toBeInTheDocument();
  });

  it("propose un menu « Thème » Clair / Sombre, clair par défaut", () => {
    render(<FootprintPanel fetchImpl={vi.fn()} />);
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

  it("garde le thème choisi en plein écran et entre les modes, sans requête", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(resp(JSON.stringify(syntheticReplay())));
    Object.defineProperty(HTMLElement.prototype, "requestFullscreen", { configurable: true, value: undefined });
    render(<FootprintPanel fetchImpl={fetchImpl} />);
    const panel = screen.getByTestId("footprint-panel");
    const select = screen.getByRole("combobox", { name: "Thème" });
    fireEvent.change(select, { target: { value: "dark" } });
    expect(fetchImpl).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Plein écran" }));
    expect(panel).toHaveClass("footprint-fullscreen");
    expect(panel).toHaveAttribute("data-footprint-theme", "dark");
    fireEvent.click(screen.getByRole("button", { name: "Quitter le plein écran" }));
    expect(panel).toHaveAttribute("data-footprint-theme", "dark");
    fireEvent.click(screen.getByRole("radio", { name: "Démo historique" }));
    expect(await screen.findByTestId("footprint-table")).toBeInTheDocument();
    expect(panel).toHaveAttribute("data-footprint-theme", "dark");
    fireEvent.click(screen.getByRole("radio", { name: "Temps réel" }));
    expect(screen.getByTestId("footprint-unfed")).toBeInTheDocument();
    expect(select).toHaveValue("dark");
  });

  it("passe en plein écran par l'API Fullscreen, avec repli CSS", () => {
    const request = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(HTMLElement.prototype, "requestFullscreen", { configurable: true, value: request });
    render(<FootprintPanel fetchImpl={vi.fn()} />);
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

  it("reste présent dans la vue Microstructure même quand la source LMI est indisponible", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({ error_code: "MICROSTRUCTURE_MISSING" }) } as Response));
    render(<MarketMicrostructureView />);
    expect(screen.getByTestId("footprint-unfed")).toHaveTextContent("Panneau non alimenté");
    await waitFor(() => expect(screen.getByTestId("microstructure-status")).toHaveTextContent("INCONNU"));
  });
});
