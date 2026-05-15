// ── ScoresView.tsx — Suivi des scores : equity curve, régimes, optimizer ─────

import React, { useMemo, useState } from "react";
import type { ScoreSnapshot, RegimePerf, OptimizerEntry } from "../types";
import { MetricCard, PnLCard } from "../components/MetricCard";

// ── Données démo (miroir du dashboard.md backend) ─────────────────────────────

const DEMO_SCORE: ScoreSnapshot = {
  trades:      26,
  winrate:     0.9231,
  expectancy:  0.0346,
  efficiency:  0.9897,
  pnl_total:   -1.75,
  avg_mfe:     0.0373,
  avg_mae:    -0.0027,
  equity_curve: [
    0.50, 0.55, 0.553, 0.563, 0.566, 0.576, 0.579, 0.589, 0.592,
    0.602, 0.652, 0.702, 0.752, 0.802, 0.852, 0.902, 0.952, 1.002,
    1.052, 1.102, 1.152, 1.202, 1.252, 1.302, -0.257, -1.747,
  ],
  regimes: [
    { regime: "bull_trend", trades: 23, winrate: 1.00,  avg_pnl:  0.0413, status: "STRONG" },
    { regime: "bullish",    trades:  1, winrate: 1.00,  avg_pnl:  0.0100, status: "GOOD"   },
    { regime: "sideways",   trades:  2, winrate: 0.00,  avg_pnl: -0.0305, status: "AVOID"  },
  ],
  optimizer: [
    { regime: "bull_trend", tp: 0.012, sl: 0.008, trailing: 0.004, score: 0.041304, winrate: 1.0 },
    { regime: "bullish",    tp: 0.012, sl: 0.008, trailing: 0.004, score: 0.020000, winrate: 1.0 },
  ],
  last_updated: "2026-05-06T11:06:03Z",
};

// ── Equity curve SVG ──────────────────────────────────────────────────────────

const EquityCurveChart: React.FC<{ data: number[] }> = ({ data }) => {
  const W = 100, H = 48, pad = 2;

  const { pts, color, zeroY } = useMemo(() => {
    if (data.length < 2) return { pts: [], color: "var(--neutral)", zeroY: H / 2 };
    const minV = Math.min(0, ...data);
    const maxV = Math.max(0, ...data);
    const rng  = maxV - minV || 1;
    const usW  = W - pad * 2;
    const usH  = H - pad * 2;
    const pts  = data.map((v, i) => ({
      x: pad + (i / (data.length - 1)) * usW,
      y: pad + (1 - (v - minV) / rng) * usH,
    }));
    const last  = data[data.length - 1];
    const color = last >= 0 ? "var(--ok)" : "var(--danger)";
    const zeroY = pad + (1 - (0 - minV) / rng) * usH;
    return { pts, color, zeroY };
  }, [data]);

  if (pts.length < 2) return null;

  const line = "M" + pts.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" L");
  const area = `${line} L${pts.at(-1)!.x.toFixed(1)},${zeroY.toFixed(1)} L${pts[0].x.toFixed(1)},${zeroY.toFixed(1)} Z`;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      style={{ width: "100%", height: "144px", display: "block" }}
      aria-label="Equity curve"
    >
      <line x1={pad} y1={zeroY} x2={W - pad} y2={zeroY}
        stroke="var(--bg-border)" strokeWidth="0.5" strokeDasharray="2,2" />
      <path d={area} fill={color} opacity={0.08} />
      <path d={line} fill="none" stroke={color} strokeWidth="1.2"
        strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
};

// ── Régimes table ─────────────────────────────────────────────────────────────

const STATUS_COLOR: Record<string, string> = {
  STRONG: "var(--ok)",
  GOOD:   "var(--accent)",
  WEAK:   "var(--warn)",
  AVOID:  "var(--danger)",
};

