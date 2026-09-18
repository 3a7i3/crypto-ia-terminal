# PPL-02E-R3 — Legacy Compatibility & Scientific-Capital Handoff

Status: **SOURCE IMPLEMENTATION CANDIDATE**

Parent: #180  
Mission issue: #183  
Baseline: `main@0308fb4ac6f59b2c8f611b928141060ecbb5c1b3`

## 1. Purpose

R3 removes the remaining authority split that would exist if PPL owned PAPER
lifecycle truth while decision capital and restart still trusted
`paper_trades.jsonl`.

R3 does not promote PPL. It establishes the source contracts required before
R4 may implement cutover.

## 2. Scientific capital

### Legacy / SHADOW

Existing behavior is preserved:

`WALLET_PAPER_CAPITAL + SUM(legacy CLOSE.pnl_usd)`

### PPL authority

Scientific capital is:

`epoch.initial_virtual_capital + projection.realized_pnl`

The explicit source is:

- `PPL_AUTHORITY_STORE_ROOT`
- `PPL_AUTHORITY_EPOCH_ID`

No legacy JSONL or exchange fallback exists.

If replay fails, the epoch is not schema v2, or unresolved capital exists,
scientific capital raises `ScientificCapitalUnavailableError`.

UNKNOWN is never converted to zero.

## 3. Legacy restart

`MexcSimulator._restore_positions()` is disabled when its process-lifetime
authority is `PPL_AUTHORITY`.

Future restart state must be rebuilt from PPL R2 replay facts.

Legacy/SHADOW behavior remains unchanged.

## 4. PPL authority dataset gate

`validate_ppl_authority_dataset()` is read-only.

Mutation readiness requires:

- exact epoch load succeeds;
- deterministic PPL replay succeeds;
- schema v2;
- every open position is replay-complete;
- no unresolved capital.

It performs no remediation.

## 5. paper_trades.jsonl after cutover

The historical prefix remains immutable evidence.

Post-cutover rows are written only as compatibility/research projection:

`PPL -> project_ppl_to_legacy_jsonl() -> paper_trades.jsonl`

The projector:

- validates the PPL epoch first;
- requires replay-complete schema v2;
- never rewrites existing bytes;
- appends only missing rows;
- fsyncs appended rows;
- uses deterministic `projection_id`;
- preserves `paper_epoch_id` and `ppl_event_id`;
- refuses malformed/truncated target data.

## 6. Compatibility evidence honesty

Projected rows keep legacy reader schema 5 for compatibility and carry a
separate projection schema version.

Missing research metadata is not inferred.

Rows explicitly expose:

- `source_authority=PPL`
- `paper_epoch_id`
- `ppl_event_id`
- `projection_id`
- `projection_schema_version`
- `evidence_status`
- `missing_evidence_fields`

Where the legacy schema requires a display sentinel (for example score 0 or
regime "unknown"), `evidence_status=PARTIAL_METADATA` and
`missing_evidence_fields` make clear that the sentinel is not evidence.

## 7. CLOSE projection

Known CLOSE PnL is derived exclusively from durable PPL facts:

- side
- principal
- entry_price
- entry_fee
- exit_price
- exit_fee

For compatibility with the existing recorder:

- `pnl_usd` is net of entry/exit fees;
- `pnl_pct` retains the historical gross price-return convention.

A normal PPL CLOSE lacks a durable legacy reason/MAE/MFE; those remain marked
missing.

## 8. UNRESOLVED projection

`POSITION_UNRESOLVED` projects a compatibility CLOSE with:

- exit_price = null
- pnl_usd = null
- pnl_pct = null
- evidence_status = UNRESOLVED

No synthetic zero outcome is emitted.

## 9. Research-reader provenance

`PaperTradeRecorder.events()` and `trades()` preserve PPL compatibility
provenance fields when present.

Historical legacy rows continue to load with empty provenance fields.

## 10. Boundaries

R3 does not:

- make PPL authoritative;
- create/cut over an authority epoch;
- alter strategy/risk/sizing formulas beyond source selection;
- implement Financial Institute semantics;
- change LIVE execution;
- authorize F-00/burn-in.

R4 owns cutover, rollback, authority epoch creation, runtime wiring and WEB-02
authority adaptation.
