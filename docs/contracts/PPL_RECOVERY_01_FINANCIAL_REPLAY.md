# PPL-RECOVERY-01 — Financial/PPL Restart & Replay Determinism

Status: **SOURCE IMPLEMENTATION CANDIDATE**

Mission: #246  
Parent architecture: #150  
Governance: #148  
Dependency: #245 FIN-01  
Baseline: `main@b3cb2fe206f621445323f0a9287d3da902a07d0a`

## 1. Mission

Certify that authoritative PAPER lifecycle truth and its Financial Institute
projection survive restart/replay without duplication, silent repair or
financial drift.

Target verdict:

`PPL_FINANCIAL_RECOVERY_REPLAY_CERTIFIED`

## 2. Authority boundary

PPL remains authoritative for lifecycle facts.

FIN remains a deterministic financial interpretation of durable PPL facts.

Recovery must never:
- rebuild missing PPL facts from current runtime configuration;
- reconstruct unknown outcomes as zero;
- release reserved principal twice;
- charge fees twice;
- duplicate realized PnL;
- silently repair durable bytes;
- mutate active F00 strategy/risk/sizing/execution.

## 3. Source certification architecture

Canonical source proof:

```text
DurableEventStore instance A
        ↓ load_epoch
PPL project
        ↓
restart recovery plan
        ↓
FIN snapshot
        │
        │ independent process-equivalent reconstruction
        ↓
DurableEventStore instance B
        ↓ load_epoch
PPL project
        ↓
restart recovery plan
        ↓
FIN snapshot
```

The two projections must match exactly when their explicit inputs match.

## 4. Explicit inputs

Replay certification receives explicitly:
- durable store root;
- paper_epoch_id;
- FinancialContext;
- valuation observations;
- valuation_as_of;
- maximum mark age;
- restart_now.

No wall clock, exchange API, environment lookup or randomness is allowed in
the source certificate.

## 5. Replay identity

The source certificate binds:
- complete PPL source stream digest;
- event count;
- last source sequence;
- complete PPL state digest;
- restart recovery plan digest;
- FIN snapshot id;
- canonical FIN financial-state digest.

The PPL state digest includes:
- epoch id;
- epoch created_at;
- initial capital;
- source code SHA;
- config hash;
- epoch status/schema;
- cash;
- reserved principal;
- unresolved capital;
- realized PnL;
- fees;
- open positions and replay deadlines;
- unresolved positions;
- closed trade ids;
- seen event ids;
- recovery counters;
- last sequence.

## 6. Restart semantics

### Open position inside monitoring window

A fresh `PPLAuthorityRuntime` instance must replay the same durable state
without appending a lifecycle event.

### Timeout due but still recoverable

Restart disposition is
`RESTORE_TIMEOUT_DUE`.

Planning itself does not mutate PPL.

### Recovery window expired

Restart disposition is
`UNRESOLVED_REQUIRED`.

The authoritative runtime may then append exactly one
`POSITION_UNRESOLVED` durable event.

A subsequent restart must not append another unresolved event or release the
same principal again.

## 7. Close idempotence

A retry of the exact same durable CLOSE event must return
`ALREADY_EXISTS`.

Replay after process restart must preserve exactly one:
- principal release;
- exit fee;
- realized price PnL;
- realized net PnL.

Replay is reconstruction, not a second financial application.

## 8. Funding and attribution

Current FIN-01 PAPER model does not contain a generic funding cashflow stream.

When funding is explicitly certified NOT_APPLICABLE, the exact certified
funding evidence reference must survive restart unchanged.

Strategy/version/experiment attribution is explicit FinancialContext evidence
and must reproduce identically under identical replay inputs.

## 9. Unresolved evidence

A durable `POSITION_UNRESOLVED` must survive restart as unresolved capital.

It must not become:
- available cash;
- realized PnL;
- certified economic equity.

`RECOVERY_COMPLETED` may change source provenance/recovery counters but is
not itself a financial posting.

## 10. Failure isolation

Two failure boundaries are certified source-side.

### Invalid PPL lifecycle projection

A semantically invalid prospective lifecycle event must fail before the
durable append boundary.

The authoritative PPL bytes remain byte-identical.

### FIN projection failure

A valuation or Financial Institute projection failure occurs strictly
downstream of PPL facts.

It must not modify the PPL durable store.

## 11. Different explicit inputs are not replay drift

Determinism means:

same durable PPL facts + same explicit context + same valuation inputs +
same replay time inputs → same result.

A different market mark, valuation time or restart time is a different input
population and is allowed to produce a different snapshot or recovery
disposition.

This must never be mislabeled as nondeterministic replay.

## 12. Runtime production boundary

Source certification does not authorize deploying current `main` into the
active F00 epoch.

Current F00 remains pinned to its existing deployed source/config.

A real VPS restart proof requires a separately governed checkpoint because
the current active F00 source predates FIN-00/FIN-01.

Before any production restart/deployment, record at minimum:
- active F00 epoch id;
- deployed source SHA;
- config hash;
- PPL event count/last sequence/digest;
- open trade ids;
- available cash;
- reserved principal;
- unresolved capital;
- fees/realized PnL;
- compatibility boundary;
- service PID/restart count;
- exact terminal checkpoint timestamp.

No runtime restart is part of the source PR.

## 13. Exit gates

Source gate:
- independent durable reload equivalence PASS;
- real `PPLAuthorityRuntime` restart simulation PASS;
- OPEN replay PASS;
- CLOSE idempotence PASS;
- UNRESOLVED recovery PASS;
- no double reserved release PASS;
- fee/PnL/funding attribution preservation PASS;
- invalid PPL projection non-corruption PASS;
- FIN projection non-corruption PASS;
- maintained CI PASS.

Runtime gate:
- governed F00 checkpoint/freeze;
- exact deployed/source boundary recorded;
- controlled restart/replay;
- durable PPL digest continuity or explicitly attributable deterministic
  recovery append;
- post-restart PPL state explained;
- FIN projection replayed from the captured durable population;
- no compatibility corruption;
- no strategy/risk/sizing/execution mutation.

Final verdict is issued only after the required source and runtime evidence are
both satisfied:

`PPL_FINANCIAL_RECOVERY_REPLAY_CERTIFIED`