const RegimeTable: React.FC<{ regimes: RegimePerf[] }> = ({ regimes }) => (
  <div className="overflow-x-auto rounded-[var(--r-card)]"
    style={{ border: "1px solid var(--bg-border)", background: "var(--bg-card)" }}>
    <table className="w-full border-collapse">
      <thead>
        <tr style={{ borderBottom: "1px solid var(--bg-border)" }}>
          {["Régime", "Trades", "Win Rate", "Avg PnL", "Statut"].map(h => (
            <th key={h} className="px-3 py-2 text-left font-mono text-[10px] font-bold tracking-widest uppercase"
              style={{ color: "var(--text-muted)" }}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {regimes.map(r => {
          const col    = STATUS_COLOR[r.status] ?? "var(--neutral)";
          const pnlCol = r.avg_pnl >= 0 ? "var(--ok)" : "var(--danger)";
          return (
            <tr key={r.regime} style={{ borderBottom: "1px solid var(--bg-border)" }}>
              <td className="px-3 py-2">
                <span className="font-mono text-xs font-semibold" style={{ color: "var(--text-pri)" }}>
                  {r.regime}
                </span>
              </td>
              <td className="px-3 py-2 font-mono text-xs" style={{ color: "var(--text-sec)" }}>
                {r.trades}
              </td>
              <td className="px-3 py-2">
                <div className="flex items-center gap-2">
                  <div className="w-16 h-1 rounded-full overflow-hidden" style={{ background: "var(--bg-border)" }}>
                    <div className="h-full rounded-full"
                      style={{ width: `${(r.winrate * 100).toFixed(0)}%`, background: col }} />
                  </div>
                  <span className="font-mono text-[11px]" style={{ color: col }}>
                    {(r.winrate * 100).toFixed(0)}%
                  </span>
                </div>
              </td>
              <td className="px-3 py-2">
                <span className="font-mono text-xs font-semibold" style={{ color: pnlCol }}>
                  {r.avg_pnl >= 0 ? "+" : ""}{(r.avg_pnl * 100).toFixed(2)}%
                </span>
              </td>
              <td className="px-3 py-2">
                <span className="inline-block px-1.5 py-0.5 font-mono text-[10px] font-bold"
                  style={{ color: col, background: `${col}18`, borderRadius: "var(--r-chip)" }}>
                  {r.status}
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  </div>
);

// ── Optimizer cards ───────────────────────────────────────────────────────────

const OptimizerGrid: React.FC<{ entries: OptimizerEntry[] }> = ({ entries }) => (
  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
    {entries.map(e => (
      <div key={e.regime} className="rounded-[var(--r-card)] px-4 py-3 space-y-2"
        style={{ background: "var(--bg-card)", border: "1px solid var(--bg-border)" }}>
        <div className="flex items-center justify-between">
          <span className="font-mono text-xs font-bold" style={{ color: "var(--text-pri)" }}>
            {e.regime}
          </span>
          <span className="font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>
            score {e.score.toFixed(4)}
          </span>
        </div>
        <div className="grid grid-cols-3 gap-2">
          {[
            { label: "TP",    value: `${(e.tp * 100).toFixed(1)}%`,       color: "var(--ok)"     },
            { label: "SL",    value: `${(e.sl * 100).toFixed(1)}%`,       color: "var(--danger)" },
            { label: "Trail", value: `${(e.trailing * 100).toFixed(1)}%`, color: "var(--warn)"   },
          ].map(({ label, value, color }) => (
            <div key={label}>
              <div className="text-[9px] tracking-widest uppercase" style={{ color: "var(--text-muted)" }}>
                {label}
              </div>
              <div className="font-mono text-sm font-bold" style={{ color }}>{value}</div>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-2 pt-1" style={{ borderTop: "1px solid var(--bg-border)" }}>
          <div className="flex-1 h-1 rounded-full overflow-hidden" style={{ background: "var(--bg-border)" }}>
            <div className="h-full rounded-full"
              style={{ width: `${(e.winrate * 100).toFixed(0)}%`, background: "var(--ok)" }} />
          </div>
          <span className="font-mono text-[10px] shrink-0" style={{ color: "var(--ok)" }}>
            {(e.winrate * 100).toFixed(0)}% WR
          </span>
        </div>
      </div>
    ))}
  </div>
);

// ── ScoresView ────────────────────────────────────────────────────────────────

type Panel = "curve" | "regimes" | "optimizer";

export const ScoresView: React.FC = () => {
  const s = DEMO_SCORE;
  const [panel, setPanel] = useState<Panel>("curve");

  const tabs: { id: Panel; label: string }[] = [
    { id: "curve",     label: "Equity Curve" },
    { id: "regimes",   label: "Régimes"      },
    { id: "optimizer", label: "Optimizer"    },
  ];

  const updated = new Date(s.last_updated).toLocaleString("fr-FR");

  return (
    <div className="space-y-5">
      {/* Section label + date */}
      <div className="flex items-center justify-between">
        <div className="text-[10px] font-bold tracking-widest uppercase"
          style={{ color: "var(--text-muted)" }}>
          Suivi des scores
        </div>
        <span className="font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>
          màj {updated}
        </span>
      </div>

      {/* KPI row — 4 cartes */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard
          label="Win rate"
          value={`${(s.winrate * 100).toFixed(1)}%`}
          sub={`${s.trades} trades`}
          accent={s.winrate >= 0.6 ? "var(--ok)" : s.winrate >= 0.5 ? "var(--warn)" : "var(--danger)"}
        />
        <MetricCard
          label="Expectancy"
          value={`${(s.expectancy * 100).toFixed(2)}%`}
          sub="par trade"
          accent={s.expectancy >= 0.002 ? "var(--ok)" : s.expectancy >= 0 ? "var(--warn)" : "var(--danger)"}
        />
        <MetricCard
          label="Efficiency"
          value={`${(s.efficiency * 100).toFixed(1)}%`}
          sub="MFE capturé"
          accent={s.efficiency >= 0.75 ? "var(--accent)" : "var(--warn)"}
        />
        <PnLCard label="PnL total" value={s.pnl_total} sub="USD réalisé" />
      </div>

      {/* MFE / MAE */}
      <div className="grid grid-cols-2 gap-3">
        <MetricCard label="Avg MFE" value={`+${(s.avg_mfe * 100).toFixed(2)}%`}
          sub="potentiel max" accent="var(--ok)" />
        <MetricCard label="Avg MAE" value={`${(s.avg_mae * 100).toFixed(2)}%`}
          sub="adverse max" accent="var(--danger)" />
      </div>

      {/* Alerte WR élevé + PnL négatif */}
      {s.winrate >= 0.85 && s.pnl_total < 0 && (
        <div className="flex items-center gap-3 px-4 py-2.5 rounded-[var(--r-card)] font-mono text-xs"
          style={{ background: "var(--warn-dim)", border: "1px solid var(--warn)", color: "var(--warn)" }}>
          <span aria-hidden="true">⚠</span>
          <span>
            Win rate élevé ({(s.winrate * 100).toFixed(0)}%) mais PnL négatif —
            pertes asymétriques détectées. Vérifier les tailles sur les trades perdants.
          </span>
        </div>
      )}

      {/* Sub-tabs */}
      <div className="flex gap-1">
        {tabs.map(t => {
          const active = t.id === panel;
          return (
            <button key={t.id} onClick={() => setPanel(t.id)}
              className="px-3 py-1 font-mono text-xs transition-colors"
              style={{
                borderRadius: "var(--r-chip)",
                background: active ? "var(--bg-hover)"  : "transparent",
                color:       active ? "var(--text-pri)"  : "var(--text-muted)",
                fontWeight:  active ? 600 : 400,
                border:      active ? "1px solid var(--bg-border)" : "1px solid transparent",
                cursor: "pointer",
              }}>
              {t.label}
            </button>
          );
        })}
      </div>

      {/* Equity Curve panel */}
      {panel === "curve" && (
        <div className="rounded-[var(--r-card)] px-4 pt-3 pb-4 fade-in"
          style={{ background: "var(--bg-card)", border: "1px solid var(--bg-border)" }}>
          <div className="flex items-center justify-between mb-3">
            <span className="font-mono text-[10px] font-bold tracking-widest uppercase"
              style={{ color: "var(--text-muted)" }}>
              Equity Curve — {s.trades} trades
            </span>
            <span className="font-mono text-sm font-bold"
              style={{ color: s.pnl_total >= 0 ? "var(--ok)" : "var(--danger)" }}>
              {s.pnl_total >= 0 ? "+" : ""}{s.pnl_total.toFixed(2)} USD
            </span>
          </div>
          <EquityCurveChart data={s.equity_curve} />
          <div className="flex items-center justify-between mt-2 font-mono text-[10px]"
            style={{ color: "var(--text-muted)" }}>
            <span>Trade 1</span>
            <span>Trade {s.trades}</span>
          </div>
        </div>
      )}

      {/* Régimes panel */}
      {panel === "regimes" && (
        <div className="fade-in">
          <RegimeTable regimes={s.regimes} />
        </div>
      )}

      {/* Optimizer panel */}
      {panel === "optimizer" && (
        <div className="fade-in">
          <OptimizerGrid entries={s.optimizer} />
        </div>
      )}
    </div>
  );
};
