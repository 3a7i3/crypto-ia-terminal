# 3C-2c — Private single-owner acquisition before proof wiring

SOURCE_ONLY / LAB_ONLY / PARTIAL_IMPLEMENTATION / NO_PUBLIC_POPULATION_SCAN.
Prepared on the exact reviewed #512 preflight tree
`8912af21adf288456167afd8cc89f298e2e9976b`, without an early merge. The remote
base must be the eventual verified #512 merge, not a claimed equivalence of local
and remote commit IDs. This delivery cannot merge before #512's private closure
after its own complete merge CI.

References: [3C contract](P4_3C_POPULATION_AND_CEILINGS_V0.md) §3–4, §10–12;
[plan](P4_3C_PLAN_AND_REUSE_V0.md) §8; private
[inventory/core](P4_3C_INVENTORY_CORE_DELIVERY_V0.md),
[log phase](P4_3C_LOG_PHASE_DELIVERY_V0.md) and
[preflight](P4_3C_PREFLIGHT_DELIVERY_V0.md). The 107 specification cases remain
SPECIFICATION_ONLY_NOT_EXECUTED; they are not a count of executed tests.

## Acquisition property

`_population_acquisition.acquire` is private, accepts the existing detached
AttestationConfig and returns an immutable Acquisition. It validates configuration
before IO and owns one ExitStack/InventorySource for the entire lifetime. No
PopulationConfig, public scanner, home classification or proof-core invocation
is introduced. `ACQUIRED` means only that the bounded acquisition exited
successfully; it does not imply a population, science or ledger-coverage verdict.
Snapshot completeness, population, OWN, counts, ceilings, terminal linkage and
authorization stay permanently NE, accepted=false.

The owner opens the existing L1 read-only with an exclusive nonblocking lock,
acquires faults/installed trust/history once, validates current root/pin/floor,
and reuses the existing operator-policy/checkout acquisition. It calls #511's
log phase once, including all external IDs (also /0 and absent faulty logs) in U.
Strictly targeted faulty log contents remain unread regardless of whether the
eventual terminal evidence can succeed. No STICKY_FAULT or historical external
status is converted into either a global veto or a favorable terminal fact here;
the retained raw evidence must still be scoped and compared by the proof phase.

Before opening the ledger it inventories every real home/layout, admissions and
envelope namespaces, and optional quarantine namespace/layouts. Counts share the
8192-entry/4096-FD limits. Known record/envelope sizes and candidate BirthPlan
record sizes are bounded before the ledger. Quarantine op names are hex64;
destination names are canonical positive decimal (at most128 digits) or terminal.
Unknown action correspondence remains NE; it never grants permission to omit a
home or infer that an action finished. Runtime/SQLite/tasks/results/inflight and
quarantine usage contents are not read.

There is one fresh offset-zero O_RDONLY ledger FD and one inspection of sorted U
under L2. The owner never adds a late operation ID, opens a second ledger, retries
a lock or calls another public scan. Existing borrowed-FD inspection establishes
the L2 lock/unlock boundary. The single source cache supplies all home/branch/
candidate records, statement/envelope copies and quarantined identity material.
Missing or invalid stable private records remain detached local facts rather
than disappearing from the universe. Initial usage is acquired only for the
latest open effective BEGIN D3 before DONE D3; historical attempts do not read
current usage as a historical snapshot, and DONE D3 usage stays opaque.

The global #512 preflight receives every acquired home and readable attempt,
plus all unresolved external IDs, before any later proof phase could run.
Supported R8/C9 checkout evidence/code closures are acquired through one shared
Checkout, without importing submitted code. The owner invokes no envelope
signature verification or science classification. Detached branch/envelope/
artifact material is retained for later proof wiring, never relabeled as proof.

Checkout listings/absences and all source listings/absences/FD/path metadata are
revalidated. Explicit L1 unlock and every close must succeed before the result
escapes. Acquisition/configuration/limit/verify/unlock/close failure erases the
whole payload, including homes, operations, quarantine, logs, preflight, stamps,
root/trust/fault/policy/artifact bytes and ledger bytes. Only fixed codes and
named limits remain. No partially successful result is salvaged.

## Remaining integration

This owner is the acquisition prerequisite, not a complete PopulationObserver.
It deliberately does not call the private proof core yet. The next tranche must
wire crypto/science/home proofs ONLY after this global preflight within the same
owner; a later independent scan is not a valid composition. It must implement
exact OWN D2/D3/current /1/DECISION, full partitions and all copies, current versus
historical scopes, classified counts/plan/ceilings, current external-ledger
terminal linkage, fault scopes, action/quarantine/incarnation correspondence,
aggregation and whole-context invalidation for every added proof payload.
No provisional P/F or potential OWN becomes a classified count/exclusion.

PC2/p1 remains SCIENTIFIC_PROFILE_UNSUPPORTED/NE blocking and p1 remains in g0.
#510 is a proposed normative amendment, not adopted or implemented by this code.
No signature, review identity, historic campaign or qualification is fabricated.
3C and step3/7 remain open, #286 ACTIVE; P1/pins/scenarios/formats/g0 and qualified
colony_lab/sentinel_activity/colony_pilot sources remain unchanged. No VPS/runtime/
systemd/PPL/FIN/epoch/production/TESTNET/LIVE/exchange/secret/replay/campaign/birth/
installation/recovery or operational writer. Rollback is source-only.

## Validation and delivery gate

Temporary LAB_TEST fixtures and public test keys only. Tests instrument L1/L2,
ledger FD mode/offset/unique call, de-duplicated reads, complete external U and
unread faulty content, all-home inclusion, closed namespaces/known limits before
ledger, runtime usage rules, supported checkout after preflight, and complete
erasure on source mutation/limit/close/unlock. Normal/-O suites overlap and are
run sequentially with PYTHONDONTWRITEBYTECODE=1. Exact final counts and independent
agent review belong in the PR after execution, not as anticipated claims here.

Each exact final tree requires independent agent review, complete exact HEAD CI
with all check-runs/workflows and pagination to empty, source-justified skips,
failure/Codecov log inspection, main/composition/threads/ruleset/pins checks,
guarded merge without bypass, then the entire CI of that exact merge. No green
status transfers from #512, a local run, HEAD or a different composition.
