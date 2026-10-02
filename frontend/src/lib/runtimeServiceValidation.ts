import type { RuntimeServiceSnapshot } from "./runtimeServiceTypes";

const loadStates = ["stub", "loaded", "not-found", "bad-setting", "error", "merged", "masked"];
const activeStates = ["active", "reloading", "inactive", "failed", "activating", "deactivating", "maintenance", "refreshing"];
const subStates = ["dead", "condition", "start-pre", "start", "start-post", "running", "exited", "reload", "reload-signal", "reload-notify", "stop", "stop-watchdog", "stop-sigterm", "stop-sigkill", "stop-post", "final-sigterm", "final-sigkill", "failed", "auto-restart", "auto-restart-queued", "cleaning", "maintenance"];
const queryStates = ["OK", "NOT_FOUND", "TIMEOUT", "COMMAND_UNAVAILABLE", "COMMAND_FAILED", "INVALID_PROPERTIES", "OUTPUT_LIMIT"];
const reasons = ["NO_EVIDENCE", "INVALID_EVIDENCE", "HOST_MISMATCH", "INVOCATION_MISMATCH", "SERVICE_UNAVAILABLE", "EVIDENCE_TIME_MISMATCH"];
const serviceFields = ["unit", "query_status", "load_state", "active_state", "sub_state", "main_pid", "restart_count", "exec_main_started_at_utc", "invocation_id"];
const deploymentFields = ["status", "reason", "source_code_sha", "evidence_ref", "observed_at_utc", "artifact_sha256", "host_id", "invocation_id"];

function exact(x: unknown, keys: string[]): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x) && Object.keys(x).length === keys.length && keys.every((key) => Object.prototype.hasOwnProperty.call(x, key));
}
function member(x: unknown, values: string[]): boolean { return typeof x === "string" && values.includes(x); }
function hex(x: unknown, size: number): boolean { return typeof x === "string" && new RegExp(`^[0-9a-f]{${size}}$`).test(x); }
function safeText(x: unknown): boolean { return typeof x === "string" && /^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$/.test(x); }
function unsigned(x: unknown): boolean { return typeof x === "number" && Number.isSafeInteger(x) && x >= 0; }
function utc(x: unknown): number | null {
  if (typeof x !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(x)) return null;
  const value = Date.parse(x);
  // Date.parse alone silently normalizes impossible dates, e.g. Feb 30.
  if (!Number.isFinite(value) || new Date(value).toISOString().slice(0, 19) !== x.slice(0, 19)) return null;
  const fraction = x.match(/\.(\d{1,6})Z$/)?.[1] ?? "";
  return Date.parse(x.slice(0, 19) + "Z") * 1000 + Number(fraction.padEnd(6, "0"));
}

export function validateRuntimeServiceSnapshot(x: unknown): x is RuntimeServiceSnapshot {
  if (!exact(x, ["schema_version", "product", "domain", "authority", "mode", "generated_at_utc", "observed_at_utc", "host_id", "service", "deployment", "snapshot_age_s", "freshness_classification"])) return false;
  if (x.schema_version !== "1.0.0" || x.product !== "RuntimeServiceSnapshot" || x.domain !== "runtime_service" || x.authority !== "HOST_SYSTEMD_OBSERVATION" || x.mode !== "READ_ONLY" || !safeText(x.host_id)) return false;
  const observed = utc(x.observed_at_utc), generated = utc(x.generated_at_utc);
  if (observed === null || generated === null || observed > generated) return false;
  const s = x.service, d = x.deployment;
  if (!exact(s, serviceFields) || s.unit !== "crypto-advisor.service" || !member(s.query_status, queryStates)) return false;
  if (s.query_status === "OK") {
    if (!member(s.load_state, loadStates.filter((v) => v !== "not-found")) || !member(s.active_state, activeStates) || !member(s.sub_state, subStates) || !unsigned(s.main_pid) || !unsigned(s.restart_count)) return false;
    const started = utc(s.exec_main_started_at_utc);
    if (s.exec_main_started_at_utc !== null && (started === null || started > observed)) return false;
    if (s.invocation_id !== null && !hex(s.invocation_id, 32)) return false;
    if (s.active_state === "active" && s.sub_state === "running" && (s.main_pid === 0 || started === null || s.invocation_id === null)) return false;
  } else {
    if (s.load_state !== (s.query_status === "NOT_FOUND" ? "not-found" : null)) return false;
    if (serviceFields.filter((key) => !["unit", "query_status", "load_state"].includes(key)).some((key) => s[key] !== null)) return false;
  }
  if (!exact(d, deploymentFields)) return false;
  if (d.status === "PRESENT") {
    const stamp = utc(d.observed_at_utc), started = utc(s.exec_main_started_at_utc);
    if (d.reason !== null || d.host_id !== x.host_id || d.invocation_id !== s.invocation_id || s.query_status !== "OK" || s.invocation_id === null || started === null || stamp === null || stamp < started || stamp > observed || !hex(d.source_code_sha, 40) || !hex(d.artifact_sha256, 64) || !safeText(d.evidence_ref)) return false;
  } else if (d.status === "NOT_AVAILABLE") {
    if (!member(d.reason, reasons) || deploymentFields.filter((key) => !["status", "reason"].includes(key)).some((key) => d[key] !== null)) return false;
  } else return false;
  return typeof x.snapshot_age_s === "number" && Number.isFinite(x.snapshot_age_s) && x.snapshot_age_s >= 0 && member(x.freshness_classification, ["FRESH", "STALE"]);
}
