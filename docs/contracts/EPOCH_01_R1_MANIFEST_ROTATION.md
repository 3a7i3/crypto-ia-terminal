# EPOCH-01-R1 — F00 Experiment Manifest & Authority Epoch Rotation

Status: **SOURCE IMPLEMENTATION CANDIDATE**

Parent: #219  
Mission: #220  
Baseline: `main@c3de51f6269ec71e8a5e1f7a71b9484249ed7e60`

## Purpose

EPOCH-01 must be a truthful scientific experiment boundary, not another
PPL-02E authority-transition epoch.

The existing PPL authority implementation remains the lifecycle engine, but
its manifest semantics are extended so a stopped authoritative PPL runtime can
rotate from a transition epoch into a distinct F00 experiment epoch without
rewriting predecessor evidence.

This source change does not create EPOCH-01 on the VPS and does not authorize
PAPER admissions.

## Backward compatibility

PPL-02E transition manifests remain manifest schema v1:

- `epoch_role=PPL_AUTHORITY_TRANSITION`;
- `predecessor_shadow_epoch_id`;
- PPL event schema v2;
- event-identity domain `PPL-02E-R4-AUTHORITY-V1`;
- event-id prefix `ppl02e-`.

Their serialized field set remains unchanged. Existing transition manifests,
including the certified AUTH-002 manifest, must continue to load without
migration or rewrite.

## F00 experiment manifest

F00 experiment manifests use manifest schema v2:

- `epoch_role=F00_EXPERIMENT`;
- `predecessor_authority_epoch_id`;
- PPL event schema v2;
- event-identity domain `F00-EPOCH-AUTHORITY-V1`;
- event-id prefix `f00-`.

The predecessor authority id is mandatory and must differ from the new
experiment epoch id. A F00 manifest may not carry SHADOW-predecessor semantics.

The manifest also preserves the existing authority identity fields:

- `paper_epoch_id`;
- `created_at`;
- `initial_virtual_capital`;
- `code_sha`;
- `config_snapshot_hash`;
- `legacy_boundary_sha256`;
- `legacy_event_count`;
- `ppl_event_schema_version`.

## Rotation boundary

A F00 experiment manifest may be constructed only from an explicit stopped,
quiescent authority boundary:

- authority process stopped;
- zero authoritative open positions;
- zero pending orders;
- zero lifecycle transitions in flight.

The builder is explicit. Restart, deploy and pull do not create a new
experiment manifest.

## Runtime bootstrap

`PPL_AUTHORITY` continues to require:

- `PPL_AUTHORITY_MANIFEST`;
- `PPL_AUTHORITY_STORE_ROOT`;
- `PPL_AUTHORITY_EPOCH_ID`.

The configured epoch id must exactly equal the manifest epoch id.

The runtime loads either:

1. a schema-v1 `PPL_AUTHORITY_TRANSITION` manifest; or
2. a schema-v2 `F00_EXPERIMENT` manifest.

Any other role/schema combination fails closed.

For a new F00 epoch, explicit `bind()` creates exactly one schema-v2
`EPOCH_CREATED`. Restart replays the same event and must not create a second
birth event.

## Predecessor immutability

Rotating into F00 creates a new durable epoch namespace.

The predecessor authority epoch:

- is not copied;
- is not rewritten;
- is not relabeled;
- remains independently replayable;
- remains historical authority evidence for its own boundary.

The compatibility/Legacy corpus is fingerprinted in the new manifest but is
not imported into the F00 durable event stream.

## Scientific population

F00-DATA-01 remains the scientific population contract.

Under `PPL_AUTHORITY`:

- only rows with `source_authority=PPL`;
- and exact `paper_epoch_id=PPL_AUTHORITY_EPOCH_ID`;

enter the canonical realized-trade population.

Prior Legacy rows and prior PPL epochs remain excluded. The new epoch's
`initial_virtual_capital` is the drawdown/ROI baseline. No numeric fallback
to Legacy or exchange capital is introduced here.

## Failure semantics

- malformed manifest: fail closed;
- unsupported manifest role/schema: fail closed;
- partial predecessor provenance: fail closed;
- configured epoch mismatch: fail closed;
- missing PPL store/manifest/epoch config: fail closed;
- no automatic Legacy fallback.

## Runtime boundaries

This mission does not:

- create production EPOCH-01;
- modify AUTH-002 bytes;
- rewrite `paper_trades.jsonl`;
- change strategy/signal/risk/sizing;
- change `PB_MAX_POSITIONS=0`;
- start Advisor or Watchdog;
- open PAPER admissions;
- start F-00 measurement;
- authorize burn-in, TESTNET or LIVE.

## Source exit

Required source verdict:

`EPOCH_01_MANIFEST_ROTATION_SOURCE_CERTIFIED`

After merge/deployment, EPOCH-01 preparation must be recalculated on the new
exact source SHA before any production manifest or durable epoch bytes are
created.
