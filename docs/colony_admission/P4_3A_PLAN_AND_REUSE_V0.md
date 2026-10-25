# 3A — Validated scope, reuse audit and decisions

2026-10-25, America/Mexico_City. SOURCE_ONLY / CONTRACT_FOR_REVIEW / NO_IMPLEMENTATION.
Baseline main `e566e51ecd67ec6444eca577202a9d18d1ad0b5d`, tree
`b20f487c8170422aa99bc489b2775e765bc7d76e` rechecked in GitHub.
The operator's current instruction validates the 3A plan and requests its contract before code.
It does not validate 3B/3C implementation, deployment, qualification or any real birth.

## Roadmap and acceptance boundary

| Work | Current state / next gate |
|---|---|
| Step 1 / #500 | CLOSED, selected-candidate source reader |
| Step 2 / #501 + #502 | CLOSED, inventory/one ledger read plus ACK/CR correction; exact main CI 24 checks / 19 workflows SUCCESS |
| Step 3A scope | VALIDATED by operator; contract and case matrix drafted for review, code not started |
| Step 3B | Planned only: complete required attestations, signatures and ancestors |
| Step 3C | Planned only: exhaustive population classification, ceilings and object correspondences |
| Steps 4–7 | Unchanged: durable controller, explicit recovery, P5/P6, operations/first agent role preparation under separate gates |

The 2026-10-24 standalone audit was a proposal and still recorded the then-open ACK/CR issue.
This record supersedes those historical status paragraphs for the current repository scope.
Step 2 closure: https://github.com/3a7i3/crypto-ia-terminal/pull/502#issuecomment-6395340869.
The underlying CI skips/xfails and supplemental Codecov transport limitation remain documented
there; source CI is not runtime or sandbox qualification.

## Verified reuse inventory

| Existing source / contract read | Reuse | Concrete limit to preserve |
|---|---|---|
| `colony_admission/observer.py` | Config, acquisition owner, source stamps, L1 and final descriptor/path/close checks | Existing scan/observe API and outputs stay unchanged |
| `formats.py`, `oplog.py` | Canonical log format and strict machine, historical attempt boundaries | AttemptSummary alone is not full frozen material; preserve physical LF boundaries and original reserve positions |
| `trust.inspect_operations_fd` | One strict 16 MiB/16384-entry snapshot under shared L2 | At most 256 requested IDs; caller owns newly opened O_RDONLY FD and successful close |
| `trust.check_bundle`, `verify_consumed`, `_spend` | Semantics to reuse later in 3B | Existing path APIs reopen ledger / take L2; not used inside 3A's one-read acquisition |
| Registrar `BirthPlan`, `_prepare`, `commit` and amendment 3 | Frozen inputs, canonical admission equality, conflict and write-step boundaries | No prepare/commit call in the diagnostic; policy/ceiling decisions remain separate |
| `Supervisor._dump`, `load`, `admit`; lineage validators | Existing byte encoding and identity/qualification conventions | No qualified source edit, lab call or SQLite access; do not confuse identity matches with complete lab verification |
| `external_evidence.py` | Structural fault/policy/history readers | Sticky faults and external-termination limits stay blocking; no rotation/restore gate inferred |
| P1 sections 3, 6–8, 13 and 122 pinned scenarios | Controlling proof/state/limit requirements | New contract adds no P1 edit and is not a complete controller |

No available code currently implements the complete physical join, full population admission
guard or durable controller. Reuse the existing acquisitions/parsers instead of rebuilding
trust, registrar or the qualified lab. This is a source audit, not a VPS inventory.

## Decisions frozen for review

| ID | Decision / reason |
|---|---|
| 3A-D01 | New no-argument scan_evidence diagnostic shares one acquisition; existing public methods retain behavior |
| 3A-D02 | Request every historical/current operation, cap 256 before ledger open; larger histories explicitly block rather than reread or silently enlarge trust's contract |
| 3A-D03 | Strict ledger parse + unique all-attempt ID set + zero legacy + entry-count equality detects unbound rows without a new trust export API; unknown row identities are not invented |
| 3A-D04 | Keep frozen-hash D1 binding distinct from full stored-envelope identity binding; the latter may be unavailable before D2 |
| 3A-D05 | Make birth-material directory ownership explicit: child namespace; qualification/statement subjects remain parent. This refines previously underspecified P1 path mapping, not an installed writer |
| 3A-D06 | Compare D2 canonical record identities, D3 writer bytes, and stamp raw-byte hashes separately; no storage-format migration |
| 3A-D07 | Compare old attempts' D1 only; latest child material does not retroactively belong to an older REFUSED/ABANDONED attempt |
| 3A-D08 | Completed D3 excludes usage content, while initial D3 compares initial usage; prefix files are not recoverable partials |
| 3A-D09 | Observe only bounded selected layout and journal metadata; SQLite/task/result content, recovery and terminal relocation remain unqualified |
| 3A-D10 | Missing bound roots are unavailable; only stable absence under acquired parents is an absence fact |
| 3A-D11 | Fixed 32 MiB D2/D3 content, 4096-FD and namespace caps fail closed; they are diagnostic capacity limits, not retention policies |
| 3A-D12 | Every result remains accepted=false, with explicit coverage; no signature/attestation/population/ceiling/durability PASS |

Decisions D02, D05, D06 and D09 require particular attention in independent contract review:
they set supported capacity, storage mapping, equality modes and proof coverage. If review finds
a conflict with P1, revise this unpinned draft before implementation; never edit the pinned P1.

## Deliverables and gate

- [Contract](P4_3A_PHYSICAL_EVIDENCE_JOIN_V0.md): acquisition, limits, history/ledger coverage,
  D1/D2/D3 comparisons, result states and exclusions.
- [Case matrix](P4_3A_PHYSICAL_EVIDENCE_CASES_V0.json): future test obligations and P1 references,
  no executable campaign or fabricated pass count.

This PR contains documentation only. Validate JSON, IDs, references, links, pins, source hashes
and scope. Do not add a test that only mirrors prose. Independent final-tree contract review
and exact CI/composition checks are required before treating this draft as implementation-ready.
Publication before code is traceable; publication alone is neither approval nor qualification.

The later implementation must supply the matrix's real-file/adversarial tests, old-reader
regressions, ledger instrumentation, exact-tree independent review and final CI before its
guarded merge. Step 3 remains open after 3A. Rollback of this contract-only slice is source
revert, with no data or format migration. No additional source approval is requested for
work already in the validated 3A scope; 3B/3C remain separately scoped.
