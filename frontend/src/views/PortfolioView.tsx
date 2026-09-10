// ── PortfolioView — canonical portfolio domain, rendered exactly as supplied ─
//
// PAPER and REAL_API/TESTNET_API data are always kept in visually separate
// blocks and are never added, merged, netted, or compared. No PnL, equity,
// exposure, totals, percentages, or position counts are computed here —
// every number shown is a producer-supplied ObservedValue.

import React from "react";
import type { OperatorSnapshot, OpenPosition } from "../types";
import { ObservedValueView } from "../components/ObservedValueView";
import { ModeBadge } from "../components/ModeBadge";
import { isObservedValue } from "../lib/observedValue";

const fmtUsd = (v: unknown) => (typeof v === "number" ? `$${v.toFixed(2)}` : String(v));
const fmtPct = (v: unknown) => (typeof v === "number" ? `${v.toFixed(2)}%` : String(v));

const PositionRow: React.FC<{ pos: OpenPosition }> = ({ pos }) => (
  <tr data-testid="open-position-row" className="border-b" style={{ borderColor: "var(--bg-border)" }}>
    <td className="py-1.5 pr-3 font-mono text-xs">{pos.symbol}</td>
    <td className="py-1.5 pr-3 font-mono text-xs">{pos.side ?? "—"}</td>
    <td className="py-1.5 pr-3 font-mono text-xs">{pos.size_usd ?? "—"}</td>
    <td className="py-1.5 pr-3 font-mono text-xs">{pos.entry_price ?? "—"}</td>
    <td className="py-1.5 pr-3 font-mono text-xs">
      <ObservedValueView ov={pos.current_price} render={fmtUsd} />
    </td>
    <td className="py-1.5 pr-3 font-mono text-xs">
      <ObservedValueView ov={pos.unrealized_pnl_usd} render={fmtUsd} />
    </td>
    <td className="py-1.5 pr-3 font-mono text-xs">
      <ObservedValueView ov={pos.unrealized_pnl_pct} render={fmtPct} />
    </td>
    <td className="py-1.5 pr-3 font-mono text-xs">
      <ObservedValueView ov={pos.regime} />
      {pos.restored_without_regime && (
        <span className="ml-1 text-[10px]" style={{ color: "var(--text-muted)" }} data-testid="restored-without-regime">
          (restored, no ledger regime)
        </span>
      )}
    </td>
    <td className="py-1.5 pr-3 font-mono text-xs">{pos.tp_sl_source}</td>
    <td className="py-1.5 pr-3 font-mono text-xs">{pos.personality ?? "—"}</td>
  </tr>
);

const Field: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex items-center justify-between py-1.5 border-b" style={{ borderColor: "var(--bg-border)" }}>
    <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
      {label}
    </span>
    <span className="font-mono text-xs" style={{ color: "var(--text-pri)" }}>
      {children}
    </span>
  </div>
);

