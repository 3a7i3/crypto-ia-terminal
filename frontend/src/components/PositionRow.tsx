// ── PositionRow.tsx — Ligne de position ouverte ou fermée ────────────────────

import React from "react";
import type { OpenPosition, ClosedPosition } from "../types";
import {
  ConvictionBadge, RegimeBadge, PostmortemBadge,
} from "./Badges";
import { Sparkline } from "./Sparkline";
import { pnlColor, fmtPrice, fmtPct, fmtUsd, fmtDur } from "../lib/tokens";

// ── Shared cell ───────────────────────────────────────────────────────────────

const Cell: React.FC<{ className?: string; children: React.ReactNode }> = ({
  className = "", children,
}) => (
  <td className={`px-3 py-2 text-xs ${className}`}>{children}</td>
);

// ── Open positions table ──────────────────────────────────────────────────────

export const OpenPositionHeader: React.FC = () => (
  <thead>
    <tr style={{ borderBottom: "1px solid var(--bg-border)" }}>
      {["Symbol", "Side", "Size", "Entry", "Current", "PnL", "SL / TP", "Regime", "Conv", "PnL trend", ""].map(h => (
        <th
          key={h}
          className="px-3 py-2 text-left font-mono text-[10px] font-bold tracking-widest uppercase"
          style={{ color: "var(--text-muted)" }}
        >
          {h}
        </th>
      ))}
    </tr>
  </thead>
);

export const OpenPositionRow: React.FC<{ pos: OpenPosition }> = ({ pos }) => {
  const pnlCol  = pnlColor(pos.pnl_usd);
  const sideCol = pos.side === "long" ? "var(--ok)" : "var(--danger)";
  return (
    <tr
      className="transition-colors"
      style={{ borderBottom: "1px solid var(--bg-border)" }}
      onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-hover)")}
      onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
    >
      {/* Symbol */}
      <Cell>
        <span className="font-mono font-semibold" style={{ color: "var(--text-pri)" }}>
          {pos.symbol.replace("/USDT", "")}
          <span className="font-normal text-[10px]" style={{ color: "var(--text-muted)" }}>/USDT</span>
        </span>
        <div className="text-[10px]" style={{ color: "var(--text-muted)" }}>
          {pos.subaccount}
        </div>
      </Cell>

      {/* Side */}
      <Cell>
        <span className="font-mono text-[11px] font-bold uppercase" style={{ color: sideCol }}>
          {pos.side}
        </span>
      </Cell>

      {/* Size */}
      <Cell>
        <span className="font-mono" style={{ color: "var(--text-sec)" }}>
          {pos.size.toFixed(4)}
        </span>
      </Cell>

      {/* Entry */}
      <Cell>
        <span className="font-mono" style={{ color: "var(--text-sec)" }}>
          ${fmtPrice(pos.entry_price)}
        </span>
      </Cell>

      {/* Current */}
      <Cell>
        <span className="font-mono font-semibold" style={{ color: "var(--text-pri)" }}>
          ${fmtPrice(pos.current_price)}
        </span>
      </Cell>

      {/* PnL */}
      <Cell>
        <div className="font-mono text-xs font-bold" style={{ color: pnlCol }}>
          {fmtUsd(pos.pnl_usd)}
        </div>
        <div className="font-mono text-[10px]" style={{ color: pnlCol }}>
          {fmtPct(pos.pnl_pct)}
        </div>
      </Cell>

      {/* SL / TP */}
      <Cell>
        <div className="font-mono text-[10px] space-y-0.5">
          <div style={{ color: "var(--danger)" }}>
            SL {pos.sl_price ? "$" + fmtPrice(pos.sl_price) : "—"}
          </div>
          <div style={{ color: "var(--ok)" }}>
            TP {pos.tp_price ? "$" + fmtPrice(pos.tp_price) : "—"}
          </div>
        </div>
      </Cell>

      {/* Regime */}
      <Cell><RegimeBadge regime={pos.regime} /></Cell>

      {/* Conviction */}
      <Cell><ConvictionBadge level={pos.conviction} /></Cell>

      {/* Sparkline */}
      <Cell>
        {pos.pnl_series.length >= 2 ? (
          <Sparkline data={pos.pnl_series} width={72} height={22} showArea />
        ) : (
          <span style={{ color: "var(--text-muted)", fontSize: 10 }}>—</span>
        )}
      </Cell>

      {/* Opened at */}
      <Cell>
        <span className="font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>
          {pos.opened_at}
        </span>
      </Cell>
    </tr>
  );
};

