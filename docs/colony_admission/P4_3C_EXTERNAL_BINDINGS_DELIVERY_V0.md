# 3C-2d — Private current-ledger external terminal bindings

SOURCE_ONLY / LAB_ONLY / PARTIAL_IMPLEMENTATION / NO_PUBLIC_POPULATION_SCAN.
Prepared on the reviewed #513 acquisition tree
`121e574ff8203329d507093635f8a8bc05a95ae2`, while its MAIN CI is pending.
Local parent4a0fa9a48bbb6cf89051f8633f8563db0479f463 and remote parent
c045c6a76222379ee3c854d98cb8f971aaf489b3 share that tree, not a commit SHA.
This dependent delivery cannot merge before #513's private closure after its
own complete merge CI. No prior green transfers to this tree.

References: [3C contract](P4_3C_POPULATION_AND_CEILINGS_V0.md) §3, §10–12;
[plan](P4_3C_PLAN_AND_REUSE_V0.md) §8;
[log phase](P4_3C_LOG_PHASE_DELIVERY_V0.md),
[preflight](P4_3C_PREFLIGHT_DELIVERY_V0.md) and
[owner](P4_3C_ACQUISITION_OWNER_DELIVERY_V0.md).
The107matrix cases remain SPECIFICATION_ONLY_NOT_EXECUTED, not a test count.

## Narrow property integrated in the one owner

`_population_external.link` is a private pure comparison on retained fault bytes,
lab ID, exactly the owner's sorted U and its one current ledger batch. It opens
nothing, imports no submitted code and calls neither a log parser nor signature
verification. Detached inputs do not prove acquisition or authenticity by their
existence. The strict batch shape/rows/U/counts/flags/digest consistency is checked
before any binding can be favorable. Rows must cover U exactly, with no missing,
extra, duplicate or late ID. A malformed batch is a fundamental source failure,
not an excuse to salvage favorable rows. Tuple/row counts are bounded at256 and
the detached batch bytes at16MiB; limits have fixed names.

Faults are reprojected with the existing strict parser: exact preceding
OPERATION_LOG fault, target, child/op/attempt, fault hash, terminal schema/code,
historical embedded observation hash and closed finding shape remain required.
The /0 reference-only external format always stays NE/unresolved, even if a
current row appears compatible. No historical observation is fabricated.

For /1 embedded evidence, match current status, operation_entries and the ENTIRE
consumed/1 entry (issuer_id, envelope_id, envelope_sha256, operation_sha256).
NO_OPERATION_ENTRY requires zero current and zero legacy; current legacy ambiguity
stays NE. A changed specific finding or conflict is FAIL. A specific PRESENT row
with the exact entry can match even if other legacy rows exist, while the whole
ledger coverage remains LEGACY_UNBOUND and blocks any future favorable scan.
Historical ledger SHA and total_entries are not compared to current SHA/total:
unrelated later ledger entries do not change the per-operation finding. Such
unexplained current entries still make whole-ledger coverage UNBOUND.

A named terminal_linkage PASS establishes only ABANDONED or FAILED_CONSUMED as
an observed terminal fact. OPERATION_LOG_FAULTY is retained. It does not establish
a birth, COMMITTED, BirthPlan, D2/D3, durability, fault clearance, home identity or
action completion. Those fields remain NE. In particular a terminal home still
present must be classified UNAUTHENTICATED by the later home-proof integration;
this delivery does not classify it or silently discard it.

The existing owner calls this comparison just after its single ledger inspection,
within the SAME ExitStack/InventorySource, before the global preflight and any
future crypto. Only positively bound external IDs are removed from the unresolved
IDs passed to that preflight, allowing a uniquely known readable current open
operation to derive its structural bounds. /0, mismatch and legacy ambiguity still
prevent that selection. No global pending verdict is published: pending_completeness
remains NE, and the old readable-only pending subset remains explicitly partial.
The earlier LogInventory/UnreadLog frozen facts keep their original permanent NE
fields; the new comparison has separate immutable facts, not mutated old claims.

The same batch supplies whole-ledger coverage: sum distinct U rows, require zero
legacy/zero unmatched/no conflict for MATCH. External rows can explain ledger
entries without proving a birth. No second query, hidden ledger scan or ID recovery
from a faulty log occurs. All faulty content remains unread for PASS, FAIL and NE.

New facts are retained only inside the owner's provisional result and are erased
with EVERY other payload on failed acquisition/validation/verify/close/unlock.
The top Acquisition terminal_linkage/population/OWN/counts/ceilings/completeness/
authorization remain permanently NE, accepted=false. ACQUIRED is acquisition only.
Older public observe/scan/scan_evidence/scan_attestations modes retain their
conservative external refusal and are not redirected through this private mode.

## Still required

The proof core must still be wired inside this owner after the complete global
preflight and before revalidation/close/restitution. Fault-resource scopes,
current/terminal child classifications, exact OWN D2/D3/current /1/DECISION,
partitions/all copies, historical versus current completeness, classified counts/
plan/ceilings and quarantine/action/incarnation correspondences remain required.
No global PASS/public PopulationObserver is exposed before the full proof.

Tests use detached and temporary LAB_TEST fixtures, public test keys and opaque
faulty logs. They cover exact /1 zero/one rows, later unrelated ledger entries,
all full-entry swaps, /0 unknown references, current conflicts/legacy ambiguity,
malformed source batch/U, whole coverage, immutable facts, same-owner ordering,
one ledger inspection/no faulty read and all-context erasure. Normal/-O runs are
sequential without bytecode, overlapping. Final exact counts, meaningful mutants
and independent agent review belong in the PR after execution, not promised here.

Gate: final exact-tree independent review; #513 private closure; retarget MAIN;
source-relevant exact HEAD CI/checks/workflows paginated to empty, logs/skips/Codecov,
threads/ruleset/main/composition/pins; guarded merge with expected head/no bypass;
then all CI of the exact merge before private3C-2d closure. No blind rerun or source
edit to make a qualified tree green.

P1/pins/formats/g0 and colony_lab/sentinel_activity/colony_pilot are unchanged.
PC2/p1 remains SCIENTIFIC_PROFILE_UNSUPPORTED/NE blocking, #510 not adopted,
p1 stays in g0, #286 ACTIVE, 3C and step3/7 open. No VPS/runtime/systemd/PPL/FIN/
epoch/production/TESTNET/LIVE/exchange/secret/replay/campaign/birth/installation/
recovery or operational writer. Rollback is source only.
