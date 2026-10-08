export interface AccountingSample {
  sequence: number;
  event_id: string;
  timestamp_utc: string;
  available_cash: string;
  realized_pnl: string;
  reserved_principal: string;
  unresolved_capital: string;
  fees_paid: string;
  open_positions: number;
}
export interface AccountingHistory {
  schema_version: 1;
  product: string;
  authority: string;
  unit: string;
  paper_epoch_id: string;
  source_generated_at_utc: string;
  source_snapshot_sha256: string;
  producer_source_sha: string;
  samples: AccountingSample[];
  last_sequence: number;
  snapshot_age_s: number;
  freshness_classification: "FRESH" | "STALE";
  allocation: null | {
    denominator: string;
    segments: { id: string; amount: string; share: string }[];
  };
}
const obj = (x: unknown): x is Record<string, unknown> =>
  typeof x === "object" && x !== null && !Array.isArray(x);
const amount = (x: unknown) =>
  typeof x === "string" &&
  x.length < 128 &&
  /^-?\d+(\.\d+)?([eE][+-]?\d+)?$/.test(x) &&
  Number.isFinite(Number(x));
const utc = (x: unknown): x is string =>
  typeof x === "string" &&
  /(Z|[+-]\d{2}:\d{2})$/.test(x) &&
  Number.isFinite(Date.parse(x));
export function validAccountingHistory(x: unknown): x is AccountingHistory {
  if (
    !obj(x) ||
    x.schema_version !== 1 ||
    x.product !== "PPLAccountingHistory" ||
    x.authority !== "DERIVED_OBSERVATION" ||
    x.unit !== "PAPER_ACCOUNT_UNIT" ||
    x.ppl_event_schema_version !== 2 ||
    x.checkpoint_verified !== false ||
    x.replay_validated !== true ||
    x.semantics !== "PPL_V2_FLOAT_PROJECTOR_REALIZED_NET_ENTRY_EXIT_FEES" ||
    typeof x.paper_epoch_id !== "string" ||
    !x.paper_epoch_id ||
    !utc(x.source_generated_at_utc) ||
    typeof x.snapshot_age_s !== "number" ||
    !Number.isFinite(x.snapshot_age_s) ||
    x.snapshot_age_s < 0 ||
    !["FRESH", "STALE"].includes(String(x.freshness_classification))
  )
    return false;
  for (const [key, len] of [
    ["source_snapshot_sha256", 64],
    ["source_manifest_sha256", 64],
    ["producer_source_sha", 40],
    ["epoch_code_sha", 40],
    ["config_snapshot_hash", 64],
  ] as const) {
    if (
      typeof x[key] !== "string" ||
      !new RegExp(`^[0-9a-f]{${len}}$`).test(x[key] as string)
    )
      return false;
  }
  if (
    !Array.isArray(x.samples) ||
    x.samples.length < 1 ||
    x.samples.length > 1000 ||
    x.last_sequence !== x.samples.length
  )
    return false;
  const ids = new Set<string>();
  let prev = -Infinity;
  for (let i = 0; i < x.samples.length; i++) {
    const s: unknown = x.samples[i];
    if (
      !obj(s) ||
      s.sequence !== i + 1 ||
      typeof s.event_id !== "string" ||
      !s.event_id ||
      ids.has(s.event_id) ||
      !utc(s.timestamp_utc)
    )
      return false;
    ids.add(s.event_id);
    const time = Date.parse(s.timestamp_utc);
    if (time < prev || time > Date.parse(x.source_generated_at_utc))
      return false;
    prev = time;
    for (const k of [
      "available_cash",
      "realized_pnl",
      "reserved_principal",
      "unresolved_capital",
      "fees_paid",
    ])
      if (!amount(s[k]) || (k !== "realized_pnl" && Number(s[k]) < 0))
        return false;
    if (!Number.isInteger(s.open_positions) || Number(s.open_positions) < 0)
      return false;
  }
  if (x.allocation !== null) {
    const a = x.allocation;
    if (
      !obj(a) ||
      !amount(a.denominator) ||
      Number(a.denominator) <= 0 ||
      a.definition !== "AVAILABLE_PLUS_RESERVED_PLUS_UNRESOLVED_AT_COST" ||
      !Array.isArray(a.segments) ||
      a.segments.length !== 3
    )
      return false;
    let total = 0,
      shares = 0;
    for (let i = 0; i < 3; i++) {
      const s: unknown = a.segments[i];
      if (
        !obj(s) ||
        s.id !==
          ["available_cash", "reserved_principal", "unresolved_capital"][i] ||
        !amount(s.amount) ||
        Number(s.amount) < 0 ||
        !amount(s.share) ||
        Number(s.share) < 0 ||
        Number(s.share) > 1
      )
        return false;
      const last = x.samples[x.samples.length - 1];
      if (
        !obj(last) ||
        Number(last[String(s.id)]) !== Number(s.amount) ||
        Math.abs(Number(s.share) - Number(s.amount) / Number(a.denominator)) >
          1e-10
      )
        return false;
      total += Number(s.amount);
      shares += Number(s.share);
    }
    if (
      Math.abs(total - Number(a.denominator)) >
        Math.max(1, Number(a.denominator)) * 1e-10 ||
      Math.abs(shares - 1) > 1e-10
    )
      return false;
  }
  return true;
}
