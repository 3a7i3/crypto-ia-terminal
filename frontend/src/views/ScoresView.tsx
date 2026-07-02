// ── ScoresView.tsx — Suivi des scores : données réelles depuis /api/trades ────

import React, { useMemo, useState } from "react";
import type { TradesResponse, ApiClosedPosition } from "../lib/api";
import { usePolling } from "../hooks/usePolling";
import { MetricCard, PnLCard } from "../components/MetricCard";

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

// ── Panneau en attente de données ─────────────────────────────────────────────

const WaitingPanel: React.FC<{ title: string }> = ({ title }) => (
  <div
    className="rounded-[var(--r-card)] px-4 py-4 flex flex-col items-center justify-center gap-2"
    style={{ background: "var(--bg-card)", border: "1px solid var(--bg-border)", minHeight: "80px" }}
  >
    <span
      className="font-mono text-[10px] font-bold tracking-widest uppercase"
      style={{ color: "var(--text-muted)" }}
    >
      {title}
    </span>
    <span className="font-mono text-[11px]" style={{ color: "var(--text-muted)" }}>
      Waiting for evidence — N ≥ 50 requis
    </span>
  </div>
);

// ── État dégradé ──────────────────────────────────────────────────────────────

const Placeholder: React.FC<{ error: boolean }> = ({ error }) => (
  <div
    className="flex items-center justify-center h-40 rounded-[var(--r-card)]"
    style={{ background: "var(--bg-card)", border: "1px solid var(--bg-border)" }}
  >
    <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
      {error ? "⊘ API indisponible — uvicorn api_server:app --port 8000" : "Chargement…"}
    </span>
  </div>
);

// ── ScoresView ────────────────────────────────────────────────────────────────

type Panel = "curve" | "regimes" | "optimizer";

export const ScoresView: React.FC = () => {
  const { data, loading, error } = usePolling<TradesResponse>("/api/trades");
  const [panel, setPanel] = useState<Panel>("curve");

  // L'API renvoie closed newest-first ; on inverse pour le calcul chronologique
  const closed: ApiClosedPosition[] = useMemo(
    () => (data ? [...data.closed].reverse() : []),
    [data],
  );

  const pnl_total = useMemo(
    () => closed.reduce((sum, t) => sum + t.pnl_usd, 0),
    [closed],
  );

  const n_wins = useMemo(
    () => closed.filter(t => t.pnl_usd > 0).length,
    [closed],
  );

  const equity_curve = useMemo(
    () => closed.reduce<number[]>((acc, t) => {
      acc.push((acc.at(-1) ?? 0) + t.pnl_usd);
      return acc;
    }, []),
    [closed],
  );

  if (loading || !data) return <Placeholder error={error} />;

  const n        = closed.length;
  const hasData  = n > 0;
  const winrate  = hasData ? n_wins / n : 0;
  const expectancy: number | null = hasData ? pnl_total / n : null;
  const lastUpdate = hasData ? closed[n - 1].closed_at : null;

  const tabs: { id: Panel; label: string }[] = [
    { id: "curve",     label: "Equity Curve" },
    { id: "regimes",   label: "Régimes"      },
    { id: "optimizer", label: "Optimizer"    },
  ];

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div
          className="text-[10px] font-bold tracking-widest uppercase"
          style={{ color: "var(--text-muted)" }}
        >
          Suivi des scores
        </div>
        {lastUpdate && (
          <span className="font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>
            màj {lastUpdate}
          </span>
        )}
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard
          label="Win rate"
          value={hasData ? `${(winrate * 100).toFixed(1)}%` : "—"}
          sub={`${n} trades`}
          accent={
            !hasData      ? "var(--text-muted)"
            : winrate >= 0.6 ? "var(--ok)"
            : winrate >= 0.5 ? "var(--warn)"
            : "var(--danger)"
          }
        />
        <MetricCard
          label="Expectancy"
          value={
            expectancy !== null
              ? `${expectancy >= 0 ? "+" : ""}$${Math.abs(expectancy).toFixed(3)}`
              : "—"
          }
          sub="par trade"
          accent={
            expectancy === null ? "var(--text-muted)"
            : expectancy >= 0   ? "var(--ok)"
            : "var(--danger)"
          }
        />
        <MetricCard
          label="Efficiency"
          value="—"
          sub="non calculé"
          accent="var(--text-muted)"
        />
        <PnLCard label="PnL total" value={pnl_total} sub="USD réalisé" />
      </div>

      {/* MFE / MAE */}
      <div className="grid grid-cols-2 gap-3">
        <MetricCard label="Avg MFE" value="—" sub="non calculé" accent="var(--text-muted)" />
        <MetricCard label="Avg MAE" value="—" sub="non calculé" accent="var(--text-muted)" />
      </div>

      {/* Alerte WR élevé + PnL négatif */}
      {hasData && winrate >= 0.85 && pnl_total < 0 && (
        <div
          className="flex items-center gap-3 px-4 py-2.5 rounded-[var(--r-card)] font-mono text-xs"
          style={{ background: "var(--warn-dim)", border: "1px solid var(--warn)", color: "var(--warn)" }}
        >
          <span aria-hidden="true">⚠</span>
          <span>
            Win rate élevé ({(winrate * 100).toFixed(0)}%) mais PnL négatif —
            pertes asymétriques détectées. Vérifier les tailles sur les trades perdants.
          </span>
        </div>
      )}

      {/* Sub-tabs */}
      <div className="flex gap-1">
        {tabs.map(t => {
          const active = t.id === panel;
          return (
            <button
              key={t.id}
              onClick={() => setPanel(t.id)}
              className="px-3 py-1 font-mono text-xs transition-colors"
              style={{
                borderRadius: "var(--r-chip)",
                background: active ? "var(--bg-hover)"  : "transparent",
                color:       active ? "var(--text-pri)"  : "var(--text-muted)",
                fontWeight:  active ? 600 : 400,
                border:      active ? "1px solid var(--bg-border)" : "1px solid transparent",
                cursor: "pointer",
              }}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      {/* Equity Curve panel */}
      {panel === "curve" && (
        hasData ? (
          <div
            className="rounded-[var(--r-card)] px-4 pt-3 pb-4 fade-in"
            style={{ background: "var(--bg-card)", border: "1px solid var(--bg-border)" }}
          >
            <div className="flex items-center justify-between mb-3">
              <span
                className="font-mono text-[10px] font-bold tracking-widest uppercase"
                style={{ color: "var(--text-muted)" }}
              >
                Equity Curve — {n} trades
              </span>
              <span
                className="font-mono text-sm font-bold"
                style={{ color: pnl_total >= 0 ? "var(--ok)" : "var(--danger)" }}
              >
                {pnl_total >= 0 ? "+" : ""}{pnl_total.toFixed(2)} USD
              </span>
            </div>
            <EquityCurveChart data={equity_curve} />
            <div
              className="flex items-center justify-between mt-2 font-mono text-[10px]"
              style={{ color: "var(--text-muted)" }}
            >
              <span>Trade 1</span>
              <span>Trade {n}</span>
            </div>
          </div>
        ) : (
          <WaitingPanel title="Equity Curve" />
        )
      )}

      {panel === "regimes"   && <WaitingPanel title="Régimes par marché" />}
      {panel === "optimizer" && <WaitingPanel title="Optimizer" />}
    </div>
  );
};
