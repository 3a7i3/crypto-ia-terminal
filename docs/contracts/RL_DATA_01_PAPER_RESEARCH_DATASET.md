# RL-DATA-01 — PAPER → Research Dataset & Provenance Contract

Status: SOURCE CONTRACT V1 / implementation pending

Parent: #237  
Governance: #148  
Mission: #238  
Draft implementation PR: #243

Reference source baseline:

`main@98082ef01e8bef93f86fe5e4d1d2af48dddec53e`

Certified F00 experiment:

`F00-EPOCH-01-20260920T084335Z`

Final F00 verdict:

`F00_FINAL_SCIENTIFIC_EXPERIMENT_CERTIFIED`

---

## 1. Mission

RL-DATA-01 creates the canonical one-way scientific boundary from PAPER into
Research Lab.

The direction is strictly:

`PAPER FACTS → IMMUTABLE RESEARCH DATASET`

Never:

`RESEARCH → ACTIVE PAPER MUTATION`

Research may consume certified PAPER evidence, derive replay/diagnostic artifacts,
and produce hypotheses, but it never becomes a PAPER lifecycle authority.

This contract is intentionally fail-closed:

- missing evidence is represented;
- unresolved provenance is preserved;
- unavailable systems are not converted to empty datasets;
- no timestamp-only, cycle-only, symbol-only, or filename-date heuristic may
  promote a record into a certified F00 population.

---

## 2. Authority hierarchy

RL-DATA-01 distinguishes four source classes.

### 2.1 AUTHORITATIVE_CORE

Only these sources define the scientific PAPER boundary:

1. PPL durable F00 event stream;
2. F00 experiment manifest;
3. F00 experiment configuration freeze.

These sources define experiment identity and lifecycle facts.

### 2.2 DERIVED_CERTIFIED

Derived evidence may accompany the dataset but cannot override AUTHORITATIVE_CORE:

- FIN-01 deterministic financial interpretation;
- FIN-02 reconciliation certification;
- bounded Legacy compatibility projection when explicitly exported.

### 2.3 OPTIONAL_CERTIFIED

Optional evidence is admissible only when exact causal provenance is proven.

For F00 v1 this includes:

- the exact 13 DecisionPacket records selected by PPL OPEN packet IDs;
- the exact 13 DecisionIdentityJournal records selected through the certified
  packet → trace bridge.

### 2.4 EXPLICITLY_UNAVAILABLE_OR_UNBOUND

These sources are not silently dropped and not represented as zero:

- DIP: NOT_STARTED / NOT_AVAILABLE;
- Regret v2: UNRESOLVED_PROVENANCE;
- RejectionStore: UNBOUND;
- AdmissionLedger: UNBOUND.

Their status must appear explicitly in the Research manifest.

---

## 3. Two-level immutable identity model

A PAPER scientific boundary and a Research export artifact are not the same
identity.

RL-DATA-01 therefore defines two deterministic identifiers.

### 3.1 `source_boundary_id`

`source_boundary_id` identifies the authoritative PAPER scientific boundary.

It must be deterministically derived from a canonical JSON identity document
containing at minimum:

- identity schema version;
- `source_domain = PAPER`;
- `source_authority = PPL_AUTHORITY`;
- `paper_epoch_id`;
- `manifest_file_sha256`;
- `ppl_birth_code_sha`;
- `ppl_semantic_config_snapshot_hash`;
- `experiment_config_file_sha256`;
- `experiment_config_snapshot_sha256`;
- `experiment_runtime_source_sha`;
- `ppl_stream_sha256`;
- `source_event_count`;
- `source_first_sequence`;
- `source_last_sequence`;
- `legacy_boundary_sha256`;
- `legacy_event_count`.

Canonicalization rule:

```
UTF-8 JSON
sort_keys = true
separators = (",", ":")
no insignificant whitespace
SHA-256 over canonical bytes
```

The following MUST NOT participate in `source_boundary_id`:

- extraction timestamp;
- absolute VPS path;
- hostname;
- mutable live-journal SHA;
- file mtime;
- FIN-02 freshness/generated timestamp;
- invocation ID;
- process PID.

Those values are operational/extraction provenance, not scientific-boundary
identity.

### 3.2 `dataset_id`

`dataset_id` identifies one immutable Research export artifact.

It must be deterministically derived from a canonical dataset identity document
containing:

- dataset schema version;
- `derivation = PAPER_EXPORT`;
- `source_boundary_id`;
- exact ordered list of included Research components;
- canonical subset digest for each included component;
- record count for each included component;
- explicit component status;
- Research exporter code SHA.

