// ── MiniChartPanel.tsx — Panel repliable pour Marché Live ────────────────────
//
// Priorité d'info (du haut vers le bas) :
//   1. Statut marché (state + gate)
//   2. Score signal + barre de progression
//   3. Variation récente + exposition
//   4. Mini chart SVG (repliable)
//   5. Badges indicateurs
//
// Compact (fermé) : lignes 1-3 uniquement — lecture en 1 seconde
// Expanded         : + chart SVG + indicateurs

import React, { useState, useMemo } from "react";
import type { SymbolSignal, MiniChartMetric } from "../types";
import { getMarketState, pnlColor, fmtPrice, fmtPct } from "../lib/tokens";
import { SignalBadge, IndicatorChipSet } from "./Badges";

// ── Icônes SVG inline sobres ──────────────────────────────────────────────────

const IconChart: React.FC<{ className?: string }> = ({ className = "" }) => (
  <svg width="12" height="10" viewBox="0 0 12 10" fill="none" aria-hidden="true" className={className}>
    <polyline
      points="0,9 3,5 6,7 9,2 12,1"
      stroke="currentColor" strokeWidth="1.5"
      strokeLinejoin="round" strokeLinecap="round"
    />
  </svg>
);

const IconChevron: React.FC<{ open: boolean }> = ({ open }) => (
  <svg
    width="10" height="6" viewBox="0 0 10 6" fill="none" aria-hidden="true"
    style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform 0.15s ease" }}
  >
    <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const IconBlock: React.FC = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
    <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.5" />
    <line x1="2.5" y1="2.5" x2="9.5" y2="9.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

// ── Score bar ─────────────────────────────────────────────────────────────────

const ScoreBar: React.FC<{ score: number }> = ({ score }) => {
  const color =
    score >= 70 ? "var(--accent)" :
    score >= 50 ? "var(--warn)"   : "var(--neutral)";
  return (
    <div className="flex items-center gap-2">
      <div
        className="relative flex-1 h-1 rounded-full overflow-hidden"
        style={{ background: "var(--bg-hover)" }}
        role="progressbar"
        aria-valuenow={score}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className="absolute inset-y-0 left-0 rounded-full"
          style={{ width: `${score}%`, background: color, transition: "width 0.4s ease" }}
        />
      </div>
      <span className="font-mono text-[11px] w-6 text-right" style={{ color }}>
        {score}
      </span>
    </div>
  );
};

// ── Chart SVG interne ─────────────────────────────────────────────────────────

const METRIC_LABELS: Record<MiniChartMetric, string> = {
  pnl:          "PnL",
  signal_score: "Score",
  exposure:     "Expo",
};

interface ChartData { ts: string; value: number }

const InlineSVGChart: React.FC<{ data: ChartData[]; w?: number; h?: number }> = ({
  data, w = 280, h = 56,
}) => {
  const { line, area, dot, color } = useMemo(() => {
    const values = data.map(d => d.value);
    if (values.length < 2) return { line: null, area: null, dot: null, color: "var(--neutral)" };

    const min = Math.min(...values);
    const max = Math.max(...values);
    const rng = max - min || 1;
    const PX = 4, PY = 4;

    const pts = values.map((v, i) => ({
      x: PX + (i / (values.length - 1)) * (w - PX * 2),
      y: PY + (1 - (v - min) / rng) * (h - PY * 2),
    }));

    const lineD = "M" + pts.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" L");
    const areaD = lineD +
      ` L${pts.at(-1)!.x.toFixed(1)},${(h - PY).toFixed(1)}` +
      ` L${pts[0].x.toFixed(1)},${(h - PY).toFixed(1)} Z`;
    const last = values.at(-1) ?? 0;
    const clr  = pnlColor(last - values[0]);

    return { line: lineD, area: areaD, dot: pts.at(-1)!, color: clr };
  }, [data, w, h]);

  if (!line) return (
    <div className="flex items-center justify-center text-[11px]" style={{ height: h, color: "var(--text-muted)" }}>
      No data
    </div>
  );

  const values = data.map(d => d.value);
  const min = Math.min(...values).toFixed(2);
  const max = Math.max(...values).toFixed(2);

  return (
    <div>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="w-full" aria-hidden="true">
        <path d={area!} fill={color} opacity={0.07} />
        <path d={line} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
        {dot && <circle cx={dot.x} cy={dot.y} r={2.5} fill={color} />}
      </svg>
      <div className="flex justify-between font-mono text-[10px] px-1" style={{ color: "var(--text-muted)" }}>
        <span>{min}</span>
        <span>{max}</span>
      </div>
    </div>
  );
};

// ── MiniChartPanel ────────────────────────────────────────────────────────────

interface MiniChartPanelProps {
  signal: SymbolSignal;
  /** Données historiques pour le chart. Si vide, chart masqué. */
  chartData?: ChartData[];
  exposure?: number;
  defaultOpen?: boolean;
  className?: string;
}

