# 3C-1 — Private inventory and own-proof building blocks

SOURCE_ONLY / LAB_ONLY / PARTIAL_IMPLEMENTATION / NO_PUBLIC_POPULATION_SCAN.
Base: `5df6c6c248f3a1aef9b5f8819e18153def16fca5`, tree
`9fb13944121b5cf4b461c2280da4afdafe52638e`. The documentary contract #508
is closed; this is the first small code tranche authorized by Mathieu.

Normative references: [contract](P4_3C_POPULATION_AND_CEILINGS_V0.md),
[107 specification cases](P4_3C_POPULATION_AND_CEILINGS_CASES_V0.json),
[delivery split](P4_3C_PLAN_AND_REUSE_V0.md#8-découpage-gates-et-validation-demandée).
The matrix stays SPECIFICATION_ONLY_NOT_EXECUTED; its 107 cases are not a count
of executed tests and this tranche does not claim to implement the whole matrix.

## What this tranche provides

`_population_inventory.InventorySource` extends the existing FD/content owner,
without replacing the old APIs. It inventories every `individuals/<id>`, up to
65 names, and retains directory/file metadata and listings for revalidation.
The private-entry cap is cumulative (8192), with the existing shared private
content/FD budgets. It validates task/result names using the exact Supervisor
task-ID grammar; opaque task/result/inflight/usage/SQLite payloads are not read.
Records, specs, own qualification/admission/statement and envelopes are acquired
through the existing cache with paths derived from owner IDs and record hashes.

`_population_core` verifies full founder-to-home structure without inventing an
operation for an isolated founder. It compares each descendant with one exact
COMMITTED, its stored spec/record/qualification/admission, all three presented
record/envelope hashes and corresponding DECISION items, and the unique `/1`
admission entry. It reuses existing trust, qualification and R8/C9 comparisons.
Individual absence is distinct from falsification; genuine revocations retain
conservative SUSPENDED counting. Revocation plus a forged signature cannot
suspend. Supported-science failure/absence propagates into the named birth proof;
the cryptographic proof does not PASS merely because frozen hashes match.

All home-proof result fields and collections are immutable; accepted=false,
authorization/completeness/filiation remain NOT_EVALUATED. A local classification
is not a right to become a parent. Public imports and older observer results are
unchanged. Open candidate homes stay explicitly NE, never EXCLUDED_OWN, in this
partial tranche. This avoids exposing a positive incomplete scan.

## Deliberately not yet integrated

There is no PopulationObserver/PopulationConfig/public scan in this tranche.
The future single owner must still validate detached configuration, take L1,
acquire trust and all logs/external claims, build complete U before one ledger
inspection, and run the full derived K/N/P/F preflight before any signature.
The private core checks frozen item caps and lineage bounds but does not replace
that global preflight. Its caller-supplied detached snapshots are not proof of
their own acquisition/stability or complete code closures.

Still required before the full public API: current/historical operation scopes,
OWN after exact D2/D3 and live trust evidence, complete DECISION/POPULATION
partitions and copies, counts/plan/ceilings, fault/termination/action bindings,
quarantine incarnations, full scan aggregation and all-context close invalidation.
The inventory helper must be used inside that owner, not as an independent scan
whose results are combined with a second ledger or trust snapshot.

## Validation

Temporary LAB_TEST fixtures and public test keys only. Local Python 3.12.14;
pytest warns about the unavailable asyncio_mode plugin option. No operational
dataset, registered subject, campaign or product worker is executed.

Targeted command:
`python -m pytest tests/colony_admission tests/colony_trust tests/colony_registrar tests/colony_lab/test_lineage.py -q`

Optimized command:
`python -O -m pytest tests/colony_admission/test_population_core.py tests/colony_admission/test_population_inventory.py tests/colony_admission/test_attestation_core.py tests/colony_admission/test_attestation_projection.py -q`

These suites overlap. Exact final counts and the independent final tree review
are recorded in the PR after the final run, rather than anticipating CI results.
The existing purity test explicitly recognizes the new IO module; the new pure
core retains a closed import allowlist and an additional no-IO/no-public-API test.

P1 raw pins recalculated unchanged:
`e8a125bd67964a01f8a06a5f2d3c50f34e9a154e521dce201cb4fb6d1a40bfcd` and
`4e518bfec6faaa582c2c42633d80e989b8204708b554f74b0eb1bbee6eaa59a1`.
Bounded equivalent code-closure calculation, without importing products:
subject `2c926421416731dc629915067bcea472729e6785ec8dcb6e28f15ae7b41e4ec8`,
evaluator `41b78971184809652dd1190dded49ab27d58c35c8a995351a47bf0f85756faa4`,
pilot `97fb6b0489976f8b003823c1536932ec10a1c7faa699ef6f6eb1bd4056238bc7`;
irregularities `[]`. No qualified source or policy was modified.

## PC2/p1: blocker and possible separate amendment

PC2 is not blocked because its stored campaign failed: the pinned evidence
reports two rounds of 28 cases, PROPOSED_QUALIFIED_SIMULATED and no failure reasons.
The 3B contract §9.2 deliberately has no mapping from pilot-evidence/0 into the
external qualification/0 record. Evidence names the Sentinel worker subject,
the Sentinel evaluator AND the pilot evaluator; qualification/0 has only two
code fields. There is no historical pilot qualification/0 record in this base.

A possible separate profile, NOT approved or implemented here, would bind the
subject ID/spec to `evidence.pilot`, the qualification's subject hash to the
Sentinel worker closure, its evaluator hash to the pilot closure, and separately
require the Sentinel evaluator and parent R8/C9 evidence bindings. The pilot runs
the same worker as Sentinel, with narrower declared lab permissions. None of
these choices should be inferred silently from a valid signature.

That amendment must pin p1 and PC2 raw bytes, define all three code closures,
parent/identity/spec/budget/permission bindings, statement scope and required
present author, and adversarial tests swapping any two hashes or subjects.
PRESENT cannot reuse the R8 rule requiring a historical qualification/0 record
for the pilot: the contract must explicitly specify a native-evidence
re-attestation rule or retain the block. FRESH cannot be claimed from an old
campaign file. No historical issuer, signature, qualification or freshness is
invented. This paragraph is an audit/proposal, not the normative amendment.

Until that separate contract is validated and implemented, PC2/p1 remains
SCIENTIFIC_PROFILE_UNSUPPORTED / NE blocking; p1 remains in g0. This tranche
does not close 3C or step 3/7. #286 ACTIVE; no VPS/runtime/systemd/PPL/FIN/epoch/
production/TESTNET/LIVE/exchange/secret/replay/diagnostic campaign, trust
installation, birth, recovery or operational writer changes.
