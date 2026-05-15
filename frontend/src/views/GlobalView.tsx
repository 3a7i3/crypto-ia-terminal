// ── GlobalView.tsx — Vue Globale : KPI système + santé modules ───────────────

import React from "react";
import type { SnapshotResponse, ApiModule } from "../lib/api";
import { usePolling } from "../hooks/usePolling";
import { MetricCard, PnLCard, ModuleCard } from "../components/MetricCard";
import { ModeBadge } from "../components/Badges";
import { fmtDur } from "../lib/tokens";

// ── Module card depuis l'API ─────────────────────────────────────────────────

const ApiModuleCard: React.FC<{ mod: ApiModule }> = ({ mod }) => (
  <ModuleCard
    name={mod.name}
    status={mod.status as "ok" | "warn" | "error" | "offline"}
    lastTickMs={mod.last_tick_ms}
    detail={mod.detail}
  />
);

// ── Etat chargement / erreur ──────────────────────────────────────────────────

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

// ── GlobalView ────────────────────────────────────────────────────────────────

export const GlobalView: React.FC = () => {
  const { data: snap, loading, error } = usePolling<SnapshotResponse>("/api/snapshot");

  if (loading || !snap) return <Placeholder error={error} />;

  const okCount   = snap.modules.filter(m => m.status === "ok").length;
  const warnCount = snap.modules.filter(m => m.status === "warn").length;
  const errCount  = snap.modules.filter(m => ["error", "offline"].includes(m.status)).length;

  const exchOk    = snap.exchange?.healthy ?? false;
  const latency   = snap.exchange?.last_latency_ms ?? 0;
  const uptime    = snap.exchange?.uptime_pct ?? 0;

  return (
    <div className="space-y-5">
      <div
        className="text-[10px] font-bold tracking-widest uppercase"
        style={{ color: "var(--text-muted)" }}
      >
        Vue Globale — cycle #{snap.cycle}
      </div>

      {/* ── KPI row ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard
          label="Capital"
          value={`$${snap.capital_usd.toLocaleString("en-US", { minimumFractionDigits: 2 })}`}
          sub="USDT total"
          accent="var(--accent)"
        />
        <PnLCard
          label="PnL du jour"
          value={snap.daily_pnl}
          sub="depuis 00:00 UTC"
        />
        <MetricCard
          label="Positions ouvertes"
          value={String(snap.open_positions)}
          sub="actives"
          accent="var(--warn)"
        />
        <MetricCard
          label="Win rate"
          value={`${snap.win_rate_7d.toFixed(1)}%`}
          sub="100 derniers trades"
          accent={snap.win_rate_7d >= 55 ? "var(--ok)" : "var(--warn)"}
        />
      </div>

      {/* ── Mode + exchange status ── */}
      <div
        className="flex flex-wrap items-center gap-3 px-4 py-2.5 rounded-[var(--r-card)]"
        style={{ background: "var(--bg-card)", border: "1px solid var(--bg-border)" }}
      >
        <ModeBadge mode={snap.mode} />
        <span className="font-mono text-[11px]" style={{ color: exchOk ? "var(--ok)" : "var(--danger)" }}>
          {exchOk ? "↗ Exchange connecté" : "⊘ Exchange déconnecté"}
        </span>
        <span className="font-mono text-[11px]" style={{ color: "var(--text-muted)" }}>
          latence {latency.toFixed(0)} ms · uptime {uptime.toFixed(1)}%
        </span>
        {snap.safe_mode && (
          <span className="font-mono text-[11px] font-bold" style={{ color: "var(--warn)" }}>
            ◎ SAFE MODE
          </span>
        )}
        <span className="font-mono text-[11px]" style={{ color: "var(--text-muted)" }}>
          cycle {fmtDur(snap.cycle_duration_ms)}
        </span>
        <div className="ml-auto flex items-center gap-3 font-mono text-[11px]">
          <span style={{ color: "var(--ok)" }}>● {okCount} OK</span>
          {warnCount > 0 && <span style={{ color: "var(--warn)" }}>◎ {warnCount} warn</span>}
          {errCount  > 0 && <span style={{ color: "var(--danger)" }}>✕ {errCount} hors-ligne</span>}
        </div>
      </div>

      {/* ── Signaux ce cycle ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard label="Symboles" value={String(snap.n_symbols)} sub="analysés"  accent="var(--text-muted)" />
        <MetricCard label="Actionnables" value={String(snap.n_actionable)} sub="ce cycle" accent="var(--accent)" />
        {Object.entries(snap.regime_distribution).map(([r, n]) => (
          <MetricCard key={r} label={r} value={String(n)} sub="symboles" accent="var(--text-muted)" />
        ))}
      </div>

      {/* ── Modules grid ── */}
      <div>
        <div
          className="text-[10px] font-bold tracking-widest uppercase mb-2"
          style={{ color: "var(--text-muted)" }}
        >
          Modules système
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-2">
          {snap.modules.map(m => <ApiModuleCard key={m.name} mod={m} />)}
        </div>
      </div>

      {/* ── Refus ce cycle ── */}
      {Object.keys(snap.refusal_breakdown).length > 0 && (
        <div>
          <div
            className="text-[10px] font-bold tracking-widest uppercase mb-2"
            style={{ color: "var(--text-muted)" }}
          >
            Refus — cycle courant
          </div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(snap.refusal_breakdown).map(([layer, count]) => (
              <span
                key={layer}
                className="px-2 py-0.5 font-mono text-[11px]"
                style={{
                  background: "var(--bg-card)",
                  border: "1px solid var(--bg-border)",
                  borderRadius: "var(--r-chip)",
                  color: "var(--danger)",
                }}
              >
                {layer} <strong>{count}</strong>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
