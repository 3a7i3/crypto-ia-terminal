import React from "react";
import { useMarketSnapshot } from "../lib/marketClient";
import type { MarketOpportunity } from "../lib/marketTypes";

function formatUtc(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toISOString().replace("T", " ").replace(".000Z", "Z");
}

const Stat: React.FC<{ label: string; value: React.ReactNode; hint?: string }> = ({ label, value, hint }) => (
  <div className="market-stat">
    <div className="market-stat-label">{label}</div>
    <div className="market-stat-value">{value}</div>
    {hint && <div className="market-stat-hint">{hint}</div>}
  </div>
);

const Side: React.FC<{ row: MarketOpportunity }> = ({ row }) => {
  const glyph = row.dominant_side === "LONG" ? "▲" : row.dominant_side === "SHORT" ? "▼" : "◆";
  const tone = row.dominant_side === "LONG" ? "long" : row.dominant_side === "SHORT" ? "short" : "neutral";
  return (
    <span className={`market-side market-side-${tone}`}>
      {glyph} {row.dominant_side}
    </span>
  );
};

function regimeTone(regime: string): string {
  const value = regime.toLowerCase();
  if (value.includes("bull")) return "bull";
  if (value.includes("bear")) return "bear";
  if (value.includes("range") || value.includes("sideway")) return "range";
  return "neutral";
}

const Regime: React.FC<{ value: string }> = ({ value }) => (
  <span className={`market-regime market-regime-${regimeTone(value)}`}>{value}</span>
);

export const MarketView: React.FC = () => {
  const state = useMarketSnapshot();

  if (state.status === "loading") {
    return (
      <div data-testid="market-view" className="market-panel market-loading">
        Loading CryptoRadar MARKET telemetry…
      </div>
    );
  }

  if (state.status === "api_error") {
    return (
      <div data-testid="market-view" className="market-panel market-error">
        <div data-testid="market-error" className="market-error-title">
          MARKET unavailable — HTTP {state.httpStatus}
        </div>
        <div className="market-error-detail">
          {state.error.error_code ?? "MARKET_API_ERROR"}: {state.error.error_message ?? "No market artifact available."}
        </div>
      </div>
    );
  }

  if (state.status === "transport_error") {
    return (
      <div data-testid="market-view" className="market-panel market-error">
        <div data-testid="market-error" className="market-error-title">
          MARKET contract/transport error
        </div>
        <div className="market-error-detail">{state.message}</div>
      </div>
    );
  }

  const m = state.snapshot;
  const stale = m.freshness_classification === "STALE";

  return (
    <div className="market-stack" data-testid="market-view">
      <section className="market-panel market-summary">
        <div className="market-summary-row">
          <div>
            <div className="market-eyebrow">PASSIVE MARKET OBSERVATION</div>
            <div className="market-title">CryptoRadar · MARKET</div>
            <div className="market-subtitle">
              {m.authority} · rolling {m.window_hours}h observation window · no execution authority
            </div>
          </div>
          <div
            data-testid="market-freshness"
            className={`market-freshness ${stale ? "market-freshness-stale" : "market-freshness-fresh"}`}
          >
            <span className="market-freshness-dot" aria-hidden="true" />
            {m.freshness_classification} · {Math.round(m.snapshot_age_s)}s
          </div>
        </div>

        <details className="market-provenance-details">
          <summary>Provenance & source timing</summary>
          <div className="market-provenance-grid">
            <div className="market-provenance">
              Generated: <span className="market-provenance-value">{formatUtc(m.generated_at_utc)}</span>
            </div>
            <div className="market-provenance">
              Latest source packet: <span className="market-provenance-value">{formatUtc(m.source_updated_at_utc)}</span>
            </div>
          </div>
        </details>
      </section>

      <section className="market-stats" aria-label="Market observation summary">
        <Stat label="Market regime" value={m.market_regime ? <Regime value={m.market_regime} /> : "UNKNOWN"} hint="observed regime" />
        <Stat label="Symbols observed" value={m.universe_size} hint={`rolling ${m.window_hours}h telemetry`} />
        <Stat label={`Radar ≥ ${m.min_confidence}`} value={m.actionable_count} hint="display classification only" />
        <Stat label="Watchlist" value={m.watchlist_count} hint="50 → display threshold" />
      </section>

      <section className="market-panel market-opportunities-panel">
        <div className="market-section-head">
          <div>
            <div className="market-section-title">Top market opportunities</div>
            <div className="market-section-subtitle">Observation ranking supplied by CryptoRadar · unchanged by the UI</div>
          </div>
          <div className="market-table-meta">
            {m.packets_observed} packets observed · no execution levels
          </div>
        </div>

        {m.top_opportunities.length === 0 ? (
          <div className="market-empty" data-testid="market-empty">
            No symbol meets the CryptoRadar display threshold in the current observation window.
          </div>
        ) : (
          <>
            <div className="market-table-wrap market-table-desktop">
              <table className="market-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th className="market-num">Avg conf</th>
                    <th className="market-num">Max</th>
                    <th>Bias</th>
                    <th className="market-num">Dominance</th>
                    <th className="market-num">Signals</th>
                    <th>Regime</th>
                  </tr>
                </thead>
                <tbody>
                  {m.top_opportunities.map((row) => (
                    <tr key={row.symbol} data-testid="market-opportunity-row">
                      <td className="market-table-symbol">{row.symbol}</td>
                      <td className="market-num">{row.avg_confidence.toFixed(1)}</td>
                      <td className="market-num">{row.max_confidence.toFixed(1)}</td>
                      <td><Side row={row} /></td>
                      <td className="market-num">{row.dominance_pct.toFixed(0)}%</td>
                      <td className="market-num">{row.n_signals}</td>
                      <td><Regime value={row.regime} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="market-card-list" data-testid="market-opportunity-cards">
              {m.top_opportunities.map((row) => (
                <article className="market-opportunity-card" key={row.symbol} data-testid="market-opportunity-card">
                  <div className="market-card-head">
                    <div className="market-card-symbol">{row.symbol}</div>
                    <Side row={row} />
                  </div>
                  <div className="market-card-metrics">
                    <div><span>Avg conf</span><strong>{row.avg_confidence.toFixed(1)}</strong></div>
                    <div><span>Max</span><strong>{row.max_confidence.toFixed(1)}</strong></div>
                    <div><span>Dominance</span><strong>{row.dominance_pct.toFixed(0)}%</strong></div>
                    <div><span>Signals</span><strong>{row.n_signals}</strong></div>
                  </div>
                  <div className="market-card-footer">
                    <span className="market-card-label">Regime</span>
                    <Regime value={row.regime} />
                  </div>
                </article>
              ))}
            </div>
          </>
        )}
      </section>

      <div className="market-footer">
        MARKET is observational telemetry. “Radar ≥ threshold” is a display classification, not `DecisionPacket.is_actionable()` and not permission to trade.
      </div>
    </div>
  );
};
