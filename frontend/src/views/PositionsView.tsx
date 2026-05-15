// ── PositionsView.tsx — Positions ouvertes + historique ──────────────────────

import React, { useState } from "react";
import type {
  OpenPosition, ClosedPosition,
  MarketRegime, ConvictionLevel, PostmortemCategory,
} from "../types";
import type { TradesResponse, ApiOpenPosition, ApiClosedPosition } from "../lib/api";
import { usePolling } from "../hooks/usePolling";
import {
  DataTable,
  OpenPositionHeader, OpenPositionRow,
  ClosedPositionHeader, ClosedPositionRow,
} from "../components/PositionRow";

// ── Mappers API → types internes ─────────────────────────────────────────────

function mapOpen(p: ApiOpenPosition): OpenPosition {
  return {
    id:            p.id,
    symbol:        p.symbol,
    side:          p.side === "short" ? "short" : "long",
    size:          p.size,
    entry_price:   p.entry_price,
    current_price: p.current_price,
    pnl_usd:       p.pnl_usd,
    pnl_pct:       p.pnl_pct,
    sl_price:      p.sl_price,
    tp_price:      p.tp_price,
    regime:        p.regime as MarketRegime,
    conviction:    p.conviction as ConvictionLevel,
    subaccount:    p.subaccount,
    opened_at:     p.opened_at,
    pnl_series:    p.pnl_series,
  };
}

function mapClosed(p: ApiClosedPosition): ClosedPosition {
  return {
    id:          p.id,
    symbol:      p.symbol,
    side:        p.side === "short" ? "short" : "long",
    pnl_usd:     p.pnl_usd,
    pnl_pct:     p.pnl_pct,
    r_multiple:  p.r_multiple,
    regime:      p.regime as MarketRegime,
    conviction:  p.conviction as ConvictionLevel,
    postmortem:  p.postmortem as PostmortemCategory,
    duration_ms: p.duration_ms,
    closed_at:   p.closed_at,
    pnl_series:  p.pnl_series,
  };
}

// ── Summary bar ───────────────────────────────────────────────────────────────

const SummaryBar: React.FC<{ positions: ClosedPosition[] }> = ({ positions }) => {
  const totalPnl = positions.reduce((s, p) => s + p.pnl_usd, 0);
  const wins     = positions.filter(p => p.pnl_usd > 0).length;
  const winRate  = positions.length ? (wins / positions.length * 100).toFixed(0) : "0";
  const avgR     = positions.length
    ? (positions.reduce((s, p) => s + p.r_multiple, 0) / positions.length).toFixed(2)
    : "0";
  const pclr     = totalPnl >= 0 ? "var(--ok)" : "var(--danger)";

  return (
    <div
      className="flex items-center gap-6 px-4 py-2.5 rounded-[var(--r-card)]"
      style={{ background: "var(--bg-card)", border: "1px solid var(--bg-border)" }}
    >
      {([
        { label: "PnL total",
          value: `${totalPnl >= 0 ? "+" : ""}$${Math.abs(totalPnl).toFixed(2)}`,
          color: pclr },
        { label: "Win rate",
          value: `${winRate}%`,
          color: Number(winRate) >= 55 ? "var(--ok)" : "var(--warn)" },
        { label: "Avg R",
          value: `${Number(avgR) >= 0 ? "+" : ""}${avgR}R`,
          color: Number(avgR) >= 1 ? "var(--ok)" : "var(--danger)" },
        { label: "Trades",
          value: String(positions.length),
          color: "var(--text-sec)" },
      ] as const).map(({ label, value, color }) => (
        <div key={label}>
          <div className="text-[10px] tracking-widest uppercase" style={{ color: "var(--text-muted)" }}>
            {label}
          </div>
          <div className="font-mono text-sm font-bold" style={{ color }}>
            {value}
          </div>
        </div>
      ))}
    </div>
  );
};

// ── Placeholder ───────────────────────────────────────────────────────────────

