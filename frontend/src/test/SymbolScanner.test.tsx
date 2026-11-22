import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { fetchRadar, type RadarScanner } from "../lib/spotRadarClient";
import { SymbolScanner } from "../views/SymbolScanner";
import fixture from "./fixtures/spotRadar-scanner.json";

vi.mock("../lib/spotRadarClient", async original => ({
  ...await original<typeof import("../lib/spotRadarClient")>(),
  fetchRadar: vi.fn(),
}));
afterEach(cleanup);

it("keeps rank distinct from freshness and selects by instrument identity", async () => {
  const data = structuredClone(fixture) as RadarScanner;
  const atom = data.rows.find(row => row.base_asset === "ATOM")!;
  atom.freshness.state = "STALE";
  vi.mocked(fetchRadar).mockResolvedValue(data);
  const select = vi.fn();
  const { container } = render(<SymbolScanner bubbles={false} selection={[]} onSelect={select} />);
  await screen.findByRole("table");
  for (const [tier, count] of [["gold", 3], ["silver", 7], ["bronze", 15]] as const) {
    expect(container.querySelectorAll(`.${tier}`)).toHaveLength(count);
  }
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "ATOM" } });
  fireEvent.click(screen.getByRole("button", { name: "ATOM/USDT" }));
  const detail = within(screen.getByRole("dialog"));
  expect(detail.getByText("Non classée · Ancienne")).toBeInTheDocument();
  fireEvent.click(detail.getByRole("button", { name: "Ajouter à la sélection" }));
  expect(select).toHaveBeenCalledWith(atom.instrument_id);
});

it.each([[false, false], [true, false], [false, true], [true, true]])(
  "gates the chart link with burn-in=%s and chart=%s", async (burnInPassed, chartAvailable) => {
    const data = fixture as RadarScanner;
    const btc = data.rows.find(row => row.base_asset === "BTC")!;
    vi.mocked(fetchRadar).mockResolvedValue(data);
    render(<SymbolScanner bubbles selection={[]} onSelect={() => {}} qualifications={[
      { instrumentId: btc.instrument_id, burnInPassed,
        chartHref: chartAvailable ? `/paper-live/market/radar/unified?instrument=${encodeURIComponent(btc.instrument_id)}` : undefined },
    ]} />);
    fireEvent.click(await screen.findByRole("button", { name: /^BTC\/USDT / }));
    const link = screen.queryByRole("link", { name: "Ouvrir le graphique unifié" });
    expect(Boolean(link)).toBe(burnInPassed && chartAvailable);
    if (link) expect(decodeURIComponent(link.getAttribute("href")!)).toContain(btc.instrument_id);
  },
);
