# Governed early termination — preparation only

Target `BURN-IN-EPOCH-01-20260926T064144Z`.
**NOT EXECUTED. Runtime activation is BLOCKED by this mission's constraints.**
No production command is supplied for deployment, systemd, Advisor restart,
exchange access, epoch rotation or modification of PB_MAX_POSITIONS.

## Gate S — source review

Review the [contract/audit](../contracts/PPL_BURNIN_EARLY_TERMINATION.md), isolated
branch and draft PR at its exact HEAD. Confirm tests, CI, immutable epoch/config/
capital, unchanged PPL authority and no automatic merge/deploy. Record exceptions
and stopping rationale in a GitHub decision. Review the fixed DENY behavior:
installing this candidate closes admission even without a receipt.

The historic source SHA is not upgraded by a source merge. Runtime #286 remains
protected. READY_FOR_REVIEW means source may be reviewed; it does not mean a
production drainage or scientific closure has occurred.

## Gate O — distinct future runtime authorization

Before any runtime action, obtain a decision explicitly identifying operator,
reviewed source SHA, exact scope, permitted installation/activation mechanism,
maintenance/stop permissions, target epoch, unchanged experiment config hash
`9d9de1af4ac5aa5afc030ff64b08eeada0e1388a5d87c6475cb39c042be230d4`,
capital, manifests, authority PPL, and rollback limitations.

Establish fresh writer/process provenance, permissions, single authority writer,
store filesystem/lock durability, pending order count and transitions in flight.
Prove legacy fallback, stale binaries and any direct writers cannot create PPL
facts. Archive source files and stream hashes without modifying them. Count
unknown values as UNKNOWN. Preserve baseline and admission-boundary timestamps.

**Stop here under the current mission.** The old running Python process cannot
apply this source fence without an independently authorized runtime change.
Do not write a receipt under the baseline and label the machine fenced. Do not
attempt hot patches or alter PB_MAX_POSITIONS/config to bypass this gate.

## Governed boundary receipt — future authorized operator only

After proved installation of the reviewed fence, capture a read-only canonical
PPL stream boundary under stable writer conditions. Validate contiguous sequence,
canonical bytes, epoch birth/code/config/capital and deterministic projection.
Record exact last sequence and SHA-256 over the canonical JSONL bytes.

The explicit API is `DurableEventStore(approved_root).seal_burn_in_admission` with
`expected_sequence`, `expected_stream_sha256`, `decision_url`, `operator`, and
`decided_at` (UTC Z). All inputs must come from fresh evidence and the actual
approval; never from example fixture values. The API's lock protects the compare
and receipt creation. A concurrent CLOSE can stale the supplied boundary:
recapture and retry only if no receipt exists. Preserve existing receipts.

Archive receipt bytes/hash and reviewed executable SHA in GitHub. Verify the
receipt is durable and report its boundary separately from the later terminal
boundary. A partial/sync failure is not a success; preserve evidence and keep
admission closed. No ALLOW transition or receipt deletion rollback exists.

## Drain existing positions

Permit original TP/SL/TIMEOUT paths using original durable terms and existing
fees; no altered thresholds, sizing, capital, synthetic prices or fabricated
CLOSE. New MARKET orders must be REJECTED without debit; LIMIT/STOP_LIMIT retain
their existing fail-closed behavior. Drain is asynchronous, without a promised
deadline. For stale market data or stalled CLOSE, escalate with evidence rather
than manufacturing a terminal outcome.

Capture repeated read-only boundaries and verify no new OPEN event IDs or count
increase, sequence continuity, no duplicates/collisions, PPL states and downstream
compatibility lag. An exact OPEN retry is ALREADY_EXISTS, not a new admission.
Record outstanding pending orders/transitions; a receipt alone does not count
or cancel them. Under PPL authority pending LIMIT/STOP_LIMIT are not admitted,
but actual runtime state must still be checked.

At an independently authorized restart, replay original positions/deadlines;
expired recovery records UNRESOLVED, never a invented CLOSE or zero PnL. No
restart is authorized in this mission. Drain completion requires zero OPEN;
UNRESOLVED remains explicit and prevents declaring all capital realized.

## Reconcile PPL / FIN offline

From the same immutable captured source boundary:

1. `project(events)` determines lifecycle truth; preserve CLOSED and UNRESOLVED
   counts and trade identities. Match receipt prefix bytes/digest to the final
   stream and account for every suffix event. No new OPEN suffix permitted.
