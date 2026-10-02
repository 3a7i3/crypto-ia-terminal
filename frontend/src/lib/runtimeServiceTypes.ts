export type RuntimeServiceSnapshot = {
  schema_version: "1.0.0";
  product: "RuntimeServiceSnapshot";
  domain: "runtime_service";
  authority: "HOST_SYSTEMD_OBSERVATION";
  mode: "READ_ONLY";
  generated_at_utc: string;
  observed_at_utc: string;
  host_id: string;
  service: {
    unit: "crypto-advisor.service";
    query_status: "OK" | "NOT_FOUND" | "TIMEOUT" | "COMMAND_UNAVAILABLE" | "COMMAND_FAILED" | "INVALID_PROPERTIES" | "OUTPUT_LIMIT";
    load_state: string | null;
    active_state: string | null;
    sub_state: string | null;
    main_pid: number | null;
    restart_count: number | null;
    exec_main_started_at_utc: string | null;
    invocation_id: string | null;
  };
  deployment: {
    status: "PRESENT" | "NOT_AVAILABLE";
    reason: string | null;
    source_code_sha: string | null;
    evidence_ref: string | null;
    observed_at_utc: string | null;
    artifact_sha256: string | null;
    host_id: string | null;
    invocation_id: string | null;
  };
  snapshot_age_s: number;
  freshness_classification: "FRESH" | "STALE";
};
