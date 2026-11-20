import { readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { DerivativesStressPanel } from "../components/DerivativesStressPanel";
import { TradeTimingPanel } from "../components/TradeTimingPanel";
import { elapsedStressPublication } from "../lib/derivativesStressClient";
import { validateStressPublication, type StressPublication } from "../lib/derivativesStress";
const dir = process.env.CROSS_STACK_FIXTURES_DIR;
const suite = dir ? describe : describe.skip;
const NAMES = ["S_derivatives_stress", "S_derivatives_stress_stale", "S_derivatives_stress_partial", "S_derivatives_stress_unresolved"];
const fixture = (name = "S_derivatives_stress") => JSON.parse(readFileSync(path.join(dir!, name + ".json"), "utf8")).body as StressPublication;
const response = (body: unknown, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => body } as Response);
afterEach(() => vi.unstubAllGlobals());
const serve = (body: unknown, status = 200) => vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(body, status)));

suite("Derivatives stress through the real offline producer/reader/API", () => {
  it.each(NAMES)("admits %s without changing a published value", name => {
    expect(validateStressPublication(fixture(name))).toBe(true);
  });

  it.each([
    (d: StressPublication) => { (d as unknown as Record<string, unknown>).score = 1; },
    (d: StressPublication) => { d.execution_authority = true as false; },
    (d: StressPublication) => { d.source_counts.available = 0; },
    (d: StressPublication) => { d.underlyings[0].legs[1].funding.annualized_simple_pct = "NaN"; },
    (d: StressPublication) => { d.underlyings[0].legs[1].funding.rate = 0 as unknown as string; },
    (d: StressPublication) => { d.underlyings[0].legs[1].open_interest.notional_quote = null; },
    (d: StressPublication) => { d.underlyings[0].legs[0].status = "NOT_AVAILABLE"; },
    (d: StressPublication) => { d.underlyings[0].legs[1].windows.pop(); },
    (d: StressPublication) => { d.underlyings[0].legs[1].windows[0].price_sign = null; },
    (d: StressPublication) => { d.underlyings[0].legs[1].timing.histogram!.counts[0] += 1; },
    (d: StressPublication) => { d.underlyings[0].legs[1].timing.scan![0].radius_ms = 7; },
    (d: StressPublication) => { d.underlyings[0].legs[0].premium_to_index.status = "AVAILABLE"; d.underlyings[0].legs[0].premium_to_index.bps = "1"; },
    (d: StressPublication) => { d.underlyings[0].pairs.pop(); d.underlyings[0].pairs[0].reference_venue = d.underlyings[0].pairs[0].other_venue; },
    (d: StressPublication) => { d.parameters.windows_s = [60]; },
    (d: StressPublication) => { d.valid_until_utc = null; },
  ])("refuses invalid or inconsistent publications", mutate => {
    const d = fixture(); mutate(d); expect(validateStressPublication(d)).toBe(false);
  });

  it("shows exact published values, synthetic provenance and the complete open-interest total", async () => {
    serve(fixture());
    render(<DerivativesStressPanel/>);
    await screen.findByTestId("stress-synthetic");
    const rows = screen.getAllByTestId("stress-leg");
    expect(rows).toHaveLength(4);
    const perp = rows[1];
    expect(within(perp).getByText("12.997401")).toBeInTheDocument();
    expect(within(perp).getByText("15.000000")).toBeInTheDocument();
    expect(within(perp).getByText("0.0001000000")).toBeInTheDocument();
    expect(within(perp).getByText(/150225000\.00000000 USDT/)).toBeInTheDocument();
    expect(within(rows[0]).getAllByText("Sans objet").length).toBeGreaterThan(0); // spot has no funding: not a zero
    expect(screen.getByTestId("stress-oi-total")).toHaveTextContent("280978000.00000000 USDT");
    expect(screen.getByText(/aucun score, seuil ni signal/)).toBeInTheDocument();
  });

  it("changes underlying and keeps USD apart from USDT", async () => {
    const doc = fixture(); serve(doc);
    render(<DerivativesStressPanel/>);
    await screen.findByTestId("stress-synthetic");
    fireEvent.change(screen.getByLabelText("Sous-jacent observé"), { target: { value: doc.underlyings[1].underlying_id } });
    expect(screen.getAllByTestId("stress-leg").map(r => r.querySelector("th")!.textContent)).toEqual([
      expect.stringContaining("Kraken"), expect.stringContaining("Kraken")]);
    expect(screen.getAllByText(/-0\.0000500000/).length).toBeGreaterThan(0);
    expect(screen.getByTestId("stress-oi-total")).toHaveTextContent("80000000.00000000 USD");
  });

  it("publishes no total when a derivative is missing, and keeps the gap visible", async () => {
    serve(fixture("S_derivatives_stress_partial"));
    render(<DerivativesStressPanel/>);
    await screen.findByTestId("stress-synthetic");
    fireEvent.change(screen.getByLabelText("Sous-jacent observé"), { target: { value: fixture("S_derivatives_stress_partial").underlyings[1].underlying_id } });
    expect(screen.getByTestId("stress-oi-total")).toHaveTextContent("non publié");
    expect(screen.getByTestId("stress-oi-total")).toHaveTextContent("kraken:PI_XBTUSD");
    expect(screen.getAllByText("Source non reçue").length).toBeGreaterThan(0);
  });

  it("marks a stale publication and a publication without any qualified quote", async () => {
    const stale = fixture("S_derivatives_stress_stale");
    serve(stale);
    const { unmount } = render(<DerivativesStressPanel/>);
    await screen.findByText(/Publication périmée · valeurs actuelles INCONNUES/);
    unmount();
    serve(fixture("S_derivatives_stress_unresolved"));
    render(<DerivativesStressPanel/>);
    await screen.findByText("Qualité temporelle indisponible.");
  });

  it.each([[503, "DERIVATIVES_STRESS_NOT_CONFIGURED"], [503, "DERIVATIVES_STRESS_MISSING"]])("treats %s %s as unavailable, never as an empty market", async (status, errorCode) => {
    serve({ error_code: errorCode }, status);
    render(<DerivativesStressPanel/>);
    await screen.findByText("Aucune publication de dérivés disponible.");
    expect(screen.getByText(/ne sont pas déclarés vides ni nuls/)).toBeInTheDocument();
    expect(Boolean(screen.queryByTestId("market-source-not-configured"))).toBe(errorCode.endsWith("NOT_CONFIGURED"));
  });

  it("refuses a contract-invalid 200", async () => {
    const d = fixture(); (d as unknown as Record<string, unknown>).extra = 1; serve(d);
    render(<DerivativesStressPanel/>);
    await screen.findByText("Contrat de publication invalide");
  });

  it("only ages the presentation, never a price", () => {
    const doc = fixture("S_derivatives_stress");
    const aged = elapsedStressPublication(doc, 60_000)!;
    expect(aged.freshness_classification).toBe("STALE");
    expect(aged.underlyings).toEqual(doc.underlyings);
    expect(elapsedStressPublication(doc, -1)).toBeUndefined();
  });

  it("shows the quarter-hour measure beside its baseline and placebo", async () => {
    serve(fixture());
    render(<TradeTimingPanel/>);
    await screen.findByTestId("timing-synthetic");
    expect(screen.getByRole("img", { name: /Transactions par seconde autour de la frontière/ })).toBeInTheDocument();
    const rows = screen.getAllByTestId("timing-scan-row");
    expect(rows).toHaveLength(7);
    const main = rows.find(r => within(r).queryByText("15 min") && within(r).queryByText("± 1000 ms"))!;
    expect(within(main).getByText("0.00222333")).toBeInTheDocument();
    expect(screen.getByText(/aucune p-valeur n’est publiée/)).toBeInTheDocument();
    expect(screen.getByText(/ne doit pas être négocié sans validation/)).toBeInTheDocument();
  });

  it("says why a market has no timing measure instead of showing zero concentration", async () => {
    const doc = fixture(); serve(doc);
    render(<TradeTimingPanel/>);
    await screen.findByTestId("timing-synthetic");
    const other = doc.underlyings[0].legs[0];
    fireEvent.change(screen.getByLabelText("Marché observé"), { target: { value: other.instrument_id + "|" + other.venue } });
    expect(screen.getByTestId("timing-unavailable")).toHaveTextContent("Aucune série de transactions reçue");
    expect(screen.queryAllByTestId("timing-scan-row")).toHaveLength(0);
  });
});
