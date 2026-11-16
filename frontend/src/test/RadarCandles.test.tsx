import { describe, it, expect } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { RadarCandles } from "../components/RadarCandles";
import type { Bar } from "../lib/spotRadarClient";
const bar={open_ms:"1794820800000",open:"100",high:"103",low:"98",close:"102",base_volume:"12.5",closed:false} as Bar;
describe("RadarCandles operational chart",()=>{
 it("renders OHLC and volume without replacing native decimals",()=>{render(<RadarCandles rows={[bar]} symbol="BTC/USDT" timeframe="M5"/>);expect(screen.getByRole("img").getAttribute("aria-label")).toContain("BTC/USDT M5");expect(document.querySelector("svg")?.textContent).toContain("O 100 · H 103 · L 98 · C 102");cleanup();});
 it("handles a flat candle and zero volume",()=>{render(<RadarCandles rows={[{...bar,open:"1",close:"1",low:"1",high:"1",base_volume:"0"}]} symbol="A/USDT" timeframe="H1"/>);expect(document.querySelector("svg")?.outerHTML).not.toMatch(/NaN|Infinity/);cleanup();});
 it("does not invent candles when empty",()=>{render(<RadarCandles rows={[]} symbol="BTC/USDT" timeframe="M5"/>);expect(screen.queryByRole("img")).toBeNull();expect(screen.getByText("Pas de bougies disponibles.")).toBeTruthy();cleanup();});
 it("refuses nonfinite chart scaling",()=>{render(<RadarCandles rows={[{...bar,high:"invalid"}]} symbol="BTC/USDT" timeframe="M5"/>);expect(screen.queryByRole("img")).toBeNull();cleanup();});
});
