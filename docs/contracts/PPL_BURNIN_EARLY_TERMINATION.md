# PPL-BURNIN-EARLY-TERMINATION — source review contract

Verdict scope: candidate source and isolated tests only. No runtime authority.
Target: `BURN-IN-EPOCH-01-20260926T064144Z`.
Operator request permits preparation of early termination, not production mutation.
GitHub #285 and #286 remain authoritative; #286 is ACTIVE.

## Audit before implementation

GitHub comparison and local full-history comparison on 2026-10-10:

- Historical runtime: `116634be0d3c015cce1cfa58be7da7255414fbfd`.
- Audited main: `8c0dc27fbe456834423e8543c8ff30d657ec2d86`.
- Baseline is the merge base; main is ahead by 244 commits, behind by zero.
- `git diff --name-only BASE MAIN` has 256 paths. GitHub compare stats are
  incomplete for large responses; the clone is used for exhaustive comparison.
- No diff in `paper_trading/`, `core/advisor_loop.py`, `financial_institute/`
  or `research_data/`. Changes include observability, operator decision storage,
  Research presentation/publication, frontend, dependencies, CI and governance.
- Current GitHub #285 reflects L3/U7; CURRENT_TASK and developer-entrypoint
  contain older dated state. They are navigation references, not fresh runtime evidence.
- No AGENTS.md was found in the repository. CLAUDE and developer-entrypoint read.

Contracts inspected: PPL-02B durable store, PPL-02E-R4 cutover/rollback,
PPL-RECOVERY-01 financial replay; existing burn-in finalization implementation.
No VPS observation, current position count or deployed SHA is claimed.

## Complete OPEN route inventory at audited source

| Route | Creation and persistence | Fence outcome |
|---|---|---|
| Advisor PAPER MARKET → MexcSimulator | `_fill_market_ppl_authority` → `PPLAuthorityRuntime.commit_open` → semantic validation → `DurableEventStore.append` | New target OPEN denied; simulator returns REJECTED without capital/position change |
| Direct authority caller / retry | `commit_open` | Same durable fence; exact persisted retry allowed |
| SHADOW observer | `PPLShadowRuntime.observe_open` → `_append_semantic` → store | Same target fence; observer can degrade; no claim to stop a legacy simulator |
| Offline legacy import | `build_legacy_import_plan` constructs OPEN; `apply_legacy_import_plan` appends | Same target fence; bridge is not transactionally all-or-nothing |
| Arbitrary store caller | `LedgerEvent` or `make_position_opened_event` → store | Same target fence, schema v1 and v2 |
| Visual fixture | `scripts/generate_fin02_visual_fixture.py` uses OPEN constructor | In-memory construction is not persistence |
| Legacy PAPER writers | MexcSimulator legacy path and Advisor PaperTradeRecorder | OPEN journal entries are not authoritative PPL POSITION_OPENED; never a permitted fallback |

A constructor and pure replay can represent old facts; they are deliberately
not admission enforcement points. FIN, Research and passive projections consume
OPEN facts without authoring PPL truth. A direct filesystem writer or an old
binary can bypass a Python API; exclusive writer provenance must be proved at
the future runtime gate. Enumerating source paths is not proving runtime users.

LIMIT and STOP_LIMIT already reject under PPL_AUTHORITY. The pending fill path
also enters `_fill_market_ppl_authority`. The central rejection catch covers
public MARKET and internal pending fills. CLOSE/TP/SL/TIMEOUT and expired
restart UNRESOLVED continue through their existing durable-first paths.

## Admission and governance model

This is a deliberately one-way, epoch-specific fence, not a general toggle.
Installing this source candidate changes target admission immediately to DENY.
Missing, unreadable, malformed, removed or stale governance receipts cannot
permit OPEN. There is no environment override, ALLOW mode or reopening API.
Other epochs retain their existing behavior. The future epoch is not enrolled,
created or authorized by this change.

The runtime gate must therefore authorize **installation of the fence** as the
activation step. Writing the receipt alone under the old baseline has no effect
and must not be presented as activation. This mission installs neither.

