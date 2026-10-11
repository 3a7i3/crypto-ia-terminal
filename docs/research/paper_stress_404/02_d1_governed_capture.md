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
  --input-root /path/to/approved/research_d1_staging \
  --request /path/to/approved/research_d1_staging/capture_request.json \
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