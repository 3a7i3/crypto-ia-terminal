// ── DecisionView.tsx — Analyse des décisions ─────────────────────────────────

import React, { useState } from "react";
import type { DecisionState, ConvictionLevel, MarketRegime, PostmortemCategory } from "../types";
import type { DecisionsResponse, ApiDecision } from "../lib/api";
import { usePolling } from "../hooks/usePolling";
import {
  DecisionStateBadge, ConvictionBadge,
  RegimeBadge, PostmortemBadge,
} from "../components/Badges";
import { fmtDur } from "../lib/tokens";

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

// ── Stats ─────────────────────────────────────────────────────────────────────

const DecisionStats: React.FC<{ decisions: ApiDecision[] }> = ({ decisions }) => {
  const total    = decisions.length;
  const executed = decisions.filter(d => d.state === "EXECUTED").length;
  const rejected = decisions.filter(d => ["REJECTED", "VETOED"].includes(d.state)).length;
  const execRate = total ? (executed / total * 100).toFixed(0) : "0";

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {([
        { label: "Total",     value: String(total),    color: "var(--text-sec)"  },
        { label: "Exécutés",  value: String(executed), color: "var(--ok)"        },
        { label: "Rejetés",   value: String(rejected), color: "var(--danger)"    },
        { label: "Exec rate", value: `${execRate}%`,
          color: Number(execRate) >= 40 ? "var(--ok)" : "var(--warn)" },
      ] as const).map(({ label, value, color }) => (
        <div
          key={label}
          className="px-4 py-3 rounded-[var(--r-card)]"
          style={{ background: "var(--bg-card)", border: "1px solid var(--bg-border)" }}
        >
          <div className="text-[10px] tracking-widest uppercase mb-1" style={{ color: "var(--text-muted)" }}>
            {label}
          </div>
          <div className="font-mono text-xl font-bold" style={{ color }}>
            {value}
          </div>
        </div>
      ))}
    </div>
  );
};

// ── Decision row ──────────────────────────────────────────────────────────────

const DecisionRow: React.FC<{ d: ApiDecision }> = ({ d }) => {
  const [expanded, setExpanded] = useState(false);
  const hasDetail = d.rejection_reason;
  const pm = d.state === "CLOSED" ? ("VALIDATED" as PostmortemCategory) : undefined;

  return (
    <>
      <tr
        onClick={() => hasDetail && setExpanded(v => !v)}
        className="transition-colors"
        style={{
          borderBottom: "1px solid var(--bg-border)",
          cursor:       hasDetail ? "pointer" : "default",
        }}
        onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-hover)")}
        onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
      >
        <td className="px-3 py-2 font-mono text-[11px]" style={{ color: "var(--text-muted)" }}>
          {d.created_at}
        </td>
        <td className="px-3 py-2">
          <span className="font-mono text-xs font-semibold" style={{ color: "var(--text-pri)" }}>
            {d.symbol.replace("/USDT", "")}
          </span>
        </td>
        <td className="px-3 py-2">
          <DecisionStateBadge state={d.state as DecisionState} />
        </td>
        <td className="px-3 py-2">
          <div className="flex items-center gap-2">
            <div
              className="w-12 h-1 rounded-full overflow-hidden"
              style={{ background: "var(--bg-border)" }}
            >
              <div
                className="h-full rounded-full"
                style={{
                  width:      `${d.score}%`,
                  background: d.score >= 70 ? "var(--accent)" :
                              d.score >= 50 ? "var(--warn)"   : "var(--neutral)",
                }}
              />
            </div>
            <span className="font-mono text-[11px]" style={{ color: "var(--text-sec)" }}>
              {d.score}
            </span>
          </div>
        </td>
        <td className="px-3 py-2">
          <ConvictionBadge level={d.conviction as ConvictionLevel} />
        </td>
        <td className="px-3 py-2 hidden lg:table-cell">
          <RegimeBadge regime={d.regime as MarketRegime} />
        </td>
        <td className="px-3 py-2">
          <span className="font-mono text-[11px]" style={{ color: "var(--text-muted)" }}>
            {fmtDur(d.duration_ms)}
          </span>
        </td>
        <td className="px-3 py-2 hidden md:table-cell">
          {pm ? <PostmortemBadge category={pm} /> : <span style={{ color: "var(--text-muted)", fontSize: 10 }}>—</span>}
        </td>
        <td className="px-2 py-2">
          {hasDetail && (
            <svg width="8" height="6" viewBox="0 0 8 6" fill="none" aria-hidden="true"
              style={{ transform: expanded ? "rotate(180deg)" : "none", transition: "transform 0.12s" }}>
              <path d="M1 1l3 3 3-3" stroke="var(--text-muted)" strokeWidth="1.5"
                strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </td>
      </tr>

      {expanded && hasDetail && (
        <tr style={{ background: "var(--bg-hover)" }}>
          <td colSpan={9} className="px-4 py-2">
            <div className="flex items-center gap-2 font-mono text-[11px]" style={{ color: "var(--danger)" }}>
              <span aria-hidden="true">⊘</span>
              <span>{d.rejection_reason}</span>
            </div>
          </td>
        </tr>
      )}
    </>
  );
};

// ── DecisionView ──────────────────────────────────────────────────────────────

export const DecisionView: React.FC = () => {
  const { data, loading, error } = usePolling<DecisionsResponse>("/api/decisions");

  if (loading || !data) return <Placeholder error={error} />;

  const decisions = data.decisions;

  return (
    <div className="space-y-4">
      <div
        className="text-[10px] font-bold tracking-widest uppercase"
        style={{ color: "var(--text-muted)" }}
      >
        Analyse des décisions — {decisions.length} dernières
        <span className="ml-3 font-normal" style={{ color: "var(--ok)" }}>auto-refresh 20s</span>
      </div>

      <DecisionStats decisions={decisions} />

      {decisions.length === 0 ? (
        <div
          className="flex items-center justify-center h-24 rounded-[var(--r-card)]"
          style={{ background: "var(--bg-card)", border: "1px solid var(--bg-border)" }}
        >
          <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
            Aucune décision — lancer le bot pour générer des données
          </span>
        </div>
      ) : (
        <div
          className="overflow-x-auto rounded-[var(--r-card)]"
          style={{ border: "1px solid var(--bg-border)", background: "var(--bg-card)" }}
        >
          <table className="w-full border-collapse">
            <thead>
              <tr style={{ borderBottom: "1px solid var(--bg-border)" }}>
                {[
                  "Heure", "Symbol", "État", "Score", "Conviction",
                  { label: "Régime",     cls: "hidden lg:table-cell" },
                  "Durée",
                  { label: "Postmortem", cls: "hidden md:table-cell" },
                  "",
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
            <tbody>
              {decisions.map(d => <DecisionRow key={d.id} d={d} />)}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