`seal_burn_in_admission` is an explicit-root, offline/operator API. It uses the
same exclusive flock as append and checks exact current sequence plus SHA-256
of the canonical stream before publishing `burn-in-drain-receipt.json` at the
store root. It captures epoch birth (capital/code/config), operator, GitHub
decision URL, explicit UTC decision time and DRAIN_ONLY. It never writes a PPL
event or changes an epoch manifest/config. Receipt creation is O_EXCL, mode
0600, file fsync plus parent fsync. Exact retries reconfirm durability; conflicting
or partial receipts are preserved and rejected. No import-time I/O, network,
production path or wall-clock lookup exists.

The URL is syntactically validated, not remotely authenticated. The operator
must verify actual GitHub approval, actor permissions, reviewed code SHA and
runtime provenance in the separate gate. A string is not a signature. This API
is not wired to Advisor, Research, an automatic job or the GET-only Operator API.

Admission is evaluated under the store lock after exact identity/collision
handling and before new append. Exact persisted OPEN retry returns ALREADY_EXISTS
and does not enlarge the population, even if its position is already terminal.
Different content with an existing event ID remains a collision. CLOSE never
consults the admission receipt. Concurrent receipt/CLOSE can either publish at
the old boundary or reject a stale request; recapture rather than repair.

## Risks and limits requiring review

- The frozen baseline cannot hot-load this implementation. Under the current
  no-VPS/no-restart/no-runtime-mutation constraints, actual activation and final
  Research designation are BLOCKED. No workaround via PB_MAX_POSITIONS exists.
- An old writer in memory ignores the fence and its control receipt. Mixed
  versions and direct file writes must be excluded by operational evidence.
- flock/fsync guarantees assume cooperating processes, stable paths, a local
  filesystem supporting their semantics and no malicious root actor. NFS,
  lock-file replacement, storage loss and hostile directory mutation are outside
  the demonstrated model. Protect root ownership and paths at the runtime gate.
- Receipt deletion loses audit evidence but cannot restore OPEN in this binary.
  Archive its hash and bytes on GitHub. File-sync failures are ambiguous until
  retry/read-only inspection; no success is returned, admission remains denied.
- An exact receipt retry after a subsequent CLOSE uses a stale boundary and
  rejects. Preserve the original receipt and inspect it; do not replace it with
  a later boundary. Partial receipts require a separate evidence-preserving
  remediation decision. None is automatically removed.
- The fence serializes new OPEN admission with receipt publication; it does not
  make the entire runtime read-project-append sequence a multiprocess transaction.
  Existing sequence/identity guards can reject competing lifecycle commits;
  one authoritative runtime writer remains a prerequisite.
- Pure replay preserves historical OPEN. Do not confuse construction, projection
  or exact retry with admission of a new position.
- The receipt attests a fenced boundary, not zero pending/transitions, financial
  reconciliation, terminal status, stopped authority or a final dataset.
- UNRESOLVED retains principal and unknown outcome. Zero OPEN does not prove
  all outcomes known, FIN reconciled, or experimental success.
- Existing final designation requires authority_process_stopped=True. An
  admission fence does not satisfy that boolean. No invented quiescence proof.
- Early termination changes the sampling/stopping protocol. Record operator
  rationale and selection bias; results remain an early-terminated population,
  not evidence of the original planned duration or a successful stress test.

## Validation scope

New synthetic proofs cover direct-store admission, historical exact retries,
missing/corrupt/deleted/symlink receipts, immutable boundaries, invalid governance,
file and directory sync failure, independent-process seal/OPEN/CLOSE races,
simulator admission with preserved capital and subsequent CLOSE, expired recovery
as UNRESOLVED, unaffected other epochs, and exact PPL/FIN replay.

See [runbook](../runbooks/PPL_BURNIN_EARLY_TERMINATION.md) and the dated
[validation report](../audit/PPL_BURNIN_EARLY_TERMINATION_VALIDATION.md).
