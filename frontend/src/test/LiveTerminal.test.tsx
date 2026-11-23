// Terminal live — LOCAL TEST FIXTURE ONLY (spotRadar-scanner.json), not runtime evidence.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { fetchRadar, type RadarScanner } from "../lib/spotRadarClient";
import { LiveTerminal } from "../views/LiveTerminal";
import fixture from "./fixtures/spotRadar-scanner.json";

vi.mock("../lib/spotRadarClient", async original => ({ ...await original<typeof import("../lib/spotRadarClient")>(), fetchRadar: vi.fn() }));
let data: RadarScanner;
beforeEach(() => { data = structuredClone(fixture) as RadarScanner; vi.spyOn(Date, "now").mockReturnValue(Number(data.server_time_ms)); vi.mocked(fetchRadar).mockImplementation(async () => data as never); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("lists only LIVE rows, by qualified volume, without any score", async () => {
  data.rows.find(r => r.base_asset === "ATOM")!.freshness.state = "STALE";
  data.rows.find(r => r.base_asset === "DOGE")!.freshness.age_ms = 46_000;
  render(<LiveTerminal />);
  const table = await screen.findByRole("table", { name: "Paires live" });
  const names = within(table).getAllByRole("rowheader").map(h => h.textContent);
  expect(names).not.toContain("ATOM/USDT");
  expect(names).not.toContain("DOGE/USDT");
  expect(names.length).toBe(data.rows.length - 2);
  expect(screen.getByRole("status")).toHaveTextContent(`● LIVE · ${data.rows.length - 2} paires`);
});

it("never presents a demonstration fixture or a stopped collector as live", async () => {
  data.evidence_kind = "SYNTHETIC";
  const view = render(<LiveTerminal />);
  await screen.findByText(/Démonstration · aucune paire/);
  expect(screen.queryByRole("table")).toBeNull();
  view.unmount();
  data = structuredClone(fixture) as RadarScanner; data.collector.state = "STOPPED";
  render(<LiveTerminal />);
  await screen.findByText(/Flux non live \(STOPPED\)/);
  expect(screen.queryByRole("table")).toBeNull();
});
