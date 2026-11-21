import { readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { DerivativesPositioningPanel } from "../components/DerivativesPositioningPanel";
import { validatePositioning, type Positioning } from "../lib/derivativesPositioning";
const dir = process.env.CROSS_STACK_FIXTURES_DIR;
const suite = dir ? describe : describe.skip;
const fixture = (name = "S_derivatives_positioning") => JSON.parse(readFileSync(path.join(dir!, name + ".json"), "utf8")).body as Positioning;
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const B = "exchange_b:PF_XBTUSD:PERPETUAL_LINEAR", C = "exchange_c:BTC-PERP:PERPETUAL_LINEAR", D = "exchange_d:BTCUSDT:PERPETUAL_LINEAR";
afterEach(() => vi.unstubAllGlobals());
const mount = async (body: unknown, status = 200) => { vi.stubGlobal("fetch", vi.fn(async () => response(body, status))); render(<DerivativesPositioningPanel/>); };
const pick = (id: string) => fireEvent.change(screen.getByLabelText("Plateforme et contrat"), { target: { value: id } });

suite("Derivatives positioning through the real store, projection and API", () => {
  it.each(["S_derivatives_positioning", "S_derivatives_positioning_stale"])("admits %s", n => expect(validatePositioning(fixture(n))).toBe(true));
  it.each([
    (d: Positioning) => { d.execution_authority = true as false; },
    (d: Positioning) => { (d as unknown as Record<string, unknown>).score = 1; },
    (d: Positioning) => { d.legs = []; },
  ])("refuses an invalid document", m => { const d = fixture(); m(d); expect(validatePositioning(d)).toBe(false); });

  it("shows the four cards with units, provenance and freshness", async () => {
    await mount(fixture());
    expect(await screen.findByTestId("pos-synthetic")).toBeInTheDocument();
    for (const id of ["pos-card-oi", "pos-card-oi-change", "pos-card-funding", "pos-card-premium-basis"]) expect(screen.getByTestId(id)).toBeInTheDocument();
    const oi = screen.getByTestId("pos-card-oi");
    expect(oi).toHaveTextContent("contrats");
    expect(oi).toHaveTextContent("Récente");
    expect(oi).toHaveTextContent("Source");
    expect(screen.getByTestId("pos-card-funding")).toHaveTextContent("par 8 h");
    expect(screen.getByTestId("pos-chart")).toBeInTheDocument();
  });

  it("states partial coverage and missing fields instead of zeros", async () => {
    await mount(fixture());
    await screen.findByTestId("pos-card-oi");
    pick(B);
    const windows = screen.getAllByTestId("pos-oi-window").map(w => w.textContent ?? "");
    expect(windows.some(t => t.includes("INSUFFICIENT_COVERAGE"))).toBe(true);
    expect(screen.getByTestId("pos-card-oi")).toHaveTextContent("unités de base");
    expect(screen.getByTestId("pos-card-funding")).toHaveTextContent("par 1 h");
    expect(screen.getByTestId("pos-card-premium-basis")).toHaveTextContent("Référence spot non qualifiée");
  });

  it("hides the chart of non-comparable contracts and of legs without observation", async () => {
    await mount(fixture());
    await screen.findByTestId("pos-card-oi");
    pick(C);
    expect(screen.queryByTestId("pos-chart")).toBeNull();
    expect(screen.getByTestId("pos-chart-unavailable")).toHaveTextContent("Tailles de contrat différentes");
    expect(screen.getByTestId("pos-unavailable")).toHaveTextContent("Prix d’indice");
    pick(D);
    expect(screen.getByTestId("pos-chart-unavailable")).toHaveTextContent("Aucune observation enregistrée");
    expect(screen.queryByTestId("pos-card-oi")).toBeNull();
    const pairs = screen.getAllByTestId("pos-pair").map(p => p.textContent ?? "").join("\n");
    expect(pairs).toContain("OPEN_INTEREST_UNITS_DIFFER");
    expect(pairs).toContain("CONTRACT_SIZES_DIFFER");
    expect(within(screen.getByTestId("positioning-panel")).queryByText(/^0 contrats$/)).toBeNull();
  });

  it("marks a stale reading", async () => {
    await mount(fixture("S_derivatives_positioning_stale"));
    expect(await screen.findByTestId("pos-card-oi")).toHaveTextContent("Périmée");
  });

  it("keeps a 503 as an unavailable source", async () => {
    await mount({ error_code: "DERIVATIVES_POSITIONING_NOT_CONFIGURED" }, 503);
    expect(await screen.findByText("Aucune lecture de positionnement disponible.")).toBeInTheDocument();
    expect(screen.queryByTestId("pos-card-oi")).toBeNull();
  });
});
