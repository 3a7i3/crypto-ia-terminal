// ── MarketLiveView.tsx — Vue Marché Live ─────────────────────────────────────

import React, { useState } from "react";
import type { SymbolSignal, MarketRegime, SignalKind } from "../types";
import type { SnapshotResponse, ApiSymbol } from "../lib/api";
import { usePolling } from "../hooks/usePolling";
import { MiniChartPanel }  from "../components/MiniChartPanel";
import { SignalBadge, IndicatorChipSet, RegimeBadge } from "../components/Badges";
import { Sparkline }       from "../components/Sparkline";
import { getMarketState, pnlColor, fmtPrice, fmtPct } from "../lib/tokens";

// ── Mapping API → type frontend ───────────────────────────────────────────────

function apiSymbolToSignal(s: ApiSymbol): SymbolSignal {
  return {
    symbol:       s.symbol,
    price:        s.prix,
    change_24h:   0,
    regime:       s.regime as MarketRegime,
    score:        s.score,
    signal:       s.signal_kind as SignalKind,
    gate_allowed: s.gate_allowed,
    actionable:   s.actionable,
    indicators: {
      rsi:       s.indicators.rsi,
      bb_pct:    s.indicators.bb_pct,
      atr:       s.indicators.atr,
      macd_bull: s.indicators.macd_bull,
      ema_bull:  s.indicators.ema_bull,
      squeeze:   s.indicators.squeeze,
    },
    pnl_series: [],
  };
}

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

// ── Symbol row ────────────────────────────────────────────────────────────────

const SymbolRow: React.FC<{
  signal: SymbolSignal;
  selected: boolean;
  onSelect: () => void;
}> = ({ signal, selected, onSelect }) => {
  const state      = getMarketState(signal.regime, signal.score, signal.gate_allowed);
  const chgColor   = pnlColor(signal.change_24h);
  const scoreColor = signal.score >= 70 ? "var(--accent)" :
                     signal.score >= 50 ? "var(--warn)"   : "var(--neutral)";

  return (
    <tr
      onClick={onSelect}
      className="cursor-pointer transition-colors"
      style={{
        borderBottom: "1px solid var(--bg-border)",
        background:   selected ? "var(--bg-hover)" : "transparent",
      }}
      onMouseEnter={e => !selected && (e.currentTarget.style.background = "var(--bg-hover)")}
      onMouseLeave={e => !selected && (e.currentTarget.style.background = "transparent")}
      tabIndex={0}
      aria-selected={selected}
      onKeyDown={e => e.key === "Enter" && onSelect()}
    >
      {/* Symbol */}
      <td className="px-3 py-2">
        <span className="font-mono text-sm font-semibold" style={{ color: "var(--text-pri)" }}>
          {signal.symbol.replace("/USDT", "")}
          <span className="text-[10px] font-normal" style={{ color: "var(--text-muted)" }}>/USDT</span>
        </span>
      </td>

      {/* Price */}
      <td className="px-3 py-2">
        <span className="font-mono text-sm" style={{ color: "var(--text-pri)" }}>
          ${fmtPrice(signal.price, signal.price < 1 ? 4 : 2)}
        </span>
      </td>

      {/* 24h — non disponible dans le snapshot, masqué */}
      <td className="px-3 py-2">
        <span className="font-mono text-xs font-semibold" style={{ color: chgColor }}>
          {signal.change_24h !== 0 ? fmtPct(signal.change_24h) : "—"}
        </span>
      </td>

      {/* Score */}
      <td className="px-3 py-2">
        <div className="flex items-center gap-2">
          <div
            className="w-16 h-1 rounded-full overflow-hidden"
            style={{ background: "var(--bg-border)" }}
          >
            <div
              className="h-full rounded-full"
              style={{ width: `${signal.score}%`, background: scoreColor }}
            />
          </div>
          <span className="font-mono text-[11px] w-5 text-right" style={{ color: scoreColor }}>
            {signal.score}
          </span>
        </div>
      </td>

      {/* Market state */}
      <td className="px-3 py-2">
        <span
          className="inline-flex items-center gap-1 px-1.5 py-0.5 font-mono text-[11px] font-bold"
          style={{
            color:        state.color,
            background:   `${state.color}15`,
            borderRadius: "var(--r-chip)",
          }}
        >
          {state.glyph} {state.label}
        </span>
      </td>

      {/* Signal */}
      <td className="px-3 py-2">
        <SignalBadge kind={signal.signal} />
      </td>

      {/* Regime */}
      <td className="px-3 py-2 hidden lg:table-cell">
        <RegimeBadge regime={signal.regime} />
      </td>

      {/* Indicators */}
      <td className="px-3 py-2 hidden xl:table-cell">
        <IndicatorChipSet indicators={signal.indicators} />
      </td>

      {/* Sparkline */}
      <td className="px-3 py-2 hidden md:table-cell">
        {(signal.pnl_series?.length ?? 0) >= 2 ? (
          <Sparkline data={signal.pnl_series!} width={64} height={20} showArea />
        ) : (
          <span style={{ color: "var(--text-muted)", fontSize: 10 }}>—</span>
        )}
      </td>
    </tr>
  );
};

