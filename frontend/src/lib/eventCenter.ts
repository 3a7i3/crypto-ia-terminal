import { useEffect, useState } from "react";

export const EVENTS_ENDPOINT = "/api/operator/v1/events";
export const SOURCE_IDS = ["p12_alerts", "supervision_alerts", "ppl_lifecycles"] as const;
export type SourceId = typeof SOURCE_IDS[number];
export interface EventSource {
  source_id: SourceId; format: string;
  status: "PRESENT" | "NOT_CONFIGURED" | "MISSING" | "READ_ERROR" | "INVALID" | "OUTPUT_LIMIT";
  source_sha256: string | null; records_observed: number | null; events_observed: number | null;
  excluded_records: number | null; published_count: number | null; undated_count: number | null;
  truncated: boolean | null; source_generated_at_utc: string | null; paper_epoch_id: string | null;
  source_age_s: number | null; freshness_classification: "FRESH" | "STALE" | "UNKNOWN" | "NOT_AVAILABLE";
}
export interface OperatorEvent {
  event_id: string; source_id: SourceId; source_record: number; kind: string;
  severity: "INFO" | "WARNING" | "CRITICAL" | "UNKNOWN";
  occurred_at_utc: string | null; time_status: "PRESENT" | "UNKNOWN";
  symbol: string | null; sequence: number | null;
}
export interface EventCenterSnapshot {
  schema_version: "1.0.0"; product: "EventCenterSnapshot"; domain: "event_center";
  authority: "OBSERVATIONAL_PRESENTATION"; mode: "READ_ONLY";
  generated_at_utc: string; sources: EventSource[]; events: OperatorEvent[];
  order: "SOURCE_THEN_TIME_DESC_UNDATED_LAST";
  snapshot_age_s: number; freshness_classification: "FRESH" | "STALE";
}
const sourceKeys = ["source_id", "format", "status", "source_sha256", "records_observed", "events_observed", "excluded_records", "published_count", "undated_count", "truncated", "source_generated_at_utc", "paper_epoch_id", "source_age_s", "freshness_classification"];
const eventKeys = ["event_id", "source_id", "source_record", "kind", "severity", "occurred_at_utc", "time_status", "symbol", "sequence"];
const alertKinds = ["DRAWDOWN", "MEMORY", "ERROR_RATE", "RECONCILE", "BOOT_BLOCKED", "HIGH_LATENCY", "EXCEPTION", "OTHER_ALERT"];
const pplKinds = ["POSITION_OPENED", "POSITION_CLOSED", "POSITION_UNRESOLVED"];
function exact(x: unknown, keys: string[]): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x) && Object.keys(x).length === keys.length && keys.every(k => Object.hasOwn(x, k));
}
function member(x: unknown, values: readonly string[]): boolean { return typeof x === "string" && values.includes(x); }
function uint(x: unknown): x is number { return typeof x === "number" && Number.isSafeInteger(x) && x >= 0; }
function finite(x: unknown): x is number { return typeof x === "number" && Number.isFinite(x) && x >= 0; }
function match(x: unknown, regex: RegExp): x is string { return typeof x === "string" && regex.test(x); }
function utc(x: unknown): number | null {
  if (!match(x, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/)) return null;
  const ms = Date.parse(x);
  if (!Number.isFinite(ms) || new Date(ms).toISOString().slice(0, 19) !== x.slice(0, 19)) return null;
  return Date.parse(x.slice(0, 19) + "Z") * 1000 + Number((x.match(/\.(\d{1,6})Z$/)?.[1] ?? "").padEnd(6, "0"));
}
export function validateEventCenter(x: unknown): x is EventCenterSnapshot {
  if (!exact(x, ["schema_version", "product", "domain", "authority", "mode", "generated_at_utc", "sources", "events", "order", "snapshot_age_s", "freshness_classification"])) return false;
  if (x.schema_version !== "1.0.0" || x.product !== "EventCenterSnapshot" || x.domain !== "event_center" || x.authority !== "OBSERVATIONAL_PRESENTATION" || x.mode !== "READ_ONLY" || x.order !== "SOURCE_THEN_TIME_DESC_UNDATED_LAST") return false;
  const generated = utc(x.generated_at_utc);
  if (generated === null || !finite(x.snapshot_age_s) || !member(x.freshness_classification, ["FRESH", "STALE"]) || !Array.isArray(x.sources) || x.sources.length !== 3 || !Array.isArray(x.events) || x.events.length > 300) return false;
  for (const [i, s] of x.sources.entries()) {
    if (!exact(s, sourceKeys) || s.source_id !== SOURCE_IDS[i] || s.format !== ["P12_ALERT_JSONL", "SUPERVISION_AUDIT_JSONL", "BURN_IN_LIFECYCLE_PROJECTION"][i] || !member(s.status, ["PRESENT", "NOT_CONFIGURED", "MISSING", "READ_ERROR", "INVALID", "OUTPUT_LIMIT"])) return false;
    if (s.status !== "PRESENT") {
      if (s.source_age_s !== null || s.freshness_classification !== "NOT_AVAILABLE" || sourceKeys.filter(k => !["source_id", "format", "status", "source_age_s", "freshness_classification"].includes(k)).some(k => s[k] !== null)) return false;
      continue;
    }
    if (!match(s.source_sha256, /^[0-9a-f]{64}$/)) return false;
    if (![s.records_observed, s.events_observed, s.excluded_records, s.published_count, s.undated_count].every(uint)) return false;
    const records = s.records_observed as number, total = s.events_observed as number, count = s.published_count as number, excluded = s.excluded_records as number, undated = s.undated_count as number;
    if (records > 10000 || count > 100 || count !== Math.min(total, 100) || undated > total || s.truncated !== (total > count)) return false;
    if (i < 2) {
      if (records !== total + excluded || s.source_generated_at_utc !== null || s.paper_epoch_id !== null || s.source_age_s !== null || s.freshness_classification !== "UNKNOWN") return false;
    } else {
      const stamp = utc(s.source_generated_at_utc);
      if (stamp === null || stamp > generated || !match(s.paper_epoch_id, /^[A-Za-z0-9_.:-]{1,128}$/) || records !== total || excluded !== 0 || undated !== 0 || !finite(s.source_age_s) || !member(s.freshness_classification, ["FRESH", "STALE"])) return false;
    }
  }
  const ids = new Set<string>(), records = new Set<string>(), sequences = new Set<number>();
  let prior: [number, number, number, number, string] | null = null;
  for (const e of x.events) {
    if (!exact(e, eventKeys) || !member(e.source_id, SOURCE_IDS) || !uint(e.source_record) || e.source_record < 1 || !match(e.event_id, /^[0-9a-f]{64}$/) || ids.has(e.event_id) || !member(e.kind, [...alertKinds, ...pplKinds]) || !member(e.severity, ["INFO", "WARNING", "CRITICAL", "UNKNOWN"])) return false;
    ids.add(e.event_id);
    const recordKey = `${e.source_id}:${e.source_record}`;
    if (records.has(recordKey)) return false;
    records.add(recordKey);
    const index = SOURCE_IDS.indexOf(e.source_id as SourceId), source = x.sources[index];
    if (source.status !== "PRESENT" || e.source_record > source.records_observed) return false;
    const stamp = utc(e.occurred_at_utc);
    if (e.time_status === "PRESENT" ? stamp === null || stamp > generated : e.time_status !== "UNKNOWN" || e.occurred_at_utc !== null) return false;
    if (index === 2) {
      if (!member(e.kind, pplKinds) || e.time_status !== "PRESENT" || e.severity !== (e.kind === "POSITION_UNRESOLVED" ? "WARNING" : "INFO") || !match(e.symbol, /^[A-Z0-9]{2,24}(?:\/[A-Z0-9]{2,24})?$/) || !uint(e.sequence) || e.sequence < 1 || stamp! > utc(source.source_generated_at_utc)!) return false;
          if (sequences.has(e.sequence)) return false;
      sequences.add(e.sequence);
    } else if (!member(e.kind, alertKinds) || e.symbol !== null || e.sequence !== null) return false;
    const order: [number, number, number, number, string] = [index, stamp === null ? 1 : 0, -(stamp ?? 0), -e.source_record, e.event_id];
    if (prior) {
      for (let i = 0; i < order.length; i++) {
        if (order[i] < prior[i]) return false;
        if (order[i] > prior[i]) break;
      }
    }
    prior = order;
  }
  for (const source of x.sources) {
    const rows = x.events.filter(e => e.source_id === source.source_id);
    const undated = rows.filter(e => e.time_status === "UNKNOWN").length;
    if (rows.length !== (source.published_count ?? 0) || (source.status === "PRESENT" && (undated > source.undated_count || (!source.truncated && undated !== source.undated_count)))) return false;
  }
  return true;
}

