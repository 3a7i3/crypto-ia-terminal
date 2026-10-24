# Operation-only ledger inspection contract, version 0

Status: SOURCE_ONLY / LAB_ONLY / CONTRACT_BEFORE_CODE / READ_ONLY.
Baseline: main `c1b7f4925925f23ae510d1d72df6931b7fd280c5`, after #495.
No function, writer, termination, key, record, individual or runtime is introduced.
P1 `ADMISSION_CONTRACT.md` and its 122 scenarios remain unchanged. #286 stays ACTIVE.

## 1. Problem and reuse

`inspect_consumption(envelope, ledger, operation_sha256)` (#492) requires a complete expected
admission envelope. It distinguishes a matching envelope from foreign/legacy consumption.
When PREPARED is unreadable, the controller cannot recover that envelope by rereading the
faulty operation log. #495 correctly blocks termination without another reviewed evidence
source. Supplying an arbitrary envelope does not solve the provenance gap.

Proposed new API:

`inspect_operation_consumption(ledger: pathlib.Path, operation_sha256: str) -> dict`

It counts ledger entries bound to exactly one operation, without accepting an envelope,
root, authorization, fault-log contents or action argument. It must reuse the existing
strict /0-/1 parser and same-inode shared lock. It neither replaces nor changes the
contract/behavior of inspect_consumption, consume, check_bundle, verify_bundle or
verify_consumed. No ledger schema, migration or repair is introduced.

The caller obtains the operation digest from the independently acquired, constructor-bound
external fault log. A digest supplied by an individual is never sufficient. The inspector
itself validates only its lexical shape (64 lowercase hexadecimal characters); it cannot
prove that the digest belongs to this lab, child, attempt or permission. These are later
controller/observer obligations. They do not become function parameters that assert PASS.

## 2. Closed observation format

Every return has exactly:

| Field | Rule |
|---|---|
| `inspection_schema` | `colony-trust.operation-inspection/0` |
| `status` | One closed status below |
| `operation_sha256` | Valid requested digest, or null for invalid digest |
| `operation_entries` | Number of matching /1 entries after a complete valid read, otherwise null |
| `legacy_entries` | Total /0 entries after that read, otherwise null |
| `ledger_entries` | Total /0 and /1 entries after that read, otherwise null |
| `ledger_sha256` | SHA256 of the exact full bytes read and parsed from the same descriptor, otherwise null |
| `entry` | The unique matching /1 entry for OPERATION_ENTRY_PRESENT only; otherwise null |
| `failures` | Closed symbolic codes; empty on the two uncomplicated observations |
| `accepted` | Always false |
| `authenticity`, `authorization`, `completeness` | Always NOT_EVALUATED |
| `provenance`, `durability` | Always NOT_EVALUATED |

Counters are integers excluding bool. The returned unique entry is a detached JSON object
with exactly existing /1 fields: ledger_schema, issuer_id, envelope_id, envelope_sha256,
operation_sha256. No complete envelope, signature, record contents, filesystem path,
exception text or unrelated entry is returned. Mutation of the returned dict cannot change
any stored state or future result. JSON serialization is canonical when hashed for evidence.

`ledger_sha256` is a snapshot fingerprint, not a MAC, root pin, integrity chain, source proof,
fsync result, durable reservation or statement of current ledger state after the call.
Hash and counts describe one complete read only; they must not combine separate reads.

| Status | Meaning |
|---|---|
| NO_OPERATION_ENTRY | Entire existing private ledger valid, zero matching /1 entries, zero /0 entries |
| OPERATION_ENTRY_PRESENT | Entire ledger valid, exactly one matching /1 entry (possibly other /0 entries elsewhere) |
| LEGACY_AMBIGUITY | Entire ledger valid, zero matching /1 entries, at least one unbound /0 entry |
| CONFLICT | Entire ledger valid, more than one distinct entry bound to this operation |
| LEDGER_MISSING | Final ledger file absent in an existing real parent; not an empty observation |
| LEDGER_CORRUPT | Existing private regular/single-link check fails or any strict parser rule fails |
| LEDGER_UNAVAILABLE | Invalid path, absent parent, I/O/permission/close failure or inspection limit |
| LEDGER_BUSY | Nonblocking shared lock cannot be acquired because a cooperating writer holds it |
| INVALID_INPUT | Invalid operation digest, rejected before any ledger open |

Precedence after the ENTIRE read: multiple matching entries -> CONFLICT; exactly one ->
OPERATION_ENTRY_PRESENT; zero with any /0 -> LEGACY_AMBIGUITY; zero without /0 ->
NO_OPERATION_ENTRY. A later malformed/truncated line overrides an earlier valid match.
For those four full-read statuses, all counts and ledger hash are present, and:
`0 <= operation_entries + legacy_entries <= ledger_entries <= 16384`.
Only OPERATION_ENTRY_PRESENT has a non-null entry, whose operation digest matches input.
For every failed/incomplete read (including missing, busy, limits and close errors), all
counts/hash/entry are null; no valid prefix or partial count is exposed as usable evidence.

Failures are empty for NO_OPERATION_ENTRY and OPERATION_ENTRY_PRESENT. CONFLICT has
OPERATION_MULTIPLE_ENTRIES; LEGACY_AMBIGUITY has LEGACY_OPERATION_UNBOUND. Other codes:
OPERATION_INVALID, LEDGER_MISSING, LEDGER_CORRUPT, LEDGER_UNAVAILABLE, LEDGER_TOO_LARGE,
LEDGER_BUSY. A limit is status LEDGER_UNAVAILABLE with failure LEDGER_TOO_LARGE.
The operation digest remains present after an I/O failure when its input was valid.
An invalid ledger argument with a valid digest is LEDGER_UNAVAILABLE without an open.

## 3. What zero, one and legacy entries do not prove

NO_OPERATION_ENTRY means no /1 entry is bound to this digest. It DOES NOT mean the unknown
expected envelope has never been consumed: it might belong to another operation. A later
birth must still use normal trust/envelope replay checks. Neither this observation nor an
ABANDONED classification releases, refunds or recreates an authorization.

A /0 entry has no operation binding. With no matching /1 and no expected envelope, the
inspector cannot establish whether that legacy consumption belongs to the interrupted
birth. Thus LEGACY_AMBIGUITY cannot support an unspent finding or an automatic termination
as ABANDONED. No migration or inference from issuer/name/order/time is permitted. A future
reviewed provenance gate may resolve it; this contract supplies none.

One /1 entry proves only that a strictly parsed line claims this operation digest. Without
an expected envelope, OPERATION_ENTRY_PRESENT is deliberately weaker than the existing
CONSUMED_BY_OPERATION result. It is never reported as that status and never substitutes for
inspect_consumption or verify_consumed during ordinary admission/resume/ancestor checks.
For an explicit conservative termination only, an observed bound consumption can keep the
authorization spent without authenticating the envelope. Other /0 entries do not undo it.

Two or more matching /1 entries are ambiguous even when their envelope hashes are equal.
Duplicate (issuer_id,envelope_id) keys remain LEDGER_CORRUPT under the shared parser; they
are not counted as a legitimate CONFLICT. Unrelated entries must still parse strictly.
No matching entry is selected as "first wins" or "last wins".

## 4. Read boundary and error precedence

Validate the digest before any filesystem access. Use an O_RDONLY descriptor with
O_NOFOLLOW on the final component, O_NONBLOCK, no O_CREAT/O_APPEND and nonblocking
LOCK_SH on the same inode used by consumers. Before reading, fstat requires a regular,
single-link file in mode0600. The existing final-component and parser rules remain controlling.
Missing parent and a non-real parent are unavailable, never ledger absence.

At most 16MiB and 16384 entries, reusing the existing inspection constants. Enforce file-size
and streamed-byte bounds and entry count, then strict canonical newline-terminated JSON,
closed /0-/1 fields, names/digests and duplicate-key rules. No early return at zero or one
matching entries. Closing or reading failure discards all provisional observations and
returns LEDGER_UNAVAILABLE. Unlock/close faults cannot preserve a successful count/hash.
Symlink/device/FIFO/private-mode/I/O failures must never return NO_OPERATION_ENTRY.

No writable descriptor, lock-file creation, write, fsync, chmod, mkdir, rename, truncation,
repair, signature verification, source file execution or callback. OS atime updates are not
content/namespace writes. The inspector takes only L2; it never takes L1. The controller
holds L1 when it needs transaction-wide consistency, and never acquires L1 while holding L2.

The trusted caller binds the ledger location and its parent namespace. Parent replacement,
noncooperating writers, operator edits/truncation/restoration, inode replacement outside
cooperating locks, privileged compromise and dishonest storage remain NOT PROVEN. A bare
JSON observation is never source-authenticated merely because it has the right shape/hash.
A future observer must acquire it directly through the trusted code/path, under the required
locks, not accept it from agent output or a termination request.

## 5. P4 compatibility without changing meanings

The #495 `colony-admission.fault-entry/0` TERMINATED_EXTERNALLY format names the stronger
inspect_consumption statuses. Its existing fields/statuses are NOT reinterpreted. In
particular, NO_OPERATION_ENTRY must never be relabeled ABSENT_IN_VALID_LEDGER and
OPERATION_ENTRY_PRESENT must never be relabeled CONSUMED_BY_OPERATION.

Before a termination writer uses this new API, it must use the explicitly versioned
`colony-admission.fault-entry/1` extension specified here. It retains exactly the /0 outer
keys, scopes and event-specific rules, except:

- `schema` is colony-admission.fault-entry/1;
- TERMINATED_EXTERNALLY.data.ledger_finding has exactly `inspection_schema`, `status`,
  `operation_entries`, `observation_sha256`, `observation`;
- inspection_schema is colony-trust.operation-inspection/0; allowed status/count pairs are
  NO_OPERATION_ENTRY/0 or OPERATION_ENTRY_PRESENT/1; no legacy/conflict/missing/error status;
- observation_sha256 names the canonical COMPLETE acquired observation, with its original
  operation digest, counts, ledger snapshot hash, entry and NOT_EVALUATED fields intact.
  `observation` embeds that complete detached JSON object, not a path or an unavailable
  digest-only reference. Its canonical digest must equal observation_sha256; its digest,
  operation, status/count and immutable NOT_EVALUATED/accepted fields are all checked
  against this finding and the original bound fault. The redundant status/count fields
  must agree exactly. The finding plus outer entry must fit #495's 16384-byte line bound;
  overflow refuses the write, never truncates or drops the observation.

This is a versioned format extension for future code, not an implemented writer. A future
external-log reader must explicitly recognize /0 and /1, validate each version's own
semantics, and reject unsupported/mixed-version fields. It may not skip unfamiliar lines.
Other /1 events keep /0 data rules. Fault-entry digests include the versioned schema in the
canonical bytes. All P1 controls still apply, including exact original fault/operation/child
binding, sticky faults and no reading/retrying the faulty operation log.

Only an explicit operator termination under L1, with an independently acquired matching
OPERATION_LOG fault, may use the two allowed observations. NO_OPERATION_ENTRY supports a
claim that this operation consumed no /1 line (ABANDONED); it grants no envelope reuse.
OPERATION_ENTRY_PRESENT supports conservative FAILED_CONSUMED. Other statuses leave
termination blocked; current unavailable evidence cannot be turned into a terminal finding.
A count/hash alone, a caller-supplied finding, or a previously cached observation is not a
current acquisition. Before the durable terminal record is written, the observer must retain
L1 and use a newly acquired result for this same operation and bound ledger location.
The resulting /1 terminal entry durably carries the complete observation in the same
canonical fault-log line, subject to the later writer's durability protocol. No second
observation store or implicit lookup by digest is assumed.

On subsequent calls, the observer acquires the fault log and validates the embedded
observation as HISTORICAL evidence: exact schema/field closure, own canonical hash,
operation/fault binding and allowed status/count. It must not compare its ledger_sha256
against today's ledger or recompute its digest from a new inspection; legitimate later
consumptions change the snapshot. That historical evidence supports only the already
recorded terminal classification and exclusion of this faulty log. It is not reused as
a fresh observation for another action or birth. Current ledger/global/directory faults
are acquired and enforced separately and are never cleared by a historical terminal entry.
An absent/corrupt embedded observation blocks that terminal override; no healthy-prefix
assumption or fallback reconstruction is allowed.

Terminating does not clear the ledger/directory fault or make the child usable; external
set-aside still requires independently bound expected identity bytes, D3 provenance and
P1's name/link/prefix checks. This contract supplies neither that identity source nor a
termination implementation. No admission, COMMITTED or execution permission is inferred.

## 6. Acceptance and delivery

The companion OPERATION_LEDGER_INSPECTION_CASES_V0.json fixes observable acceptance cases.
Implementation, later: extend only colony_trust and its tests/docs, reuse existing lock and
parser, and preserve their default behavior for all callers. Publish this contract before
code. Exact-SHA independent review, targeted regression, non-root tests, differential Ruff,
unchanged P1/Sentinel/pilot hashes and final CI precede a code merge. No test is weakened.

Document-only validation now: JSON case uniqueness/structure, P1 pins and diff scope. These
are design cases, not tests that have been executed against a nonexistent function. A
positive result here is not controller qualification, runtime evidence or deployment.
The subsequent external observation join and termination writer require their own reviews.
Rollback: close/revert these documents; no ledger or fault record has been written.
