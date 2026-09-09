// ── OverviewView — snapshot identity/provenance + per-domain status ────────
// No liveness is derived from any of these fields (mission §Overview).

import React from "react";
import type { OperatorSnapshot } from "../types";

const Row: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex items-center justify-between py-1.5 border-b" style={{ borderColor: "var(--bg-border)" }}>
    <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
      {label}
    </span>
    <span className="font-mono text-xs" style={{ color: "var(--text-pri)" }}>
      {children}
    </span>
  </div>
);

const INSTANCE_RELATION_EXPLAIN: Record<string, string> = {
  CURRENT_INSTANCE: "This snapshot was produced by the currently-identified process instance.",
  PREVIOUS_INSTANCE: "This snapshot was produced by a prior process instance (producer restarted since).",
  UNKNOWN: "No usable runtime manifest evidence to compare instance identity.",
};

const DomainCard: React.FC<{ title: string; domain: { status: string; freshness: string } }> = ({ title, domain }) => (
  <div className="p-3" style={{ background: "var(--bg-card)", borderRadius: 8, border: "1px solid var(--bg-border)" }}>
    <div className="font-mono text-xs font-bold mb-2" style={{ color: "var(--text-pri)" }}>
      {title}
    </div>
    <Row label="status">{domain.status}</Row>
    <Row label="freshness">{domain.freshness}</Row>
  </div>
);

export const OverviewView: React.FC<{ snapshot: OperatorSnapshot }> = ({ snapshot }) => {
  return (
    <div className="flex flex-col gap-4" data-testid="overview-view">
      <div className="p-3" style={{ background: "var(--bg-card)", borderRadius: 8, border: "1px solid var(--bg-border)" }}>
        <Row label="snapshot_id">{snapshot.snapshot_id}</Row>
        <Row label="cycle">{snapshot.cycle}</Row>
        <Row label="generated_at_utc">{snapshot.generated_at_utc}</Row>
        <Row label="snapshot_age_s">{snapshot.snapshot_age_s ?? "—"}</Row>
        <Row label="process_instance_id">{snapshot.process_instance_id}</Row>
        <Row label="instance_relation">
          <span data-testid="instance-relation" title={INSTANCE_RELATION_EXPLAIN[snapshot.instance_relation] ?? ""}>
            {snapshot.instance_relation}
          </span>
        </Row>
        <Row label="runtime_state">
          <span data-testid="runtime-state">{snapshot.runtime_state}</span>
        </Row>
        <Row label="stale_reason">{snapshot.stale_reason ?? "—"}</Row>
        <Row label="freshness_classification">{snapshot.freshness_classification}</Row>
      </div>

      <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
        <DomainCard title="Portfolio" domain={snapshot.portfolio} />
        <DomainCard title="Decision pipeline" domain={snapshot.decision_pipeline} />
        <DomainCard title="System health" domain={snapshot.system_health} />
      </div>
    </div>
  );
};
