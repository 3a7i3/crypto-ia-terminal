# D1-E — frozen-source forensic, not current runtime proof

Inspection reference: **`116634be0d3c015cce1cfa58be7da7255414fbfd`**.
Files were read from the Git object database in a fresh source checkout;
no VPS log, running process, production file or new Research capture was read.
The historical source identity is not a fresh runtime/process attestation.

| Frozen source artifact | SHA256 of inspected complete file |
|---|---|
| `core/advisor_loop.py` | `3a402aa3aeddbb67978c0efaa1eb8ebeaac6dec655b859201bd8205d96273664` |
| `observability/decision_observation.py` | `2a7a94702da2e56eb1fdf063f5b13c4dc5043ae86a6c2ab01f6090966a52798a` |
| `observability/decision_event_bus.py` | `475827862111d6ed8d7015c5f560f1a4b4932ae17636e236f652fdc3c9a312f5` |
| `observability/rejection_store.py` | `9082c05e456754bdeb00774e908068ba30cd585f19d0a6756a7bc6355509f4a9` |

Reproduce without importing/executing production modules:

```bash
git show 116634be0d3c015cce1cfa58be7da7255414fbfd:observability/rejection_store.py | sha256sum
git show 116634be0d3c015cce1cfa58be7da7255414fbfd:observability/decision_event_bus.py | sha256sum
git show 116634be0d3c015cce1cfa58be7da7255414fbfd:observability/decision_observation.py | sha256sum
git show 116634be0d3c015cce1cfa58be7da7255414fbfd:core/advisor_loop.py | sha256sum
```

## Chain and source observations

| Boundary | Source facts at frozen ref | Evidence not supplied by source |
|---|---|---|
| Producer dispatch | `core/advisor_loop.py:7088–7125`: actionable and not safe mode; configured bus; builder then publish; caught exception and Telegram fallback; safe mode skips the block | Native per-decision flags, actual path execution, builder receipt, target store registration |
| Builder | `decision_observation.py::build_from_result` (~319): price conversion (~349), packet-based provenance (~389), separate trace provenance (~406) | Which packet failed to build, whether price/provenance existed for an unlinked captured packet |
| Bus submission | `decision_event_bus.py:102–135`: no listeners returns; start if inactive; executor can be absent; submit to copied listener list; shutdown RuntimeError increments aggregate drop and breaks | Per-target acceptance/delivery/causal identity, durable acknowledgment, native queue fence |
| Async execution | `decision_event_bus.py:137–151`: listener normal return increments succeeded, exception increments failed | RejectionStore persist result or fsync outcome; thread can start before post-submit counter increment |
| Listener filter | `rejection_store.py:293–323`: actionable, not trade_allowed, supported side, nonempty packet, provenance; legacy missing provenance flag defaults True | Native criteria for unseen observation, actual filter execution or validated admission |
| Persist return | `rejection_store.py:258–291`: validate, lock, `_get_path`, JSON serialization, append, flush, fsync, close, increment; exceptions return False | Per-decision native result or captured prefix; `on_observation` discards persist bool |
| Partition | `rejection_store.py:250–256`: `_get_path` chooses current UTC date before open/write | Physical file identity and native partition-selection time; event date is not partition date |
| Durability | `os.fsync(f.fileno())` follows flush; no parent-directory fsync in this path | Crash/power-loss guarantees, new-file directory metadata durability, exact descriptor/range witness |

The module's introductory wording about “zero silent loss” or “atomic JSONL” is
not treated as a proved guarantee. The actual control flow is the evidence.
`f.write`, `flush`, `fsync` and `close` can fail at different stages; appended
bytes and persist False can coexist, as can successful fsync and later close
failure. Aggregate counters cannot resolve any such per-decision case.

The frozen validator (~200–220) checks required keys, packet ID, symbol and
`price <= 0`. It does not explicitly guard bool/nonfinite prices. The new offline
Research verifier rejects nonfinite/bool claims rather than silently expanding
admissibility. This is an observable source-method limit, not a finding that a
nonfinite price occurred in production, and is not repaired in the active runtime.

## What remains actually unknown

No producer-native attempt roster, stage ledger, separate fsync witness or native
boundary binding was obtained in this mission. Historical D1-C remains:

- `[2026-10-10T00:00:00Z, 2026-10-11T00:00:00Z)`, governed immutable Research copy,
  captured execution exit code 0, under the historical `chatgpt-ro` audit.
- 10,824 DecisionPackets: 9,672 REJECTED and 1,152 EXECUTION_PENDING, not FILLED.
- REJECTED: 5,486 LINKED + 4,186 PROVEN_NOT_ELIGIBLE, native
  `NATIVE_LSE_NON_ACTIONABLE`; no eligible-unlinked/unknown inside that capture.
- These exclusions do not demonstrate lost writes. Capture coverage does not
  prove producer completeness or native binding to the governed active epoch.

The active epoch `BURN-IN-EPOCH-01-20260926T064144Z` and historical config
`9d9de1af4ac5aa5afc030ff64b08eeada0e1388a5d87c6475cb39c042be230d4`
are governance reference identities, not inferred native labels for D1 data.

`ACTUAL_PERSISTENCE_PROOF=NOT_OBSERVED`
`D1_E_PER_PACKET_DURABILITY=NOT_PROVEN`
`D1_D_PRODUCER_COMPLETENESS=NOT_PROVEN`
`D1_NATIVE_EPOCH_BOUNDARY_BINDING=NOT_PROVEN`
`PAPER_STRESS_RUNTIME_GO=DENIED`
`ACTIVE_BURN_IN_IMMUTABILITY_GUARD=ACTIVE`
