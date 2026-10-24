# P4 file observer and bounded evidence join v0

SOURCE_ONLY / CONTRACT_BEFORE_CODE. Baseline main760bd76799be434274c4f37a672e1e10d25c8db7.
Pinned P1 and prior reader contracts are unchanged. #286 ACTIVE, runtime unchanged.

## Scope and operator binding
Add a separate IO module, never imported by pure format/projection modules.
A frozen operator configuration binds absolute normalized lab root, ledger file,
trust directory, fault file, checkout root, expected lab id, current root pin and
minimum root version. No per-observation path/root override or caller health booleans.
External namespaces must be pairwise disjoint and outside lab and checkout.
This is a selected-child diagnostic, NOT the P1 whole-population/open-operation scan,
an admission controller, a source of permission, a writer or a recovery action.

## Acquisition
Open existing registrar.lock only, take nonblocking exclusive L1, then invoke existing
operation-only inspection (L2 inside trust). Never create a missing lock or evidence file.
Walk absolute paths component by component with directory descriptors and NOFOLLOW.
Bound roots and directories below them must be real owner-private mode0700 directories;
files must be regular mode0600, single-link and owned by the observer uid. Ancestors
above bound roots are checked as real directories, not silently resolved through links.
Read fixed fault file, trust policy.json and trust-history.log, and
admission-ops/<child hex64>.log with prior bounded readers' byte limits.
The bound ledger is independently read with a 16MiB limit and its snapshot hash must
match existing inspection's whole-ledger hash. Inspect each resource before/after;
retain descriptor/path identity and size/mtime/ctime until final acquisition checks.
Any missing, busy, nonprivate, linked, changed, oversized or unreadable source blocks.
No permission modification, fsync, repair, truncation, directory creation or write open.
Advisory locking coordinates cooperating controller/registrar writers only. Trusted
operator/ancestor mutation, in-kernel IO caches and adversarial timestamp restoration
are outside the guarantee. Read syscalls may update atime; no durability proof.

## Cross checks and explicit limits
Run pure readers, then existing colony_trust.check_root with constructor pin/floor and
installed policy binding. Full historical root rotation is NOT_EVALUATED.
Bind PREPARED lab/child/attempt/operation to the selected filename and projection.
Each operation DURABILITY_FAULT must name an acquired exact FAULT for the same operation,
child, attempt and step. Missing or mismatched links block. All acquired sticky faults
are blocking diagnostic evidence; this first join never clears them, skips a faulty log,
or converts external termination into authority. Historical /1 observations stay historical;
they are not replaced by today's ledger. /0 references remain unresolved and blocked.
Compare D1 completion claims against the current operation-only ledger observation.
If exactly one entry is present, require its envelope_sha256 equals PREPARED's frozen
presented admission envelope digest. This does not authenticate that envelope.
No-entry with completed D1, or consumed-entry with a pre-D1 terminal absence claim,
is inconsistent. Ambiguous/legacy/conflicting/unavailable inspection blocks.
Interrupted D1 with/without a line remains an observation, never automatic recovery.

## Output and acceptance
Frozen results carry only immutable summaries: observed source hashes/identities,
log projection, current-root validation status, ledger observation bytes and fixed blockers.
accepted=false, authorization/completeness/durability=NOT_EVALUATED always.
A successful status is OBSERVED, not PASS/QUALIFIED/COMMITTED/READY. D2/D3 disk contents,
stored envelopes, ancestor attestations, ceilings, full lab scan, acquired boot identity,
external-set-aside expected identity and installer rotation remain NOT_EVALUATED.
On acquisition failure return BLOCKED without a usable partial payload. Cross-check
failures return BLOCKED with diagnostic claims explicitly marked untrusted.
Test actual private temp files; symlink components/leaf, hardlinks, FIFO, modes/owner,
missing lock/evidence, L1/L2 busy, oversized/mutated inputs, root pin/key rejection,
foreign lab/child, D1 mismatch, missing/foreign fault links, readonly byte preservation,
closure errors and immutable non-authorizing output. Exact-SHA independent review and
CI precede merge. No qualified source changes or campaigns.