2. Build FIN using explicit FinancialContext, funding evidence, valuation marks,
   valuation_as_of and maximum age. Never enable FIN-02 runtime as a side effect.
3. Run `financial_institute.recovery.certify_recovery_replay` with the captured
   store root and epoch, fixed context/observations/time. Archive source/state/
   plan hashes and exact financial snapshot equivalence between instances.
4. Reconcile initial capital, available cash, reserved principal, entry/exit fees,
   realized PnL and unresolved principal. Compare lifecycle IDs, fee debits once,
   principal release once and FIN reconciliation checks. Missing marks/outcomes
   remain UNKNOWN; no invented zero, backfill or capital adjustment.
5. Report compatibility artifacts as downstream projections; they cannot repair
   PPL truth. Record mismatch/lag separately and block final closure on unexplained
   discrepancy. A read-only FIN proof is not FIN runtime activation.

Use exact decimal financial values and existing FIN semantics. Do not derive
financial authority from frontend counters or simulator legacy balances.

## Final Research capture and closure

A drained stream is not yet a final quiescent boundary. Existing
`BurnInQuiescence` requires authority process stopped, pending_order_count=0
and lifecycle_transitions_in_flight=0. Process stop and any subsequent operations
need their own operator authorization. **Do not set these fields to satisfy a
validator without observed proof.** While stop is not authorized, finalization
remains BLOCKED; an intermediate immutable export can be labeled intermediate.

Once independently proven terminal and quiescent, capture bytes, last sequence,
event counts, receipt prefix and epoch/manifest/config hashes. Verify unchanged
source boundaries before and after extraction. Use existing PAPER exporter
(`scripts/rl_data_01_export.py`; inspect its help and accepted burn-in source
arguments), burn-in manifest/config provenance and optional-component completeness.
Create new content-addressed datasets outside runtime roots; never overwrite
an export or rewrite historical events.

Run `research_data.burn_in_finalization.designate_final_burn_in_dataset` only on
the validated immutable burn-in dataset and actual quiescence evidence. Archive
`dataset_id`, `source_boundary_id`, designation identity/hash, population CLOSED/
UNRESOLVED/OPEN, extraction time, code/config provenance and completeness. Preserve
UNRESOLVED in replay/diagnostics, with uncertainty and early stopping bias.
Research remains non-authoritative and produces no feedback to the same epoch.

GitHub closure decision must link receipt, final boundary, FIN proof, immutable
Research designation, replay/diagnostics and limitations. #286 is not lifted by
this source PR, zero OPEN, a receipt or an unreviewed green test run.

## Rollback

Before production adoption: discard/revert the isolated source proposal through
review; production is unchanged. Never merge or deploy automatically.

After adoption: maintain DENY and existing CLOSE/recovery capability. Do not run
the old baseline against this epoch as an automatic rollback: it can admit new
OPEN and invalidate the terminal boundary. A receipt does not stop an old binary.
Use a separately reviewed corrective version retaining the fixed epoch fence.
Restore backups only into isolated forensic roots; validate hashes and replay.
Never restore a stale PPL prefix over current history, delete receipts/events,
release unresolved capital or switch to legacy authority. If executable recovery
is necessary, obtain a separate bounded maintenance decision and preserve current
facts first. Existing `BLOCKED_RECONCILIATION_REQUIRED` semantics remain in force.
A source rollback and admission reopening are different decisions; reopening this
population has no implementation path and is outside this mission.

## Future PAPER_STRESS_RESEARCH

See [inactive proposal](../plans/PAPER_STRESS_RESEARCH_PREPARATION.json).
This is a proposed experiment name, not a supported runtime epoch_role. Existing
manifest parser supports its existing roles only; no new runtime role is added.
Do not pass the proposal to any builder, bind(), environment or configuration.

Prepare a distinct future protocol: preregister hypothesis, independent epoch ID,
PPL authority, capital source, reviewed code/config manifests, explicit PAPER-only
mode, stress scenarios, risk/sizing/position-limit decision, sample/stopping rules,
cost/funding assumptions, UNKNOWN handling, data completeness, immutable export,
FIN replay, admission and rollback gates. Do not inherit burn-in approval or funds,
change PB_MAX_POSITIONS here, or promote Research recommendations automatically.
Activation remains unapproved until scientific closure and its own creation gate.
