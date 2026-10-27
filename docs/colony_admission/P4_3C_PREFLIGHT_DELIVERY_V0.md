# 3C-2b — Private global structural preflight

SOURCE_ONLY / LAB_ONLY / PARTIAL_IMPLEMENTATION / NO_PUBLIC_POPULATION_SCAN.
Remote base: `main@7f6d13b7c911b31c51eb30d5f500a320ec0a698b`, tree
`cee29f6e666f535cc37df994bbb0cad020b7df3a` (#511 closed privately after its
own exact merge CI). Local parent `38823b2e874e0bd4d934e58014ac68a7ab5d26c9`
has that same tree; it is not the remote merge commit.

References: [3C contract](P4_3C_POPULATION_AND_CEILINGS_V0.md) §3, §6–9, §12;
[107 specification cases](P4_3C_POPULATION_AND_CEILINGS_CASES_V0.json), especially
BOUND-01..04, KEY-01..03, PLAN-04; [delivery split](P4_3C_PLAN_AND_REUSE_V0.md) §8;
[inventory/core](P4_3C_INVENTORY_CORE_DELIVERY_V0.md) and
[pre-ledger phase](P4_3C_LOG_PHASE_DELIVERY_V0.md).
This is a smaller prerequisite of the future single owner, not that complete owner.
The 107 matrix cases remain SPECIFICATION_ONLY_NOT_EXECUTED.

## Private property provided

`_population_preflight.derive` takes only detached immutable HomeInput and
OperationInput tuples plus the pinned operator policy and unresolved external IDs
from the one acquisition. It performs no IO, ledger call, envelope verification,
science classification or operational action. No public export/config is added.
The caller must acquire/bind these inputs exhaustively; their existence as Python
objects is never evidence of acquisition, trust, stability or complete coverage.

The helper validates source counts, sizes, policy and readable operation/log binds;
all frozen-item policy/hard caps are enforced, including historical attempts.
Current open operations are selected from latest readable attempts. Multiple open
operations or any unresolved external claim prevent a unique selection and any
OWN potential/P/F bound. Historical plans have no derived current population graph
or counts, and remain explicitly HISTORICAL_POPULATION_NOT_EVALUATED.

For a current open operation, derive the union of structural keys K from the three
candidate records and EVERY real acquired home. PREPARED's list/roles are not used
to shrink or define that graph. Founders always require their individual key;
descendants require their own admission/qualification/statement and, if present,
individual. Branch individuals remain required even when their envelope is absent.
Identical K is deduplicated with all namespace copies retained; distinct full-record
hashes of qualifications of one subject remain distinct K. No home is filtered
because it seems revoked, invalid or scientifically unsupported. A missing record
makes the graph incomplete, not a permission to omit its home. Known lower-bound
keys still enforce universal caps; derived_n is null when records needed to derive
the full graph are missing/divergent or its structural universe, branch or unique
operation scope is not established. Declared candidate q/admission sizes are
checked explicitly too, and an oversized declared record is a global named
limit, never a local missing/divergent-record downgrade. Named derivation FAIL dominates NE.

A *potential* OWN candidate is recognized only for the unique open operation after
an effective pending BEGIN D3 or completed D3, matching its exact home identity
storage bytes, complete layout and existing pure D2 material comparisons. Before
DONE D3 the initial usage must also match exact storage bytes; after DONE D3 usage
is not parsed or compared. An incomplete potential gives no P/F bound. This fact
never establishes OWN_OPERATION: exact current /1, signatures, DECISION and all
other P1/3C preconditions are still required. A false/absent potential is not a
claim that the home is authenticated, nor a full own-home validation verdict.

Only on a fully valid structural home universe and a unique known open operation
are provisional P/F computed (potential candidate excluded structurally). The
P/F item bound is applied only under P<=max_population-1 and F>=1. Always apply
min(252,4*policy.max_population-4); do not assert the tighter chain when population
is over policy or a prerequisite is absent. Any excess raises a named PreflightLimit
for whole-context invalidation by the future owner, before any signature.

Private result fields make scope explicit: provisional_p/f, known_keys vs derived_n,
potential_own_agent_id, per-operation CURRENT_OPEN/HISTORICAL and named derivation.
They are immutable tuples/frozen dataclasses; accepted=false, population, counts,
own_home, frozen_completeness, ceilings and authorization remain NE permanently.
A derivation PASS means only that this detached structural graph was derived under
these bounds. It is not a PASS of population/classification, policy birth ceilings,
frozen partitions, OWN, crypto, terminal linkage, source acquisition or a scan.

## Integration still required

The future owner must validate detached config before IO, hold L1, acquire current
trust/faults and the complete log/external universe, inventory all homes/layouts and
other required private namespaces before one fresh offset-zero ledger FD under L2,
then acquire all records/branches/envelopes/checkout with shared caches. Construct
OperationInput from those exact retained snapshots, supplying initial usage only
where required and never reading mutable usage after DONE D3.

Call preflight before the FIRST signature anywhere in the scan, not once after
some homes have already been classified. Handle every named limit by clearing all
payload and retaining fixed codes/limit names. No second ledger or late external
ID, no nested public scans, no override caller selecting a preferred open operation.
Only then may the proof core be wired. Re-derive after classifications on a valid
corpus to verify the same K; provisional values never become counts by relabeling.

Still missing before any complete public PopulationObserver: owner acquisition,
full proof wiring/OWN, exact DECISION/POPULATION roles and envelope copies,
current-vs-historical completeness, classified counts/plan/ceilings, fault scopes,
external current-ledger findings, quarantine/incarnation/action correspondences,
aggregation and all-context verify/close/unlock invalidation. Structural graph
preflight does not implement these later properties or certify that its caller
already performed them. Older public observer contracts remain unchanged.

## Validation and gates

Temporary LAB_TEST detached fixtures only. Adversarial tests cover frozen-list
omission/reclassification, all-home participation regardless of envelope validity,
missing/invalid structures, shared and distinct qualification K/copies, exact
physical OWN potential vs cancelled/partial/substituted evidence, opaque runtime
usage after DONE D3, multiple/externally unresolved opens, historical scopes,
known keys despite missing records, policy20/21 and absolute252/253 bounds,
P/F precondition failure,
strict limits, immutable permanent NE fields and import without IO. Exact final
test counts, normal/-O sequential runs, lint and independent exact-tree review are
recorded in the PR after execution; no count promised by this document.

Pins P1/scenarios/g0/formats/colony_lab/sentinel_activity/colony_pilot and all three
qualified code closures remain unchanged. PC2/p1 stays SCIENTIFIC_PROFILE_UNSUPPORTED
/NE blocking; #510 remains a distinct proposed amendment, not adopted here.
Before merge: exact-tree independent agent review, complete exact-HEAD check-runs
filter=all and workflows all events/statuses paginated to empty, logs/skips/coverage,
threads/ruleset/main/composition/pins, guarded expected_head_sha and no bypass.
Then all CI of the exact merge before private closure; never transfer HEAD green.
accepted=false; #286 ACTIVE; 3C and step3/7 open. No VPS/runtime/systemd/PPL/FIN/
epoch/production/TESTNET/LIVE/exchange/secret/replay/campaign/birth/trust installation/
recovery or operational writer. Rollback source only.
