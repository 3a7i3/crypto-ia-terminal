import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { validateTrade } from "../lib/footprintEngine";
import { IMB, buildFootprintModel } from "../lib/footprintModel";
import { FootprintChart } from "./FootprintChart";
import { FOOTPRINT_REPLAY_SHA256, loadFootprintReplay, type FootprintReplay, type FootprintReplayState } from "../lib/footprintReplay";
import "../footprint.css";

// Panneau Footprint de la vue Microstructure : vue unique BTC_USDT.
// À l'ouverture, le panneau lit la capture MEXC figée livrée avec la release
// (vérifiée par SHA-256) et affiche un seul tableau. Aucun flux temps réel n'est
// branché ici ; un branchement futur relève d'une décision gouvernée distincte.
// Observation passive : aucun signal, aucun ordre, aucune autorité.

export const FOOTPRINT_SYMBOL_LABEL = "BTC_USDT · perpétuel · MEXC";
const PERIODS = [
  { ms: 60_000, label: "1 min" }, { ms: 300_000, label: "5 min" },
  { ms: 900_000, label: "15 min" }, { ms: 3_600_000, label: "1 h" },
];
const STEP_MULTIPLIERS = [1, 5, 10, 50, 100, 500, 1000, 5000];
const VISIBLE_COUNTS = [6, 12, 24];
const MAX_LADDER_ROWS = 240;

const fmt = (v: number, digits = 4) => v.toLocaleString("fr-FR", { maximumFractionDigits: digits });
const signed = (v: number) => `${v > 0 ? "+" : ""}${fmt(v)}`;
const utc = (ms: number) => new Date(ms).toISOString().replace(".000Z", "Z");
const hhmm = (ms: number) => new Date(ms).toISOString().slice(11, 16);
const duration = (ms: number) => {
  if (ms < 60_000) return `${(Math.round(ms / 100) / 10).toLocaleString("fr-FR")} s`;
  const h = Math.floor(ms / 3_600_000); const m = Math.round((ms % 3_600_000) / 60_000);
  return h > 0 ? `${h} h ${String(m).padStart(2, "0")}` : `${m} min`;
};

/** Qualité au pas natif de la source, indépendante de l'agrégation d'affichage. */
function nativeQuality(replay: FootprintReplay) {
  const rejected: Record<string, number> = {};
  let accepted = 0; let offTick = 0; let unc = 0; let total = 0; let lo = Infinity; let hi = -Infinity;
  for (const t of replay.trades) {
    const reason = validateTrade(t);
    if (reason) { rejected[reason] = (rejected[reason] ?? 0) + 1; continue; }
    accepted += 1;
    const ratio = t.price / replay.tick_size;
    if (Math.abs(ratio - Math.round(ratio)) > 1e-6) offTick += 1;
    total += t.qty; if (t.side == null) unc += t.qty;
    lo = Math.min(lo, t.price); hi = Math.max(hi, t.price);
  }
  return { accepted, rejected, offTick, unclassifiedRatio: total > 0 ? unc / total : 0, lo, hi };
}

export function autoStepMultiplier(tick: number, lo: number, hi: number, targetRows = 80) {
  if (!(hi > lo)) return 1;
  return STEP_MULTIPLIERS.find((m) => (hi - lo) / (tick * m) <= targetRows) ?? STEP_MULTIPLIERS[STEP_MULTIPLIERS.length - 1];
}