Required behavior:

- same PAPER boundary + same included component bytes/semantics + same exporter
  code identity ⇒ same `dataset_id`;
- same PAPER boundary + changed optional component content ⇒ same
  `source_boundary_id`, different `dataset_id`;
- changed PPL source stream ⇒ different `source_boundary_id` and different
  `dataset_id`.

---

## 4. Certified F00 authoritative boundary

### 4.1 PPL event stream

Canonical physical source:

`databases/ppl_authority/store/epochs/9b265710c1d5ebe6ccaf8d301deafea6812e73cfa4c8ea1666714452f14fea8c.jsonl`

Certified properties:

- event count: 27;
- first sequence: 1;
- last sequence: 27;
- EPOCH_CREATED: 1;
- POSITION_OPENED: 13;
- POSITION_CLOSED: 13;
- POSITION_UNRESOLVED: 0;
- open residual: 0;
- unresolved residual: 0.

Certified SHA-256:

`50220fdfd4a75d219795db518d77ab6c6574883eb74a6a8db9e26a6d8cf729b2`

The exporter must preserve original event identities and event content. It must not
rewrite or normalize source facts into a semantically different event stream.

### 4.2 F00 experiment manifest

Canonical source:

`databases/ppl_authority/F00-EPOCH-01-20260920T084335Z.manifest.json`

Raw file SHA-256:

`1d7a3386b2eb2ec7a0f253500ecd2431379c45047698b33f84ae0e08644553af`

Certified semantic fields:

- `manifest_schema_version = 2`;
- `epoch_role = F00_EXPERIMENT`;
- `paper_epoch_id = F00-EPOCH-01-20260920T084335Z`;
- `created_at = 1789893816.0022893`;
- `initial_virtual_capital = 1000.0`;
- `code_sha = 11e955d15cd1ea7ef75988943c978f3eb3a8006b`;
- `config_snapshot_hash = 6a86a11b201778602eaa4575fbbdfde6dc253760b528cb79b72145d4ac417aae`;
- `legacy_boundary_sha256 = f44b2df8deb950cb2e026193f31d3089d27e5ee08d58dfda753e6041d3462f42`;
- `legacy_event_count = 2364`;
- `predecessor_authority_epoch_id = PPL02E-AUTH-002-20260919T055150Z`;
- `ppl_event_schema_version = 2`.

### 4.3 F00 experiment configuration freeze

Canonical source:

`databases/ppl_authority/F00-EPOCH-01-20260920T084335Z.experiment-config.json`

Raw file SHA-256:

`0054f00325aae069bc9a972851d4436a885bae73605f9b53a7d323a56170b35c`

Internal deterministic snapshot SHA-256:

`aa8c20e8acd1ad489da7572c6d35c2d5e37fcd265c0ef292035dbb2c8bbd83e6`

Frozen runtime source SHA:

`c8dae319442bf751336ff22fd7c6257bb6d69783`

Material parameter count:

`258`

Frozen prestart guard:

`PB_MAX_POSITIONS=0`

Frozen activation overlay:

- path:
  `databases/ppl_authority/F00-EPOCH-01-20260920T084335Z.admission.env`
- SHA-256:
  `0f33c91d5d14cdd5bd6a0845853c854dc5f3772fd74a29b288bc113888cb205e`
- frozen override:
  `PB_MAX_POSITIONS=2`.

### 4.4 Identity fields must remain distinct

The following identifiers are different concepts and MUST NOT be collapsed into
generic `source_sha` or `config_hash` fields:

1. `manifest_file_sha256`;
2. `ppl_birth_code_sha`;
3. `ppl_semantic_config_snapshot_hash`;
4. `experiment_config_file_sha256`;
5. `experiment_config_snapshot_sha256`;
6. `experiment_runtime_source_sha`;
7. `ppl_stream_sha256`;
8. `research_exporter_code_sha`.

---

## 5. Optional certified decision evidence

### 5.1 Canonical causal key

For the certified F00 OPEN population, source inspection and runtime evidence
prove:

`PPL POSITION_OPENED.decision_id == DecisionPacket.packet_id`

All 13 OPEN events carry a unique non-null `decision_id`.

Some CLOSE events carry `decision_id=None`. Those missing values are preserved
as missing. CLOSE remains lifecycle-linked to OPEN by exact `trade_id`.

No CLOSE decision ID is inferred.

### 5.2 DecisionPacket subset

Selection rule:

