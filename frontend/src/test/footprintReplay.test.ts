import { describe, expect, it, vi } from "vitest";
import { FOOTPRINT_REPLAY_URL, FootprintReplayError, loadFootprintReplay, parseFootprintReplay } from "../lib/footprintReplay";
import { syntheticReplay } from "./footprintReplayFixture";

const resp = (body: string, status = 200, type = "application/json; charset=utf-8") =>
  new Response(body, { status, headers: { "content-type": type } });

describe("contrat du rejeu Footprint", () => {
  it("accepte un rejeu BTC_USDT perpétuel MEXC complet", () => {
    expect(parseFootprintReplay(syntheticReplay()).trades).toHaveLength(6);
  });

  it.each([
    ["schéma", (d: ReturnType<typeof syntheticReplay>) => { (d as Record<string, unknown>).schema = "v0"; }, /schéma/],
    ["symbole", (d: ReturnType<typeof syntheticReplay>) => { d.provenance.symbol = "ETH_USDT"; }, /BTC_USDT perpétuel MEXC/],
    ["marché spot", (d: ReturnType<typeof syntheticReplay>) => { d.provenance.market_type = "spot"; }, /perpétuel/],
    ["source vide", (d: ReturnType<typeof syntheticReplay>) => { d.provenance.source = " "; }, /source/],
    ["date non UTC", (d: ReturnType<typeof syntheticReplay>) => { d.provenance.coverage_to_utc = "2026-01-05 10:20"; }, /coverage_to_utc/],
    ["fenêtre inversée", (d: ReturnType<typeof syntheticReplay>) => { d.provenance.coverage_to_utc = "2026-01-05T09:00:00Z"; }, /fenêtre/],
    ["unité", (d: ReturnType<typeof syntheticReplay>) => { d.provenance.qty_unit = "usd"; }, /qty_unit/],
    ["côté non agresseur", (d: ReturnType<typeof syntheticReplay>) => { d.provenance.side_semantics = "maker"; }, /aggressor/],
    ["lacunes absentes", (d: ReturnType<typeof syntheticReplay>) => { delete d.provenance.gaps; }, /gaps/],
    ["tick infini", (d: ReturnType<typeof syntheticReplay>) => { d.tick_size = Infinity; }, /tick_size/],
    ["aucune transaction", (d: ReturnType<typeof syntheticReplay>) => { d.trades = []; }, /aucune transaction/],
    ["hors couverture", (d: ReturnType<typeof syntheticReplay>) => { d.trades[0].ts = Date.UTC(2026, 0, 5, 12); }, /hors de la fenêtre/],
  ])("refuse un rejeu invalide : %s", (_name, mutate, reason) => {
    const doc = syntheticReplay(); mutate(doc);
    expect(() => parseFootprintReplay(doc)).toThrow(FootprintReplayError);
    expect(() => parseFootprintReplay(doc)).toThrow(reason);
  });

  it("distingue fichier absent, repli HTML, panne, JSON illisible et rejeu valide", async () => {
    expect((await loadFootprintReplay(vi.fn().mockResolvedValue(resp("", 404)))).status).toBe("absent");
    expect((await loadFootprintReplay(vi.fn().mockResolvedValue(resp("<!doctype html>", 200, "text/html")))).status).toBe("absent");
    expect(await loadFootprintReplay(vi.fn().mockResolvedValue(resp("{}", 503)))).toEqual({ status: "error", message: "HTTP 503" });
    expect(await loadFootprintReplay(vi.fn().mockRejectedValue(new Error("offline")))).toEqual({ status: "error", message: "offline" });
    expect(await loadFootprintReplay(vi.fn().mockResolvedValue(resp("{")))).toEqual({ status: "invalid", reason: "JSON illisible" });
    const body = JSON.stringify(syntheticReplay());
    const fetchImpl = vi.fn().mockResolvedValue(resp(body));
    const ready = await loadFootprintReplay(fetchImpl);
    expect(fetchImpl).toHaveBeenCalledWith(FOOTPRINT_REPLAY_URL, expect.objectContaining({ cache: "no-store" }));
    expect(ready.status).toBe("ready");
    if (ready.status === "ready") {
      expect(ready.sha256).toMatch(/^[0-9a-f]{64}$/);
      expect(ready.bytes).toBe(new TextEncoder().encode(body).length);
    }
  });
});