const Ladder: React.FC<{ replay: FootprintReplay; tfMs: number; step: number; visible: number }> = ({ replay, tfMs, step, visible }) => {
  const model = useMemo(() => buildFootprintModel(replay, tfMs, step, visible), [replay, tfMs, step, visible]);
  const { snap, bars, gaps, profile } = model;
  if (bars.length === 0) return <p data-testid="footprint-empty">Aucune bougie : aucune transaction valide dans le rejeu.</p>;
  const hiIdx = Math.max(...bars.map((b) => b.hiIdx));
  const loIdx = Math.min(...bars.map((b) => b.loIdx));
  const rows = hiIdx - loIdx + 1;
  const maxVol = Math.max(...profile.levels.map((l) => l.volume), 0);
  const profileByIdx = new Map(profile.levels.map((l) => [l.idx, l]));
  const byBar = bars.map((b) => new Map(b.levels.map((l) => [l.idx, l])));
  const priceDigits = Math.max(0, -Math.floor(Math.log10(step)) + 1);
  const priceOf = (idx: number) => (idx * step).toLocaleString("fr-FR", { minimumFractionDigits: Math.min(priceDigits, 8), maximumFractionDigits: Math.min(priceDigits, 8) });
  return <>
    {rows <= MAX_LADDER_ROWS && <FootprintChart model={model} step={step} />}
    <details open={rows > MAX_LADDER_ROWS || undefined}>
    <summary>Valeurs exactes</summary>
    <div className="footprint-scroll" data-testid="footprint-scroll" tabIndex={0} aria-label="Footprint Bid × Ask par niveau">
      {rows > MAX_LADDER_ROWS
        ? <p data-testid="footprint-too-many-levels">{rows} niveaux à afficher : augmentez le pas des niveaux (limite {MAX_LADDER_ROWS}).</p>
        : <table className="footprint-table" data-testid="footprint-table">
          <thead><tr>
            <th scope="col" className="footprint-price">Prix</th>
            {bars.map((b, i) => {
              const inGap = gaps.some(([a, z]) => b.t0 < z && b.t0 + tfMs > a);
              return <th scope="col" key={b.t0} title={utc(b.t0)}>
                {hhmm(b.t0)}{model.partial[i] && <span className="footprint-flag" title="Session commencée avant la couverture du rejeu"> · partiel</span>}{inGap && <span className="footprint-flag"> · lacune</span>}
              </th>;
            })}
            <th scope="col">Profil vol.</th>
          </tr></thead>
          <tbody>
            {Array.from({ length: rows }, (_, k) => hiIdx - k).map((idx) => {
              const p = profileByIdx.get(idx);
              const isPoc = profile.pocVolume?.idx === idx;
              return <tr key={idx} className={isPoc ? "footprint-poc-row" : undefined}>
                <th scope="row" className="footprint-price">{priceOf(idx)}</th>
                {bars.map((b, i) => {
                  const l = byBar[i].get(idx);
                  const inBody = idx <= Math.max(b.openIdx, b.closeIdx) && idx >= Math.min(b.openIdx, b.closeIdx);
                  const cls = ["footprint-cell", inBody ? (b.closeIdx >= b.openIdx ? "footprint-body-up" : "footprint-body-down") : ""].join(" ");
                  if (!l) return <td key={b.t0} className={cls} />;
                  const exact = `Bid ${l.bid} × Ask ${l.ask}${l.unc ? ` · non classé ${l.unc}` : ""}`;
                  return <td key={b.t0} className={cls} title={exact}>
                    <span className={l.sellImb ? `footprint-imb-sell${l.stackedSell ? " footprint-stacked" : ""}` : undefined}>{fmt(l.bid, 2)}</span>
                    <span className="footprint-x">×</span>
                    <span className={l.buyImb ? `footprint-imb-buy${l.stackedBuy ? " footprint-stacked" : ""}` : undefined}>{fmt(l.ask, 2)}</span>
                  </td>;
                })}
                <td className="footprint-profile" title={p ? `Volume ${p.volume} · Delta ${p.delta}` : undefined}>
                  {p && <span className="footprint-profile-bar" style={{ width: `${maxVol > 0 ? (p.volume / maxVol) * 100 : 0}%` }} data-delta-sign={Math.sign(p.delta)} />}
                </td>
              </tr>;
            })}
          </tbody>
          <tfoot>
            {([
              ["Volume", (b: typeof bars[number]) => fmt(b.volume, 2)],
              ["Delta", (b: typeof bars[number]) => signed(b.delta)],
              ["DeltaChg", (b: typeof bars[number]) => b.deltaChg === null ? "—" : signed(b.deltaChg)],
              ["DltaDay", (b: typeof bars[number]) => `${signed(b.dltaDay)}${b.sessionPartial ? " *" : ""}`],
            ] as const).map(([label, cell]) => <tr key={label} data-testid={`footprint-row-${label}`}>
              <th scope="row" className="footprint-price">{label}</th>
              {bars.map((b) => <td key={b.t0}>{cell(b)}</td>)}
              <td />
            </tr>)}
          </tfoot>
        </table>}
    </div>
    <p className="footprint-legend" data-testid="footprint-profile-summary">
      Bougies affichées : {bars.length} sur {snap.bars.length}. POC volume {profile.pocVolume ? priceOf(profile.pocVolume.idx) : "—"} · Delta extrême {profile.pocDelta ? `${priceOf(profile.pocDelta.idx)} (${signed(profile.pocDelta.delta)})` : "—"} · Delta cumulé affiché {signed(profile.totalDelta)}.
      {" "}Niveaux au plancher du pas {fmt(step, 8)}.
      {bars.some((b) => b.sessionPartial) && " * DltaDay partiel : le cumul commence au début de la couverture, pas à l'ouverture de session (00:00 UTC)."}
    </p>
    </details>
  </>;
};

