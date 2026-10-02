import { describe, expect, it } from "vitest";
import { validateRuntimeServiceSnapshot } from "../lib/runtimeServiceValidation";
import { runtimeServiceFixture } from "./runtimeServiceFixtures";

describe("U2b closed host observation validator", () => {
  it("accepts observed zero restarts and unavailable deployment without inventing a source", () => {
    expect(validateRuntimeServiceSnapshot(runtimeServiceFixture())).toBe(true);
  });
  it.each([
    (d: any) => { d.service.main_pid = true; },
    (d: any) => { d.service.restart_count = null; },
    (d: any) => { d.service.restart_count = -1; },
    (d: any) => { d.service.main_pid = 0; },
    (d: any) => { d.service.main_pid = Number.MAX_SAFE_INTEGER + 1; },
    (d: any) => { d.service.active_state = "HEALTHY"; },
    (d: any) => { d.service.active_state = []; },
    (d: any) => { d.service.query_status = "TIMEOUT"; },
    (d: any) => { d.service.unit = "another.service"; },
    (d: any) => { d.service.exec_main_started_at_utc = "2099-01-01T00:00:00Z"; },
    (d: any) => { d.observed_at_utc = "2026-02-30T00:00:00Z"; },
    (d: any) => { d.authority = "ADVISOR_LIVENESS"; },
    (d: any) => { d.deployment.status = "PRESENT"; },
    (d: any) => { d.deployment.source_code_sha = "b".repeat(40); },
    (d: any) => { d.host_id = "host\nsecret"; },
    (d: any) => { d.extra = "secret"; },
    (d: any) => { d.snapshot_age_s = NaN; },
    (d: any) => { d.freshness_classification = "LIVE"; },
  ])("rejects malformed or contradictory host evidence %#", (mutate) => {
    const d = runtimeServiceFixture(); mutate(d);
    expect(validateRuntimeServiceSnapshot(d)).toBe(false);
  });
  it("accepts fully unavailable service evidence without fake zeros", () => {
    const d = runtimeServiceFixture();
    d.service = { unit: "crypto-advisor.service", query_status: "TIMEOUT", load_state: null, active_state: null, sub_state: null, main_pid: null, restart_count: null, exec_main_started_at_utc: null, invocation_id: null };
    expect(validateRuntimeServiceSnapshot(d)).toBe(true);
  });
  it("accepts supplied deployment evidence but rejects it when its time predates invocation", () => {
    const d = runtimeServiceFixture();
    d.deployment = { status: "PRESENT", reason: null, source_code_sha: "b".repeat(40), evidence_ref: "deployment-proof-01", observed_at_utc: "2026-10-01T00:00:01Z", artifact_sha256: "c".repeat(64), host_id: d.host_id, invocation_id: d.service.invocation_id };
    expect(validateRuntimeServiceSnapshot(d)).toBe(true);
    d.deployment.observed_at_utc = "2026-09-30T23:59:59Z";
    expect(validateRuntimeServiceSnapshot(d)).toBe(false);
  });
  it("rejects a deployment bound to a different systemd invocation", () => {
    const d = runtimeServiceFixture();
    d.deployment = { status: "PRESENT", reason: null, source_code_sha: "b".repeat(40), evidence_ref: "deployment-proof-01", observed_at_utc: "2026-10-01T00:00:01Z", artifact_sha256: "c".repeat(64), host_id: d.host_id, invocation_id: "c".repeat(32) };
    expect(validateRuntimeServiceSnapshot(d)).toBe(false);
  });
});
