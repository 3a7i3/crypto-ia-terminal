// Modèle d'affichage Footprint partagé par le graphique et le tableau « Valeurs exactes ».
// Une seule agrégation à partir de la capture figée : les deux rendus lisent les mêmes
// bougies, le même profil et les mêmes drapeaux de couverture partielle.
import { FootprintBuilder, profileOf, validateTrade } from "./footprintEngine";
import type { FootprintReplay } from "./footprintReplay";

// Réglages par défaut du moteur, affichés tels quels : ils ne sont pas validés.
export const IMB = Object.freeze({ imbPct: 150, imbMin: 50, stackN: 3, imbMinSide: "dominant" as const });

export function buildFootprint(replay: FootprintReplay, tfMs: number, step: number) {
  const coverageFromMs = Date.parse(replay.provenance.coverage_from_utc);
  const builder = new FootprintBuilder({ tickSize: step, tfMs, coverageFromMs, maxBars: 100_000, maxLevels: 2_000_000 });
  for (const t of replay.trades) {
    if (validateTrade(t)) continue; // déjà comptée dans la qualité native
    // Niveau = plancher du pas d'affichage : un prix appartient au niveau qui le contient.
    builder.push({ ...t, price: Math.floor(t.price / step + 1e-9) * step });
  }
  return builder.snapshot(IMB);
}

/**
 * Bougies visibles, lacunes, profil de la fenêtre affichée et bougies partielles :
 * une bougie est partielle si la capture ne couvre pas toute sa fenêtre ou si une
 * lacune déclarée la recoupe. Ses extrêmes sont alors des extrêmes observés.
 */
export function buildFootprintModel(replay: FootprintReplay, tfMs: number, step: number, visible: number) {
  const snap = buildFootprint(replay, tfMs, step);
  const bars = snap.bars.slice(-visible);
  const from = Date.parse(replay.provenance.coverage_from_utc);
  const to = Date.parse(replay.provenance.coverage_to_utc);
  const gaps = replay.provenance.gaps.map((g) => [Date.parse(g.from_utc), Date.parse(g.to_utc)] as const);
  return {
    snap, bars, gaps,
    partial: bars.map((b) => from > b.t0 || to < b.t0 + tfMs || gaps.some(([a, z]) => b.t0 < z && a < b.t0 + tfMs)),
    profile: profileOf(bars),
  };
}
export type FootprintModel = ReturnType<typeof buildFootprintModel>;
