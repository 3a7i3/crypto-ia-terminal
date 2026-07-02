// ── ScientificView.tsx — Tableau de bord scientifique EXP-001 ────────────────

import React from "react";
import type { ScientificResponse, ApiGate } from "../lib/api";
import { usePolling } from "../hooks/usePolling";

// ── État dégradé ──────────────────────────────────────────────────────────────

const Placeholder: React.FC<{ error: boolean }> = ({ error }) => (
  <div
    className="flex items-center justify-center h-40 rounded-[var(--r-card)]"
    style={{ background: "var(--bg-card)", border: "1px solid var(--bg-border)" }}
  >
    <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
      {error ? "⊘ /api/scientific indisponible — uvicorn api_server:app --port 8000" : "Chargement…"}
    </span>
  </div>
);

// ── ExperimentCard ────────────────────────────────────────────────────────────

const STATUS_COLOR: Record<string, string> = {
  IN_PROGRESS: "var(--warn)",
  COMPLETED:   "var(--ok)",
  ABANDONED:   "var(--danger)",
};

const ExperimentCard: React.FC<{ exp: ScientificResponse["experiment"] }> = ({ exp }) => {
  const col = STATUS_COLOR[exp.status] ?? "var(--text-muted)";
  return (
    <div
      className="rounded-[var(--r-card)] px-4 py-3 space-y-2"
      style={{ background: "var(--bg-card)", border: "1px solid var(--bg-border)" }}
    >
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs font-bold" style={{ color: "var(--text-pri)" }}>
          {exp.id || "EXP-001"}
        </span>
        {exp.status && (
          <span
            className="inline-block px-1.5 py-0.5 font-mono text-[10px] font-bold"
            style={{ color: col, background: `${col}18`, borderRadius: "var(--r-chip)" }}
          >
            {exp.status}
          </span>
        )}
      </div>

      {exp.title && (
        <div className="font-mono text-[11px]" style={{ color: "var(--text-sec)" }}>
          {exp.title}
        </div>
      )}

      {exp.objective && (
        <div className="font-mono text-[11px] leading-relaxed" style={{ color: "var(--text-muted)" }}>
          {exp.objective}
        </div>
      )}

      <div
        className="grid grid-cols-2 md:grid-cols-4 gap-2 pt-2"
        style={{ borderTop: "1px solid var(--bg-border)" }}
      >
        {[
          { label: "Start",        value: exp.date_start || "—" },
          { label: "End",          value: exp.date_end ?? "en cours" },
          { label: "Engine",       value: exp.engine_version || "—" },
          { label: "Dataset UUID", value: exp.dataset_uuid ? exp.dataset_uuid.slice(0, 8) + "…" : "—" },
        ].map(({ label, value }) => (
          <div key={label}>
            <div
              className="text-[9px] tracking-widest uppercase"
              style={{ color: "var(--text-muted)" }}
            >
              {label}
            </div>
            <div
              className="font-mono text-[11px]"
              style={{ color: "var(--text-sec)" }}
              title={label === "Dataset UUID" ? exp.dataset_uuid : undefined}
            >
              {value}
            </div>
          </div>
        ))}
      </div>

      {exp.hypotheses.length > 0 && (
        <div className="flex flex-wrap gap-1 pt-1">
          {exp.hypotheses.map(h => (
            <span
              key={h}
              className="inline-block px-1.5 py-0.5 font-mono text-[10px] font-semibold"
              style={{ color: "var(--accent)", background: "var(--accent-dim)", borderRadius: "var(--r-chip)" }}
            >
              {h}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};

// ── ProgressGauge ─────────────────────────────────────────────────────────────

const ProgressGauge: React.FC<{ progress: ScientificResponse["progress"] }> = ({ progress }) => {
  const { n_closed, n_required, n_calibration, wr, pf, pnl_paper } = progress;
  const pctDip = Math.min(100, n_required > 0 ? Math.round((n_closed / n_required) * 100) : 0);
  const pctCal = Math.min(100, n_calibration > 0 ? Math.round((n_closed / n_calibration) * 100) : 0);
  const hasData = n_closed > 0;

  return (
    <div
      className="rounded-[var(--r-card)] px-4 py-3 space-y-3"
      style={{ background: "var(--bg-card)", border: "1px solid var(--bg-border)" }}
    >
      <div
        className="text-[10px] font-bold tracking-widest uppercase"
        style={{ color: "var(--text-muted)" }}
      >
        Progression EXP-001
      </div>

      <div>
        <div className="flex items-center justify-between mb-1">
          <span className="font-mono text-[11px]" style={{ color: "var(--text-sec)" }}>
            Gate analyse DIP (N≥{n_required})
          </span>
          <span
            className="font-mono text-[11px] font-bold"
            style={{ color: pctDip >= 100 ? "var(--ok)" : "var(--warn)" }}
          >
            {n_closed}/{n_required}
          </span>
        </div>
        <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ background: "var(--bg-border)" }}>
          <div
            className="h-full rounded-full transition-all"
            style={{ width: `${pctDip}%`, background: pctDip >= 100 ? "var(--ok)" : "var(--accent)" }}
          />
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-1">
          <span className="font-mono text-[11px]" style={{ color: "var(--text-sec)" }}>
            Gate calibration (N≥{n_calibration})
          </span>
          <span className="font-mono text-[11px]" style={{ color: "var(--text-muted)" }}>
            {n_closed}/{n_calibration}
          </span>
        </div>
        <div className="w-full h-1 rounded-full overflow-hidden" style={{ background: "var(--bg-border)" }}>
          <div
            className="h-full rounded-full"
            style={{ width: `${pctCal}%`, background: "var(--text-muted)" }}
          />
        </div>
      </div>

      <div
        className="grid grid-cols-3 gap-2 pt-2"
        style={{ borderTop: "1px solid var(--bg-border)" }}
      >
        <div>
          <div className="text-[9px] tracking-widest uppercase" style={{ color: "var(--text-muted)" }}>
            Win Rate
          </div>
          <div
            className="font-mono text-sm font-bold"
            style={{ color: !hasData ? "var(--text-muted)" : wr >= 50 ? "var(--ok)" : "var(--danger)" }}
          >
            {hasData ? `${wr.toFixed(1)}%` : "—"}
          </div>
        </div>
        <div>
          <div className="text-[9px] tracking-widest uppercase" style={{ color: "var(--text-muted)" }}>
            Profit Factor
          </div>
          <div
            className="font-mono text-sm font-bold"
            style={{ color: !hasData ? "var(--text-muted)" : pf >= 1.4 ? "var(--ok)" : pf > 0 ? "var(--warn)" : "var(--danger)" }}
          >
            {hasData ? pf.toFixed(2) : "—"}
          </div>
        </div>
        <div>
          <div className="text-[9px] tracking-widest uppercase" style={{ color: "var(--text-muted)" }}>
            PnL Paper
          </div>
          <div
            className="font-mono text-sm font-bold"
            style={{ color: !hasData ? "var(--text-muted)" : pnl_paper >= 0 ? "var(--ok)" : "var(--danger)" }}
          >
            {hasData ? `${pnl_paper >= 0 ? "+" : ""}${pnl_paper.toFixed(2)}$` : "—"}
          </div>
        </div>
      </div>

      {!hasData && (
        <div className="font-mono text-[11px] text-center" style={{ color: "var(--text-muted)" }}>
          En attente des premiers trades…
        </div>
      )}
    </div>
  );
};

// ── GatesTable ────────────────────────────────────────────────────────────────

const GATE_COLOR: Record<ApiGate["status"], string> = {
  PASSED:      "var(--ok)",
  IN_PROGRESS: "var(--warn)",
  LOCKED:      "var(--text-muted)",
};

const GATE_GLYPH: Record<ApiGate["status"], string> = {
  PASSED:      "✓",
  IN_PROGRESS: "◎",
  LOCKED:      "⊘",
};

const GatesTable: React.FC<{ gates: ApiGate[] }> = ({ gates }) => (
  <div
    className="overflow-x-auto rounded-[var(--r-card)]"
    style={{ border: "1px solid var(--bg-border)", background: "var(--bg-card)" }}
  >
    <table className="w-full border-collapse">
      <thead>
        <tr style={{ borderBottom: "1px solid var(--bg-border)" }}>
          {["Critère (Règle du statisticien)", "Requis", "Actuel", "Statut"].map(h => (
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
      <tbody>
        {gates.map(gate => {
          const col   = GATE_COLOR[gate.status];
          const glyph = GATE_GLYPH[gate.status];
          const pct   = gate.required > 0
            ? Math.min(100, Math.round((gate.current / gate.required) * 100))
            : 0;
          return (
            <tr key={gate.id} style={{ borderBottom: "1px solid var(--bg-border)" }}>
              <td className="px-3 py-2 font-mono text-[11px]" style={{ color: "var(--text-sec)" }}>
                {gate.label}
              </td>
              <td className="px-3 py-2 font-mono text-[11px]" style={{ color: "var(--text-muted)" }}>
                {gate.required}
              </td>
              <td className="px-3 py-2">
                <div className="flex items-center gap-2">
                  <div
                    className="w-12 h-1 rounded-full overflow-hidden"
                    style={{ background: "var(--bg-border)" }}
                  >
                    <div className="h-full rounded-full" style={{ width: `${pct}%`, background: col }} />
                  </div>
                  <span className="font-mono text-[11px]" style={{ color: "var(--text-sec)" }}>
                    {gate.current}
                  </span>
                </div>
              </td>
              <td className="px-3 py-2">
                <span
                  className="inline-flex items-center gap-1 px-1.5 py-0.5 font-mono text-[10px] font-bold"
                  style={{ color: col, background: `${col}18`, borderRadius: "var(--r-chip)" }}
                >
                  <span aria-hidden="true">{glyph}</span>
                  {gate.status}
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  </div>
);

// ── Panneaux en attente d'evidence ────────────────────────────────────────────

const WaitingPanel: React.FC<{ title: string; n_required: number }> = ({ title, n_required }) => (
  <div
    className="rounded-[var(--r-card)] px-4 py-4 flex flex-col items-center justify-center gap-2"
    style={{ background: "var(--bg-card)", border: "1px solid var(--bg-border)", minHeight: "80px" }}
  >
    <span
      className="font-mono text-[10px] font-bold tracking-widest uppercase"
      style={{ color: "var(--text-muted)" }}
    >
      {title}
    </span>
    <span className="font-mono text-[11px]" style={{ color: "var(--text-muted)" }}>
      Waiting for evidence — N ≥ {n_required} requis
    </span>
  </div>
);

const HypothesisCard: React.FC<{ n_required: number }> = ({ n_required }) => (
  <WaitingPanel title="Hypothèses H1–H6" n_required={n_required} />
);

const EvidenceTable: React.FC<{ n_required: number }> = ({ n_required }) => (
  <WaitingPanel title="Evidence Table" n_required={n_required} />
);

const ContradictionPanel: React.FC<{ n_required: number }> = ({ n_required }) => (
  <WaitingPanel title="Contradiction Panel" n_required={n_required} />
);

// ── ScientificView ────────────────────────────────────────────────────────────

export const ScientificView: React.FC = () => {
  const { data, loading, error } = usePolling<ScientificResponse>("/api/scientific");

  if (loading || !data) return <Placeholder error={error} />;

  return (
    <div className="space-y-5">
      <div
        className="text-[10px] font-bold tracking-widest uppercase"
        style={{ color: "var(--text-muted)" }}
      >
        Scientific — Phase Validation
      </div>

      <ExperimentCard exp={data.experiment} />
      <ProgressGauge progress={data.progress} />

      <div>
        <div
          className="text-[10px] font-bold tracking-widest uppercase mb-2"
          style={{ color: "var(--text-muted)" }}
        >
          Règle du statisticien — Gates
        </div>
        <GatesTable gates={data.gates} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <HypothesisCard   n_required={data.progress.n_required} />
        <EvidenceTable    n_required={data.progress.n_required} />
        <ContradictionPanel n_required={data.progress.n_required} />
      </div>
    </div>
  );
};
