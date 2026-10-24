# P4 external evidence formats, version 0

Status: SOURCE_ONLY / CONTRACT_FOR_REVIEW / NO_WRITER. Baseline main
`9fd56a59a22fdcea338350f0bb8384e939e55b88`, after the pure reader (#494).
P1 `ADMISSION_CONTRACT.md` and its 122 scenarios remain controlling and unchanged.
This slice specifies inputs for future read-only observers. It does not implement an
observer, install trust, clear a fault, terminate an operation or create an individual.
#286 stays ACTIVE. No runtime, VPS, secret, PPL, FIN or lab source changes.

## 1. Evidence is acquired, not supplied as authority

The pure reader accepts bytes and returns structural claims with `accepted=false` and
external facts NOT_EVALUATED. The later observer must establish where these bytes came
from. Passing a dictionary named `fault_log_ok`, a path from an agent, or a caller-provided
root cannot satisfy a controller guard.

The controller constructor binds one lab id, lab root, ledger location, operator trust
directory and external fault-log location. The last two are outside the lab root, checkout
and sandbox views; the fault log should use another filesystem. Acquisition holds L1,
then uses L2 only for the ledger. Files must be regular, single-link, mode0600; containing
operator directories are real mode0700 directories. These checks belong to the future
filesystem adapter, not to a JSON parser. No caller or individual can replace locations at
an admission/resume entry point. The operator account remains trusted; these formats do
not resist its compromise or demonstrate storage durability.

Missing/unreadable/foreign/corrupt evidence is unknown or blocked, never healthy or empty.
A newly provisioned empty fault log is acceptable only after the adapter has established
its expected file and lab provenance. A missing path is not an empty log. No reader creates
that file to make a check pass.

## 2. Common bytes and limits

Reuse the pure reader's canonical JSON convention: UTF-8, sorted keys, compact separators,
no duplicate keys, floats, nonfinite values, invalid Unicode scalars or coercions. Closed
key sets below; unknown versions refuse. Hex64 is lowercase SHA-256, integers exclude bool,
boot ids are canonical UUID text and codes are uppercase symbolic strings. All optional
fields are present with explicit null. JSON depth <=32, integer tokens <=128 digits.

Fault entries: <=4096 newline-terminated physical lines, <=16384 bytes per line including
newline, <=64MiB total. Trust history: <=4096 terminated lines, <=1024 bytes each, <=4MiB
total. Policy file: one canonical object without a newline, <=65536 bytes. Overflow refuses
all affected observations; no partial-history or prefix health verdict. These are declared
fail-closed capacity limits, not automatic retention or permission to erase evidence.

A malformed or unterminated fault/history line blocks the corresponding observation.
There is NO torn-tail acknowledgement, truncation, repair or fragment skipping in either
external log. P1's operation-log ACK exception does not apply here. Restoration remains a
separate operator gate; neither reader nor later admission controller implements it.

## 3. Trust history: exact P1 line format

Each `trust-history.log` line has exactly the four fields P1 specifies:

| Field | Rule |
|---|---|
| `root_version` | Positive integer |
| `root_sha256` | Hex64, digest of canonical full root |
| `pin` | Hex64, equal to `root_sha256` |
| `minimum_version` | Positive integer, not above `root_version` |

There is no added schema key on these lines. Scope and format version belong to the
constructor and policy wrapper, not to an invented history discriminator. Versions strictly
increase and minimum_version never decreases. Duplicate/equal-version lines are refused:
an interrupted equal-root installation completes the already written history line, never
appends a second equal-version line. Empty history cannot establish current trust.

Root-version ordering alone is not proof of an authorized rotation. History contains root
digests, not complete past key material. Comparing roots for issuer/key disappearance,
immutable scopes/public keys, sticky revocation, nonretroactive retirement and envelope
revocation growth remains the installer's separate semantic check against the prior installed
root. The parser must never report these properties PASS from history metadata alone.

## 4. Installed policy: `colony-admission.installed-trust/0`

Closed object fields:

| Field | Rule |
|---|---|
| `schema` | `colony-admission.installed-trust/0` |
| `lab_id` | Constructor-bound lab id |
| `root` | Complete existing `colony-trust.root/0` payload, no private keys |
| `root_sha256` | Digest of canonical `root` |
| `pin` | Same digest, the installed explicit pin |
| `minimum_version` | Positive integer <= root.root_version |

The wrapper, computed root digest, embedded root version and floor must match the last
history entry exactly. A root for another lab or environment is refused; LAB_TEST only.
The later join calls existing `colony_trust.check_root` with the installed pin, floor and
bound lab id. A pure parser may verify canonical/digest/visible bindings, but does not
validate root issuer semantics, key authorization, installation provenance or durability.

An appended history head with the previous policy still installed yields
TRUST_CURRENT_UNAVAILABLE. It is not repaired by reading an older history prefix or by
accepting either version. Only an explicit `install_trust` of exactly the pending root may
finish the interrupted install under L1. The old installed root must still be used for
monotonic semantic comparison before this completion; it is not silently adopted as current.
A mismatch/absence/corruption never becomes TRUST_REVOKED_AFTER_CONSUMPTION: unavailable
trust is nonterminal and never burns a birth.

## 5. External fault entry: `colony-admission.fault-entry/0`

Every entry has exactly:
`schema`, `lab_id`, `scope`, `child_agent_id`, `operation_sha256`, `attempt`, `boot_id`,
`event`, `step`, `phase`, `code`, `data`.

`scope=OPERATION` requires non-null child, operation and positive attempt.
`scope=LAB` is allowed only for event=FAULT, phase=TRUST_INSTALL and step=null;
Conversely phase=TRUST_INSTALL requires scope=LAB.
child_agent_id, operation_sha256 and attempt must all be null. It records a real trust
installation failure without inventing a birth. A LAB fault cannot be terminated or set
aside using an operation event; a recorded trust resource fault blocks trust use until the
separate restore gate. It never turns unavailable trust into a spent birth.

The child, operation and attempt of OPERATION entries identify the affected birth, even if its PREPARED write
was interrupted. Identity and attempt must be lexically valid; after the observer joins
facts they must match the frozen operation or the recorded faulty-child binding. All entries
for an operation retain the same lab/child/attempt. Distinct operations may share a child
only where P1 permits another attempt; a faulty operation log permanently bars that child
until the separate restore gate. The fault file is scoped to one constructor-bound lab.

`step` is D1, D2, D3 or null. `phase` is one of PREPARE, D1, D2, D3, QUARANTINE, SET_ASIDE,
TERMINATE, ACK or TRUST_INSTALL. Dk phases require step=Dk. QUARANTINE/SET_ASIDE require step=D3.
Other phases use null. Phase reports the action at the fault, not an invented completed
step. A PREPARE fault does not establish PREPARED. A QUARANTINE/SET_ASIDE entry must be
joined with that action's prior D3 provenance, not used as proof of a successful birth.
For a faulty operation log, P1's step-at-fault evidence is kept even if the log cannot be
read; later TERMINATED_EXTERNALLY never overwrites this original fault entry.

### 5.1 FAULT

`event=FAULT`, `code=DURABILITY_UNKNOWN` and `data` has exactly:
`origin`, `failure`, `target`.

- `origin=SUPERVISOR`, `failure=ADMIT`, `step=D3`, `phase=D3`, `target=null`.
  P1 records errors from Supervisor.admit against the step only; no guessed faulty file.
- `origin=CONTROLLER`; failure is WRITE, SHORT_WRITE, FSYNC or RENAME; target is the exact
  controller resource on which that operation failed. No generic unspecified target.

- `origin=TRUST`, `failure=CONSUMPTION_IO_UNKNOWN`, `step=D1`, `phase=D1`, target=LEDGER.
  This maps the existing consume result LEDGER_DURABILITY_UNKNOWN without pretending to
  know whether its write, fsync or close failed. It creates the same sticky ledger block.

A target is exactly `{resource, object_kind, relative_path}`. object_kind is FILE or DIRECTORY.
Resource is LEDGER, LEDGER_DIRECTORY, OPERATION_LOG, OPERATION_LOG_DIRECTORY, LAB_DIRECTORY,
INDIVIDUALS_DIRECTORY, HOME_DIRECTORY, HOME_ENTRY, ADMISSION_ENTRY, ADMISSION_DIRECTORY,
ENVELOPE_ENTRY, ENVELOPE_DIRECTORY, QUARANTINE_DIRECTORY, TRUST_POLICY, TRUST_HISTORY or
TRUST_DIRECTORY. The *_DIRECTORY resources require DIRECTORY; fixed LEDGER, OPERATION_LOG,
ADMISSION_ENTRY, ENVELOPE_ENTRY, TRUST_POLICY and TRUST_HISTORY require FILE. HOME_ENTRY
may be either, so a home subdirectory fsync is not disguised as a file fault. Relative paths are normalized relative components
within that constructor-bound resource namespace: no leading slash, empty component,
`.`/`..`, backslash or NUL. The adapter maps and compares targets to actual opened resources;
a path label in an untrusted JSON object cannot establish this mapping. Singleton resources
LEDGER, LEDGER_DIRECTORY, OPERATION_LOG_DIRECTORY, LAB_DIRECTORY, INDIVIDUALS_DIRECTORY,
ADMISSION_DIRECTORY, ENVELOPE_DIRECTORY, TRUST_POLICY, TRUST_HISTORY and TRUST_DIRECTORY
use the empty relative_path. Their namespace is the fixed constructor-bound file or exact
parent/root directory, so a parent fsync failure can be named without pretending it was
a file write. A LAB/TRUST_INSTALL fault targets only TRUST_POLICY/HISTORY/DIRECTORY. OPERATION_LOG is exactly
`<child_agent_id>.log`; HOME_DIRECTORY exactly `<child_agent_id>`; HOME_ENTRY begins with
that child component. QUARANTINE_DIRECTORY may name its root (empty relative_path) or the
known operation/attempt directory. No secret value or raw exception text is recorded.
All parent-directory fsyncs must map to one of these exact directory resources; an
unrepresentable resource is a blocked unsupported observer/writer case, never relabeled
as a supported home file. The adapter checks these mappings before any future write.

The exact failing directory is recorded for a directory fsync/rename fault; it must not be
misclassified as a home-file fault to permit retry. A failed rename with ambiguous source or
destination directory records each implicated directory in separate FAULT entries and blocks
both; a later fault-log write failure blocks the entire lab. This is conservative, not a
claim that every device fault can be localized.

SHA256(canonical(FAULT entry)) is the `fault_sha256` named by a usable operation-log
DURABILITY_FAULT line. This linkage is checked by the evidence join. A fault recorded for
another operation, step, lab or resource never clears or explains this operation's fault.
The external FAULT is authoritative blocking evidence even when no corresponding operation
line could be appended. A missing FAULT for a claimed operation DURABILITY_FAULT is unknown,
not a clean lab; missing linkage cannot be automatically repaired.

### 5.2 TERMINATED_EXTERNALLY

Only for scope=OPERATION, after a recorded FAULT on that operation's OPERATION_LOG. `code=OPERATOR_TERMINATED`,
`phase=TERMINATE`, `step=null`. Data has exactly `fault_sha256`, `ledger_finding`.
The fault digest names the prior matching OPERATION_LOG fault. `ledger_finding` is:

| Field | Rule |
|---|---|
| `status` | ABSENT_IN_VALID_LEDGER or CONSUMED_BY_OPERATION |
| `operation_entries` | 0 for ABSENT, exactly1 for consumed |
| `observation_sha256` | Digest of the complete observer-issued ledger observation |

This is a reference to acquired evidence, not an operator assertion accepted by a parser.
**Implementation prerequisite:** current `inspect_consumption` requires the complete expected
envelope. It cannot be called from only an operation digest after a faulty PREPARED becomes
unreadable. The later adapter may use an independently acquired, bound original envelope
from a reviewed durable source outside the faulty log; this contract introduces no such
source and accepts no arbitrary envelope supplied by the terminating caller. Otherwise
termination stays blocked. A read-only operation-only inspection primitive needs its own
contract and review before termination can use it. It must read the complete strict ledger,
count every entry for the operation, preserve MISSING vs absence, and never authenticate
an envelope or a birth. No such primitive is claimed implemented here. Resolving this
prerequisite is required before the termination writer, not deferred to deployment.

Only a valid entire-ledger observation for the same operation can support termination.
LEDGER_MISSING, corrupt, conflict, busy, unavailable, multiple or foreign entries cannot be
converted into absence. A missing ledger requires separate provisioned-origin evidence;
this design supplies no such shortcut. A CONSUMED_BY_OPERATION result grants no admission:
it conservatively classifies the ended operation FAILED_CONSUMED, even if durability is
unknown. Valid absence classifies it ABANDONED. No refund or reuse is inferred otherwise.

The original log is then excluded from the P1 open-operation scan without reading it.
Only that child's id remains OPERATION_LOG_FAULTY. Other operations are still blocked by
any independent ledger/global fault or unavailable fault log. External termination does
not clear a fault, rehabilitate that child, establish COMMITTED or lift a directory block.
Duplicate terminations and contradictory findings are refused, never last-write-wins.

### 5.3 External set-aside brackets

For an operation already TERMINATED_EXTERNALLY, external SET_ASIDE_BEGIN/SET_ASIDE_DONE
entries have phase=SET_ASIDE, step=D3, code=OPERATOR_SET_ASIDE, and data exactly
`termination_sha256`. It names the matching prior external termination entry. BEGIN occurs
once; DONE requires the matching BEGIN and successful explicit move/directory syncs.
An incomplete pair remains pending; the same explicit operator action observes source and
destination, with exactly one location present, before it may finish. No parser renames it.
Faults during this action are new FAULT entries and forbid retry on recorded faulty
resources; the prior terminal result stays terminal. A later termination entry cannot
clear that action fault. External set-aside requires actual D3 provenance from the earlier
fault/action context and P1's identity-prefix/name/link checks. A prior step=D1 or D2 alone
cannot authorize a home move. Original faulty operation bytes are not read to invent D3.
The expected identity bytes must also come from a reviewed independently bound frozen-operation
source. D3 provenance alone cannot supply those bytes, and the observed partial home must
not become its own expected identity. No such independent source is introduced here;
external set-aside remains blocked without it. Its contract and acquisition are prerequisites
before that writer, just as envelope provenance/operation inspection are for termination.

## 6. Joining evidence and guard precedence

This is an order of checks, not an implemented controller:

1. Acquire and validate the external fault log and its lab/resource provenance. Unavailable
   or corrupt means every birth blocked. No fallback to the operation log as healthier data.
2. Collect all sticky faults; never clear them through a later event. Faults on LEDGER or LEDGER_DIRECTORY retain
   P1's lab-wide ledger action restrictions. Controller directory faults retain conservative
   set-aside restrictions, including individuals/ and quarantine root scopes.
3. Derive external termination overrides from valid matching entries and acquired ledger
   observations. Only these overrides allow skipping a faulty child's operation log.
4. Acquire installed policy/history; check full head equality and existing trust semantics.
   Establish the current policy independently of historical roots claimed by operations.
5. Read usable operation logs and bounded external facts under L1. Recompute consistency;
   do not elevate the pure log's terminal_claim into an admitted birth on its own.

Every future read-only result must distinguish lexical validity, source provenance,
current trust validation, durability and operation consistency. It retains accepted=false
unless a separate reviewed controller eventually evaluates every P1 acceptance guard.
This design introduces no boolean that lets a caller claim all five are verified.

## 7. Next implementation and acceptance

Before external termination, specify and review the operation-only ledger observation
prerequisite above (or a reviewed independent envelope-provenance source).
First implement pure, bounded decoders for these formats with immutable observations and
NOT_EVALUATED provenance/durability. Then implement the source-authenticated read-only
adapter and evidence join. Only after their tests and independent review should durable
writers, installation and explicit recovery actions be coded.

Acceptance cases live in P4_EXTERNAL_EVIDENCE_CASES_V0.json; they supplement, never replace
P1 scenarios. Required checks: field/type/encoding closure; bounds; whole-history reading;
head mismatch after interrupted installation; monotone versions and floors; no parser claim
of semantic rotation; missing ledger never absent; external termination bound to original
fault/operation/child and acquired observation; sticky ledger/directory faults; external
set-aside ordering; unavailable evidence remains blocked. Independent review at exact SHA,
CI and unchanged P1 pins precede fusion. No campaign or runtime qualification is claimed.

Rollback: revert these documents. No evidence file or installed policy has been created.
