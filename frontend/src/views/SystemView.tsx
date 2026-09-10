// ── SystemView — canonical system_health domain, rendered honestly ─────────
//
// boot_alive stays UNKNOWN when supplied as value=null/semantics=UNKNOWN.
// Advisor liveness is never inferred from /healthz, snapshot age, manifest
// presence, PID, process identity, or S-03.

import React from "react";
import type { OperatorSnapshot } from "../types";
import { ObservedValueView } from "../components/ObservedValueView";

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

export const SystemView: React.FC<{ snapshot: OperatorSnapshot }> = ({ snapshot }) => {
  const sh = snapshot.system_health;
  const moduleStatuses = sh.module_statuses ?? {};
  const moduleKeys = Object.keys(moduleStatuses);

  return (
    <div className="flex flex-col gap-4" data-testid="system-view">
      <div className="p-3" style={{ background: "var(--bg-card)", borderRadius: 8, border: "1px solid var(--bg-border)" }}>
        <div className="font-mono text-[10px] mb-2" style={{ color: "var(--text-muted)" }} data-testid="boot-alive-note">
          /healthz means only that the API transport process responds. It never claims the advisor is alive.
        </div>
        <Field label="boot_alive">
          <ObservedValueView ov={sh.boot_alive} render={(v) => (v ? "true" : "false")} />
        </Field>
        <Field label="health_score">
          <ObservedValueView ov={sh.health_score} />
        </Field>
        <Field label="health_level">
          <ObservedValueView ov={sh.health_level} />
        </Field>
        <Field label="exchange_connectivity_healthy">
          <ObservedValueView ov={sh.exchange_connectivity_healthy} render={(v) => (v ? "true" : "false")} />
        </Field>
        <Field label="exchange_latency_ms">
          <ObservedValueView ov={sh.exchange_latency_ms} />
        </Field>
        <Field label="status">{sh.status}</Field>
        <Field label="freshness">{sh.freshness}</Field>
      </div>

      <div className="p-3" style={{ background: "var(--bg-card)", borderRadius: 8, border: "1px solid var(--bg-border)" }}>
        <div className="font-mono text-xs font-bold mb-2">Module statuses</div>
        {moduleKeys.length === 0 ? (
          <div className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
            (empty — no module statuses supplied)
          </div>
        ) : (
          moduleKeys.map((k) => (
            <Field key={k} label={k}>
              {JSON.stringify((moduleStatuses as Record<string, unknown>)[k])}
            </Field>
          ))
        )}
      </div>
    </div>
  );
};