export const MiniChartPanel: React.FC<MiniChartPanelProps> = ({
  signal,
  chartData = [],
  exposure = 0,
  defaultOpen = false,
  className = "",
}) => {
  const [open, setOpen]      = useState(defaultOpen);
  const [metric, setMetric]  = useState<MiniChartMetric>("pnl");

  const state = getMarketState(signal.regime, signal.score, signal.gate_allowed);
  const changeColor = pnlColor(signal.change_24h);
  const hasChart    = chartData.length >= 2;

  // Données filtrées selon métrique sélectionnée
  // Dans un vrai contexte, les données varieraient par métrique
  const displayData = chartData;

  return (
    <div
      className={`rounded-[var(--r-card)] overflow-hidden ${className}`}
      style={{ background: "var(--bg-card)", border: "1px solid var(--bg-border)" }}
    >
      {/* ─── Ligne 1 : Symbol + State + Signal ─────────────────────────────── */}
      <div className="flex items-center justify-between px-3 pt-2.5 pb-1.5">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-semibold" style={{ color: "var(--text-pri)" }}>
            {signal.symbol.replace("/USDT", "")}
            <span className="font-normal text-[11px]" style={{ color: "var(--text-muted)" }}>/USDT</span>
          </span>

          {/* Market state */}
          <span
            className="inline-flex items-center gap-1 px-1.5 py-0.5 font-mono text-[11px] font-bold"
            style={{
              color: state.color,
              background: `${state.color}15`,
              borderRadius: "var(--r-chip)",
            }}
            title={state.description}
          >
            {!signal.gate_allowed ? <IconBlock /> : state.glyph}
            {state.label}
          </span>
        </div>

        <SignalBadge kind={signal.signal} />
      </div>

      {/* ─── Ligne 2 : Prix + variation ─────────────────────────────────────── */}
      <div className="flex items-baseline gap-3 px-3 pb-1">
        <span className="font-mono text-base font-semibold" style={{ color: "var(--text-pri)" }}>
          ${fmtPrice(signal.price)}
        </span>
        <span className="font-mono text-xs font-semibold" style={{ color: changeColor }}>
          {fmtPct(signal.change_24h)}
        </span>
      </div>

      {/* ─── Ligne 3 : Score + exposition ───────────────────────────────────── */}
      <div className="px-3 pb-2 space-y-1">
        <div className="flex items-center gap-2">
          <span className="text-[10px] tracking-wide uppercase" style={{ color: "var(--text-muted)", minWidth: 36 }}>
            Score
          </span>
          <ScoreBar score={signal.score} />
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] tracking-wide uppercase" style={{ color: "var(--text-muted)", minWidth: 36 }}>
            Expo
          </span>
          <span className="font-mono text-xs" style={{ color: "var(--text-sec)" }}>
            {exposure > 0 ? `${exposure.toFixed(1)}%` : "—"}
          </span>
        </div>
      </div>

      {/* ─── Toggle chart ────────────────────────────────────────────────────── */}
      {hasChart && (
        <button
          onClick={() => setOpen(v => !v)}
          className="w-full flex items-center justify-between px-3 py-1.5 text-left"
          style={{
            borderTop: "1px solid var(--bg-border)",
            color: "var(--text-muted)",
            background: "transparent",
            cursor: "pointer",
          }}
          aria-expanded={open}
        >
          <div className="flex items-center gap-1.5 text-[11px]">
            <IconChart />
            Chart
          </div>
          <IconChevron open={open} />
        </button>
      )}

      {/* ─── Chart expanded ──────────────────────────────────────────────────── */}
      {open && hasChart && (
        <div className="px-3 pb-3 fade-in">
          {/* Metric selector */}
          <div className="flex gap-1 mb-2 pt-1">
            {(["pnl", "signal_score", "exposure"] as MiniChartMetric[]).map(m => (
              <button
                key={m}
                onClick={() => setMetric(m)}
                className="px-2 py-0.5 font-mono text-[10px] transition-colors"
                style={{
                  borderRadius: "var(--r-chip)",
                  background: metric === m ? "var(--accent-dim)" : "transparent",
                  color: metric === m ? "var(--accent)" : "var(--text-muted)",
                  fontWeight: metric === m ? 700 : 400,
                  cursor: "pointer",
                  border: "none",
                }}
              >
                {METRIC_LABELS[m]}
              </button>
            ))}
          </div>
          <InlineSVGChart data={displayData} />
        </div>
      )}

      {/* ─── Indicateurs (toujours visibles) ────────────────────────────────── */}
      <div
        className="px-3 py-2"
        style={{ borderTop: "1px solid var(--bg-border)" }}
      >
        <IndicatorChipSet indicators={signal.indicators} />
      </div>
    </div>
  );
};
