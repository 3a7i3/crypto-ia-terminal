# PAPER-STRESS #404 — D1 governed decision / rejection / admission capture

**Status**: `SOURCE_DESIGN_ONLY / TESTED_ON_SYNTHETIC_FIXTURES / PRODUCTION_CAPTURE_NOT_EXECUTED`.

**Constitution**: #282 remains an active PAPER burn-in; #286 immutability guard remains active. No Advisor restart/deploy, no live PPL/FIN read from the restricted MCP identity, no change to risk/sizing/positions/epoch, no Research feedback, no PAPER-STRESS runtime GO.

## 1. Source inventory and what is actually missing

The O4 and O6-B Research copies passed the real-byte D0 component integrity checks on the VPS and an independent 32-open-event causal identity audit. They do not contain all decisions rejected before PPL OPEN and are **not** a complete candidate population. The official `research_replay.validate_dataset` replay remains a separate, unexecuted gate in this mission.

At source revision `main@2015a88f10c31e3379b569f864696d62c282b0f0`:

| Producer | Source record | Join capability | Known limitation |
|---|---|---|---|
| DecisionPackets | `databases/decision_packets_YYYY-MM-DD.jsonl` | `packet_id`, `metadata.trace_id`, cycle and symbol | O6-B intentionally selects packets for 32 PPL OPEN only; raw full decision shards require separately governed capture |
| DecisionIdentityJournal | `databases/decision_identity_journal.jsonl` | identity `decision_id` (trace), symbol and cycle | historical O6-B contains 32 matched records, not the whole decision stream |
| AdmissionLedger | `databases/admission_ledger.jsonl` | `ADMISSION_ATTEMPT` / `ADMISSION_OUTCOME` joined by `attempt_id` | v1 lacks native `paper_epoch_id`, packet `decision_id`, `trace_id`; tolerant `.events()` drops malformed records; `.pairs()` overwrites duplicate IDs |
| RejectionStore | `databases/rejections/rejections_YYYY-MM-DD.jsonl` (source default) | `observation_id`, `packet_id`, optional `trace_id`, blockers and timestamp | different coverage from gate CSV; epoch binding, all-signal denominator and actual historical presence must be separately proved |
| Gate rejections CSV | `databases/gate_rejections.csv` | gate-only context | **supplementary**, not a complete independent RejectionStore nor a proxy for all decisions |

These are **source-code configured names**, not new assertions about VPS file existence, permissions, windows or integrity.

## 2. Two distinct, gated operations

1. **Operator snapshot (not yet performed)**: an authorized operator, separately and explicitly, makes *bounded, byte-stable Research copies* of the four kinds of producer records under a dedicated Research root. Capture the file-level raw SHA256, size, start/end boundary offsets, acquisition timestamp, selected closed UTC interval, source code/config/epoch identity and any rotation gaps **without silently treating live mutable files as stable**. No restart, mutation of the original producer, or reconfiguration. Never grant `chatgpt-ro` entry to `/home/mathieu`. Keep secrets out of the share, do not publish raw trading data to GitHub. A read-only snapshot can be performed only after reviewing the actual locations and an operator-specific source inventory; current #404 work **does not execute this step**.
2. **Research-only offline capture**: once the pre-staged immutable source bytes are independently authorized, run `research_data/stress_d1_capture.py` with *explicit* `--input-root`, `--request`, `--output-root`. The tool never discovers producer paths. It recomputes declared file digests, validates strict JSONL, counts join gaps and duplicates, and emits a new content-addressed **provisional** Research bundle. A manifest **claim** about epoch/config or completeness is not external proof.

Do not treat a provisional bundle as completed full-population data. Do not treat one time interval as a complete epoch. Data disclosure must be limited to the Research custodian and a small review team; source paths and raw payloads are never embedded in issues or PRs.

## 3. Request format (for authorized pre-staged immutable Research data only)

