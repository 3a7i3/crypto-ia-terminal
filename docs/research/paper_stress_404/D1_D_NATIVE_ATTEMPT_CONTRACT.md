# D1-D V2 — independent roster and native attempts

Mission [#408](https://github.com/3a7i3/crypto-ia-terminal/issues/408), Draft
[#409](https://github.com/3a7i3/crypto-ia-terminal/pull/409). Source-only extension;
the historical V1 function and its 19 tests remain intact. V2 is a separate API,
`research_data.stress_d1_producer_attempts.reconcile_producer_attempts`.

## Problem and accounting units

V1 keys on `(cycle_id, symbol)` and cannot represent reanalysis in a cycle.
V2 accepts an independently acquired native roster, an explicit per-roster
attempt plan, invocation terminal receipts, and captured packets. A roster row
has `roster_id`, `cycle_id`, `symbol`, boolean `selected_for_analysis`, UTC
`selected_at`, and `attempt_ids`. These IDs must be producer-native planned
invocations, not UUIDs assigned by Research, counters reconstructed from packets,
or inferred retries. A selected row with an empty plan is unresolved; a missing
plan field is malformed. A non-selected row cannot carry an invocation plan.

Multiple native `attempt_id` values can share one cycle-symbol. Receipts and
packets must join on attempt **and** roster/cycle/symbol. Packet IDs are unique
across attempts; cross-attempt aliases abort reconciliation. Packet presence
without a terminal return receipt remains ambiguous. There is no temporal
nearest-neighbor join. The input objects remain unchanged and order is irrelevant.

Two conservation equations, never interchangeable:

```
roster_entries = not_selected + selected_roster_entries
planned_attempts = sum(counts.values())
```

The seven exclusive attempt categories are missing receipt, captured returned
packet, returned packet not captured, observed no-packet return, observed exception
before packet, exception with unknown packet state, and unknown outcome. A missing
packet does not establish a RejectionStore loss. `unresolved_evidence_count` counts
evidence gaps, not distinct lost decisions; correlated gaps can count twice.
An unobserved extra invocation outside the declared plan cannot be detected from
these inputs. Observed extra invocations fail closed. A complete-looking plan
does not establish producer completeness.

## Boundary and interval contract

Every row supplies the same strict `boundary` mapping:

| Field | Requirement |
|---|---|
| `paper_epoch_id`, `dataset_id`, `source_boundary_id` | nonempty explicit native declarations |
| `code_sha` | lowercase 40-character hexadecimal source identity |
| `config_sha256` | lowercase 64-character hexadecimal config identity |
| `window_start`, `window_end`, `capture_cutoff` | timezone-aware UTC, start < end <= cutoff |

Roster selection belongs to `[window_start, window_end)`. Each terminal receipt
supplies `started_at`, `ended_at`, `outcome`, and `packet_id` (nonempty only on
`RETURN_WITH_PACKET`). Selection <= start <= end <= cutoff. An invocation can
end outside the selection window; `late_terminal_receipts` preserves it.
In-flight invocations without a terminal receipt remain missing/unknown; they
are not synthesized as no packet. UTC syntax checks do not certify clocks.

`stress_d1_evidence_contract` also checks supplied immutable JSON bytes against
explicit SHA256 pins, rejects duplicate JSON keys and nonfinite values, and checks
row/envelope boundaries. This helper is shared with the D1-E source stage. A hash
match proves byte consistency only: a caller can fabricate bytes and their pin.
No native origin, independent acquisition, signature trust, root-owned custody,
prefix continuity, queue fence or current runtime binding is certified here.

## Scientific disposition

The captured D1-C population remains historical evidence: 10,824 packets,
9,672 REJECTED (5,486 LINKED + 4,186 `NATIVE_LSE_NON_ACTIONABLE`) and 1,152
EXECUTION_PENDING, not FILLED. It cannot supply the independent roster/plan.
There is no new real-data classification or historical early-return count.

All V2 outputs retain `producer_completeness=NOT_PROVEN`,
`native_epoch_binding=NOT_PROVEN`, `custody=NOT_VERIFIED`,
`counterfactual_performance_eligibility=NOT_PROVEN`,
`paper_stress_runtime_go=DENIED`. Declared identities are not attestations.
The active #282/#286 burn-in remains protected; no export, instrumentation,
deploy, restart, merge, runtime/config/epoch/PPL/FIN mutation is authorized.

D1-E must separately reconcile native packet/trace/decision identities and
`BUILD → PUBLISH → DELIVERY → FILTER → VALIDATE → APPEND → FLUSH → FSYNC`.
V2 invocation reconciliation does not substitute for that chain.
