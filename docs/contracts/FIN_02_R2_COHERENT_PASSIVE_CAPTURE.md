# FIN-02R2 — Coherent Passive Capture Boundary

Status: **SOURCE IMPLEMENTATION CANDIDATE**

Parent mission: #247 — FIN-02
Parent architecture: #150
Governance: #148
Reference PR: #254

Dependency:

`FIN_02_R1_RUNTIME_PROVENANCE_SOURCE_CERTIFIED`

Certified R1 HEAD:

`4d7fbe73381d22ff2195405ba4a92df1bdd2ce4c`

## 1. Scientific question

FIN-02 cannot reconcile financial truth from observations captured at unrelated
instants.

R2 must answer:

> Can the already-running PAPER authority stack expose one passive observation
> in which the authoritative PPL event population and the independent MEXC_SIM
> accounting state are frozen across one causally coherent boundary?

The answer must be demonstrated without:
- creating a second PPL authority;
- mutating PPL;
- mutating simulator accounting;
- calling execution;
- calling an exchange;
- reading marks implicitly;
- using wall-clock time inside the capture;
- restarting or deploying active F00.

## 2. Existing production lock order

Source audit of authoritative MEXC_SIM OPEN/CLOSE paths establishes:

```
MEXC_SIM._lock
    ↓
PPLAuthorityRuntime.commit_open / commit_close
    ↓
PPLAuthorityRuntime._lock
```

Therefore the certified R2 lock order is:

`MEXC_SIM_LOCK_THEN_PPL_RUNTIME_LOCK`

The inverse order is forbidden by the R2 boundary.

## 3. Single-authority rule

R2 does not accept a `PPLAuthorityRuntime` argument.

It also rejects an attached `_shadow_observer` while PPL is authoritative.

It obtains the runtime only from:

`simulator._authority_runtime`

and requires:

`simulator._lifecycle_authority.ppl_is_authoritative == True`

This prevents a caller from combining:
- simulator A;
- PPL runtime B;
- unrelated epoch C.

The capture is therefore bound to the authority runtime already owned by the
running simulator.

## 4. Critical section

R2 acquires `MEXC_SIM._lock` once.

While that same lock remains held:

1. verify MEXC_SIM is already running;
2. capture current simulator generation;
3. call the simulator-owned `PPLAuthorityRuntime.consistent_view()`;
4. require PPL runtime status `READY`;
5. read simulator:
   - available cash;
   - reserved principal from live positions;
   - exact open trade ids;
   - pending order count;
   - lifecycle transitions in flight;
6. verify simulator generation did not change;
7. require lifecycle transitions in flight = 0.

Only then is the simulator lock released.

The resulting event tuple and simulator observation are immutable copies for all
subsequent R1/provenance and valuation-evidence processing.

## 5. Why simulator observation needed a lower-level primitive

Existing FIN-02 function:

`capture_simulator_observation(...)`

acquires `MEXC_SIM._lock` internally.

MEXC_SIM uses `threading.Lock`, not `threading.RLock`.

Calling that API while R2 already owns the simulator lock would deadlock.

R2 therefore factors the read-only field copy into:

`_capture_simulator_observation_locked(...)`

Precondition:
the caller already owns the simulator lock.

The existing public `capture_simulator_observation(...)` retains its previous
behavior by taking the lock and delegating to the same primitive.

No accounting formula was changed.

## 6. PPL binding after critical section

R2 freezes `view.events` while the simulator lock is held.

After release, pure deterministic functions build:

- `PPLFinancialObservation`;
- certified R1 `FinancialRuntimeProvenance`.

R2 then proves exact equality of:
- paper epoch id;
- PPL source-stream digest;
- last source sequence.

A mismatch fails closed.

## 7. Independent divergence is preserved

R2 is a capture boundary, not a reconciliation decision.

Therefore it does **not** require MEXC_SIM values to equal PPL values.

Examples that remain capturable:
- different simulator cash;
- missing simulator position;
- additional simulator position.

Those differences must survive into FIN-02 reconciliation as visible evidence.

Rejecting them at R2 would hide the very divergence FIN-02 exists to expose.

## 8. Valuation evidence

R2 never fetches market data.

Valuation observations must be supplied explicitly as existing
`ValuationObservation` objects.