// ── Closed positions table ────────────────────────────────────────────────────

export const ClosedPositionHeader: React.FC = () => (
  <thead>
    <tr style={{ borderBottom: "1px solid var(--bg-border)" }}>
      {["Symbol", "Side", "PnL", "R", "Duration", "Regime", "Conv", "Result", "Trend", "Closed"].map(h => (
        <th
          key={h}
          className="px-3 py-2 text-left font-mono text-[10px] font-bold tracking-widest uppercase"
          style={{ color: "var(--text-muted)" }}
        >
          {h}
        </th>
      ))}
    </tr>
  </thead>
);

export const ClosedPositionRow: React.FC<{ pos: ClosedPosition }> = ({ pos }) => {
  const pnlCol  = pnlColor(pos.pnl_usd);
  const sideCol = pos.side === "long" ? "var(--ok)" : "var(--danger)";
  const rCol    = pnlColor(pos.r_multiple);
  return (
    <tr
      className="transition-colors"
      style={{ borderBottom: "1px solid var(--bg-border)" }}
      onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-hover)")}
      onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
    >
      {/* Symbol */}
      <Cell>
        <span className="font-mono font-semibold" style={{ color: "var(--text-pri)" }}>
          {pos.symbol.replace("/USDT", "")}
        </span>
      </Cell>

      {/* Side */}
      <Cell>
        <span className="font-mono text-[11px] font-bold uppercase" style={{ color: sideCol }}>
          {pos.side}
        </span>
      </Cell>

      {/* PnL */}
      <Cell>
        <div className="font-mono text-xs font-bold" style={{ color: pnlCol }}>
          {fmtUsd(pos.pnl_usd)}
        </div>
        <div className="font-mono text-[10px]" style={{ color: pnlCol }}>
          {fmtPct(pos.pnl_pct)}
        </div>
      </Cell>

      {/* R multiple */}
      <Cell>
        <span
          className="font-mono text-xs font-bold"
          style={{ color: rCol }}
        >
          {pos.r_multiple >= 0 ? "+" : ""}{pos.r_multiple.toFixed(2)}R
        </span>
      </Cell>

      {/* Duration */}
      <Cell>
        <span className="font-mono text-[11px]" style={{ color: "var(--text-sec)" }}>
          {fmtDur(pos.duration_ms)}
        </span>
      </Cell>

      {/* Regime */}
      <Cell><RegimeBadge regime={pos.regime} /></Cell>

      {/* Conviction */}
      <Cell><ConvictionBadge level={pos.conviction} /></Cell>

      {/* Postmortem */}
      <Cell><PostmortemBadge category={pos.postmortem} /></Cell>

      {/* Sparkline */}
      <Cell>
        {pos.pnl_series.length >= 2 ? (
          <Sparkline data={pos.pnl_series} width={72} height={22} showArea />
        ) : (
          <span style={{ color: "var(--text-muted)", fontSize: 10 }}>—</span>
        )}
      </Cell>

      {/* Closed at */}
      <Cell>
        <span className="font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>
          {pos.closed_at}
        </span>
      </Cell>
    </tr>
  );
};

// ── Shared table wrapper ──────────────────────────────────────────────────────

export const DataTable: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div
    className="overflow-x-auto rounded-[var(--r-card)]"
    style={{ border: "1px solid var(--bg-border)", background: "var(--bg-card)" }}
  >
    <table className="w-full border-collapse">{children}</table>
  </div>
);