- collect the 13 PPL OPEN `decision_id` values;
- select DecisionPacket records by exact `packet_id` equality only;
- fail if any ID is missing or duplicated.

Certified F00 evidence:

- matched packet IDs: 13/13;
- missing: none;
- duplicates: none;
- all 13 carry non-empty `metadata.trace_id`.

Canonical Research subset SHA-256, computed from the 13 original DecisionPacket
records sorted by `packet_id` using canonical JSON:

`cab875c1a7313c028351edd42410f2e780ecb33e59f3c4e583d566ea8413c170`

Physical source shards:

#### 2026-09-20

`databases/decision_packets_2026-09-20.jsonl`

- matched F00 records: 2;
- total rows: 2793;
- bytes: 12516523;
- SHA-256:
  `59ca17c017ac7f4d35c7b99ff0a69f9b376ea7af4dd1ec5ad757539e4d3c70c8`.

#### 2026-09-21

`databases/decision_packets_2026-09-21.jsonl`

- matched F00 records: 7;
- total rows: 18972;
- bytes: 83706178;
- SHA-256:
  `59467a52681e376bdb87505f0c90ef8828938e967bf5d3555d371fb93f8464ac`.

#### 2026-09-22

`databases/decision_packets_2026-09-22.jsonl`

- matched F00 records: 4;
- total rows: 15453;
- bytes: 66811259;
- SHA-256:
  `a840d4ae31a0e9a0e2a50e0374a9612aecd6fbb17015f04d39b7a2ac4956c593`.

The physical shard hashes are extraction provenance. The canonical 13-record
subset digest identifies the optional Research component.

### 5.3 DecisionIdentityJournal bridge

Direct equality is invalid:

`PPL packet_id != DecisionIdentityJournal.decision_id`

Fresh audit result:

- direct PPL OPEN ID matches in DecisionIdentityJournal: 0/13.

The certified bridge is:

`PPL decision_id (= packet_id)`
→ `DecisionPacket.packet_id`
→ `DecisionPacket.metadata.trace_id`
→ `DecisionIdentityJournal.decision_id`

Fresh audit proved:

- packet matches: 13/13;
- unique trace IDs: 13;
- trace→journal matches: 13/13;
- missing: none;
- duplicates: none;
- symbol mismatch: 0;
- cycle mismatch: 0;
- journal bad JSON: 0;
- stored payload-digest failures: 0.

Canonical Research subset SHA-256 over the 13 original journal records sorted by
`decision_id`:

`98aab51a987c49c0f5cf6bd230de98363313bffed8becf2d861248d3579608c9`

The full live journal is append-only and continues to grow. Its whole-file SHA is
therefore extraction provenance only and MUST NOT participate in `dataset_id`.

Audit-time fingerprint:

- path:
  `databases/decision_identity_journal.jsonl`
- bytes:
  `87263259`
- SHA-256 at audit:
  `4a21711cc3116e9adca73b2e3a71c983db280ae8bd1a0cbe771e81a0ff78430d`.

---

## 6. Explicit unavailable and unresolved sources

### 6.1 DIP

Dataset status:

`NOT_AVAILABLE`

Reason:

`NOT_STARTED`

Certified evidence:

- no `dip.sqlite`, `dip.sqlite-*`, or other `*dip*.sqlite*` file existed
  under the project tree;
- no `DIP_*` environment override existed in the Advisor process;
- canonical S-03D runtime provenance snapshot exposed:

`{"status":"NOT_STARTED"}`

The Research export MUST NOT create an empty DIP dataset and MUST NOT initialize
DIP as a side effect.

### 6.2 Regret v2

Dataset status:

`UNRESOLVED_PROVENANCE`

Fresh source audit:

- records scanned: 524152;
- `experiment_id=None`: all;
- `source_authority=None`: all;
- `paper_epoch_id=None`: all;
- explicit F00 matches: 0.

No date/cycle/symbol attribution is allowed.

### 6.3 RejectionStore

Dataset status:

`UNBOUND`

Fresh source audit:

- records scanned: 1066814;
- `experiment_id=None`: all;
- explicit F00 experiment matches: 0.

Rejection records may later become Research-eligible only through a separately
certified exact packet provenance contract.

### 6.4 AdmissionLedger

Dataset status:

`UNBOUND`

Fresh source audit:

- records scanned: 19268;
- records carrying `experiment_id`: 0;
- `paper_epoch_id`: 0;
- `packet_id`: 0;
- `trace_id`: 0.

`cycle_id` is not globally unique and cannot certify F00 membership.

---

