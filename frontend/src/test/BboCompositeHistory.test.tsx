import { beforeEach, afterEach, it, expect, vi } from "vitest";
import { render, screen, fireEvent, cleanup, within } from "@testing-library/react";
import { BboCompositeHistory } from "../views/BboCompositeHistory";
import { fetchBboHistory, BboHistoryError, BBO_HISTORY_LABEL } from "../lib/bboHistoryClient";
import raw from "./fixtures/bboCompositeHistory-synthetic.json";
vi.mock("../lib/bboHistoryClient", async original => ({ ...await original<typeof import("../lib/bboHistoryClient")>(), fetchBboHistory: vi.fn() }));
const served = () => ({ ...structuredClone(raw), serving: { freshness_classification: "HISTORICAL_NOT_LIVE" } }) as any;
beforeEach(() => { vi.mocked(fetchBboHistory).mockResolvedValue(served()); });
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("shows BTC first with label, venues, UTC window and exact candle counts", async () => {
  render(<BboCompositeHistory />);
  expect(await screen.findByRole("heading", { name: BBO_HISTORY_LABEL })).toBeTruthy();
  expect(screen.getByRole("button", { name: "BTC/USDT" }).getAttribute("aria-pressed")).toBe("true");
  expect(screen.getByText(/Fenêtre UTC : 2026-11-19 22:40 UTC → 2026-11-19 22:50 UTC/)).toBeTruthy();
  const m = screen.getByLabelText("Couverture BTC/USDT");
  expect(within(m).getByText("59 / 60")).toBeTruthy();
  expect(within(m).getByText("1 / 2")).toBeTruthy();
  expect(screen.getByRole("img").getAttribute("aria-label")).toContain("BTC/USDT M5, 1 bougies complètes");
  expect(document.querySelectorAll("svg rect")).toHaveLength(1); // one body, no volume bar, incomplete window not drawn
  expect(screen.getByText("O 62024.79 · H 62051.485 · L 62002.445 · C 62006.18")).toBeTruthy();
  expect(screen.getAllByText("Incomplète · 29 / 30 points · aucune valeur OHLC").length).toBeGreaterThan(0);
  expect(screen.getAllByRole("article")).toHaveLength(2);
  expect(screen.getByText("◆ SYNTHETIC")).toBeTruthy();
  expect(screen.queryByText(/LIVE qualifié/)).toBeNull();
  expect(screen.queryByText(/hypothèse A-ORDER\)/)).toBeNull();
});

it("switches to ATOM and exposes A-ORDER and the 10 bps sensitivity in the provenance", async () => {
  render(<BboCompositeHistory />);
  fireEvent.click(await screen.findByRole("button", { name: "ATOM/USDT" }));
  expect(screen.getByRole("button", { name: "ATOM/USDT" }).getAttribute("aria-pressed")).toBe("true");
  const m = screen.getByLabelText("Couverture ATOM/USDT");
  expect(within(m).getByText("61 / 90")).toBeTruthy();
  expect(within(m).getByText("2 / 3")).toBeTruthy();
  expect(screen.getAllByRole("article")).toHaveLength(3);
  expect(screen.getByRole("img").getAttribute("aria-label")).toContain("ATOM/USDT M5, 2 bougies complètes");
  expect(screen.getByRole("note").textContent).toContain("UNCHANGED_VERIFIED (hypothèse A-ORDER)");
  const a = screen.getByRole("region", { name: "Hypothèse A-ORDER" });
  expect(within(a).getByText(/PONG received after earlier diffs/)).toBeTruthy();
  expect(within(a).getByText("Majorité de la couverture fondée sur UNCHANGED_VERIFIED : oui.")).toBeTruthy();
  const s = screen.getByRole("region", { name: "Sensibilité ATOM/USDT" });
  expect(within(s).getByText(/À 10 bps \(fraîcheur 2 s\)/).textContent).toContain("0 / 90");
  expect(s.querySelectorAll("td.bbo-col10")).toHaveLength(4);
});

it("states an absent publication without drawing candles", async () => {
  vi.mocked(fetchBboHistory).mockRejectedValue(new BboHistoryError("BBO_HISTORY_NOT_CONFIGURED", 503));
  render(<BboCompositeHistory />);
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("Aperçu historique absent · BBO_HISTORY_NOT_CONFIGURED");
  expect(alert.textContent).toContain("Aucune bougie n’est présentée");
  expect(screen.queryByRole("img")).toBeNull();
});

it("states an invalid publication and can retry", async () => {
  vi.mocked(fetchBboHistory).mockRejectedValueOnce(new BboHistoryError("INVALID_BBO_HISTORY_COVERAGE_SUM"));
  render(<BboCompositeHistory />);
  expect((await screen.findByRole("alert")).textContent).toContain("Publication historique invalide · INVALID_BBO_HISTORY_COVERAGE_SUM");
  expect(screen.queryByRole("img")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Réessayer" }));
  expect(await screen.findByLabelText("Couverture BTC/USDT")).toBeTruthy();
});