const Placeholder: React.FC<{ error: boolean }> = ({ error }) => (
  <div
    className="flex items-center justify-center h-32 rounded-[var(--r-card)]"
    style={{ background: "var(--bg-card)", border: "1px solid var(--bg-border)" }}
  >
    <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
      {error ? "⊘ API indisponible" : "Chargement…"}
    </span>
  </div>
);

// ── PositionsView ─────────────────────────────────────────────────────────────

export const PositionsView: React.FC = () => {
  const { data, loading, error } = usePolling<TradesResponse>("/api/trades");
  const [historyTab, setHistoryTab] = useState<"all" | "validated" | "mistake">("all");

  if (loading || !data) return <Placeholder error={error} />;

  const openPositions   = data.open.map(mapOpen);
  const closedPositions = data.closed.map(mapClosed);

  const filtered =
    historyTab === "validated"
      ? closedPositions.filter(p => p.postmortem === "VALIDATED" || p.postmortem === "LUCKY")
      : historyTab === "mistake"
      ? closedPositions.filter(p => p.postmortem === "MISTAKE" || p.postmortem === "UNLUCKY")
      : closedPositions;

  return (
    <div className="space-y-5">
      <div
        className="text-[10px] font-bold tracking-widest uppercase"
        style={{ color: "var(--text-muted)" }}
      >
        Positions
        <span className="ml-3 font-normal" style={{ color: "var(--ok)" }}>auto-refresh 20s</span>
      </div>

      {/* ── Open positions ── */}
      <section>
        <div
          className="text-[10px] font-semibold tracking-widest uppercase mb-2"
          style={{ color: "var(--text-muted)" }}
        >
          Ouvertes — {openPositions.length}
        </div>
        {openPositions.length === 0 ? (
          <div
            className="flex items-center justify-center h-16 rounded-[var(--r-card)]"
            style={{ background: "var(--bg-card)", border: "1px solid var(--bg-border)" }}
          >
            <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
              Aucune position ouverte
            </span>
          </div>
        ) : (
          <DataTable>
            <OpenPositionHeader />
            <tbody>
              {openPositions.map(p => <OpenPositionRow key={p.id} pos={p} />)}
            </tbody>
          </DataTable>
        )}
      </section>

      {/* ── Closed positions ── */}
      <section>
        <div className="flex items-center justify-between mb-2">
          <div
            className="text-[10px] font-semibold tracking-widest uppercase"
            style={{ color: "var(--text-muted)" }}
          >
            Historique — {closedPositions.length}
          </div>

          <div className="flex gap-1">
            {(["all", "validated", "mistake"] as const).map(t => {
              const labels = { all: "Tous", validated: "Positifs", mistake: "Erreurs" } as const;
              const active = t === historyTab;
              return (
                <button
                  key={t}
                  onClick={() => setHistoryTab(t)}
                  className="px-2 py-0.5 font-mono text-[10px] transition-colors"
                  style={{
                    borderRadius: "var(--r-chip)",
                    background:   active ? "var(--bg-hover)" : "transparent",
                    color:        active ? "var(--text-pri)" : "var(--text-muted)",
                    fontWeight:   active ? 600 : 400,
                    border:       "none",
                    cursor:       "pointer",
                  }}
                >
                  {labels[t]}
                </button>
              );
            })}
          </div>
        </div>

        <SummaryBar positions={closedPositions} />

        <div className="mt-2">
          {closedPositions.length === 0 ? (
            <div
              className="flex items-center justify-center h-16 rounded-[var(--r-card)]"
              style={{ background: "var(--bg-card)", border: "1px solid var(--bg-border)" }}
            >
              <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                Aucun historique de trade
              </span>
            </div>
          ) : (
            <DataTable>
              <ClosedPositionHeader />
              <tbody>
                {filtered.map(p => <ClosedPositionRow key={p.id} pos={p} />)}
              </tbody>
            </DataTable>
          )}
        </div>
      </section>
    </div>
  );
};