export type EventCenterState = { status: "loading" } | { status: "success"; snapshot: EventCenterSnapshot } | { status: "error"; code: string };
export function useEventCenter(intervalMs = 20_000): EventCenterState {
  const [state, setState] = useState<EventCenterState>({ status: "loading" });
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();
    async function load() {
      let next: EventCenterState;
      try {
        const response = await fetch(EVENTS_ENDPOINT, { method: "GET", signal: controller.signal });
        const body: unknown = await response.json();
        if (!response.ok) {
          const known = ["EVENT_CENTER_MISSING", "EVENT_CENTER_INVALID_SCHEMA", "EVENT_CENTER_INVALID_ARTIFACT", "EVENT_CENTER_FUTURE_TIMESTAMP"];
          const code = typeof body === "object" && body !== null && "error_code" in body && member(body.error_code, known) ? String(body.error_code) : "EVENT_CENTER_SOURCE_ERROR";
          next = { status: "error", code };
        } else next = validateEventCenter(body) ? { status: "success", snapshot: body } : { status: "error", code: "EVENT_CENTER_CONTRACT_ERROR" };
      } catch { next = { status: "error", code: "EVENT_CENTER_TRANSPORT_ERROR" }; }
      if (alive) { setState(next); timer = setTimeout(load, intervalMs); }
    }
    load();
    return () => { alive = false; controller.abort(); if (timer !== undefined) clearTimeout(timer); };
  }, [intervalMs]);
  return state;
}