## 7. FIN semantics

FIN is derived financial interpretation, not PPL lifecycle authority.

Certified F00 references:

- FIN-01 source SHA:
  `c639ac397122929769be2a1ce7654e3a1bc24cfe`;
- deterministic certified FIN snapshot ID:
  `e7bc4f1c4c4fa7b32e58d03f565a252404546165371dce3bc10e9c12e7b142f5`;
- FIN-02 source SHA:
  `71fd89d7197164f4b9b45e8e497c753b771eddcf`;
- final reconciliation:
  `WITHIN_TOLERANCE`.

The mutable live file
`databases/financial_reconciliation_snapshot.json`
MUST NOT participate in `source_boundary_id` or `dataset_id`.

A future Research-owned financial derivative may be exported as a separate
component with its own deterministic digest.

---

## 8. Legacy compatibility semantics

The complete mixed `databases/paper_trades.jsonl` file is not the canonical F00
Research population.

Certified lineage:

- immutable historical prefix rows: 2364;
- historical prefix SHA-256:
  `f44b2df8deb950cb2e026193f31d3089d27e5ee08d58dfda753e6041d3462f42`;
- final compatibility rows: 2390;
- F00 downstream projection rows: 26;
- exact composition: 13 OPEN + 13 CLOSE;
- row equality with deterministic PPL compatibility projection: TRUE.

For v1, the manifest's Legacy boundary fingerprint/count is sufficient lineage.

If a Legacy projection is exported later, it must be a distinct DERIVED component
with an explicitly bounded deterministic digest.

---

## 9. Target physical layout

V1 logical layout:

```
research_data/
  datasets/
    <dataset_id>/
      manifest.json
      authoritative/
        ppl_events.jsonl
        f00_experiment_manifest.json
        f00_experiment_config.json
      optional/
        decision_packets.jsonl
        decision_identity_records.jsonl
```

The exporter MUST write only to Research-owned storage.

It MUST NOT write to:

- `databases/ppl_authority/`;
- `databases/paper_trades.jsonl`;
- DecisionPacket source shards;
- DecisionIdentityJournal;
- FIN runtime snapshots;
- DIP/Regret/Rejection/Admission source stores.

---

## 10. Manifest model

The Research manifest must contain at minimum:

### Identity

- `dataset_id`;
- `source_boundary_id`;
- `dataset_schema_version`;
- `derivation = PAPER_EXPORT`.

### Authority

- `source_domain = PAPER`;
- `source_authority = PPL_AUTHORITY`;
- `paper_epoch_id`.

### Authoritative source identities

- `manifest_file_sha256`;
- `ppl_birth_code_sha`;
- `ppl_semantic_config_snapshot_hash`;
- `experiment_config_file_sha256`;
- `experiment_config_snapshot_sha256`;
- `experiment_runtime_source_sha`;
- `ppl_stream_sha256`;
- PPL event count and sequence range;
- Legacy boundary SHA/count.

### Components

For every component:

- logical role;
- authority class;
- status;
- record count;
- canonical component digest when present;
- source references/fingerprints;
- selection rule;
- unresolved reason when applicable.

### Extraction provenance

Outside deterministic identity inputs:

- extraction timestamp UTC;
- logical/physical source paths;
- source sizes/counts;
- whole-file SHA at extraction when useful;
- exporter invocation information;
- exact exporter code SHA.

---

## 11. Completeness doctrine

Allowed component states include at minimum:

- `COMPLETE`;
- `PARTIAL`;
- `UNRESOLVED`;
- `UNRESOLVED_PROVENANCE`;
- `UNBOUND`;
- `NOT_AVAILABLE`;
- `NOT_STARTED`;
- `NOT_APPLICABLE`.

`UNKNOWN`, `UNRESOLVED`, `UNAVAILABLE`, and `NOT_APPLICABLE` are never
equivalent to numeric zero.

Overall dataset `completeness_status` is evaluated against the declared REQUIRED
v1 components.

For v1:

Required:
- PPL event stream;
- F00 experiment manifest;
- F00 experiment config.

Optional-certified:
- DecisionPacket subset;
- DecisionIdentityJournal subset.

Declared unavailable/unbound:
- DIP;
- Regret;
- RejectionStore;
- AdmissionLedger.

Therefore the dataset may be `COMPLETE` for its declared v1 scope while still
recording explicit optional-source limitations.

---

## 12. Deterministic export rules

The exporter must:

