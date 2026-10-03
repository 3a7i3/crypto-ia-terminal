import type { RuntimeServiceSnapshot } from "../lib/runtimeServiceTypes";

export function runtimeServiceFixture(): RuntimeServiceSnapshot {
  return {
    schema_version: "1.0.0", product: "RuntimeServiceSnapshot", domain: "runtime_service",
    authority: "HOST_SYSTEMD_OBSERVATION", mode: "READ_ONLY",
    generated_at_utc: "2026-10-02T00:00:05Z", observed_at_utc: "2026-10-02T00:00:05Z", host_id: "host-fixture",
    service: { unit: "crypto-advisor.service", query_status: "OK", load_state: "loaded", active_state: "active", sub_state: "running", main_pid: 1234, restart_count: 0, exec_main_started_at_utc: "2026-10-01T00:00:00Z", invocation_id: "a".repeat(32) },
    deployment: { status: "NOT_AVAILABLE", reason: "NO_EVIDENCE", source_code_sha: null, evidence_ref: null, observed_at_utc: null, artifact_sha256: null, host_id: null, invocation_id: null },
    snapshot_age_s: 5, freshness_classification: "FRESH",
  };
}