```json
{
  "schema_version": "PAPER_STRESS_D1_CAPTURE_REQUEST_V1",
  "source_class": "PRESTAGED_IMMUTABLE_RESEARCH_COPY",
  "paper_epoch_id": "BURN-IN-EPOCH-01-20260926T064144Z",
  "source_boundary_id": "d60d1b73e48d2ff567e62469b96df0799c9711ffc90bd3f24697f17b5d6ac78e",
  "runtime_source_sha": "116634be0d3c015cce1cfa58be7da7255414fbfd",
  "experiment_config_sha256": "9d9de1af4ac5aa5afc030ff64b08eeada0e1388a5d87c6475cb39c042be230d4",
  "window_start_utc": "2026-10-01T00:00:00Z",
  "window_end_utc": "2026-10-02T00:00:00Z",
  "sources": [
    {"kind": "decision_packets", "path": "decision_packets.jsonl", "sha256": "<actual SHA256>"},
    {"kind": "decision_identity_records", "path": "decision_identity_records.jsonl", "sha256": "<actual SHA256>"},
    {"kind": "admission_ledger", "path": "admission_ledger.jsonl", "sha256": "<actual SHA256>"},
    {"kind": "rejection_store", "path": "rejection_store.jsonl", "sha256": "<actual SHA256>"}
  ]
}
```

**This is a schema example, not a real snapshot manifest.** Never substitute fake SHA256 values or extrapolate October 1 coverage to current records. The four files must exist **inside the Research staging root**; output must be a separate Research directory. For multi-shard input, add multiple explicit entries for the same `kind` with distinct paths and measured hashes. The offline tool is bounded to 64 shards and 512 MiB total, so split by UTC day as needed.

Example command, **only after governed staging and review**:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -I -B -m research_data.stress_d1_capture \
  --input-root /path/to/research_audit/d1_staging \
  --request /path/to/research_audit/d1_staging/capture_request.json \
  --output-root /path/to/separate/research_d1_outputs