1. select exactly one PPL epoch;
2. load and validate the matching F00 manifest;
3. verify manifest epoch identity;
4. verify raw manifest SHA;
5. verify exact PPL stream SHA;
6. verify contiguous sequence range;
7. validate source event count;
8. load and validate the matching experiment-config freeze;
9. preserve all distinct code/config identities;
10. compute deterministic `source_boundary_id`;
11. optionally resolve F00 DecisionPackets by exact PPL OPEN packet IDs;
12. require exactly one DecisionPacket per selected packet ID;
13. resolve journal records only through DecisionPacket trace IDs;
14. verify DecisionIdentityJournal `payload_digest`;
15. compute canonical optional subset digests;
16. encode unavailable/unbound source states explicitly;
17. compute deterministic `dataset_id`;
18. write only to Research-owned storage.

The exporter must fail closed on:

- malformed JSON;
- truncated PPL;
- duplicate sequence;
- sequence gap;
- epoch mismatch;
- SHA mismatch;
- missing required authoritative artifact;
- DecisionPacket duplicate for a selected F00 packet;
- ambiguous trace bridge;
- journal payload-digest mismatch;
- attempted output overwrite with different bytes;
- source mutation detected during export.

---

## 13. Source-mutation guard

RL-DATA-01 must prove that export is non-perturbative.

At minimum, before and after export it must compare:

- authoritative PPL SHA;
- F00 manifest SHA;
- F00 experiment-config SHA;
- any source shard fingerprint consumed by the optional decision component.

Any source digest drift during one export invocation must fail the export.

Append-only live sources such as DecisionIdentityJournal require a bounded selection
model. Their whole-file digest may change after extraction; the exported subset
identity must remain deterministic.

---

## 14. Metric provenance contract

No Research metric is scientific unless it points to its population.

Derived metrics must include at minimum:

- `dataset_id`;
- `source_boundary_id`;
- `research_run_id`;
- strategy/candidate identity when applicable;
- Research code SHA;
- Research config hash;
- derivation/method;
- population filters;
- sample size;
- timestamp.

PAPER authority metrics and Research-derived metrics must never be implicitly
summed or merged.

---

## 15. Testing requirements

RL-DATA-01 source certification must prove:

1. exact F00 epoch selection;
2. deterministic `source_boundary_id`;
3. deterministic `dataset_id`;
4. exact authoritative SHA capture;
5. exact event-count/sequence boundary;
6. manifest/config semantic identity checks;
7. read-only source behavior;
8. deterministic re-export of identical boundary;
9. changed source boundary ⇒ changed IDs;
10. optional DecisionPacket 1:1 selection;
11. packet→trace→journal 1:1 bridge;
12. DecisionIdentity payload digest validation;
13. explicit NOT_STARTED/UNBOUND/UNRESOLVED states;
14. malformed/corrupt/truncated source fail-closed behavior;
15. tests use temporary isolated fixtures;
16. no active runtime/VPS deployment;
17. no source-file mutation.

---

## 16. Runtime and deployment boundary

This mission authorizes source development only.

It does NOT authorize:

- active VPS deployment of the Research exporter;
- PPL mutation;
- PAPER compatibility mutation;
- new PAPER epoch;
- F00 reopening;
- Watchdog activation;
- burn-in;
- TESTNET/LIVE;
- exchange writes;
- strategy/signal/risk/sizing changes;
- FIN-03 capital allocation.

Any future deployment must undergo a separate read-only/non-perturbation review.

---

## 17. Certified source-audit results

A1:

`RL_DATA_01_SOURCE_AUDIT_A1 = PASS_WITH_CONTRACT_REALIGNMENT_REQUIRED`

A2:

`RL_DATA_01_SOURCE_AUDIT_A2 = PASS`

A3.1:

`RL_DATA_01_A3_1_DECISION_BOUNDARY = PASS`

A3.2:

`RL_DATA_01_A3_2_PACKET_TRACE_JOURNAL = PASS`

A3.3:

`RL_DATA_01_A3_3_DIP = PASS_AS_NOT_STARTED`

A4:

`RL_DATA_01_A4_DECISION_EVIDENCE_FREEZE = PASS`

A5:

`RL_DATA_01_A5_V1_SOURCE_CONTRACT_SPECIFIED = PASS`

Overall source audit:

`RL_DATA_01_SOURCE_AUDIT_COMPLETE`

---

## 18. Target mission verdict

The implementation is not yet certified by this document.

After exporter implementation, tests, deterministic replay/export proof, and
source-mutation proof, the target verdict remains:

`RL_DATA_01_SOURCE_CERTIFIED`
