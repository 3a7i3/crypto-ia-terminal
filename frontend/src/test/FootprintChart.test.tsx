import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FootprintChart, STAT_ROWS } from "../components/FootprintChart";
import { buildFootprintModel } from "../lib/footprintModel";
import { parseFootprintReplay } from "../lib/footprintReplay";
import { syntheticTwentyBars } from "./footprintSyntheticTwentyBars";

const real = parseFootprintReplay(JSON.parse(readFileSync(resolve(__dirname, "../../public/observations/footprint/mexc-btc_usdt-perp-replay-v1.json"), "utf8")));
const cells = (c: HTMLElement) => [...c.querySelectorAll<HTMLElement>(".fp-chart-cell")];
const stat = (c: HTMLElement, label: string) => [...c.querySelectorAll<HTMLElement>(`strong.fp-stat[data-stat="${label}"]`)].map((e) => (e.textContent ?? "").replace(/[\u202f\u00a0]/g, " "));

describe("graphique Footprint", () => {
  it("affiche le rejeu MEXC M5 avec les valeurs du modèle, sans recalcul", () => {
    const model = buildFootprintModel(real, 300_000, 1, 12);
    const { container } = render(<FootprintChart model={model} step={1} />);
    expect(stat(container, "Volume")).toEqual(["9 984", "73 521"]);
    expect(stat(container, "Delta")).toEqual(["8 960", "-15 145"]);
    expect(stat(container, "DeltaChg")).toEqual(["—", "-24 105"]);
    expect(stat(container, "DltaDay")).toEqual(["8 960 *", "-6 185 *"]);
    expect(stat(container, "UTC")).toEqual(["20:25", "20:30"]);
    const signs = (label: string) => [...container.querySelectorAll<HTMLElement>(`strong.fp-stat[data-stat="${label}"]`)].map((e) => e.dataset.sign);
    expect(signs("Delta")).toEqual(["pos", "neg"]);
    expect(signs("DeltaChg")).toEqual([undefined, "neg"]);
    expect(signs("DltaDay")).toEqual(["pos", "neg"]);
    // Axe des prix à droite, juste avant le profil, sur chaque ligne de prix.
    const grid = container.querySelector(".fp-chart-grid")!;
    for (const price of grid.querySelectorAll<HTMLElement>("b.fp-price[data-idx]")) {
      expect(price.nextElementSibling?.classList.contains("fp-profile-track")).toBe(true);
      expect(price.textContent!.replace(/[\u202f\u00a0]/g, " ")).toBe(new Intl.NumberFormat("fr-FR").format(Number(price.dataset.idx)).replace(/[\u202f\u00a0]/g, " "));
    }
    expect(screen.getByText("* DltaDay cumulé depuis le début de la capture.")).toBeInTheDocument();
    expect(container.querySelectorAll(".fp-head[data-bar]")).toHaveLength(2);
    expect([...container.querySelectorAll(".fp-head[data-bar]")].map((h) => h.textContent)).toEqual(["20:25 · partiel", "20:30 · partiel"]);
  });

  it("place une cellule Bid × Ask à chaque prix négocié, mèches comprises, et laisse vides les autres prix", () => {
    const model = buildFootprintModel(real, 300_000, 1, 12);
    const { container } = render(<FootprintChart model={model} step={1} />);
    const expected = new Set(model.bars.flatMap((b) => b.levels.map((l) => `${b.t0}:${l.idx}:${l.bid}:${l.ask}:${l.unc}`)));
    const drawn = new Set(cells(container).filter((c) => c.querySelector("button")).map((c) => `${c.dataset.bar}:${c.dataset.idx}:${c.dataset.bid}:${c.dataset.ask}:${c.dataset.unc}`));
    expect(drawn).toEqual(expected);
    for (const c of cells(container)) {
      const bar = model.bars.find((b) => String(b.t0) === c.dataset.bar)!;
      const idx = Number(c.dataset.idx);
      const inRange = idx >= bar.loIdx && idx <= bar.hiIdx;
      const inBody = idx >= Math.min(bar.openIdx, bar.closeIdx) && idx <= Math.max(bar.openIdx, bar.closeIdx);
      // Mèche jusqu'aux extrêmes observés, corps (boîte) entre ouverture et clôture.
      expect(!!c.querySelector(".fp-wick")).toBe(inRange);
      expect(!!c.querySelector(".fp-body")).toBe(inBody);
      expect(c.dataset.part).toBe(inRange ? (inBody ? "body" : "wick") : undefined);
      if (inRange) expect(c.dataset.up).toBe(String(bar.closeIdx >= bar.openIdx));
      if (inRange) expect(c.dataset.partial).toBe("true");
      if (idx === bar.hiIdx) expect(c.querySelector(".fp-wick")!.getAttribute("data-end")).toMatch(/high|both/);
      if (idx === bar.loIdx) expect(c.querySelector(".fp-wick")!.getAttribute("data-end")).toMatch(/low|both/);
    }
  });

  it("encadre seulement le côté marqué par le moteur et distingue les imbalances empilées", () => {
    const model = buildFootprintModel(syntheticTwentyBars(), 60_000, 1, 24);
    const { container } = render(<FootprintChart model={model} step={1} />);
    let framed = 0;
    for (const c of cells(container)) {
      const level = model.bars.find((b) => String(b.t0) === c.dataset.bar)!.levels.find((l) => String(l.idx) === c.dataset.idx);
      const spans = c.querySelectorAll("button span");
      if (!level) { expect(spans).toHaveLength(0); continue; }
      expect(spans[0].getAttribute("data-imb")).toBe(level.sellImb ? "sell" : null);
      expect(spans[1].getAttribute("data-imb")).toBe(level.buyImb ? "buy" : null);
      expect(spans[0].getAttribute("data-stacked")).toBe(String(!!level.stackedSell));
      framed += Number(!!level.sellImb) + Number(!!level.buyImb);
    }
    expect(framed).toBeGreaterThan(0);
  });

  it("affiche le profil Delta par défaut (Ask − Bid) et le profil Volume avec son POC, sur la fenêtre affichée", () => {
    const model = buildFootprintModel(real, 300_000, 1, 12);
    const { container } = render(<FootprintChart model={model} step={1} />);
    const tracks = () => [...container.querySelectorAll<HTMLElement>(".fp-profile-track")];
    expect(tracks().every((t) => t.dataset.profile === "delta")).toBe(true);
    expect(container.querySelector(".fp-head[data-profile]")).toHaveTextContent("Δ Ask−Bid");
    for (const t of tracks()) {
      const l = model.profile.levels.find((x) => String(x.idx) === t.dataset.idx);
      // Convention affichée : Δ = Ask − Bid, valeur exacte du modèle sur la fenêtre affichée.
      expect(t.dataset.delta).toBe(l ? String(l.delta) : undefined);
      if (l) expect(l.delta).toBeCloseTo(l.ask - l.bid, 9);
    }
    fireEvent.change(screen.getByRole("combobox", { name: /Profil/ }), { target: { value: "volume" } });
    const poc = tracks().find((t) => t.dataset.poc === "true")!;
    expect(Number(poc.dataset.idx)).toBe(model.profile.pocVolume!.idx);
    expect(within(poc).getByText("POC")).toBeInTheDocument();
  });

  it("aligne 20 bougies SYNTHETIC : une colonne par bougie et par ligne de statistiques, dans l'ordre", () => {
    const model = buildFootprintModel(syntheticTwentyBars(), 60_000, 1, 24);
    const { container } = render(<FootprintChart model={model} step={1} />);
    const grid = container.querySelector<HTMLElement>(".fp-chart-grid")!;
    expect(grid.style.gridTemplateColumns).toContain("repeat(20,");
    expect([...container.querySelectorAll("b.fp-stat[data-stat]")].map((e) => e.textContent)).toEqual([...STAT_ROWS]);
    for (const label of STAT_ROWS) expect(stat(container, label)).toHaveLength(20);
    const order = model.bars.map((b) => String(b.t0));
    for (const label of STAT_ROWS) expect([...container.querySelectorAll<HTMLElement>(`strong.fp-stat[data-stat="${label}"]`)].map((e) => e.dataset.bar)).toEqual(order);
    const rows = model.bars.length ? Math.max(...model.bars.map((b) => b.hiIdx)) - Math.min(...model.bars.map((b) => b.loIdx)) + 1 : 0;
    expect(cells(container)).toHaveLength(rows * 20);
  });
});
