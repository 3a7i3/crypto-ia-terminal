import React from "react";
import { useMarketSnapshot } from "../lib/marketClient";
import type { MarketOpportunity } from "../lib/marketTypes";

const panelStyle: React.CSSProperties = {
  background: "var(--bg-card)",
  border: "1px solid var(--bg-border)",
  borderRadius: 8,
};

const muted: React.CSSProperties = { color: "var(--text-muted)" };

function formatUtc(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toISOString().replace("T", " ").replace(".000Z", "Z");
}

const Stat: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div className="p-3" style={panelStyle}>
    <div className="font-mono text-[10px] uppercase tracking-wide" style={muted}>
      {label}
    </div>
    <div className="mt-1 font-mono text-lg font-semibold" style={{ color: "var(--text-pri)" }}>
      {value}
    </div>
  </div>
);

const Side: React.FC<{ row: MarketOpportunity }> = ({ row }) => {
  const glyph = row.dominant_side === "LONG" ? "▲" : row.dominant_side === "SHORT" ? "▼" : "◆";
  return (
    <span className="font-mono text-xs">
      {glyph} {row.dominant_side}
    </span>
  );
};

export const MarketView: React.FC = () => {
  const state = useMarketSnapshot();

  if (state.status === "loading") {
    return (
      <div data-testid="market-view" className="p-5 font-mono text-xs" style={panelStyle}>
        <span style={muted}>Loading CryptoRadar MARKET telemetry…</span>
      </div>
    );
  }

  if (state.status === "api_error") {
    return (
      <div data-testid="market-view" className="p-5 font-mono text-xs" style={panelStyle}>
        <div data-testid="market-error" style={{ color: "var(--danger, #d65b5b)" }}>
          MARKET unavailable — HTTP {state.httpStatus}
        </div>
        <div className="mt-2" style={muted}>
          {state.error.error_code ?? "MARKET_API_ERROR"}: {state.error.error_message ?? "No market artifact available."}
        </div>
      </div>
    );
  }

  if (state.status === "transport_error") {
    return (
      <div data-testid="market-view" className="p-5 font-mono text-xs" style={panelStyle}>
        <div data-testid="market-error" style={{ color: "var(--danger, #d65b5b)" }}>
          MARKET contract/transport error
        </div>
        <div className="mt-2" style={muted}>{state.message}</div>
      </div>
    );
  }

  const m = state.snapshot;
  const stale = m.freshness_classification === "STALE";

  return (
    <div className="flex flex-col gap-4" data-testid="market-view">
      <section className="p-4" style={panelStyle}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="font-mono text-sm font-semibold" style={{ color: "var(--text-pri)" }}>
              CryptoRadar · MARKET
            </div>
            <div className="mt-1 font-mono text-[10px]" style={muted}>
              Observation only · {m.authority} · rolling {m.window_hours}h window
            </div>
          </div>
          <div
            data-testid="market-freshness"
            className="px-2 py-1 font-mono text-[10px] font-semibold"
            style={{
              borderRadius: "var(--r-chip)",
              border: "1px solid var(--bg-border)",
              color: stale ? "var(--warning, #d6a85b)" : "var(--text-pri)",
              background: "var(--bg-hover)",
            }}
          >
            {m.freshness_classification} · {Math.round(m.snapshot_age_s)}s
          </div>
        </div>
        <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
          <div className="font-mono text-[10px]" style={muted}>
            Generated: <span style={{ color: "var(--text-pri)" }}>{formatUtc(m.generated_at_utc)}</span>
          </div>
          <div className="font-mono text-[10px]" style={muted}>
            Latest source packet: <span style={{ color: "var(--text-pri)" }}>{formatUtc(m.source_updated_at_utc)}</span>
          </div>
        </div>
      </section>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Market regime" value={m.market_regime ?? "UNKNOWN"} />
        <Stat label="Universe observed" value={m.universe_size} />
        <Stat label={`Radar ≥ ${m.min_confidence}`} value={m.actionable_count} />
        <Stat label="Watchlist 50→threshold" value={m.watchlist_count} />
      </section>

      <section style={panelStyle}>
        <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: "1px solid var(--bg-border)" }}>
          <div className="font-mono text-xs font-semibold" style={{ color: "var(--text-pri)" }}>
            Top market opportunities
          </div>
          <div className="font-mono text-[10px]" style={muted}>
            {m.packets_observed} packets observed · no execution levels
          </div>
        </div>

        {m.top_opportunities.length === 0 ? (
          <div className="px-4 py-6 font-mono text-xs" style={muted} data-testid="market-empty">
            No symbol meets the CryptoRadar display threshold in the current observation window.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse font-mono text-xs">
              <thead>
                <tr style={{ color: "var(--text-muted)", borderBottom: "1px solid var(--bg-border)" }}>
                  <th className="px-4 py-2 text-left font-medium">Symbol</th>
                  <th className="px-3 py-2 text-right font-medium">Avg conf</th>
                  <th className="px-3 py-2 text-right font-medium">Max</th>
                  <th className="px-3 py-2 text-left font-medium">Bias</th>
                  <th className="px-3 py-2 text-right font-medium">Dominance</th>
                  <th className="px-3 py-2 text-right font-medium">Signals</th>
                  <th className="px-4 py-2 text-left font-medium">Regime</th>
                </tr>
              </thead>
              <tbody>
                {m.top_opportunities.map((row) => (
                  <tr
                    key={row.symbol}
                    data-testid="market-opportunity-row"
                    style={{ borderBottom: "1px solid var(--bg-border)", color: "var(--text-pri)" }}
                  >
                    <td className="px-4 py-2.5 font-semibold">{row.symbol}</td>
                    <td className="px-3 py-2.5 text-right">{row.avg_confidence.toFixed(1)}</td>
                    <td className="px-3 py-2.5 text-right">{row.max_confidence.toFixed(1)}</td>
                    <td className="px-3 py-2.5"><Side row={row} /></td>
                    <td className="px-3 py-2.5 text-right">{row.dominance_pct.toFixed(0)}%</td>
                    <td className="px-3 py-2.5 text-right">{row.n_signals}</td>
                    <td className="px-4 py-2.5">{row.regime}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="font-mono text-[10px]" style={muted}>
        MARKET is observational telemetry. “Radar ≥ threshold” is a display classification, not `DecisionPacket.is_actionable()` and not permission to trade.
      </div>
    </div>
  );
};
