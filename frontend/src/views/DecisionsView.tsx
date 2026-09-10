// ── DecisionsView — decision_pipeline.per_symbol_decisions, as-supplied ────
//
// EXECUTION_AUTHORITY, OBSERVATIONAL_TELEMETRY, and any other authority
// label are always distinguished. `is_actionable` is rendered exactly as
// produced — never inferred from score/conviction/regime/blockers/lifecycle
// state. No execution rate, rejection rate, win rate, or aggregate pipeline
// statistic is computed here.

import React from "react";
import type { OperatorSnapshot, PerSymbolDecision } from "../types";
import { ObservedValueView } from "../components/ObservedValueView";

const AuthorityTag: React.FC<{ authority: string }> = ({ authority }) => (
  <span
    data-testid="authority-tag"
    data-authority={authority}
    className="font-mono text-[9px] px-1 py-0.5 ml-1"
    style={{
      borderRadius: "var(--r-chip)",
      color: authority === "EXECUTION_AUTHORITY" ? "#22c55e" : "#94a3b8",
      background: authority === "EXECUTION_AUTHORITY" ? "#22c55e18" : "#94a3b818",
    }}
  >
    {authority}
  </span>
);

const DecisionRow: React.FC<{ rec: PerSymbolDecision }> = ({ rec }) => (
  <tr data-testid="decision-row" className="border-b" style={{ borderColor: "var(--bg-border)" }}>
    <td className="py-1.5 pr-3 font-mono text-xs">{rec.symbol}</td>
    <td className="py-1.5 pr-3 font-mono text-xs">
      <ObservedValueView ov={rec.is_actionable} render={(v) => (v ? "true" : "false")} />
      <AuthorityTag authority={rec.is_actionable.authority} />
    </td>
    <td className="py-1.5 pr-3 font-mono text-xs">
      <ObservedValueView ov={rec.trade_allowed} render={(v) => (v ? "true" : "false")} />
      <AuthorityTag authority={rec.trade_allowed.authority} />
    </td>
    <td className="py-1.5 pr-3 font-mono text-xs">
      <ObservedValueView ov={rec.first_blocker} />
      <AuthorityTag authority={rec.first_blocker.authority} />
    </td>
    <td className="py-1.5 pr-3 font-mono text-xs">
      <ObservedValueView ov={rec.side} />
    </td>
    <td className="py-1.5 pr-3 font-mono text-xs">
      <ObservedValueView ov={rec.regime} />
    </td>
    <td className="py-1.5 pr-3 font-mono text-xs">
      <ObservedValueView ov={rec.lifecycle_state} />
    </td>
    <td className="py-1.5 pr-3 font-mono text-xs">
      <ObservedValueView ov={rec.confidence_raw} />
    </td>
  </tr>
);

export const DecisionsView: React.FC<{ snapshot: OperatorSnapshot }> = ({ snapshot }) => {
  const dp = snapshot.decision_pipeline;
  const records = dp.per_symbol_decisions ?? [];

  return (
    <div className="flex flex-col gap-4" data-testid="decisions-view">
      <div className="p-3" style={{ background: "var(--bg-card)", borderRadius: 8, border: "1px solid var(--bg-border)" }}>
        <div className="font-mono text-xs font-bold mb-2">Aggregate pipeline (domain-level)</div>
        <div className="flex items-center justify-between py-1 font-mono text-xs">
          <span style={{ color: "var(--text-muted)" }}>trade_allowed</span>
          <ObservedValueView ov={dp.trade_allowed} render={(v) => (v ? "true" : "false")} />
        </div>
        <div className="flex items-center justify-between py-1 font-mono text-xs">
          <span style={{ color: "var(--text-muted)" }}>first_blocker</span>
          <ObservedValueView ov={dp.first_blocker} />
        </div>
        <div className="flex items-center justify-between py-1 font-mono text-xs">
          <span style={{ color: "var(--text-muted)" }}>stages</span>
          <span>{Array.isArray(dp.stages) && dp.stages.length > 0 ? `${dp.stages.length} stage(s)` : "UNKNOWN"}</span>
        </div>
        <div className="font-mono text-[10px] mt-2" style={{ color: "var(--text-muted)" }}>
          No execution rate, rejection rate, win rate, or aggregate statistic is computed by this UI —
          UNKNOWN aggregate fields above are displayed honestly, not derived from the per-symbol rows below.
        </div>
      </div>

      <div className="p-3" style={{ background: "var(--bg-card)", borderRadius: 8, border: "1px solid var(--bg-border)" }}>
        <div className="font-mono text-xs font-bold mb-2">Per-symbol decisions</div>
        {records.length === 0 ? (
          <div className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
            (empty — no per-symbol decisions in this snapshot)
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="w-full">
              <thead>
                <tr className="text-left" style={{ color: "var(--text-muted)" }}>
                  {["Symbol", "is_actionable", "trade_allowed", "first_blocker", "Side", "Regime", "Lifecycle", "Confidence"].map(
                    (h) => (
                      <th key={h} className="font-mono text-[10px] font-normal pb-1 pr-3">
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {records.map((rec) => (
                  <DecisionRow key={rec.packet_id ?? rec.symbol} rec={rec} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
