// Moniteur de marché — programmateur de lecture et voyant. LOCAL TEST FIXTURE ONLY
// (spotRadar-scanner.json), not runtime evidence. The scheduler only paces GET reads.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchRadar, type RadarScanner } from "../lib/spotRadarClient";
import { signalOf } from "../lib/refreshSchedule";
import { SymbolScanner } from "../views/SymbolScanner";
import fixture from "./fixtures/spotRadar-scanner.json";

vi.mock("../lib/spotRadarClient", async original => ({ ...await original<typeof import("../lib/spotRadarClient")>(), fetchRadar: vi.fn() }));
const T = 1_800_000_000_000;
beforeEach(() => { try { localStorage.clear(); } catch { /* */ } });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.mocked(fetchRadar).mockReset(); });

describe("signalOf", () => {
  const base = { cadence: "live" as const, pendingSince: null, lastOk: T, error: false, sourceActive: true, now: T + 1_000 };
  it("is green when the last read is on time, orange when slow or late, red when off, failed or inactive", () => {
    expect(signalOf(base).signal).toBe("green");
    expect(signalOf({ ...base, pendingSince: T, now: T + 3_001 })).toEqual({ signal: "orange", label: "Connexion faible · en attente des résultats" });
    expect(signalOf({ ...base, lastOk: null, pendingSince: T, now: T + 100 }).label).toBe("En attente des premiers résultats");
    expect(signalOf({ ...base, now: T + 5_000 + 6_001 }).label).toBe("Résultats en retard");
    expect(signalOf({ ...base, cadence: "1m", now: T + 60_000 }).signal).toBe("green");
    expect(signalOf({ ...base, cadence: "off" })).toEqual({ signal: "red", label: "Inactif · lecture arrêtée (Off)" });
    expect(signalOf({ ...base, error: true }).signal).toBe("red");
    expect(signalOf({ ...base, sourceActive: false }).label).toBe("Source inactive");
  });
});

describe("Moniteur de marché", () => {
  const light = () => screen.getByRole("status", { name: "Voyant de connexion" });
  it("reads every 5 s in Live, every minute in 1m, and stops on Off with a red light", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
    vi.setSystemTime(Number(fixture.server_time_ms));
    vi.mocked(fetchRadar).mockResolvedValue(fixture as RadarScanner);
    render(<SymbolScanner selection={[]} onSelect={() => {}} />);
    await act(async () => {});
    expect(fetchRadar).toHaveBeenCalledTimes(1);
    expect(light()).toHaveClass("green");
    await act(async () => { vi.advanceTimersByTime(5_000); });
    expect(fetchRadar).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole("button", { name: "1m" }));
    await act(async () => {});
    expect(fetchRadar).toHaveBeenCalledTimes(3); // nouveau rythme : lecture immédiate
    await act(async () => { vi.advanceTimersByTime(59_000); });
    expect(fetchRadar).toHaveBeenCalledTimes(3);
    await act(async () => { vi.advanceTimersByTime(1_000); });
    expect(fetchRadar).toHaveBeenCalledTimes(4);
    fireEvent.click(screen.getByRole("button", { name: "Off" }));
    await act(async () => { vi.advanceTimersByTime(600_000); });
    expect(fetchRadar).toHaveBeenCalledTimes(4);
    expect(light()).toHaveClass("red");
    expect(light()).toHaveTextContent("Inactif · lecture arrêtée (Off)");
    expect(screen.getByRole("button", { name: "Off" })).toHaveAttribute("aria-pressed", "true");
  });

  it("turns orange while a read is pending for more than 3 s", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
    vi.setSystemTime(Number(fixture.server_time_ms));
    vi.mocked(fetchRadar).mockReturnValue(new Promise(() => {}));
    render(<SymbolScanner selection={[]} onSelect={() => {}} />);
    await act(async () => { vi.advanceTimersByTime(4_000); });
    expect(light()).toHaveClass("orange");
    expect(light()).toHaveTextContent("Connexion faible · en attente des résultats");
  });

  it("turns red when the collector is not running", async () => {
    const stopped = structuredClone(fixture) as RadarScanner;
    stopped.collector.state = "STOPPED" as never;
    vi.mocked(fetchRadar).mockResolvedValue(stopped);
    render(<SymbolScanner selection={[]} onSelect={() => {}} />);
    await screen.findByRole("table");
    expect(light()).toHaveClass("red");
    expect(light()).toHaveTextContent("Source inactive");
  });
});