```

`python -I` excludes ambient module lookup; execute from a separately certified package install or explicitly audited isolated Research module path. **Do not use or modify the production runtime checkout to run it.**

## 4. Independent coverage certification remains a separate gate

The provisional manifest reports `records_by_kind`, matching packet trace identities, duplicate IDs, missing/orphan admission outcomes, rejection observation IDs, native epoch/decision ID presence and causal timestamp coverage. Even if `structural_status=CONSISTENT_SUBSET_ONLY`, it still emits:

- `complete_decisions_rejections_admissions=NOT_PROVEN`;
- `independent_producer_denominator=NOT_PROVEN`;
- `epoch_binding=NOT_PROVEN_BY_SOURCE_ATTESTATION_ALONE`;
- `counterfactual_performance_eligibility=NOT_PROVEN`;
- `counterfactual_go=false`.

A legitimate D1 certification later requires external evidence of the expected full decision cycle universe and source file rotations (including upstream exits before Packet creation), immutable PPL epoch/config/clock binding, source-traced rejection and admission linkage, gaps and truncation tests, and independently reviewed reconciliation. It cannot be manufactured by joining a rejected record to a trade based on symbol/timestamp alone.

D2 still requires synchronized executable market price/quote/depth paths; D3 needs a validated 4–5-slot path-dependent portfolio counterfactual, with paired replay and OOS analysis. Neither is authorized by this source PR.

## 5. Review / testing

- Only stdlib; no runtime imports, exchange, network, database discovery or service control.
- Tests run against synthetic temporary directories, verify fail-closed SHA/path/JSON rules and mismatch reporting.
- Reviewable Research-owned module and tests are not a production export nor a certified real dataset.
- No merge or deployment until explicit operator approval and independent review; #286 remains active.

**Security boundary:** the standalone tool rejects input roots not explicitly below a `research_audit` directory (or the named synthetic-only test fixture root). This string-bound source guard is a defense-in-depth convention, **not an operating-system sandbox**: real operator custody, Unix permissions and review are still mandatory. The output is content-addressed and chmod read-only, not a WORM/immutable-filesystem guarantee.

## 6. Operator-observed producer inventory — 2026-10-11 UTC

The operator reported **file metadata only**, not file contents, signed fingerprints, row counts or immutable copies. Treat this as observed filenames/sizes/times, not certified D1 producer continuity.

- `RejectionStore`: dated shards were reported from 2026-08-18 through 2026-10-11 (latest file is mutable/current and must not be treated as closed).
- `DecisionPackets`: dated shards were reported from 2026-10-03 through 2026-10-11; no 2026-09-26 through 2026-10-02 shard appears in this operator inventory. This does **not** establish irreversible loss: separate Research snapshots/backups/archive custody must be checked before making such a claim.
- `CycleData`: the dated 2026-10-10 shard was reported; no independent producer-cycle completeness denominator was provided.
- `AdmissionLedger` and `DecisionIdentityJournal`: the **latest operator message does not include their stat lines**. They were observed in earlier terminal output, but their size/stability and bounded-capture status must be reconfirmed independently.

At `main@2015a88f`, `scripts/rotate_jsonl.sh` sets `KEEP_DAYS=7` by default and purges date-stamped DecisionPacket and CycleData shards before the cutoff. This creates a serious survivorship risk for full-epoch candidate reconstruction. The longer RejectionStore history is **not** proof of corresponding DecisionPackets or of a full denominator.

### First bounded candidate window (design only, not yet captured)

Use a *closed and previously completed* UTC day, initially `[2026-10-10T00:00:00Z, 2026-10-11T00:00:00Z)`, subject to independent producer checks. The operator's inventory reports:
- `decision_packets_2026-10-10.jsonl`: 49,070,630 bytes.
- `rejections_2026-10-10.jsonl`: 8,093,279 bytes.
- The corresponding admission/identity material is **not a pair of dated files**. Their stable source prefix and exactly bounded temporal subset would need separately governed, read-only capture with the original prefix length/hash, per-row source offsets, timestamps and complete join status.

Important exporter limitation: `stress_d1_capture.py` takes complete pre-staged JSONL shards; it **does not extract records by UTC range**. Simply feeding a full cumulative IdentityJournal or AdmissionLedger that contains other dates will report `EVENT_OUTSIDE_DECLARED_WINDOW` and must not be promoted into a consistent window. The staging process must establish integrity and range membership **before** offline capture, never silently truncate, skip malformed lines or infer missing outcomes as zero.

The O4/O6-B prefix `source_boundary_id=d60d1b...78e` refers to the **2026-10-01 historical PPL boundary**; it must not be represented as newly certified 2026-10-10 PPL authority. A new time-scoped custody/boundary attestation requires its own evidence chain. An unsigned request field is merely a claim.

### Gate before any operator snapshot

1. Read-only, bounded inventory for the missing pre-October DecisionPacket archives and independent cycle-denominator sources; explicitly label archived versus absent.
2. Confirm metadata (size, last modification, expected format and ownership) of cumulative AdmissionLedger and DecisionIdentityJournal. Do not print raw records, secrets or broad log contents.
3. Agree on the **one-day window** and output custody. Snapshot only the exact allowlisted producer files, in a separate Research-only location using a designated operator; the restricted MCP never gets production-directory access.
4. For append-only mutable inputs, record a byte-stable prefix and original file SHA / prefix SHA, validate newline boundaries, preserve offsets and prove a bounded subset against the parent prefix. If proof cannot be established, mark the component `UNKNOWN`.
5. Only after those conditions, run the offline D1 tool, and expect `PROVISIONAL_ONLY` until the independent denominator, origin epoch and causal joins have been certified.

**No full-burn-in D1 certification, no counterfactual 4/5-position simulation, no runtime operation and no change to freeze #286 follows from this inventory.**
