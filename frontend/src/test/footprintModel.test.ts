import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { buildFootprintModel } from "../lib/footprintModel";
import { parseFootprintReplay } from "../lib/footprintReplay";
import { syntheticTwentyBars } from "./footprintSyntheticTwentyBars";

const real = parseFootprintReplay(JSON.parse(readFileSync(resolve(__dirname, "../../public/observations/footprint/mexc-btc_usdt-perp-replay-v1.json"), "utf8")));
const M5 = 300_000;

describe("modèle Footprint partagé", () => {
  it("reproduit le rejeu MEXC BTC_USDT perpétuel en M5 (pas 1)", () => {
    const m = buildFootprintModel(real, M5, 1, 12);
    expect(m.bars.map((b) => b.volume)).toEqual([9984, 73521]);
    expect(m.bars.map((b) => b.delta)).toEqual([8960, -15145]);
    expect(m.bars.map((b) => b.deltaChg)).toEqual([null, -24105]);
    expect(m.bars.at(-1)!.dltaDay).toBe(-6185);
    expect(m.bars.every((b) => b.sessionPartial)).toBe(true); // DltaDay commence au début de la capture
    expect(m.partial).toEqual([true, true]); // la capture (15 s) ne couvre aucune fenêtre M5 entière
    expect(m.profile.totalDelta).toBe(-6185);
    expect(m.profile.pocVolume?.price).toBe(58680);
  });

  it("garde des invariants entre niveaux, bougies et profil", () => {
    for (const replay of [real, syntheticTwentyBars()]) {
      for (const [tf, step] of [[60_000, 0.1], [M5, 1], [900_000, 10]] as const) {
        const m = buildFootprintModel(replay, tf, step, 24);
        for (const b of m.bars) {
          const sum = b.levels.reduce((a, l) => ({ v: a.v + l.bid + l.ask + l.unc, d: a.d + l.ask - l.bid }), { v: 0, d: 0 });
          expect(sum.v).toBeCloseTo(b.volume, 6);
          expect(sum.d).toBeCloseTo(b.delta, 6);
          expect(b.levels.every((l) => l.idx >= b.loIdx && l.idx <= b.hiIdx)).toBe(true);
          expect([b.openIdx, b.closeIdx].every((i) => i >= b.loIdx && i <= b.hiIdx)).toBe(true);
        }
        expect(m.profile.levels.reduce((a, l) => a + l.volume, 0)).toBeCloseTo(m.bars.reduce((a, b) => a + b.volume, 0), 6);
      }
    }
  });

  it("produit 20 bougies M1 entières avec la fixture SYNTHETIC", () => {
    const replay = syntheticTwentyBars();
    expect(replay.provenance.source).toMatch(/^SYNTHETIC/);
    const m = buildFootprintModel(replay, 60_000, 1, 24);
    expect(m.bars).toHaveLength(20);
    expect(m.partial.every((p) => !p)).toBe(true);
  });
});
