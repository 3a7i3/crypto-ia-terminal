import React, { useEffect, useRef, useState } from "react";
import type { FootprintModel } from "../lib/footprintModel";

// Graphique Footprint : axe des prix à gauche, bougies (mèche jusqu'aux extrêmes observés,
// corps entre ouverture et clôture) avec une cellule Bid × Ask à chaque prix négocié,
// profil Delta (Δ = Ask − Bid, barres signées autour de zéro) ou Volume (POC) à droite sur
// la même échelle de prix, puis DeltaChg / Delta / DltaDay / Volume et l'heure UTC sous
// chaque bougie. Rendu seul : toutes les valeurs viennent du modèle partagé avec
// « Valeurs exactes » ; aucun recalcul.

const num = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 8 });
const hhmm = (ms: number) => new Date(ms).toISOString().slice(11, 16);
/** Lignes sous les bougies, dans l'ordre de la maquette, puis l'heure UTC d'ouverture. */
export const STAT_ROWS = ["DeltaChg", "Delta", "DltaDay", "Volume", "UTC"] as const;

export function FootprintChart({ model, step }: { model: FootprintModel; step: number }) {
  const { bars, profile, partial } = model;
  const [profileKind, setProfileKind] = useState<"delta" | "volume">("delta");
  const [selected, setSelected] = useState<{ bar: number; idx: number }>();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [overflow, setOverflow] = useState(false);
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const update = () => setOverflow(el.scrollWidth > el.clientWidth + 1);
    update();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, [bars]);
  function page(direction: number) {
    const el = scrollRef.current;
    if (el) el.scrollBy({ left: direction * Math.max(82, el.clientWidth - 120) });
  }
  const hiIdx = Math.max(...bars.map((b) => b.hiIdx));
  const loIdx = Math.min(...bars.map((b) => b.loIdx));
  const byBar = bars.map((b) => new Map(b.levels.map((l) => [l.idx, l])));
  const profileByIdx = new Map(profile.levels.map((l) => [l.idx, l]));
  const maxProfile = Math.max(1, ...profile.levels.map((l) => Math.abs(l[profileKind])));
  const maxCell = Math.max(1, ...bars.flatMap((b) => b.levels.map((l) => Math.max(l.bid, l.ask))));
  const selectedBar = bars.findIndex((b) => b.t0 === selected?.bar);
  const selectedLevel = selected && byBar[selectedBar]?.get(selected.idx);
  return <section aria-label="Graphique Footprint" data-testid="footprint-chart">
    <label className="fp-profile-choice">Profil <select value={profileKind} onChange={(e) => setProfileKind(e.target.value as "delta" | "volume")}>
      <option value="delta">Delta (Ask − Bid)</option>
      <option value="volume">Volume</option>
    </select></label>
    {overflow && <nav aria-label="Navigation des bougies">
      <button type="button" onClick={() => page(-1)} aria-label="Bougies précédentes">‹</button>
      <button type="button" onClick={() => page(1)} aria-label="Bougies suivantes">›</button>
      <button type="button" onClick={() => scrollRef.current?.scrollTo({ left: scrollRef.current.scrollWidth })}>Dernière</button>
    </nav>}
    <div className="fp-chart-scroll" tabIndex={0} ref={scrollRef} data-testid="footprint-chart-scroll" aria-label="Graphique Footprint : déplacement horizontal et vertical">
      <div className="fp-chart-grid" style={{ gridTemplateColumns: `max-content repeat(${bars.length}, minmax(max-content,1fr)) 76px` }}>
        <b className="fp-head">Prix</b>
        {bars.map((b, i) => <strong key={b.t0} className="fp-head" data-bar={b.t0} data-open={b.open} data-high={b.high} data-low={b.low} data-close={b.close}
          title={`O ${b.open} · H ${b.high} · B ${b.low} · C ${b.close} · extrêmes observés sur la capture`}>{hhmm(b.t0)}{partial[i] && " · partiel"}</strong>)}
        <b className="fp-head fp-right" data-profile={profileKind}>{profileKind === "delta" ? "Δ Ask − Bid" : "Volume"}</b>
        {Array.from({ length: hiIdx - loIdx + 1 }, (_, k) => {
          const idx = hiIdx - k;
          const value = profileByIdx.get(idx)?.[profileKind] ?? 0;
          return <React.Fragment key={idx}>
            <b>{num.format(idx * step)}</b>
            {bars.map((b, i) => {
              const level = byBar[i].get(idx);
              const inRange = idx >= b.loIdx && idx <= b.hiIdx;
              const inBody = idx >= Math.min(b.openIdx, b.closeIdx) && idx <= Math.max(b.openIdx, b.closeIdx);
              return <div key={b.t0} className="fp-chart-cell" data-active={selectedBar === i || selected?.idx === idx}
                data-bar={b.t0} data-idx={idx} data-bid={level?.bid} data-ask={level?.ask} data-unc={level?.unc}>
                {inRange && <i className={inBody ? "fp-body" : ""} data-partial={partial[i]} data-up={b.closeIdx >= b.openIdx} />}
                {level && <button type="button" onClick={() => setSelected({ bar: b.t0, idx })}
                  aria-label={`${hhmm(b.t0)} · ${idx * step} · Bid ${level.bid} · Ask ${level.ask} · non classé ${level.unc}`}>
                  <span style={{ backgroundColor: `color-mix(in srgb,var(--fp-sell) ${10 + 35 * Math.sqrt(level.bid / maxCell)}%,transparent)` }}
                    data-imb={level.sellImb ? "sell" : undefined} data-stacked={level.stackedSell} className={level.sellImb ? "footprint-imb-sell" : ""}>{num.format(level.bid)}</span>
                  {" × "}
                  <span style={{ backgroundColor: `color-mix(in srgb,var(--fp-buy) ${10 + 35 * Math.sqrt(level.ask / maxCell)}%,transparent)` }}
                    data-imb={level.buyImb ? "buy" : undefined} data-stacked={level.stackedBuy} className={level.buyImb ? "footprint-imb-buy" : ""}>{num.format(level.ask)}</span>
                </button>}
              </div>;
            })}
            <b data-idx={idx} data-volume={profileByIdx.get(idx)?.volume} data-delta={profileByIdx.get(idx)?.delta} data-poc={profile.pocVolume?.idx === idx}
              data-profile={profileKind} className="fp-profile-track" title={profileByIdx.get(idx) ? `Δ ${profileByIdx.get(idx)!.delta} · Volume ${profileByIdx.get(idx)!.volume}` : undefined}>
              <i style={{
                width: `${Math.abs(value) / maxProfile * (profileKind === "delta" ? 50 : 100)}%`,
                left: profileKind === "volume" ? "0" : value < 0 ? "auto" : "50%",
                right: profileKind === "delta" && value < 0 ? "50%" : "auto",
                background: value < 0 ? "var(--fp-sell)" : "var(--fp-buy)",
              }} />
              {profileKind === "volume" && profile.pocVolume?.idx === idx && <span className="fp-poc-tag">POC</span>}
            </b>
          </React.Fragment>;
        })}
        {STAT_ROWS.map((label, r) => <React.Fragment key={label}>
          <b className="fp-stat" data-stat={label} style={{ bottom: (STAT_ROWS.length - 1 - r) * 20 }}>{label}</b>
          {bars.map((b) => {
            const value = r === 4 ? null : [b.deltaChg, b.delta, b.dltaDay, b.volume][r];
            return <strong key={b.t0} className="fp-stat" data-stat={label} data-bar={b.t0} data-value={value ?? undefined} style={{ bottom: (STAT_ROWS.length - 1 - r) * 20 }}>
              {r === 4 ? hhmm(b.t0) : value == null ? "—" : num.format(value)}{r === 2 && b.sessionPartial && " *"}</strong>;
          })}
          <b className="fp-stat fp-right" style={{ bottom: (STAT_ROWS.length - 1 - r) * 20 }} />
        </React.Fragment>)}
      </div>
    </div>
    {selected && selectedLevel && <output>{hhmm(selected.bar)} UTC · {num.format(selected.idx * step)} · Bid {selectedLevel.bid} × Ask {selectedLevel.ask} · Non classé {selectedLevel.unc}</output>}
    {bars.some((b) => b.sessionPartial) && <small>* DltaDay cumulé depuis le début de la capture.</small>}
  </section>;
}
