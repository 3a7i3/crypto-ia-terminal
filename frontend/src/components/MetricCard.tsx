// ── MetricCard.tsx — Carte KPI compacte pour Vue Globale ─────────────────────

import React from "react";
import { pnlColor } from "../lib/tokens";

interface MetricCardProps {
  label: string;
  value: string;
  sub?: string;
  accent?: string;   // CSS color var ou hex
  className?: string;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  label, value, sub, accent = "var(--accent)", className = "",
}) => (
  <div
    className={`rounded-[var(--r-card)] px-4 py-3 ${className}`}
    style={{
      background: "var(--bg-card)",
      border: "1px solid var(--bg-border)",
      borderLeft: `3px solid ${accent}`,
    }}
  >
    <div className="text-[10px] font-semibold tracking-widest uppercase mb-1" style={{ color: "var(--text-muted)" }}>
      {label}
    </div>
    <div className="font-mono text-xl font-bold leading-none" style={{ color: "var(--text-pri)" }}>
      {value}
    </div>
    {sub && (
      <div className="font-mono text-[11px] mt-1" style={{ color: "var(--text-sec)" }}>
        {sub}
      </div>
    )}
  </div>
);

// ── PnL variant avec couleur dynamique ───────────────────────────────────────

export const PnLCard: React.FC<{ label: string; value: number; sub?: string }> = ({
  label, value, sub,
}) => (
  <MetricCard
    label={label}
    value={`${value >= 0 ? "+" : ""}$${Math.abs(value).toFixed(2)}`}
    sub={sub}
    accent={pnlColor(value)}
  />
);

// ── Module health card ────────────────────────────────────────────────────────

const STATUS_COLORS = {
  ok:      "var(--ok)",
  warn:    "var(--warn)",
  error:   "var(--danger)",
  offline: "var(--neutral)",
};

const STATUS_GLYPHS = {
  ok:      "●",
  warn:    "◎",
  error:   "✕",
  offline: "○",
};

export const ModuleCard: React.FC<{
  name: string;
  status: "ok" | "warn" | "error" | "offline";
  lastTickMs: number;
  detail?: string;
}> = ({ name, status, lastTickMs, detail }) => {
  const color = STATUS_COLORS[status];
  const glyph = STATUS_GLYPHS[status];
  const age   = lastTickMs > 60_000
    ? `${(lastTickMs / 60_000).toFixed(0)}m ago`
    : `${(lastTickMs / 1000).toFixed(0)}s ago`;

  return (
    <div
      className="flex items-center justify-between px-3 py-2 rounded-[var(--r-card)]"
      style={{ background: "var(--bg-card)", border: "1px solid var(--bg-border)" }}
    >
      <div className="flex items-center gap-2">
        <span className="font-mono text-xs" style={{ color }} aria-hidden="true">
          {glyph}
        </span>
        <div>
          <div className="text-xs font-medium" style={{ color: "var(--text-pri)" }}>
            {name}
          </div>
          {detail && (
            <div className="text-[10px]" style={{ color: "var(--text-muted)" }}>
              {detail}
            </div>
          )}
        </div>
      </div>
      <span className="font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>
        {age}
      </span>
    </div>
  );
};
