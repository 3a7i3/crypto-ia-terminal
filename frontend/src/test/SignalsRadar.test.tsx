// Radar de signaux — écran sur la fixture SYNTHÉTIQUE de référence cat.signals.indicators.v1 (BTC). Pas une preuve runtime.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { SignalsRadar, type SignalsDoc } from "../views/SignalsRadar";
import fixture from "./fixtures/signalsIndicators-v1-reference-synthetic.json";
afterEach(cleanup);
const doc = fixture as unknown as SignalsDoc;
const row = (name: RegExp) => within(screen.getByRole("table", { name: "Indicateurs BTC" })).getByRole("row", { name });
const cells = (name: RegExp) => within(row(name)).getAllByRole("cell");

it("shows each market's published closed value and the producer's dispersion, as published", () => {
  render(<SignalsRadar doc={doc} />);
  expect(screen.getByRole("note")).toHaveTextContent("Données SYNTHÉTIQUES · cat.signals.indicators.v1");
  expect(cells(/^RSI 14/).map(c => c.textContent)).toEqual(["53.1061", "53.8851", "54.9745", "56.8732", "3.767"]);
  expect(cells(/^RSI 14/)[0].getAttribute("title")).toMatch(/^valeur exacte 53.10613539( · bougie en cours : [-0-9.]+)?$/);
  expect(cells(/^RSI 14/)[4]).toHaveAttribute("title", "valeur exacte 3.76703882 · dispersion sur 4 marchés");
});

it("keeps a rejected book visible with its reason, never as a value", () => {
  render(<SignalsRadar doc={doc} />);
  const checks = within(screen.getByRole("list", { name: "Vérification des marchés" })).getAllByRole("listitem");
  expect(checks[2]).toHaveTextContent("KR·S BTC/USD · vérifié · carnet rejeté (STALE_BOOK)");
  expect(checks[2]).toHaveClass("warn");
  expect(cells(/^IMB 10 niveaux/)[2]).toHaveTextContent("n.d.");
  expect(cells(/^ADX 14/)[3]).toHaveTextContent("n.d.");
  expect(cells(/^ADX 14/)[3].getAttribute("title")).toMatch(/^INSUFFICIENT_BARS/);
});

it("marks CVD as not compared and shows the published Spot–Perp basis", () => {
  render(<SignalsRadar doc={doc} />);
  expect(cells(/^CVD séance/)[4]).toHaveTextContent("n.c.");
  expect(cells(/^Funding/)[4]).toHaveTextContent(/^0\.00003$/);
  expect(cells(/^Volume relatif 20/)[4]).toHaveTextContent(/^0$/);
  expect(screen.getByLabelText("Base Spot–Perpétuel")).toHaveTextContent("Base Spot–Perpétuel : MEXC 0.1054 % · Kraken 0.0836 %");
});

it("filters markets with the chips and keeps at least one", () => {
  render(<SignalsRadar doc={doc} />);
  for (const m of ["KR·S", "KR·P", "MX·S"]) fireEvent.click(screen.getByRole("button", { name: m }));
  expect(within(screen.getByRole("table")).getAllByRole("columnheader").map(h => h.textContent)).toEqual(["Indicateur", "MX·P", "Écart"]);
  fireEvent.click(screen.getByRole("button", { name: "MX·P" }));
  expect(screen.getByRole("button", { name: "MX·P" })).toHaveAttribute("aria-pressed", "true");
});

it("shows nothing for a symbol whose markets are not verified", () => {
  const sym = doc.symbols[0];
  const markets = Object.fromEntries(Object.entries(sym.markets).map(([m, b]) => [m, { ...b, check: "REJECTED", reason: "NOT_LISTED_CHECK" }]));
  render(<SignalsRadar doc={{ ...doc, symbols: [{ ...sym, markets } as typeof sym] }} />);
  expect(screen.getByRole("status")).toHaveTextContent("Aucun indicateur publié pour BTC");
  expect(screen.queryByRole("table")).toBeNull();
});
