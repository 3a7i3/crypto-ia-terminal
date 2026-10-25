# P4 whole-operation-log scan and descriptor ledger inspection v0

SOURCE_ONLY / CONTRACT_BEFORE_CODE. Baseline main5525905449e3ff26180db5362eef0ea3111aa5f4.
Pinned P1 and existing formats stay unchanged. #286 ACTIVE; no runtime/VPS changes.

## Descriptor primitive
Add colony_trust.inspect_operations_fd(fd, operations), a read-only diagnostic primitive.
fd is a borrowed, newly and independently opened regular single-link owner0600 O_RDONLY
descriptor, offset0. Caller owns lifetime and must establish path/lab provenance and L1.
No dup, open, close, write, create, fsync or automatic permission change inside primitive.
Caller must never lend a descriptor with a pre-existing flock: the primitive takes a
nonblocking shared L2 on that descriptor, reads strict complete /0-/1 bytes once, checks
metadata stability and releases its own lock. A borrowed writable descriptor refuses.
No L1 acquisition within trust. Caller closes the descriptor and discards provisional
observations on close failure. Successful inspection does not prove that later close,
path provenance or storage durability succeeded.
Input operations is a tuple of0..256 unique hex64 ids (invalid input performs no IO).
Strict parser/bounds are reused:16MiB and16384 entries. No path reopening or per-operation
reread. Empty requested tuple still validates the whole ledger once.
Return closed batch schema colony-trust.operations-inspection/0:
inspection_schema,status,ledger_sha256,ledger_entries,legacy_entries,observations,failures,
accepted,authenticity,authorization,completeness,provenance,durability.
Success status OBSERVED; per-operation observations use exactly existing operation-inspection/0
statuses/semantics. A conflicting or ambiguous requested operation remains a diagnostic row;
not an approval. On any input/read/lock/metadata/unlock error discard every count/hash/row
and return INVALID_INPUT,LEDGER_BUSY,LEDGER_CORRUPT or LEDGER_UNAVAILABLE with fixed failures.
Offset is advanced by the one read; never reposition or borrow a caller's open lock state.
Legacy API behavior unchanged. No record/ledger format migration.

## Observer and scan
Update selected-child observer to open/bind ledger once via existing descriptor acquisition;
pass that descriptor to the primitive and use the returned exact-byte hash for SourceStamp.
Final descriptor/path checks and close-success remain required before returning payload.
Remove former independent byte read and path-based reread. Do not weaken existing source
mode/owner/link/NOFOLLOW checks, L1 ordering or selected-child cross-checks.

Add FileObserver.scan() with no path/health/selection arguments. Under the same L1:
acquire external fault/policy/history once; enumerate admission-ops through its acquired
directory descriptor with bounded scandir; at most256 entries, every name exactly
<hex64>.log. Unexpected/linked/nonregular entries refuse, never ignored. Empty existing
directory is a valid inventory; missing directory is not provisioned empty.
Read every named log with existing limits, sorted deterministic order. Additional diagnostic
aggregate cap32MiB for all operation logs; overflow blocks with no usable partial scan.
All open file descriptors retained until final identity checks; verify directory listing
unchanged before return. One ledger descriptor/read covers all valid latest-operation ids;
duplicate operation ids across child files block instead of merging them.
Pure projectors remain byte-only and cannot import the IO boundary.
Corrupt/torn/empty/preparation-incomplete logs are retained as diagnostic projections and
block the scan. Latest readable operations reuse existing lab/child/root/fault/D1 checks.
More than one nonterminal latest operation yields OPERATION_PENDING. One is listed as
pending, never resumed. Terminal claims do not certify D2/D3 facts or admission.
External terminations do NOT authorize skipping a faulty file in this diagnostic slice;
scan remains blocked until independently bound terminal override is implemented/reviewed.
Legacy entries remain visible; no-operations+legacy remains explicitly ambiguous.
Per-operation historical attempts remain structurally projected, not externally authenticated.

## Result and limits
Frozen LabObservation with status/blockers, sources, frozen child observations, pending
operation ids, immutable canonical ledger batch bytes, root_status and source provenance.
accepted=false; authorization/completeness/durability/rotation NOT_EVALUATED always.
OBSERVED only means the acquired bounded inventory and implemented checks were observed.
No population/home scan, ceiling/ancestor/attestation verification, boot identity, exact
fault-target mapping, root installation, terminal override, recovery, termination or writer.
Lab-wide operation-log inventory is not yet the complete laboratory admission guard.
Advisory locks cover cooperating code; trusted operator/ancestor replacement outside model.
Resource limits may conservatively block a valid larger diagnostic workload; no pruning.

Tests: one strict parse/open/read pass regardless of requested operation count; fd flags,
offset/type/owner/mode/link, bounds, lock and unlock faults, samefd hash, no ownership-close;
all logs enumerated, deterministic inventory, extra entry/symlink/hardlink/FIFO,257 entries,
aggregate cap, foreign identities, duplicate ids, corrupt neighbor, multiple pending logs,
directory mutation, selected observer regression, source close failure. No IO prefixes on
acquisition failure. Exact-tree independent review, CI and frozen hashes before merge.
