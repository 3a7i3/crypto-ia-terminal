import { usePassiveSnapshot, type PassiveSnapshotState } from "./usePassiveSnapshot";

export interface StorageSnapshot {
  schema_version: "1.0.0"; product: "StorageSnapshot"; domain: "storage";
  authority: "FILESYSTEM_METADATA_OBSERVATION"; mode: "READ_ONLY";
  generated_at_utc: string; observed_at_utc: string;
  category: "DECISION_PACKET_LOGS"; scope: "DIRECT_CHILDREN_PATTERN"; pattern: "decision_packets_*.jsonl";
  source_status: "PRESENT" | "NOT_CONFIGURED" | "MISSING" | "READ_ERROR" | "INVALID_PATH" | "OUTPUT_LIMIT" | "SOURCE_CHANGED" | "INVALID_METADATA";
  entries_observed: number | null; matched_file_count: number | null; total_bytes: number | null;
  latest_file_modified_at_utc: string | null; inventory_sha256: string | null;
  snapshot_age_s: number; freshness_classification: "FRESH" | "STALE";
}
const metrics = ["entries_observed", "matched_file_count", "total_bytes", "latest_file_modified_at_utc", "inventory_sha256"];
const keys = ["schema_version", "product", "domain", "authority", "mode", "generated_at_utc", "observed_at_utc", "category", "scope", "pattern", "source_status", "snapshot_age_s", "freshness_classification", ...metrics];
const statuses = ["PRESENT", "NOT_CONFIGURED", "MISSING", "READ_ERROR", "INVALID_PATH", "OUTPUT_LIMIT", "SOURCE_CHANGED", "INVALID_METADATA"];
const errors = ["STORAGE_MISSING", "STORAGE_INVALID_ARTIFACT", "STORAGE_INVALID_SCHEMA", "STORAGE_FUTURE_TIMESTAMP"];
const uint = (x: unknown): x is number => typeof x === "number" && Number.isSafeInteger(x) && x >= 0;
function utc(x: unknown): number | null {
  if (typeof x !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(x)) return null;
  const ms = Date.parse(x);
  if (!Number.isFinite(ms) || new Date(ms).toISOString().slice(0, 19) !== x.slice(0, 19)) return null;
  return Date.parse(x.slice(0, 19) + "Z") * 1000 + Number((x.match(/\.(\d{1,6})Z$/)?.[1] ?? "").padEnd(6, "0"));
}
export function validateStorageSnapshot(x: unknown): x is StorageSnapshot {
  if (typeof x !== "object" || x === null || Array.isArray(x)) return false;
  const d = x as Record<string, unknown>;
  if (Object.keys(d).length !== keys.length || !keys.every(k => Object.hasOwn(d, k))) return false;
  if (d.schema_version !== "1.0.0" || d.product !== "StorageSnapshot" || d.domain !== "storage" || d.authority !== "FILESYSTEM_METADATA_OBSERVATION" || d.mode !== "READ_ONLY" || d.category !== "DECISION_PACKET_LOGS" || d.scope !== "DIRECT_CHILDREN_PATTERN" || d.pattern !== "decision_packets_*.jsonl") return false;
  const observed = utc(d.observed_at_utc), generated = utc(d.generated_at_utc);
  if (observed === null || generated === null || observed > generated || typeof d.source_status !== "string" || !statuses.includes(d.source_status) || typeof d.snapshot_age_s !== "number" || !Number.isFinite(d.snapshot_age_s) || d.snapshot_age_s < 0 || d.freshness_classification !== (d.snapshot_age_s > 90 ? "STALE" : "FRESH")) return false;
  if (d.source_status !== "PRESENT") return metrics.every(k => d[k] === null);
  if (!uint(d.entries_observed) || !uint(d.matched_file_count) || !uint(d.total_bytes) || d.entries_observed > 10000 || d.matched_file_count > d.entries_observed || typeof d.inventory_sha256 !== "string" || !/^[0-9a-f]{64}$/.test(d.inventory_sha256)) return false;
  const latest = utc(d.latest_file_modified_at_utc);
  return d.matched_file_count === 0 ? d.total_bytes === 0 && d.latest_file_modified_at_utc === null : latest !== null && latest <= observed;
}
export type StorageState = PassiveSnapshotState<StorageSnapshot>;
export const useStorage = (): StorageState => usePassiveSnapshot("/api/operator/v1/storage", validateStorageSnapshot, errors, "STORAGE");
