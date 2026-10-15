# D1-D — Producer Denominator & No-Packet Accountability (SOURCE-ONLY)

Parent: #404 ; issue D1-D: #408 ; next gate: D1-E. D1-C evidence: Draft #407 head `9e4bed4393caadc8f328f698c806f82fd91271e7` (not merged). Reference frozen runtime source `116634be0d3c015cce1cfa58be7da7255414fbfd`.

## Scientific boundary

D1-C already classifies 9,672 **captured** REJECTED DecisionPackets into 5,486 LINKED and 4,186 PROVEN_NOT_ELIGIBLE (`NATIVE_LSE_NON_ACTIONABLE`), with zero eligible-unlinked/unknown **inside the captured population**. This is **not** a denominator of every cycle-symbol opportunity, of all attempted analyses, or of exceptions that never produced a packet.

The D1-C custody manifest says `source_epoch_binding=UNVERIFIED`; native `dataset_id` and `source_boundary_id` are unavailable. The 10,824 DecisionPacket timestamps are naïve UTC assumed, not clock-certified. No D1-D code below supplies the missing evidence by inference.

## Frozen-source forensic

| Boundary | Source finding | Why the existing D1-C capture is insufficient |
|---|---|---|
| Entering `analyze_symbol` | `core/advisor_loop.py` near 1491 generates `trace_id` and attempts to persist DecisionIdentity before governance checks; failed journal persist is nonfatal | No independent call roster or proof of successful every-invocation journal persist |
| Authority return | Same file returns `decision_packet=None` on authority denied (~1557) and uninitialized (~1612) | These decisions need not appear in packet or RejectionStore |
| Signal/packet construction | `engine.evaluate()` (~1925) precedes `_to_decision_packet` (~1943) | Exceptions and packet-builder failure can precede a packet |
| Packet file write | Conditional on a packet and state; errors are caught (~2767–2793) | Missing row != proof no packet / lost write |
| Cycle symbol selection | TopK selection, prescan and ordering in `core/advisor_loop.py` (~6320–6400) | Full watchlist size is not equal to selected or invoked denominator |
| Alternate coordinator | `runtime/advisor_main.py` can skip `raw_signal.ok=False` and catch analyze exceptions (~142–173) | Which orchestrator ran is not certified by source availability alone |
| Publication/persist | Best-effort EventBus and RejectionStore listener | A returned listener != fsync evidence; D1-E is separate |

These source observations use GitHub at frozen runtime ref. They do not attest process launch arguments, runtime feature flags, actual call rates, live journal population or producer completeness.

## Three independently sourced streams required in a future authorized capture

All future streams MUST bind the **same** externally verified epoch, code/config, dataset_id/source_boundary_id, UTC window, source prefix hashes/offsets, freeze/quiescence boundary, selection policy and signed/immutable custody.

1. **Universe roster**: every native cycle + candidate symbol in the precisely defined universe, including `selected_for_analysis=false` and explicit selection/reordering/interruption outcome. The list must come from a provenance independent of packet capture. Its completeness cannot be established from the roster's own claimed `complete=true`.
2. **Per-invocation receipts**: every selected candidate's invocation/execution lifecycle, with native `attempt_id`, cycle, symbol, trace/decision identity, start/end time + clock quality, and exclusive terminal outcome: `RETURN_WITH_PACKET`, `RETURN_NO_PACKET`, `RAISED_BEFORE_PACKET`, `RAISED_PACKET_STATE_UNKNOWN` or `UNKNOWN`. A missing receipt is UNKNOWN, not an observed absence. A nonfatal DecisionIdentity persist failure remains visible.
3. **Captured packets**: bound packet ID and native causal correlation with the returned invocation. No join by timestamp proximity alone. `RETURNED_PACKET_NOT_CAPTURED` is a capture discrepancy, **not proof of loss in RejectionStore**.

### Accounting and the reference pure verifier

