# 3C-2a — Private pre-ledger log acquisition phase

SOURCE_ONLY / LAB_ONLY / PARTIAL_IMPLEMENTATION / NO_PUBLIC_POPULATION_SCAN.
Prepared independently while the exact merge CI of #509 is pending. Remote base
is `main@b7d010d94e04a6a9491ec241ea0da13820e486f9`, tree
`64a9faa76822f73fea5cf903f488bcbcd80f9bf1`. The local parent is the equivalent
`70ddf709f9c9f24207bf2d7fbc728b6ba919257a` tree; it is not claimed to be the
remote merge commit. No early merge or closure of 3C-1 is authorized by this work.

Normative references: [3C contract](P4_3C_POPULATION_AND_CEILINGS_V0.md) §3, §10,
§12; [matrix](P4_3C_POPULATION_AND_CEILINGS_CASES_V0.json),
[plan](P4_3C_PLAN_AND_REUSE_V0.md) §8;
[private inventory/core](P4_3C_INVENTORY_CORE_DELIVERY_V0.md).
The matrix's 107 cases remain SPECIFICATION_ONLY_NOT_EXECUTED. This delivery is
one smaller private phase toward the single acquisition owner, not that owner.

## What this phase establishes

`_population_log_acquisition.acquire_logs` borrows the caller's retained
InventorySource and lab FD. The future enclosing owner must validate detached
configuration, hold L1, acquire current trust/fault bytes once and keep the same
ExitStack/FD/cache lifetime through all phases, validation and successful close.
No caller-supplied status or fabricated FaultProjection selects unread logs:
strict project_fault_log on already-acquired raw bytes derives all external IDs
and exactly targeted prior OPERATION_LOG fault/termination pairs.

- Bound and retain the complete `admission-ops/` inventory (256 names), rejecting
  any unknown namespace. Parse every unexcepted log and every historical attempt
  strictly through the existing parser/prefix helper, with lab/child/digest binds.
- Construct sorted U from all readable PREPARED hashes and all valid external
  claim hashes, including external/0 and absent faulty logs. Bound readable
  attempts and the combined U at 256 before any future ledger opening; bound
  known frozen items by the operator-policy cap supplied by the enclosing owner.
- For a correctly targeted external claim, never read the faulty log content,
  even for external/0 or a future failing terminal linkage. Retain only private
  regular/single-link metadata or stable open-ENOENT absence. Per-log and shared
  log byte limits remain bounded from size metadata; arbitrary names do not
  exempt unrelated corrupt/torn logs. ENOENT after open is an error, not absence.
- Preserve immutable attempt bytes/projections, opaque claim bytes and separate
  unread coverage. Every unread log's terminal_linkage stays NOT_EVALUATED.
  pending_from_readable_logs is explicitly only that subset, never a complete
  pending-operation verdict. accepted=false, snapshot_completeness/external_facts
  permanently NE in this phase.

It performs **no ledger opening, ledger inspection or signature verification**,
no trust installation, terminal reconstruction, home acquisition or classification.
It never sets terminal_linkage PASS or releases OPERATION_PENDING. It does not
call or change older observe/scan/scan_evidence/scan_attestations behavior. Only
the existing architecture test's explicit IO-module list is extended; all pure
modules retain their allowlist. No public export or API is added.

## Still required before any complete scan

The next owner must call this phase once within the single context, acquire the
complete global private inventory and all structure-known limits, then inspect
exactly one fresh offset-zero ledger FD under L2 using the returned U. It must
compare current findings to external claims before treating any termination as
established; external/0 and legacy ambiguity remain blocking.

Acquire all homes/branches/envelopes/checkout with shared caches; derive the
complete K/N/P/F preflight before the first signature; only then wire the private
proof core. No public PopulationObserver or positive global result before OWN,
current/historical partitions and all copies, counts/plan/ceilings, fault scopes,
external findings, quarantine/action incarnations, aggregation and whole-context
revalidation/close invalidation are implemented and reviewed. Do not concatenate
this phase's output with results from a second scan or ledger snapshot.

## Validation and gates

Temporary LAB_TEST fixtures, no products or campaigns. New adversarial tests cover
normal historical attempts, external/0 and /1 with historical counts0/1, unread
corrupt/absent log content, exact fault/claim binds, union256/257 with absent logs,
namespace/count/byte caps, metadata permissions/types, open-versus-post-open ENOENT,
mutated listings/absence/path, ACK fragments with CR, strict corruption, immutability,
close failure and old public-API absence. The raw historical count never becomes
a current ledger proof. Normal and optimized runs are sequential without bytecode.
Exact counts, lint and independent final tree review are recorded in the PR after
execution, not anticipated here.

Before merging this tranche: full exact merge CI of #509 must be favorable and its
private closure recorded. Then own final tree review, exact HEAD checks filter=all
and workflows all events/statuses with exhaustive pagination, logs/skips/coverage,
threads/ruleset/main/composition/pins. Guard expected_head_sha, no bypass, then
all CI of the exact merge. Neither a local suite nor prior HEAD CI transfers.

PC2/p1 remains SCIENTIFIC_PROFILE_UNSUPPORTED/NE blocking; #510 is a distinct
proposed amendment awaiting normative adoption, not a new source profile here.
P1/pins/formats/g0/colony_lab/sentinel_activity/colony_pilot unchanged.
accepted=false; #286 ACTIVE; 3C and step3/7 open. No VPS/runtime/systemd/PPL/FIN/
epoch/production/TESTNET/LIVE/exchange/secret/replay/diagnostic campaign/birth/
installation/recovery or operational writer. Rollback source only.