const PositionsTable: React.FC<{ positions: OpenPosition[] }> = ({ positions }) => (
  <div style={{ overflowX: "auto" }}>
    <table className="w-full">
      <thead>
        <tr className="text-left" style={{ color: "var(--text-muted)" }}>
          {["Symbol", "Side", "Size", "Entry", "Current", "PnL $", "PnL %", "Regime", "TP/SL source", "Personality"].map((h) => (
            <th key={h} className="font-mono text-[10px] font-normal pb-1 pr-3">
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {positions.map((pos) => (
          <PositionRow key={pos.position_id || pos.symbol} pos={pos} />
        ))}
      </tbody>
    </table>
  </div>
);

/** O-02W-D2-R1 Correction D — `open_positions` presentation, never via
 * `String(value)`:
 * - PRESENT with a non-empty array: render the table.
 * - EMPTY: the genuine observed-empty state (delegated to ObservedValueView).
 * - STALE with a valid array: render the supplied last-known rows wrapped in
 *   a visible STALE warning around the whole position section.
 * - UNKNOWN/UNAVAILABLE/NOT_APPLICABLE: explicit semantics, no rows.
 * - Malformed combinations: INVALID_OBSERVED_VALUE (never repaired).
 * Never recomputes price, PnL, count, or exposure. */
const OpenPositionsSection: React.FC<{ ov: unknown }> = ({ ov }) => {
  if (!isObservedValue(ov)) {
    return <ObservedValueView ov={ov} />;
  }

  if (ov.semantics === "PRESENT" || ov.semantics === "STALE") {
    if (!Array.isArray(ov.value)) {
      // Semantics claims a list but the value isn't one — contradictory,
      // never coerced into an empty/healthy render.
      return (
        <span className="ov ov-invalid" data-testid="ov-invalid">
          INVALID_OBSERVED_VALUE
        </span>
      );
    }

    const positions = ov.value as OpenPosition[];

    if (positions.length === 0) {
      return (
        <div className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
          (empty — zero open positions observed)
        </div>
      );
    }

    const table = <PositionsTable positions={positions} />;

    if (ov.semantics === "STALE") {
      return (
        <div data-testid="open-positions-stale-wrapper">
          <div
            data-testid="open-positions-stale-badge"
            className="font-mono text-[10px] mb-2"
            style={{ color: "#f59e0b" }}
          >
            ⚠ STALE — last-known open positions, not a current observation
          </div>
          {table}
        </div>
      );
    }

    return table;
  }

  // UNKNOWN / UNAVAILABLE / NOT_APPLICABLE — no rows, explicit semantics only.
  return (
    <div className="font-mono text-xs">
      <ObservedValueView ov={ov} />
    </div>
  );
};

export const PortfolioView: React.FC<{ snapshot: OperatorSnapshot }> = ({ snapshot }) => {
  const p = snapshot.portfolio;

  return (
    <div className="flex flex-col gap-4" data-testid="portfolio-view">
      <div className="flex items-center gap-2">
        <ModeBadge mode={p.mode} />
        <span className="font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>
          portfolio.mode (canonical, never inferred)
        </span>
      </div>

      {/* PAPER block — always separate from real/testnet observation below */}
      <div
        data-testid="paper-block"
        className="p-3"
        style={{ background: "var(--bg-card)", borderRadius: 8, border: "1px solid var(--bg-border)" }}
      >
        <div className="font-mono text-xs font-bold mb-2">PAPER</div>
        <Field label="paper_equity_usd">
          <ObservedValueView ov={p.paper_equity_usd} render={fmtUsd} />
        </Field>
        <Field label="paper_open_positions_count">
          <ObservedValueView ov={p.paper_open_positions_count} />
        </Field>
        <Field label="paper_unrealized_pnl_usd">
          <ObservedValueView ov={p.paper_unrealized_pnl_usd} render={fmtUsd} />
        </Field>
        <Field label="paper_realized_pnl_usd">
          <ObservedValueView ov={p.paper_realized_pnl_usd} render={fmtUsd} />
        </Field>
      </div>

      {/* REAL/TESTNET block — never combined with PAPER numbers above */}
      <div
        data-testid="real-testnet-block"
        className="p-3"
        style={{ background: "var(--bg-card)", borderRadius: 8, border: "1px solid var(--bg-border)" }}
      >
        <div className="font-mono text-xs font-bold mb-1">REAL / TESTNET account observation</div>
        <div className="font-mono text-[10px] mb-2" style={{ color: "#f97316" }} data-testid="real-account-warning">
          READ-ONLY ACCOUNT OBSERVATION — NEVER USED FOR SIZING OR DECISION AUTHORITY
        </div>
        <Field label="real_account_equity_usd">
          <ObservedValueView ov={p.real_account_equity_usd} render={fmtUsd} />
        </Field>
        <Field label="real_account_free_usd">
          <ObservedValueView ov={p.real_account_free_usd} render={fmtUsd} />
        </Field>
        <Field label="real_account_stale">
          <ObservedValueView ov={p.real_account_stale} render={(v) => (v ? "true" : "false")} />
        </Field>
        <Field label="real_account_last_poll_utc">
          <ObservedValueView ov={p.real_account_last_poll_utc} />
        </Field>
        <Field label="non_paper_wallet_balance_usd">
          <ObservedValueView ov={p.non_paper_wallet_balance_usd} render={fmtUsd} />
        </Field>
        <Field label="capital_x_usd">
          <ObservedValueView ov={p.capital_x_usd} render={fmtUsd} />
        </Field>
      </div>

      <div
        data-testid="open-positions-section"
        className="p-3"
        style={{ background: "var(--bg-card)", borderRadius: 8, border: "1px solid var(--bg-border)" }}
      >
        <div className="font-mono text-xs font-bold mb-2">Open positions</div>
        <OpenPositionsSection ov={p.open_positions} />
      </div>
    </div>
  );
};