`research_data/stress_d1_producer_denominator.py` is an isolated, pure in-memory *prototype* with explicit supplied rows only. No IO, imports from production, network, runtime service, config or activation. It tests arithmetic and contradictions, NOT producer completeness.

For the prototype's **declared** roster:

`roster_entries = NOT_SELECTED + MISSING_INVOCATION_RECEIPT + PACKET_CAPTURED + RETURNED_PACKET_NOT_CAPTURED + PROVEN_RETURN_NO_PACKET + PROVEN_EXCEPTION_BEFORE_PACKET + EXCEPTION_PACKET_STATE_UNKNOWN + UNKNOWN_INVOCATION_OUTCOME`.

Missing receipts and packets never become zero; duplicate identities, extra records or incompatible packet outcomes raise `DenominatorIntegrityError` and abort certification. The `unresolved_evidence_count` is a count of **gaps**, not unique lost decisions; a packet without any receipt can contribute two correlated gaps.

**Important method limit:** the prototype assumes at most one invocation per `(cycle_id,symbol)`. The actual per-cycle uniqueness of invocations is NOT verified. If reanalysis within one cycle is possible, replace this prototype key with a native unique `attempt_id` and add tests **before any real data use**. The prototype's output always sets `producer_completeness=NOT_PROVEN`, `epoch_binding=NOT_PROVEN` and `paper_stress_runtime_go=DENIED`, even for a perfectly matched synthetic roster. It is forbidden to fabricate a complete roster from the D1-C four files.

## Tests and review boundaries

### Source-only V2 extension (2026-10-12)

The V1 restriction above is preserved as history and as a legacy API limit.
The separate [native-attempt V2 contract](D1_D_NATIVE_ATTEMPT_CONTRACT.md) now
accounts for multiple native attempts per roster entry, explicit boundary
declarations and late terminal receipts. It does not reconstruct a real roster,
certify custody, or promote any D1-C result to producer completeness.

19 local synthetic tests pass on isolated source; Python compilation passes. Ruff was **not available locally**. Full repository CI and tests are **not yet claimed** at this commit; review the exact final PR SHA. The only input to tests is synthetic objects; no real historical packet or producer ledger was opened.

Acceptance of a *real* denominator requires an independently proven cycle/roster completeness fence, native epoch and boundary provenance, per-invocation receipts with documented exception semantics, packet joins, interval-crossing/late event accounting and verified Research custody. Otherwise:

`D1_D_REAL_PRODUCER_ROSTER=NOT_OBSERVED`
`D1_D_PRODUCER_COMPLETENESS=NOT_PROVEN`
`D1_D_HISTORICAL_EARLY_RETURN_COUNT=UNKNOWN`
`D1_D_SOURCE_ACCOUNTING_CAPABILITY=FOR_REVIEW`.

## D1-E handoff — durability chain (NOT completed)

A separate source-only research stage must define per-decision evidence across:

`ObservationBuilder attempted/completed → EventBus publication → listener configured/enqueued/delivered/dropped → RejectionStore.filter/validate → persist attempted → append/flush → fsync returned`.

The existing EventBus marks listener execution successful when `on_observation()` returns normally, even when `persist()` returns `False` (and that bool is discarded). Thus neither EventBus success counters nor existence of fsync code prove per-decision durable write. UTC file rotation can straddle observation date and must be reconciled. **Do not** retrofit receipts or identities into the frozen burn-in.

## Immutable governance

Active #282 burn-in and #286 immutability guard unchanged; #407 remains Draft. No staging/export of new live bytes without separate operator authorization, no production instrumentation/restart, no change to strategy, risk, sizing, epoch, PPL/FIN, Watchdog, TESTNET/LIVE or exchange.

`COUNTERFACTUAL_PERFORMANCE_ELIGIBILITY=NOT_PROVEN`
`PAPER_STRESS_RUNTIME_GO=DENIED`
`ACTIVE_BURN_IN_IMMUTABILITY_GUARD=ACTIVE`
