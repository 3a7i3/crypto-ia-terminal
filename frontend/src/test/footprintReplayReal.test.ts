import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parseFootprintReplay } from "../lib/footprintReplay";
import { FootprintBuilder } from "../lib/footprintEngine";

// Rejeu MEXC réel livré par l'opérateur (100 transactions, ~15 s, continuité non vérifiée).
const FILE = resolve(__dirname, "../../public/observations/footprint/mexc-btc_usdt-perp-replay-v1.json");
const EXPECTED_SHA256 = "a41c608814c02a10e5a9369b11806196b770ad578db0d5037368413c4cce391f";

describe("rejeu MEXC réel servi par le build", () => {
  const bytes = readFileSync(FILE);

  it("conserve exactement le fichier livré", () => {
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(EXPECTED_SHA256);
  });

  it("passe le contrat cat.footprint.replay.v1 sans être une fixture", () => {
    const replay = parseFootprintReplay(JSON.parse(bytes.toString("utf8")));
    expect(replay.provenance).toMatchObject({ venue: "MEXC", market_type: "perpetual", symbol: "BTC_USDT", qty_unit: "contracts", side_semantics: "aggressor" });
    expect(replay.provenance.source).toMatch(/^https:\/\/api\.mexc\.com\//);
    expect(replay.provenance.source).not.toMatch(/SYNTH|FIXTURE/i);
    expect(replay.trades).toHaveLength(100);
    expect(replay.tick_size).toBe(0.1);
  });

  it("produit un DltaDay partiel : la couverture commence après 00:00 UTC", () => {
    const replay = parseFootprintReplay(JSON.parse(bytes.toString("utf8")));
    const b = new FootprintBuilder({ tickSize: replay.tick_size, tfMs: 60_000, coverageFromMs: Date.parse(replay.provenance.coverage_from_utc) });
    for (const t of replay.trades) b.push(t);
    const { bars, quality } = b.snapshot();
    expect(quality.accepted).toBe(100);
    expect(bars.length).toBeGreaterThan(0);
    expect(bars.every((bar) => bar.sessionPartial)).toBe(true);
  });
});