// ── Table header ──────────────────────────────────────────────────────────────

const TableHeader: React.FC = () => (
  <thead>
    <tr style={{ borderBottom: "1px solid var(--bg-border)" }}>
      {[
        "Symbol", "Price", "24h", "Score", "State", "Signal",
        { label: "Regime",     cls: "hidden lg:table-cell" },
        { label: "Indicators", cls: "hidden xl:table-cell" },
        { label: "Trend",      cls: "hidden md:table-cell" },
      ].map((h, i) => {
        const label = typeof h === "string" ? h : h.label;
        const cls   = typeof h === "string" ? "" : h.cls;
        return (
          <th
            key={i}
            className={`px-3 py-2 text-left font-mono text-[10px] font-bold tracking-widest uppercase ${cls}`}
            style={{ color: "var(--text-muted)" }}
          >
            {label}
          </th>
        );
      })}
    </tr>
  </thead>
);

// ── MarketLiveView ────────────────────────────────────────────────────────────

export const MarketLiveView: React.FC = () => {
  const { data: snap, loading, error } = usePolling<SnapshotResponse>("/api/snapshot");
  const [selected, setSelected]        = useState<string | null>(null);

  if (loading || !snap) return <Placeholder error={error} />;

  const signals       = snap.symbols.map(apiSymbolToSignal);
  const selectedSignal = signals.find(s => s.symbol === selected) ?? null;
  const chartData      = selectedSignal
    ? (selectedSignal.pnl_series ?? []).map((v, i) => ({
        ts: `T-${(selectedSignal.pnl_series?.length ?? 0) - i}`, value: v,
      }))
    : [];

  // Sélection auto sur le premier symbole si aucun sélectionné
  const activeSelected = selected ?? (signals[0]?.symbol ?? null);
  const activeSignal   = signals.find(s => s.symbol === activeSelected) ?? null;

  return (
    <div className="space-y-4">
      <div
        className="text-[10px] font-bold tracking-widest uppercase"
        style={{ color: "var(--text-muted)" }}
      >
        Marché Live — {signals.length} symboles · cycle #{snap.cycle}
        <span className="ml-3 font-normal" style={{ color: "var(--ok)" }}>
          auto-refresh 20s
        </span>
      </div>

      <div className="flex gap-4 items-start">
        {/* ── Tableau principal ── */}
        <div
          className="flex-1 overflow-x-auto rounded-[var(--r-card)]"
          style={{ border: "1px solid var(--bg-border)", background: "var(--bg-card)" }}
        >
          {signals.length === 0 ? (
            <div className="flex items-center justify-center h-24">
              <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                Aucun symbole — le bot est-il actif ?
              </span>
            </div>
          ) : (
            <table className="w-full border-collapse">
              <TableHeader />
              <tbody>
                {signals.map(s => (
                  <SymbolRow
                    key={s.symbol}
                    signal={s}
                    selected={s.symbol === activeSelected}
                    onSelect={() => setSelected(s.symbol === activeSelected ? null : s.symbol)}
                  />
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* ── Mini panel repliable ── */}
        {activeSignal && (
          <div className="w-80 shrink-0 fade-in">
            <MiniChartPanel
              signal={activeSignal}
              chartData={chartData}
              exposure={activeSignal.signal === "trade" ? snap.n_actionable * 2.5 : 0}
              defaultOpen={true}
            />
          </div>
        )}
      </div>
    </div>
  );
};