R2:
- preserves missing valuation evidence as an empty observation set;
- rejects duplicate valuation trade ids;
- rejects marks for trades not open in the captured PPL view;
- rejects symbol mismatch against captured PPL position identity;
- canonicalizes only finite numeric price/timestamp representation;
- does not classify LIVE/STALE/UNAVAILABLE;
- does not calculate unrealized PnL;
- does not fabricate a missing mark.

Future timestamps, missing prices or invalid economic marks remain explicit raw
evidence for FIN-01 valuation semantics to classify later.

R2 binds the raw evidence with:

`FIN02_R2_VALUATION_EVIDENCE_V1`

## 9. Capture identity

Namespace:

`FIN02_COHERENT_PASSIVE_CAPTURE_V1`

The deterministic capture identity binds:
- R2 schema version;
- caller-supplied capture timestamp;
- certified lock order;
- PPL runtime status/error evidence;
- simulator generation;
- R1 provenance id;
- PPL epoch/digest/sequence;
- simulator source/cash/reserved/open ids;
- simulator transition/pending-order evidence;
- raw valuation-evidence digest.

The same frozen inputs reproduce the same `capture_id`.

## 10. Fail-closed conditions

R2 rejects:
- non-PPL lifecycle authority;
- attached SHADOW observer;
- absent simulator-owned authority runtime;
- absent simulator lock;
- simulator not already running;
- absent/invalid simulator generation;
- PPL runtime not READY;
- simulator generation change inside the critical section;
- unknown/non-zero lifecycle transition state;
- empty PPL durable event population;
- absent PPL projection;
- R1 epoch/digest/sequence mismatch;
- invalid valuation evidence;
- valuation evidence for non-open trades;
- valuation symbol mismatch.

## 11. Concurrency proof requirement

Source tests must demonstrate that:

1. R2 has acquired MEXC_SIM._lock;
2. PPL `consistent_view()` is still executing;
3. a concurrent simulator mutation attempts to acquire MEXC_SIM._lock;
4. that mutation cannot acquire the lock before the R2 PPL+SIM read completes;
5. the captured simulator state therefore represents the pre-mutation state;
6. the mutation can proceed normally after capture releases the lock.

This proves the intended causality boundary rather than merely testing static
field values.

## 12. Production mutation-path audit

Repository source audit found production calls to:
- `PPLAuthorityRuntime.commit_open(...)`;
- `PPLAuthorityRuntime.commit_close(...)`;

only in authoritative `paper_trading/mexc_simulator.py`.

Those calls are inside `MEXC_SIM._lock`.

Direct authoritative commit calls elsewhere are test/certification code.

Separate direct `DurableEventStore.append(...)` paths still exist for SHADOW,
legacy-import/migration and test tooling. They are not part of the active
PPL_AUTHORITY execution path and R2 does not claim to make an unauthorized
external writer impossible.

Therefore R2 source certification proves in-process causal coherence under the
single-authority runtime contract. Runtime certification must separately prove
that no second process/tool is concurrently writing the active authority store.

Any future active PPL_AUTHORITY production caller that mutates the authority
store outside the certified lock order invalidates R2 assumptions and requires
re-certification.

## 13. Runtime boundary

R2 is source-only.

`ADVISOR_RESTART=NO`
`ACTIVE_F00_MUTATION=NO`
`PPL_APPEND=NO`
`EXCHANGE_READ_OR_WRITE=NO`
`FIN_LEDGER_MUTATION=NO`
`RUNTIME_PRODUCER_ACTIVATION=NO`

No R2 code is wired into Advisor during this subphase.

## 14. Source exit criteria

R2 is source-certified only when:

- R1 remains certified and unchanged semantically;
- one simulator-owned PPL runtime is enforced;
- SIM → PPL lock order is explicit;
- one uninterrupted PPL+SIM critical section is proven;
- simulator generation is stable inside capture;
- PPL runtime READY is required;
- divergence is preserved rather than rejected;
- valuation evidence is explicit and no-fabrication;
- concurrency test proves blocking behavior;
- existing simulator capture API remains compatible;
- full maintained CI is green on the exact R2 candidate HEAD;
- Semgrep is green;
- no active F00 runtime mutation occurs.

Target sub-verdict:

`FIN_02_R2_COHERENT_PASSIVE_CAPTURE_SOURCE_CERTIFIED`

This is not the final FIN-02 verdict.
