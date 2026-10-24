# Ledger inspection contract v0 — P4 prerequisite
Status: SOURCE_ONLY / LAB_ONLY / READ_ONLY. This contract is published before its code.
Parent: P1 ADMISSION_CONTRACT.md (sha256 e8a125bd67964a01f8a06a5f2d3c50f34e9a154e521dce201cb4fb6d1a40bfcd).
The P1 contract and 122 scenarios remain unchanged. Preparation: #491.

## API and scope
inspect_consumption(envelope, ledger: pathlib.Path, operation_sha256: str) -> dict.
The envelope must be a structurally valid single-use admission envelope and operation_sha256
a lowercase SHA-256. Their signature and authorization are NOT verified by this read API.
The caller controls the ledger path and its parent directories. An agent never supplies them.

The closed verdict fields are: inspection_schema (colony-trust.consumption-inspection/0),
status, operation_sha256 (valid input or null), operation_entries (integer or null),
failures (codes), accepted (always false), authenticity, authorization and completeness
(the last three always NOT_EVALUATED). No record contents or unrelated entries are returned.

| status | Meaning |
|---|---|
| ABSENT_IN_VALID_LEDGER | Entire private regular ledger parsed strictly; no expected envelope entry AND zero entries for this operation |
| CONSUMED_BY_OPERATION | Exactly one entry for this operation, matching issuer/id, envelope SHA-256 and /1 operation SHA-256 |
| CONFLICT | Expected envelope is legacy /0, has other bytes/operation, or any foreign/multiple entries carry this operation |
| LEDGER_MISSING | File absent in an existing parent directory; no file created, no claim of virgin authorization |
| LEDGER_CORRUPT | Opened file is not private regular single-link, or the shared strict parser refuses it |
| LEDGER_UNAVAILABLE | I/O/permission/close failure, invalid path, missing parent, or read size/entry limit reached |
| LEDGER_BUSY | A cooperating writer holds the ledger lock |
| INVALID_INPUT | Bad operation digest or envelope shape/kind; ledger not opened |

An empty existing valid ledger yields ABSENT_IN_VALID_LEDGER. An arbitrary ENOENT never does.
The controller must establish new-lab provenance or flag a missing required ledger as
inconsistent; this API cannot infer either. A legacy matching entry is never resumable.
Duplicate issuer/envelope keys and torn/foreign/noncanonical lines remain LEDGER_CORRUPT.
Different keys with the same operation are counted across the ENTIRE ledger; two are CONFLICT,
even if one matches. A foreign entry for the operation is CONFLICT, never ABSENT.

CONFLICT failures use OPERATION_MULTIPLE_ENTRIES, OPERATION_FOREIGN_ENTRY,
ENVELOPE_ID_REUSED, ENVELOPE_REPLAYED or LEGACY_CONSUMPTION, in that order of precedence.
Other failures use OPERATION_INVALID, ENVELOPE_INVALID, LEDGER_MISSING, LEDGER_CORRUPT,
LEDGER_UNAVAILABLE, LEDGER_TOO_LARGE or LEDGER_BUSY.

## Read boundary
Use the existing strict /0-/1 parser and inode lock, with a READ-ONLY descriptor,
O_NOFOLLOW on the final component, O_NONBLOCK and a nonblocking shared flock.
No O_CREAT, O_APPEND, writable descriptor, separate lock file, write, fsync, chmod,
rename or repair. The OS may update access time on reads; no content or namespace
mutation is performed. Symlink/device/FIFO/permission failures never become absence.
At most 16 MiB and 16,384 entries are inspected; overflow is LEDGER_UNAVAILABLE with
LEDGER_TOO_LARGE, never a partial absence. The parser's default behavior for existing
APIs stays unchanged. Invalid input is rejected before any open.

The caller holds L1 if it needs a transaction-wide view; the inspector takes only L2
and never L1. Cooperating consumers use the same inode lock. Parent-path replacement,
direct filesystem writers, loss/truncation/restoration by the trusted operator account
and compromised storage remain outside the guarantee. A result is one observation,
not a durable reservation, authentication, authorization, COMMITTED, current root,
record qualification, or permission to resume.

## Acceptance
Tests observe bytes, directory entries, status/count and open flags. Cover empty/missing,
missing parent, exact match, other operation, changed digest, legacy /0, unrelated and
foreign entries, multiple entries of one operation, malformed/duplicate/torn ledgers,
size limits, symlink/hardlink/FIFO/device, permissions and I/O/close failures.
Prove no create/write/fsync on inspection, nonblocking refusal under a writer lock,
and compatibility of existing consume/check_bundle/verify_bundle/verify_consumed.
No runtime, controller recovery, signatures, keys or actual individual is created.
#286 ACTIVE; no VPS or deployment.
