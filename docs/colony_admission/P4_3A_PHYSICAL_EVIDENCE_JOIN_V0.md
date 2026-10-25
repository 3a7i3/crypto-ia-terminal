# P4 / 3A — Physical D1/D2/D3 evidence join, v0

Status: **CONTRACT_FOR_REVIEW / SOURCE_ONLY / LAB_ONLY / NO_IMPLEMENTATION**.
Operator validated the 3A plan on 2026-10-25 (America/Mexico_City).
Baseline: `main@e566e51ecd67ec6444eca577202a9d18d1ad0b5d`,
tree `b20f487c8170422aa99bc489b2775e765bc7d76e` (#501 plus corrective #502).
Step 2 is closed; its closure is recorded in #502, comment 6395340869.
This document defines a later diagnostic implementation, not a controller or a birth.

Controlling documents: [P1](ADMISSION_CONTRACT.md),
[P1 scenarios](SCENARIOS_A0.json), [file boundary](P4_FILE_OBSERVER_BOUNDARY_V0.md),
[scan/FD boundary](P4_LAB_SCAN_AND_FD_LEDGER_V0.md), and
[registrar amendment 3](../colony_registrar/AMENDMENT_3_PREPARE_COMMIT.md).
P1 pins remain `e8a125bd67964a01f8a06a5f2d3c50f34e9a154e521dce201cb4fb6d1a40bfcd`
and `4e518bfec6faaa582c2c42633d80e989b8204708b554f74b0eb1bbee6eaa59a1`.
No existing contract, format, default API behavior or qualified source is amended.

The companion [case matrix](P4_3A_PHYSICAL_EVIDENCE_CASES_V0.json) is a specification,
not executed evidence. The [plan/reuse record](P4_3A_PLAN_AND_REUSE_V0.md) records decisions.

## 1. Question and non-authority

For every supported operation in the bound logs, do the acquired ledger and, for each
child's latest operation, its admission material and home identity agree with the frozen
operation and its structural state? Report the facts, their coverage and contradictions.

Every result has `accepted=false`. Authenticity, authorization, attestation completeness,
durability, root-rotation semantics, population classification, ceilings and recovery remain
`NOT_EVALUATED`. A hash match, observed layout, terminal log claim or `OBSERVED` status
never authorizes admission, execution, parenting, recovery, installation or a new consumption.
An expected incomplete step is reported as incomplete; it is never a completed proof.

No `Controller`, writer, installer, attestation issuer, operator action or supervisor call
is implemented here. No lab/pilot/Sentinel/J01 code, runtime, VPS, PPL, FIN, epoch, secret,
exchange, Replay or Diagnostic is touched. #286 remains ACTIVE.

## 2. Reuse and public boundary

The later entry point is `FileObserver.scan_evidence()`, with **no call arguments**.
It uses the existing frozen `ObserverConfig`; paths below the lab are derived below.
Existing `observe(child_agent_id)`, `scan()`, result types and trust FD behavior are preserved.
The new result does not silently replace a result consumed by an existing caller.

Reuse one acquisition owner, the existing private-file/descriptor checks, strict operation
parser/state machine, external readers and `trust.inspect_operations_fd` unchanged.
Do not implement this as `scan()` followed by an independent set of file reads, or nest a
new L1 acquisition in a locked scan. Pure comparison/projection modules import no IO boundary.
Internal factoring may share verified event traversal; it must preserve all old parser cases.

`check_bundle(..., ledger=...)`, `verify_consumed`, registrar preparation/commit and
`Supervisor.load/admit/run` are **not called** from this diagnostic: the ledger helpers
reopen a path/take another L2, and the lab/registrar readers reread paths or have wider effects.
Signature/bundle/lineage verification on acquired material belongs to 3B/3C.
No second implementation of cryptographic, policy or qualification rules is added in 3A.

## 3. One bounded acquisition, not a durable snapshot

1. Open existing L1 and hold it until all observations, final checks and closes succeed.
   Never create a lock. Use L1 before L2, never the reverse.
2. Acquire faults/policy/history once as in the existing scan. Preserve sticky-fault and
   unavailable-trust blockers. An external termination is still not permission to skip a log.
3. Inventory all `admission-ops` entries using its acquired directory FD. Retain the strict
   hex64.log namespace, deterministic ordering, per-log limits, 256-log and 32 MiB log caps.
4. Validate each complete log with `project_log`. Reuse physical `b"\n"` boundaries;
   acknowledged lexical fragments stay opaque, including CR and fake event text (#502).
5. Bind every real PREPARED to its filename, lab, attempt and operation digest. Retain
   its frozen data and its own validated transition segment, including historical attempts.
6. Before opening the ledger, enforce the operation cap in section 4. Open it once, freshly
   O_RDONLY at offset 0; inspect all requested operation IDs in one call under shared L2.
7. Acquire the fixed D2/D3 paths for each latest operation. Deduplicate identical acquired
   paths; repeated references use the same bytes/identity, not another open or read.
8. Repeat directory inventories and descriptor/path checks. No provisional payload is
   returned until the acquisition scope exits with successful closes.

Bound roots and selected directories: owner 0700, real directories, component-by-component
NOFOLLOW. Selected files: owner 0600, regular, single link, stable metadata, no FIFO blocking.
Keep all acquired descriptors until final verification. A changed source, failed read,
unexpected selected type, resource exhaustion, verification or close error gives `BLOCKED`
with **no usable partial sources, rows, counts, hashes or ledger bytes**.
No write-mode open, creation, fsync, rename, permission change, unlink or SQLite open.
Read syscalls may update atime; byte/mode/mtime preservation is the relevant non-mutation check.

The cooperating writers' advisory L1 orders their activity only. Operator/ancestor compromise,
timestamp restoration and device caches remain outside this guarantee. Releasing L2 after
the one read does not prove that an uncooperative writer cannot later change the ledger;
final metadata/path checks preserve the existing observer model, not multi-file atomicity.
An unreadable or structurally invalid foundational log/ledger/policy/history/fault source
cannot support partial operation evidence: discard the payload. A JSON decoding failure in
an acquired D2/D3 artifact is instead a divergent-file cross-check, with its safe raw hash
retained after successful acquisition; do not salvage a prefix of that JSON object.

### 3.1 Absence and namespace coverage

Existing `admission-ops`, `registrar-admissions`, `admission-envelopes` and `individuals`
root directories must be acquired and verified. A missing/inaccessible root is unavailable,
never empty. A missing child subdirectory/file is an `ABSENT` fact only beneath an acquired
parent with a repeated stable listing and final no-follow absence check. A present unsafe
entry or EACCES/IO failure is unavailable, never absence. Missing nested child paths are
represented by absence of their first missing component; no directory is provisioned.

Only log filenames are a full lab inventory in 3A. Unreferenced admissions, stored envelopes,
founders, other homes, quarantine destinations, task/result contents and SQLite contents
are outside coverage. No whole-lab safe-tree or population claim follows. Missing files
required by a completion claim block it; absence allowed during an unfinished step does
not certify the step complete.

### 3.2 Additional diagnostic limits

| Resource | Bound / behavior |
|---|---|
| All distinct operations, latest plus history | 256; overflow before ledger open gives `HISTORY_OPERATION_LIMIT` |
| Ledger | Existing 16 MiB / 16384 entries and FD rules, unchanged |
| Admission / each home JSON identity or initial usage file | 64 KiB each |
| Each stored envelope or statement | 16 KiB each, per P1 |
| Frozen item references per operation | 252 universal hard bound; deriving the policy-specific bound remains 3B |
| D2/D3 selected content, aggregate | 32 MiB; overflow discards the payload |
| Selected home root entries | 16; unknown root names/types or overflow block |
| Selected journal directory entries | 4 known store/companion names; metadata only |
| Live acquisition descriptors, including directories | 4096; lower OS limits also fail closed |

Metadata-only journal inspection reads no database bytes and claims no table/content health.
The limits are fixed diagnostic limits, not retention rules. A valid larger P1 history or
lower-FD host can block; no pruning, batching, limit increase or second ledger pass is allowed
as a fallback. Supporting more needs a separately reviewed contract. This is not support for
all 256 x 64-line P1 histories.

## 4. Historical coverage and the whole ledger

Collect **all** PREPARED operation IDs from every validated log, not just the latest IDs.
`AttemptSummary` alone is insufficient: the frozen PREPARED and validated segment are needed.
Do not maintain another permissive parser: historical segments must follow the existing
machine's rules. Prior attempts in a valid current format can only have ended REFUSED or
ABANDONED before a new PREPARED for the same child; their D1 expectation is no entry.
Keep original physical line numbers and reserve rules when deriving historical projections:
use the validated walk or validated whole-file prefixes, never rebase isolated segments.

One operation ID must belong to exactly one log/attempt. A repeated ID across logs/attempts
blocks with `DUPLICATE_OPERATION`, never coalesces the two claims. More than one nonterminal
latest birth remains `OPERATION_PENDING`; pending set-aside is not a second open birth.

Call `inspect_operations_fd` once with the sorted unique tuple of every supported ID,
including an empty tuple when there are no operations. Require a successful whole parse.
Reject any legacy /0 entries with `LEGACY_LEDGER_UNBOUND`. Reject multiple /1 entries for
one requested operation. For a valid batch let `E=ledger_entries`, `L=legacy_entries` and
`S=sum(row.operation_entries)` over the distinct requested IDs. Require `L=0` and `E=S`.
Otherwise `LEDGER_OPERATION_UNBOUND` blocks; `E-S` is the number of unmatched entries when
counts are available. Their identities are **not** exposed by this API and must not be invented.
When parsing/acquisition fails the unmatched count is null, never zero.

This count equality, strict full parse and unique complete requested ID set establish only
coverage of ledger entries by the supported structural operation inventory. They do not
establish authenticity, an admission/home bijection or completeness outside that bounded set.
No new trust API or change to the 256-ID primitive is needed for this diagnostic slice.
Coverage MATCH requires the uniqueness/conflict checks too; an E=S batch with a duplicate
consumption row must not receive MATCH. With legacy rows present, unbound_entries includes
those rows as well as any unrequested /1 rows (E-S), and status is LEGACY_UNBOUND.

## 5. D1: two different bindings

For every operation, retain the existing current-root/fault/log binding checks and compare
its row to the frozen admission-envelope digest in that operation's PREPARED.

| Structural state/fact | Required diagnostic treatment |
|---|---|
| Completed D1 (DONE or validated RECOVERY_PRESENT), COMMITTED or FAILED_CONSUMED | Exactly one matching operation entry; absence or mismatch blocks |
| REFUSED / ABANDONED, including all older attempts | No operation entry; an entry blocks `OPERATION_STATE_INCONSISTENT` |
| Open BEGIN D1 | Zero or one matching entry is observed, never recovered automatically |
| Pre-D1 with no BEGIN D1 and no consumed terminal classification | No entry; a present entry is inconsistent |
| Any foreign envelope hash, multiple entries or ambiguous inspection | Block; no partial consumption success |

In every present row require its operation digest and envelope digest to match the frozen
ones. This is `FROZEN_HASH_MATCH`, **not** full envelope authentication or identity binding.
When the latest operation's stored admission envelope is available, validate its closed
existing envelope shape and compare issuer_id, envelope_id, canonical envelope digest,
record digest, kind, purpose, lab and child subject to the row and frozen admission.
Only those lexical/identity comparisons may be reported `MATCH`.

Before D2 the envelope may not yet exist on disk. Report its identity binding as
`NOT_AVAILABLE_BEFORE_D2`, even when the D1 frozen hash matches. Do not fabricate an issuer
or envelope ID from a hash, or require a future D2 file to prove a pre-D2 structural state.
After effective D2 completion, a missing admission envelope is a missing D2 proof and blocks.
Historical attempts get `SUPERSEDED_NOT_EVALUATED` for stored-envelope/D2/D3 comparisons:
the same child's later material must not be compared as if it belonged to an older attempt.
No signature, issuer scope, revocation or fresh/spent authorization decision is made here.

## 6. D2: exact material set and comparison modes

For the **latest** operation define C=child ID, P=parent ID,
A=H(frozen admission record), Q=H(frozen parent qualification),
S=the frozen presented statement-record digest; H is the existing compact canonical hash.
The following storage mapping refines P1's per-individual directory convention explicitly:
birth material belongs under C, although qualification and statement subjects are P.
It is a contract for the future D2 writer, not a claim that one is installed.

| Path below the lab | Expected material / binding |
|---|---|
| `registrar-admissions/C.json` | Frozen BirthPlan admission, canonical-object equality |
| `admission-envelopes/C/admission-A.envelope.json` | Presented admission envelope digest; subject C, frozen child spec ID; record A |
| `admission-envelopes/C/birth-qualification-Q.envelope.json` | Presented qualification envelope digest; subject P, frozen parent spec ID; record Q |
| `admission-envelopes/C/statement-Q.json` | Record digest S; qualification_record_sha256=Q; subject P and parent spec ID |
| `admission-envelopes/C/statement-Q.envelope.json` | Presented statement-envelope digest; subject P and parent spec ID; record S |

P and parent spec ID come from the bound BirthPlan parent; missing/malformed required binding
fields give `FROZEN_MATERIAL_INVALID`, not caller defaults. Names are derived from frozen
IDs/hashes only. Do not follow a path in a statement's historical/evidence fields.
Also require the frozen admission's existing child_agent_id, child_agent_spec_id,
parent_agent_id, policy_sha256, parent_qualification_sha256, budget, lab_permissions and
declared_diff to equal the corresponding frozen operation/plan values. No new admission
field (such as a nonexistent parent_agent_spec_id) is invented. Require qualification's
agent_id/agent_spec_id to name the frozen parent; this does not validate its qualification.
Check the three presented record digests and envelope digests against matching DECISION
items in the frozen item list; missing/duplicate/contradictory references block this binding.
This local reference check does not derive the required list or validate its global completeness.

Decode selected record files with bounded strict JSON (no duplicate keys, floats, nonfinite
values, ambiguous numbers or excessive depth); storage whitespace is not record identity.
Re-use the existing canonical hashing/equality conventions. Keep raw byte hashes in stamps
separate from record/envelope canonical hashes. Do not use `formats.loads` directly on the
registrar's indented JSON and mistake its valid storage encoding for a corrupt log entry.
Admission equality preserves the registrar's canonical-object semantics; envelopes/statements
require frozen canonical-digest equality plus the visible links above. Full statement scope,
evidence/code-hash semantics and signatures remain 3B, NOT_EVALUATED here.
The statement retains P1 section 3.5's closed field set; compare its visible subject,
qualification link and issuer declarations to the qualification and envelope. Envelope
authors must name the corresponding admission admitter / qualification reviewer / statement
issuer as prescribed by existing Kind.author fields. This is lexical coherence, not an
issuer's authorization, scope, key trust or signature check.

The individual attestation is not a D2 requirement: it is a later separate operator action.
No inventory/authentication of all other stored envelopes is claimed in 3A.

| Phase | Permitted physical report / blockers |
|---|---|
| Before BEGIN D2, including pre-D1 terminal claims | Absent, or equal pre-existing material, may be observed; presence alone does not mean this operation wrote it. Any selected divergent material blocks. |
| Interrupted D2 | ABSENT, PARTIAL (only whole matching files plus missing files), or MATERIAL_MATCH; no resume, cold-read verdict or completion promotion |
| Effective completed D2 or a later completed step | All five files must match; absent/partial/divergent material blocks `OPERATION_STATE_INCONSISTENT` / `STORED_FILE_DIVERGENT` |
| Terminal after consumption without completed D2 | Report the reached phase and retained material; divergent material still blocks; do not erase the spent D1 fact |

A short/prefix/invalid JSON file is divergent, not a recoverable PARTIAL D2.
Pre-existing equal copies are not ownership, provenance or durability evidence.

## 7. D3: expected bytes, phase and layout

The fixed identity paths are `individuals/C/spec.json`, `record.json` and
`birth_qualification.json`, bound respectively to frozen BirthPlan child_spec, record and
qualification. Expected bytes use the existing `Supervisor._dump` storage profile:
UTF-8, ensure_ascii=false, allow_nan=false, sort_keys=true, indent=1, then one LF.
This differs from the compact bytes used for identity hashes. Test encoding parity with the
existing writer, including Unicode; do not change the writer or silently normalize its bytes.

Before effective D3 completion also inspect `usage.json`, whose initial expected bytes are
that same serialization of `{"runs":0}`. After DONE D3 **or a structurally validated
RECOVERY_PRESENT D3**, compare only the three identity files; usage content is NOT_EVALUATED
and is not read, so a legitimate run does not create a false identity divergence.
No comparison grants OWN_OPERATION/population status; those are 3C/controller decisions.

| Facts / phase | Treatment |
|---|---|
| Home absent before completed D3 | Observe ABSENT, unless it contradicts a completion claim |
| Home present without effective completed D2 | `OPERATION_STATE_INCONSISTENT`, even with matching identity |
| Home present after D2 but before BEGIN D3 | Matching bytes do not prove origin: report matches and `HOME_ORIGIN_NOT_EVALUATED`; do not claim the P1 HOME-01 recovery decision |
| Interrupted D3 | Report ABSENT / INITIAL_MATCH / PARTIAL / DIVERGENT; never emit recovery or claim cold read |
| Effective completed D3 / COMMITTED | Three identity files and the covered completed layout must be present and match; missing/divergent proof blocks |
| FAILED_CONSUMED after BEGIN D3 | Retain spent D1 and report terminal home facts; do not call it admitted or ignore it for population |

PARTIAL means missing components with every present required content file equal to its
expected complete bytes. Prefix/short/divergent bytes of an open D3 are DIVERGENT, not
recoverable partial material (P1's declared short-write limit). For a consumed terminal
home a prefix of expected identity bytes may be reported `TERMINAL_PREFIX`, but set-aside
eligibility remains NOT_EVALUATED and `ACTION_EVIDENCE_NOT_EVALUATED` blocks this slice.

For covered layout, list only the selected home's root: known files spec.json, record.json,
birth_qualification.json, usage.json, usage.json.tmp, inflight.json, and directories tasks,
results, j01-lab-memory. Root entries must have the expected safe type/mode/owner/link;
unknown names/types block. Do not recurse into tasks/results or open their content.
Observe the three private directories. Inspect journal directory names and regular-file
metadata only for activity.sqlite3 and its -wal/-shm/-journal companions. Completed layout
requires a present nonempty store file; initial interrupted creation can be absent/empty
and incomplete. No SQLite connection or semantic/empty-journal verification is performed.
After completion, usage presence/content is not part of layout completion; any present
selected root entry must still be safe. Task/result/journal content remains NOT_EVALUATED.

Quarantine/set-aside BEGIN/DONE, external terminations and related destination identities
remain outside 3A. Report `ACTION_EVIDENCE_NOT_EVALUATED` and block, while retaining usable
diagnostic claims after successful acquisition. Never clear a sticky fault or skip a corrupt
neighbor because another input claims that it was terminated or moved.

## 8. Result contract

Use a new immutable result, logically schema `colony-admission.physical-evidence/0`.
Closed top-level fields: schema, status, blockers, sources, metadata_sources, operations, pending_operations,
ledger_bytes, ledger_coverage, limits, accepted, authenticity, authorization, completeness,
durability, rotation, attestations, population, ceilings, recovery.

`status` is OBSERVED or BLOCKED; blockers are deterministic deduplicated symbolic codes.
All authority/semantic fields named in section 1 are fixed NOT_EVALUATED. `accepted` is the
literal false. sources contains existing immutable SourceStamps only for content actually
read and hashed. metadata_sources contains immutable resource/device/inode/mode/uid/nlink/
size/mtime_ns/ctime_ns stamps for verified directories and metadata-only files. Do not
fabricate a content hash for SQLite files that were not read. ledger_bytes is the immutable
canonical batch result or null. ledger_coverage is a closed immutable record with status
(MATCH/UNBOUND/LEGACY_UNBOUND/NOT_EVALUATED), total_entries, legacy_entries, matched_entries,
unbound_entries (integer counts or null, never invented zero). It never means complete admission.
limits exposes the integer bounds of section 3.2 and a deterministic tuple of reached limit
names, not caller-adjustable knobs.

Operations are sorted by (child ID, attempt), with closed immutable rows:
child_agent_id, operation_sha256, attempt, latest, log, d1, d2, d3, blockers.
`log` is the existing structural projection for that attempt, not an authenticated verdict.
D1 carries operation_entries (integer or null), frozen_hash_match (MATCH/ABSENT/MISMATCH/
NOT_EVALUATED), envelope_binding (MATCH/NOT_AVAILABLE_BEFORE_D2/SUPERSEDED_NOT_EVALUATED/
NOT_EVALUATED), and no caller-supplied health flag.
D2 carries material_state (ABSENT/PARTIAL/MATERIAL_MATCH/DIVERGENT/SUPERSEDED_NOT_EVALUATED/
NOT_EVALUATED) plus immutable per-file role/path/presence/comparison/hash facts.
D3 carries identity_state (ABSENT/INITIAL_MATCH/IDENTITY_MATCH/PARTIAL/DIVERGENT/
TERMINAL_PREFIX/SUPERSEDED_NOT_EVALUATED/NOT_EVALUATED),
layout_state (ABSENT/PARTIAL/OBSERVED/DIVERGENT/NOT_EVALUATED),
usage_content (INITIAL_MATCH/ABSENT/DIVERGENT/NOT_EVALUATED), and per-file facts.
Each per-file fact has closed fields role, relative_path, parent_resource, presence
(ABSENT/PRESENT), comparison (BYTES_MATCH/CANONICAL_MATCH/DIGEST_BINDING_MATCH/MISMATCH/
NOT_EVALUATED), size_bytes, raw_sha256 and record_sha256. Absent/unread content has null
hashes; metadata size is not bytes-read. Paths in output are derived lab-relative roles,
never rejected input text or secret values. The corresponding acquired parent stamp binds
an absence fact; no hash is computed for absence.

Acquisition/foundational-parse/limit failure discards all rows and facts as section 3 requires. On a
successfully acquired bounded snapshot, cross-check blockers retain explicitly diagnostic
facts. OBSERVED can include an expected unfinished step, with its ABSENT/PARTIAL facts and
NOT_EVALUATED properties visible; it means no contradiction was found in this slice, not
readiness. No physical match upgrades a structural BEGIN, RECOVERED or terminal claim.

## 9. Acceptance, review and rollback

The case matrix must become adversarial tests on real private temporary files before an
implementation is accepted. Instrument ledger opens/reads/L2 ownership; prove one pass,
no writer/second lock, stable absence checks and clearing on close failure. Preserve all
existing observer/parser/trust/registrar regressions, including the ACK/CR mutant.
Test the 256/257-operation boundary separately from the 256/257-log boundary, historical
supersession, unbound/legacy counts, byte-vs-record encodings and phase-sensitive usage.

Review the final exact tree independently, verify CI at its final HEAD and composition,
then use the existing authorized guarded source merge and verify new-main CI. No local
suite totals, sandbox proof, non-root result or independent review is claimed by this
documentation. Contract-only publication is not implementation or qualification.

Rollback is source revert only. No evidence is written, migrated, truncated or repaired.
3A alone does not close step 3: 3B must supply attestations/ancestors; 3C must supply complete
population, ceilings and object correspondences; the durable controller/recovery/P5/P6/T7
remain later, separately scoped work.
