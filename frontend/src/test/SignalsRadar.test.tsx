// Radar de signaux — prototype on the DRAFT synthetic fixture of the signals module. Not runtime evidence.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { SignalsRadar, type SignalsDoc } from "../views/SignalsRadar";
import fixture from "./fixtures/signalsIndicators-draft-synthetic.json";
afterEach(cleanup);
const doc = fixture as unknown as SignalsDoc;

it("shows each market's published value, never a rejected market's value, and the producer's gap", () => {
  render(<SignalsRadar doc={doc} />);
  expect(screen.getByRole("note")).toHaveTextContent("SYNTHÉTIQUES");
  const table = screen.getByRole("table", { name: "Indicateurs BTC" });
  const rsi = within(table).getByRole("row", { name: /^RSI 14/ });
  expect(within(rsi).getAllByRole("cell").map(c => c.textContent)).toEqual(["54.21", "56.80", "—", "n.d.", "2.59"]);
  expect(within(screen.getByRole("list", { name: "Vérification des marchés" })).getAllByRole("listitem")[2]).toHaveTextContent("KR·S XBT/USD · rejeté (STALE_BOOK)");
});

it("filters markets with the chips and keeps at least one", () => {
  render(<SignalsRadar doc={doc} />);
  for (const m of ["KR·S", "KR·P", "MX·S"]) fireEvent.click(screen.getByRole("button", { name: m }));
  expect(within(screen.getByRole("table")).getAllByRole("columnheader").map(h => h.textContent)).toEqual(["Indicateur", "MX·P", "Écart"]);
  fireEvent.click(screen.getByRole("button", { name: "MX·P" }));
  expect(screen.getByRole("button", { name: "MX·P" })).toHaveAttribute("aria-pressed", "true");
});

it("says so when no market is verified for a symbol", () => {
  render(<SignalsRadar doc={doc} />);
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "ATOM" } });
  expect(screen.getByRole("status")).toHaveTextContent("Aucun indicateur publié pour ATOM");
});