const UNAVAILABLE_DETAIL = (state: Exclude<FootprintReplayState, { status: "idle" | "loading" | "ready" }>) => {
  if (state.status === "absent") return `Fichier non livré : ${state.detail}. Aucune donnée de remplacement n'est affichée.`;
  if (state.status === "invalid") return `Fichier refusé : ${state.reason}. Rien n'est affiché à partir de ce fichier.`;
  return `Lecture impossible : ${state.message}. Une panne de lecture n'est pas une absence de transactions.`;
};

const CaptureView: React.FC<{ state: FootprintReplayState; onRetry: () => void }> = ({ state, onRetry }) => {
  const [tfMs, setTfMs] = useState(PERIODS[1].ms);
  const [stepChoice, setStepChoice] = useState<"auto" | number>("auto");
  const [visible, setVisible] = useState(12);
  const replay = state.status === "ready" ? state.replay : null;
  const quality = useMemo(() => replay ? nativeQuality(replay) : null, [replay]);
  if (state.status === "idle" || state.status === "loading") {
    return <p role="status" className="footprint-loading" data-testid="footprint-capture-loading">Chargement de la capture BTC_USDT…</p>;
  }
  if (state.status !== "ready") return <div className="footprint-notice" role="status" data-testid="footprint-capture-unavailable" data-reason={state.status}>
    <strong>Capture indisponible</strong>
    <p>{UNAVAILABLE_DETAIL(state)}</p>
    <button type="button" onClick={onRetry}>Réessayer</button>
  </div>;
  const r = state.replay; const q = quality!; const p = r.provenance;
  const step = r.tick_size * (stepChoice === "auto" ? autoStepMultiplier(r.tick_size, q.lo, q.hi) : stepChoice);
  const from = Date.parse(p.coverage_from_utc); const to = Date.parse(p.coverage_to_utc);
  const rejectedTotal = Object.values(q.rejected).reduce((a, b) => a + b, 0);
  const sessionStart = Math.floor(from / 86_400_000) * 86_400_000;
  const partial = from > sessionStart || p.gaps.length > 0 || rejectedTotal > 0 || q.unclassifiedRatio > 0;
  const unit = p.qty_unit === "contracts" ? "contrats" : "actif de base";
  return <>
    <div className="footprint-provenance" data-testid="footprint-provenance">
      <p className="footprint-mention" data-testid="footprint-mention">
        <span className="footprint-badge">Capture figée</span>
        {partial && <> · <span className="footprint-badge footprint-badge-warn" data-testid="footprint-partial">Couverture partielle</span></>}
      </p>
      <p className="footprint-coverage-line" data-testid="footprint-coverage">
        {p.venue} · {p.symbol} perpétuel · quantités en {unit} · {p.coverage_from_utc} → {p.coverage_to_utc} ({duration(to - from)}) · {q.accepted.toLocaleString("fr-FR")} transactions{p.gaps.length ? ` · ${p.gaps.length} lacune(s)` : ""} · côté agresseur publié par {p.venue}
      </p>
      <details className="footprint-details"><summary>Provenance et qualité</summary>
      <dl className="footprint-facts">
        <div><dt>Source</dt><dd>{p.source}</dd></div>
        <div><dt>Collecte</dt><dd>{p.collected_at_utc}</dd></div>
        <div><dt>Transactions</dt><dd>{q.accepted.toLocaleString("fr-FR")} acceptées · {rejectedTotal} rejetées{rejectedTotal ? ` (${Object.entries(q.rejected).map(([k, v]) => `${k} ${v}`).join(", ")})` : ""} · {q.offTick} hors pas</dd></div>
        <div><dt>Origine du côté agresseur</dt><dd data-testid="footprint-aggressor-origin">Publié par {p.venue} avec chaque transaction ({p.source}) ; jamais déduit du prix ni du carnet.</dd></div>
        <div><dt>Côté agresseur</dt><dd>{(q.unclassifiedRatio * 100).toLocaleString("fr-FR", { maximumFractionDigits: 2 })} % du volume non classé (jamais deviné)</dd></div>
        <div><dt>Unité des quantités</dt><dd>{p.qty_unit === "contracts" ? "contrats (source)" : "actif de base"}</dd></div>
        <div><dt>Lacunes connues</dt><dd data-testid="footprint-gaps">{p.gaps.length === 0 ? "aucune déclarée" : p.gaps.map((g) => `${g.from_utc} → ${g.to_utc}`).join(" ; ")}</dd></div>
        <div><dt>Session DltaDay</dt><dd>00:00 UTC (provisoire){from > sessionStart ? ` · couverture commencée ${duration(from - sessionStart)} après l'ouverture` : ""}</dd></div>
        <div><dt>Empreinte SHA-256</dt><dd className="footprint-hash" data-testid="footprint-sha256">{state.sha256} · {state.bytes.toLocaleString("fr-FR")} octets · vérifiée</dd></div>
        <div><dt>Réglages IMB</dt><dd>IMB {IMB.imbPct} % · MIN {IMB.imbMin} · empilement {IMB.stackN} · minimum côté dominant : réglages par défaut du moteur, non validés.</dd></div>
        {p.notes && <div><dt>Notes</dt><dd>{p.notes}</dd></div>}
      </dl>
      </details>
    </div>
    <div className="footprint-controls" role="group" aria-label="Réglages du tableau">
      <label>Période<select value={tfMs} onChange={(e) => setTfMs(Number(e.target.value))}>{PERIODS.map((x) => <option key={x.ms} value={x.ms}>{x.label}</option>)}</select></label>
      <label>Pas<select aria-label="Pas des niveaux" value={String(stepChoice)} onChange={(e) => setStepChoice(e.target.value === "auto" ? "auto" : Number(e.target.value))}>
        <option value="auto">Auto ({fmt(r.tick_size * autoStepMultiplier(r.tick_size, q.lo, q.hi), 8)})</option>
        {STEP_MULTIPLIERS.map((m) => <option key={m} value={m}>{fmt(r.tick_size * m, 8)}</option>)}
      </select></label>
      <label>Bougies<select value={visible} onChange={(e) => setVisible(Number(e.target.value))}>{VISIBLE_COUNTS.map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
    </div>
    <Ladder replay={r} tfMs={tfMs} step={step} visible={visible} />
  </>;
};

export const FootprintPanel: React.FC<{ fetchImpl?: typeof fetch; expectedSha256?: string | null }> = ({ fetchImpl, expectedSha256 = FOOTPRINT_REPLAY_SHA256 }) => {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [fullscreen, setFullscreen] = useState(false);
  const [replayState, setReplayState] = useState<FootprintReplayState>({ status: "idle" });
  const ref = useRef<HTMLElement>(null);

  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const load = useCallback(() => {
    setReplayState({ status: "loading" });
    void loadFootprintReplay(fetchImpl ?? fetch, undefined, expectedSha256).then((s) => { if (mounted.current) setReplayState(s); });
  }, [fetchImpl, expectedSha256]);
  // Une seule lecture à l'ouverture ; le thème et le plein écran ne la relancent pas.
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const onChange = () => { if (!document.fullscreenElement) setFullscreen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setFullscreen(false); };
    document.addEventListener("fullscreenchange", onChange);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("fullscreenchange", onChange); document.removeEventListener("keydown", onKey); };
  }, []);
  const toggleFullscreen = () => {
    const el = ref.current;
    if (fullscreen) {
      if (document.fullscreenElement && document.exitFullscreen) void document.exitFullscreen().catch(() => undefined);
      setFullscreen(false);
      return;
    }
    setFullscreen(true); // le repli CSS couvre l'écran même si l'API est refusée
    if (el?.requestFullscreen) void el.requestFullscreen().catch(() => undefined);
  };

  return <section ref={ref} className={`market-panel footprint-panel${fullscreen ? " footprint-fullscreen" : ""}`}
    data-testid="footprint-panel" data-footprint-theme={theme} aria-label="Footprint">
    <div className="footprint-head">
      <div><div className="market-eyebrow">FOOTPRINT · OBSERVATION PASSIVE</div><h2>Footprint · {FOOTPRINT_SYMBOL_LABEL}</h2></div>
      <div className="footprint-actions">
        <label className="footprint-theme">
          <span>Thème</span>
          <select data-testid="footprint-theme-select" value={theme} onChange={(e) => setTheme(e.target.value === "dark" ? "dark" : "light")}>
            <option value="light">Clair</option>
            <option value="dark">Sombre</option>
          </select>
        </label>
        <button type="button" aria-pressed={fullscreen} onClick={toggleFullscreen}>{fullscreen ? "Quitter le plein écran" : "Plein écran"}</button>
      </div>
    </div>
    {/* Aucun flux n'est branché : l'indisponibilité du temps réel est affichée, sans requête. */}
    <p className="footprint-live" data-testid="footprint-live-status">Temps réel indisponible · aucune source admise pour BTC_USDT, aucune connexion ouverte. Affichage : rejeu historique.</p>
    <CaptureView state={replayState} onRetry={load} />
    <p className="footprint-legend">Footprint non autoritaire · aucun signal d'entrée, aucun ordre, aucune permission de trading.</p>
  </section>;
};
