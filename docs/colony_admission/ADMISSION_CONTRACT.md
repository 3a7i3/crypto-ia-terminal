# Colony authenticated admission: composition and transaction contract (`colony-admission/0`)

Status: **SOURCE_ONLY / LAB_ONLY / CONTRACT BEFORE CODE.** This document is normative for the slices that
implement it (P2 `colony_trust` amendment 4, P3 `colony_registrar` amendment 3, P4–P6 `colony_admission`).
It creates no code, no record, no envelope, no key and no individual. Every future trial stays
`LAB_TEST`. Nothing here is deployed, wired into `colony_lab.Supervisor`, or reachable from the Advisor,
the Operator API or the VPS. #286 is unaffected: no strategy, signal, risk, sizing, PPL, FIN, config or
epoch code is imported or changed.

Baseline read for this contract: `main` @ `7b4b2ef6fcdaab0ba9d3db81e2a2b28481a7a2ef` (merges of #485 and
#486). The scenarios the implementation must pass are in `SCENARIOS_A0.json` in this directory. Both files
are pinned by their SHA-256 in the pull request once its review is favourable; after that, a change is a
new file, never an edit.

## 1. Why, and what already exists

`colony_trust` (#485) authenticates records and spends single-use `BIRTH_ADMITTED` envelopes in a
ledger. `colony_registrar` (#486) checks ceilings, lineage and exclusions, then writes the admission
record and the child. They are independent: calling one after the other is not a transaction. A crash
after the ledger append loses a legitimate birth (`ENVELOPE_REPLAYED` on retry); the reverse order can
leave an admitted individual whose authentication is unknown. `Supervisor.admit` enforces neither.

This contract defines the composition: one owner, the attestations it derives itself, one open operation
at a time, an operation identity frozen when it is prepared, the separation between historical proofs and
current trust, bracketed durable steps, and how an interrupted operation is recovered or ended. It does
**not** claim multi-file atomicity: no mechanism here demonstrates it. Each durable step is written once,
identifies itself and its operation, and the state is recomputed from durable facts on every call.

### Relation to #487 (draft, unchanged by this contract)

#487 (`docs/colony_registrar/STEP7_AUTHENTICATED_ADMISSION_PLAN.md`, head `e9f989a6`) is a checkpoint and a
plan. This contract takes from its §4 and makes normative: the controller called by the operator outside
the sandbox; trust root, minimum version, `lab_id` and policy pin supplied from outside the lab; the
required set derived from the records of the decision, never supplied by the individual; ancestors'
admissions verified as already spent without being spent again; the four properties evaluated separately;
a single owner serializing population check, reservation, consumption and admission (here: one open
operation per lab, §6.1); published durability assumptions and directory permissions (§6.8, §13); the six
result requirements (refusal without new consumption, no rollback of a consumption, explicit recoverable
state, exact-operation resume only, one commit under concurrency, no silent repair); and its S7.2–S7.4
slicing. It adds what #487 leaves open: lock order, frozen operation identity, step brackets and state
machine, terminal and non-terminal codes, durability faults and cold-read recovery, monotonic trust
installation, revocation against current trust, quarantine and setting aside, the bundle bound, ceilings,
the qualification scope, the present-scope attestation of an existing qualification, and the interfaces
the later slices must provide. #487 can be merged, closed or kept independently of this contract.

Two deliberate differences, declared: #487's requirement 4 refuses any change of root on resume; here a
resume is verified again against the current trust instead (§5.1), so a benign rotation lets it continue
and a revocation ends it, while the presented inputs must stay identical (§6.2). And the registrar
contract (§3) lets the operator remove an orphan admission after checking that no home exists; for an
operation of this controller, an admission record written at D2 follows a spent authorization and is never
removed (§6.5); the registrar's procedure keeps applying to direct registrar births only.

## 2. Owner, authorities, inputs and outputs

The single owner of an authenticated birth is a new operator package, `colony_admission`
(`Controller`). It imports `colony_trust`, `colony_registrar` and `colony_lab` and is imported by none of
them, by no worker, no task type and no lab module (AST test, extending the existing separation tests).
A new package is needed because the reviewed separation tests forbid `colony_registrar` to import
`colony_trust` (`tests/colony_registrar/test_registrar.py`) and `colony_trust` to import the registrar
(`tests/colony_trust/test_trust.py`).

| Input | Supplied by | Never from |
|---|---|---|
| Current trust policy: root, pin, minimum version, `lab_id` (§5) | Installed by the operator with `install_trust`, stored outside the lab root | An individual's output, the lab root, a call argument of `admit_authenticated` |
| Policy and its pin (g0 by default, `1226d889…`) | Code, or the operator with its own pin | An individual |
| Child spec, lab permissions, budget, declared diff | The operator | An individual's output taken as is |
| Presented parent qualification record, its statement (§3.5), their envelopes | An external issuer, through the operator | The lineage |
| Presented child admission record and its `BIRTH_ADMITTED` envelope | An external admitter, through the operator | The lineage |
| Population records and their stored envelopes and statements | **Read by the controller** from the lab root and `admission-envelopes/` (§3.3) | The caller |

Outputs: the operation log (§6.3), one ledger line bound to the operation (P2), the registrar admission
record and the stored envelopes (D2), the child's home (D3), a verdict. A verdict carries one controller
`code`, the operation `state`, and, when trust refused, the `trust_failures` returned by `colony_trust`
(for instance `code = TRUST_REVOKED_BEFORE_CONSUMPTION` with `trust_failures = [KEY_REVOKED]`). A trust
refusal that is not a revocation has `code = TRUST_REFUSED`; completeness refusals keep the trust codes
`ATTESTATION_MISSING`, `ATTESTATION_DUPLICATED`, `ATTESTATION_UNEXPECTED` as their `code`.
Consumers: the operator; a future read-only status projection (metadata only, no lab-root read by
Governance Tower; separate gate); qualification campaigns.

The operator account that holds the trust policy, the keys, the code and the lab root stays inside the
trust model; resistance to its compromise is not claimed (§13).

## 3. Attestations

### 3.1 Derived list

At `PREPARED`, `required_attestations(lab, parent_agent_id, child_ids)` walks the lab with `lab.load` and
returns the exact list of items (record kind, subject, record SHA-256, stored envelope SHA-256) the decision
needs; that list is frozen in the `PREPARED` line (§6.2) and never derived again for this operation. It
has two parts:

- **decision items**: the child admission, the presented parent qualification and its statement, and,
  for the parent and every ancestor, its individual attestation, its spent admission, its birth
  qualification and statement. All four properties of §4 must PASS for each of them;
- **population items**: the attestations of every other individual, used only to classify it (§3.2).

The caller presents only the new items (parent qualification, its statement, the child admission, their
envelopes), the parent qualification and statement being presented at every birth even when an identical
copy is already stored (equal bytes are accepted at D2); every other envelope is read from
`admission-envelopes/`. A presented envelope not in the list
is `ATTESTATION_UNEXPECTED`; a required item without an envelope, including R8 presented as is, is
`ATTESTATION_MISSING`.

The existing completeness key of `verify_bundle` is (kind, subject). Two children of the same parent each
store a qualification of that parent, so two qualification records may share (kind, subject). Items are
therefore keyed by (kind, subject, record SHA-256); P2 provides that key (or the controller verifies each
item in its own bundle). Identical records (same SHA-256) are one item.

### 3.2 Population status

Every home under `individuals/` is classified before any birth, from durable facts only:

| Status | Founder | Descendant | Counted for ceilings | May be parent or ancestor |
|---|---|---|---|---|
| `AUTHENTICATED` | stored individual envelope verifies under the current root | an operation log `COMMITTED` for it, whose record SHA-256 equals its `record.json`, whose ledger line binds its admission to that operation (`/1`), plus its birth qualification and statement verifying | yes | yes, if also its individual envelope verifies |
| `AWAITING_INDIVIDUAL_ATTESTATION` | — | as above, individual envelope not yet stored | yes | no (`FILIATION_NOT_ATTESTED`) |
| `SUSPENDED` | its individual envelope fails **only** with `KEY_REVOKED` and/or `ENVELOPE_REVOKED` (integrity and authorization PASS, signature valid under the revoked key) | same, for any of its envelopes | yes | no (`FILIATION_SUSPENDED`) |
| `OWN_OPERATION` | — | the home of the open operation being resumed, after `BEGIN D3`, checked against its expected bytes (§6.7; after `DONE D3`, only `spec.json`, `record.json` and `birth_qualification.json`, since a run may already have changed `usage.json`, §13) | no (the frozen plan already counts it) | no |
| `UNAUTHENTICATED` | anything else | anything else, including a home with no `COMMITTED` operation other than `OWN_OPERATION`, a home left by `FAILED_CONSUMED` (§8.2), a ledger line `/0` (bound to no operation) | — | — |

Any `UNAUTHENTICATED` home refuses every birth (`POPULATION_UNAUTHENTICATED`): such a home could be forged,
so it is never counted or skipped. `SUSPENDED` is **not** an authentication: the trust contract (§5) says a
revoked key verifies nothing, and a holder of the compromised key could have signed a forged record. The
status is decided from the existing per-envelope verdict (`colony_trust` checks the signature even for a
revoked key, `trust.py`, `verify_envelope`) and is used only in the conservative direction: the home is
counted against the ceilings (a forgery can only use up capacity) and it never grants filiation.

### 3.3 Required items and storage

| Subject | Record | Kind / purpose | Issuer | Use |
|---|---|---|---|---|
| Each population individual | `individuals/<id>/record.json` | `colony-lab.individual/0`, `INDIVIDUAL_ADMITTED` | `LAB_OPERATOR` | Durable; status per §3.2 |
| Each population descendant | `registrar-admissions/<id>.json` | `colony-registrar.admission/0`, `BIRTH_ADMITTED` | External | Already spent by its `COMMITTED` operation; verified without being spent again (P2 `verify_consumed`) |
| Each population descendant | its `birth_qualification.json` | `colony-lab.qualification/0`, `QUALIFICATION_ATTESTED` | External | Durable |
| Each qualification (stored or presented) | its statement (§3.5) | `colony-admission.attestation-statement/0`, `QUALIFICATION_STATEMENT_ATTESTED` (new kind, P2) | The issuer of that qualification | Durable |
| Parent | presented qualification | `colony-lab.qualification/0` | External | Durable |
| Child | presented admission | `colony-registrar.admission/0` | External | Fresh, spent once, bound to the operation |

Storage, outside the homes (a home set aside never takes them along):
`admission-envelopes/<agent_id>/` holds `individual-<record_sha256>.envelope.json`,
`admission-<record_sha256>.envelope.json`, `birth-qualification-<record_sha256>.envelope.json`,
`statement-<qualification_sha256>.json` and `statement-<qualification_sha256>.envelope.json`. Each file is
written once (`O_EXCL`, no link followed), regular, single link, ≤ 16 KiB. A stored file that is a link,
not regular, or differs from what an operation expects blocks that operation (`STORED_FILE_DIVERGENT`).
Individual envelopes (founders, and children after `COMMITTED`) are stored only by the operator's
`store_individual_attestation(agent_id, envelope)`, which verifies the envelope against the record and the
current root first.

### 3.4 Bound of a decision

With `P` the population before the birth (`P ≤ max_population − 1`) and `F ≥ 1` its founders, the list
holds at most: `P` individual attestations; `3 (P − F)` for the descendants (spent admission, birth
qualification, its statement); `2` for the presented qualification and its statement; `1` for the child
admission. So `N ≤ 4P − 3F + 3 ≤ 4·max_population − 4`. The depth alone does not bound it: siblings in
other branches and other founders add population attestations whatever the depth. Under g0
(`max_population = 6`) `N ≤ 20`; under the code's hard ceiling (`max_population ≤ 64`) `N ≤ 252`. A list
longer than the bound, or an envelope file over 16 KiB, is refused (`BUNDLE_TOO_LARGE`) before any
signature is checked. Reads per call are also bounded: `N` envelope files (≤ 16 KiB), `P` homes through
`lab.load` (record, spec, birth qualification, each ≤ 64 KiB, `MAX_FILE_BYTES`), every operation log
(≤ 256 logs × 64 lines × 256 KiB, §6.1, §6.3), `trust-history.log` (≤ 4096 lines), the fault log, and one
ledger read per locked section.

### 3.5 Present-scope attestation of an existing qualification (operator decision of 2026-10-23)

Sentinel's `SENTINEL_QUALIFICATION_RECORD_R8.json` stays **unchanged and historically unauthenticated**.
It names `reviewer_id = colony-review-481-r8`, and `colony_trust` requires the record's author to be the
envelope's issuer (`AUTHOR_NOT_ISSUER`). No issuer named `colony-review-481-r8` is created to satisfy
that rule. Instead, an identified, authorized external issuer makes a present-day statement:

1. A **new** qualification record `colony-lab.qualification/0`, with R8's `agent_id`, `agent_spec_id`,
   `state`, `scope`, `criteria_sha256`, `evidence_sha256`, `subject_code_sha256`,
   `evaluator_code_sha256`, and `reviewer_kind`/`reviewer_id` equal to the issuer's kind and id in the
   trust root. Its SHA-256 differs from R8's by construction. (`qualification/0` has closed fields and
   cannot carry the references below; changing it would change `colony_lab` and Sentinel's evaluator
   hash.)
2. A statement `colony-admission.attestation-statement/0` with closed, top-level fields (so that the
   `Kind` subject and author tuples of `colony_trust` apply unchanged): `statement_schema`,
   `subject_agent_id`, `subject_agent_spec_id` (subject); `issuer_kind`, `issuer_id` (author);
   `issuer_root_version`; `qualification_record_sha256` (the new record); `historical_record_path`,
   `historical_record_sha256` (R8); `evidence` (list of `{path, sha256}`, the verified R8 evidence, C9);
   `criteria_sha256`, `subject_code_sha256`, `evaluator_code_sha256` as verified;
   `verified_at_source_sha` (the `main` SHA at which the hashes were recomputed); `scope`;
   `campaign_replayed`; `campaign_evidence_sha256`; `historical_signature_claimed`.
3. Coherence, all required: `scope = PRESENT_ATTESTATION_OF_EXISTING_EVIDENCE` ⇒ historical fields set,
   `campaign_replayed = false`, `campaign_evidence_sha256 = null`; `scope = FRESH_CAMPAIGN` ⇒ historical
   fields `null`, `campaign_replayed = true`, `campaign_evidence_sha256` set;
   `historical_signature_claimed` is the literal `false`; the hashes equal the qualification record's;
   `issuer_id`/`issuer_kind` equal the record's reviewer and the envelope's issuer.
4. One envelope on each, by that issuer, under the current root.

The statement says what is attested now and its limits: it does not claim that a signature existed when
R8 was written, and when no campaign is replayed it says so. Any incoherence is `STATEMENT_INVALID`. The
same procedure applies to every qualification the controller uses. This contract emits no record and no
signature; the procedure runs only under the operator's separate authorization, with `LAB_TEST` keys in
trials.

## 4. Four properties, then the registrar

| Property | Question | A valid signature alone proves it? |
|---|---|---|
| Integrity | Is this exactly the record the envelope names? | No |
| Authenticity | Did a key of the current root, not revoked, sign it? | Only this, relative to that root |
| Authorization | May this issuer state this, for this lab, subject, record kind and birth; was the admission not spent by another operation? | No |
| Completeness | Is each frozen item present once, and nothing else? | No |

Only all four PASS on every decision item lets the operation continue; `NOT_EVALUATED` is never PASS.
Population items only need a status other than `UNAUTHENTICATED` (§3.2). The registrar's checks
(admissible criteria, admission bound to this birth, distinct identity, lineage, depth, population,
children, concurrency, costs, permissions, STOP) apply unchanged through P3 `prepare`.

## 5. Historical proofs and current trust; revocation (operator decision of 2026-10-23)

### 5.1 Two different things

- **Historical root of an operation**: the root (SHA-256, version) under which its items were verified at
  `PREPARED` and the admission spent at D1. It is frozen in the operation log as evidence of what was
  verified. It is not part of what a resuming caller presents, and it is not a trust decision for later
  steps.
- **Current trust policy**: the root the controller admits now (§5.3). It is read at the start of every
  call and before every `BEGIN`. Every frozen item is verified again against it. Signatures still verify
  under their declared `root_version`, so a benign rotation (old key `RETIRED`, new key `ACTIVE`) lets the
  operation continue; a revocation does not. The historical root never hides a revocation the current
  policy carries.

### 5.2 Effect of a revocation

A revocation is **applicable** to an operation when it makes a decision item (§3.1) fail: a key or an
envelope of the child admission, of the presented qualification or statement, or of an attestation of
the parent or of an ancestor. A revocation that touches only population items (another branch) is not
applicable: that individual becomes `SUSPENDED` and stays counted, and the operation continues.

| When the applicable revocation is seen | Effect |
|---|---|
| Before D1 (nothing spent) | Refused without consumption, `TRUST_REVOKED_BEFORE_CONSUMPTION` (no line before `PREPARED`; `REFUSED` line after it). When the failing item is an attestation of the parent or of an ancestor, the code is the same and the verdict adds the detail `FILIATION_SUSPENDED` (the status of that individual, §3.2); there is no second code |
| After `DONE D1`, before `COMMITTED` | Terminal `FAILED_CONSUMED`, `TRUST_REVOKED_AFTER_CONSUMPTION`; the authorization stays spent; no further step |
| After this operation's `COMMITTED` line (installed after it) | The birth stays a historical fact and is never erased. **Suspension** is a status (`SUSPENDED`, §3.2): the individual stays counted. It carries two separate bans: **filiation ban**, enforced by the controller (it cannot be a parent or an ancestor of a later birth, which is then refused as in the first row, with the detail `FILIATION_SUSPENDED`); **execution ban**, which needs the lab itself (T7, separate gate) and is only reported before that (`EXECUTION_SUSPENDED` in the verdict and status; the operator can `STOP` the lab) |

If the current policy cannot be established (file missing, unreadable, not regular, pin mismatch, version
below the floor, history inconsistent, not `LAB_TEST`), nothing continues: `TRUST_CURRENT_UNAVAILABLE`,
non-terminal (§6.6).

### 5.3 How the controller learns a revocation; monotonic installation; serialization

The controller learns a revocation **only** from a root installed by the operator with
`Controller.install_trust(root, pin, minimum_version)`. Under L1 (§6.1) it checks the root (`check_root`)
and refuses (`TRUST_UPDATE_REFUSED`, nothing written) unless, against the last installed root:

- `root_version` is strictly greater and `minimum_version` is not lower;
- no issuer and no key disappears; an issuer keeps its `issuer_kind` and its `scopes`; a key keeps its
  `public_key` and `introduced_in_root`; a key `REVOKED` stays `REVOKED`; a key `RETIRED` never becomes
  `ACTIVE` and keeps its `retired_in_root`; the only status changes are `ACTIVE → RETIRED` (setting
  `retired_in_root` once, equal to the new root's `root_version`, never lower: a retroactive retirement would
  make earlier envelopes fail `KEY_RETIRED`, `trust.py`, `verify_envelope`, which is a revocation in effect and must be
  installed as one) and `ACTIVE`/`RETIRED → REVOKED`; `revoked_envelopes` only grows;
- the version is above every root version recorded in any operation log.

It then appends `{root_version, root_sha256, pin, minimum_version}` to the append-only
`trust-history.log` and writes the policy file (temporary file, `fsync`, `rename`, `fsync` of the
directory), both in the operator's trust directory. That directory is given at construction, must be
outside the lab root, outside the repository checkout and outside every sandbox view, and holds regular,
single-link files in mode 0600 (refused otherwise). On every call the policy file must match the last
history entry. `trust-history.log` is read strictly (canonical, terminated lines, at most 4096); any
torn or foreign line makes the current trust unavailable until a manual operator procedure (never
automated here). An installation interrupted after its history line and before its rename is completed by
calling `install_trust` again with exactly the root of that last entry (the only case where an equal
version is accepted); until then `TRUST_CURRENT_UNAVAILABLE` holds. The pin stored next to its root protects against a lab-root writer, not against the
operator (§13).

A birth holds L1 from its first check to its last line of the call, so an installation through
`install_trust` is ordered before the call (seen by it) or after it (seen by the next call or resume). The
commit boundary is the `COMMITTED` line: a revocation installed before it ends the operation as §5.2 says;
one installed after it only suspends. This ordering covers nothing else and is not presented as doing so:
a revocation not yet installed, an edit of the trust directory made without `install_trust`, and the
latency between a compromise and its installation are not covered. A check "just before" a step does not,
by itself, remove any race.

## 6. The transaction

### 6.1 Locks and one open operation

Fixed order, never reversed:

1. **L1** `registrar.lock` (existing advisory `flock`, never deleted), taken non-blocking by the controller
   (and by `install_trust`, `recover`, `abandon`, `terminate`, `quarantine_partial_home`,
   `set_aside_terminal_home`, `acknowledge_torn_tail`, `store_individual_attestation`) and held until the
   call's last operation-log line. A second caller gets `REGISTRAR_BUSY`. P3 provides a registrar entry
   point for "L1 already held by the caller".
2. **L2** the ledger `flock`, short, inside `colony_trust`.

L1 is never taken while L2 is held. Run slots are independent of births.

**At most one non-terminal operation per lab.** Under L1, before anything else, the controller reads every
`admission-ops/*.log`; if one operation is neither `COMMITTED`, `REFUSED`, `ABANDONED` nor
`FAILED_CONSUMED` and is not the one being resumed, the call is refused `OPERATION_PENDING`. A log named by a `TERMINATED_EXTERNALLY`
entry of the fault log (§7.3) is terminal and is not read by this scan: its torn tail, inconsistency or
corruption blocks only its own child id (`OPERATION_LOG_FAULTY`). The
population and the ceilings therefore cannot change between the calls of an open operation through the
controller. The directory holds at most 256 logs (`OPERATION_LOGS_FULL` refuses a new child beyond that,
a declared capacity limit), so this scan reads at most 256 × 64 lines. Direct calls to `Registrar.birth` or `Supervisor.admit` bypass this rule until the lab enforces
it (T7); declared in §13.

### 6.2 Frozen operation identity

The `PREPARED` line freezes: child `agent_id` and `agent_spec_id`, parent `agent_id`, policy pin, `lab_id`,
historical root SHA-256 and version, the frozen item list of §3.1, the SHA-256 of the presented
qualification, statement, admission and their envelopes, the budget, lab permissions, declared diff, the
**complete canonical registrar `BirthPlan`** (P3: the sealed child record, ids, parent, generation, policy
pin, budget, permissions, diff, and the population, children and budget counts it was checked against),
the attempt number and the boot id. `operation_sha256` is the SHA-256 of
that frozen content, current trust excluded.

A resuming call presents again the child spec, permissions, budget, diff, the presented records and
envelopes, and the attempt number. The controller compares their digests to the frozen ones; it never
recomputes the item list, the plan or the historical root. Any difference is `OPERATION_DIVERGENT`
(nothing written, the open operation unchanged).

### 6.3 Operation log

`admission-ops/<child agent_id>.log` in the lab root: append-only, one canonical JSON object per line, each
written whole then `fsync`ed (directory `fsync`ed when the file is created). Lines: `PREPARED`, `BEGIN Dk`,
`DONE Dk`, `REFUSED`, `INTERRUPTED_RECOVERED Dk`, `TORN_TAIL_ACKNOWLEDGED`, `ABANDONED`, `TERMINATED`,
`FAILED_CONSUMED`, `BEGIN_CANCELLED Dk`, `QUARANTINE_BEGIN`, `QUARANTINE_DONE`, `SET_ASIDE_BEGIN`, `SET_ASIDE_DONE`,
`DURABILITY_FAULT`, `COMMITTED`; each carries `operation_sha256`, attempt, the current-root SHA-256 and
version used, the boot id, and a code. At most 64 lines per child and 256 KiB per line; lines 57 to 64 are
reserved for the lines that end an operation or clear it away: `TERMINATED`, `FAILED_CONSUMED` or
`ABANDONED`, `SET_ASIDE_BEGIN`, `SET_ASIDE_DONE` (each at most once in the reserve) and
`TORN_TAIL_ACKNOWLEDGED` (at most twice). Any other line beyond 56 is refused `OPERATION_LOG_FULL`, so an
operation can always be ended and its home set aside.

Strict reading, one rule: every line must be canonical and newline-terminated, with one exception. A final
unterminated fragment (a torn tail) is reported as `TORN_TAIL` and blocks the child until the operator's
`acknowledge_torn_tail(child)` writes `"\n"` followed by a `TORN_TAIL_ACKNOWLEDGED` line naming the SHA-256
of exactly the fragment's bytes. From then on, a non-canonical line is accepted only when the very next
line is a `TORN_TAIL_ACKNOWLEDGED` naming its exact bytes; it counts as a transition that did not happen.
Nothing is truncated or deleted. The reason is not that the fragment can never reach the disk, but that a
fragment means the write of that line never completed, so no `fsync` of it ever succeeded and the
controller never acted on it. Any other non-canonical line, or an acknowledgement naming other bytes, is
`OPERATION_LOG_CORRUPT` (blocked, no procedure in this contract). Since the state of that operation is
unknown, it may be open: a corrupt log found by the scan of §6.1 refuses every birth, not only its child's.

### 6.4 Durable steps

Each step `Dk` (k = 1…3) is bracketed: `BEGIN Dk`, the artefacts written and made durable, then `DONE Dk`,
written only after every write and `fsync` of the step reported success.

| Step | Artefacts | Re-checked before `BEGIN` |
|---|---|---|
| D0 `PREPARED` | the `PREPARED` line, after a complete dry run (trust without spending, P2 `check_bundle`; P3 `prepare`) | one open operation, current trust, STOP |
| D1 `CONSUMED` | one ledger line `colony-trust.consumed/1` carrying `operation_sha256` (P2 `consume`) | current trust, STOP |
| D2 `ADMISSION_RECORDED` | `registrar-admissions/<child>.json` (P3 writer: whole write, `fsync`, directory `fsync`) and the stored envelopes and statement of §3.3 | current trust |
| D3 `HOME_WRITTEN` | the child's home through `Supervisor.admit`, then, by the controller: `fsync` of `individuals/`, the home and its subdirectories, and a byte comparison of `spec.json`, `record.json`, `birth_qualification.json`, `usage.json` against the expected bytes | current trust, STOP |
| D4 `COMMITTED` | the `COMMITTED` line, with the SHA-256 of the child record | current trust |

The registrar reads STOP again inside `commit`, just before its first write (`registrar.py`, before
`_record_admission`), so a refusal can come after `BEGIN Dk` is written. P3 guarantees that every
`RegistrarError` raised by `commit` for a step is raised before any write of that step (§12); an error
during a write is never reported as a `RegistrarError` refusal (today `Registrar.birth` maps `OSError` to
`LAB_IO_ERROR`, `registrar.py`; P3 keeps that mapping out of `commit`). At D3, `BEGIN_CANCELLED` applies only to
the registrar's own refusals (STOP and its own checks in `commit`); any error that comes from
`Supervisor.admit`, even one raised before its first write, follows the D3 limits paragraph below
(`DURABILITY_UNKNOWN`, or the home comparison for `ALREADY_ADMITTED`), never `BEGIN_CANCELLED`. The controller then
appends `BEGIN_CANCELLED Dk` with the code: the step did not happen and the operation is back at its last
`DONE` line, non-terminal. A crash before that line leaves `BEGIN Dk` open (`INTERRUPTED`), which `recover`
classifies `ABSENT` in the same boot (§7.4). Any other error of the step stays `DURABILITY_UNKNOWN`.

D3 limits, declared (§13): `Supervisor._write_new` makes a single `os.write` and `fsync`s the file but not
its directory; the controller's byte comparison detects a short write but reads the page cache, and its
directory `fsync` comes after `admit`; the journal is created by `sentinel_activity` (SQLite WAL,
`synchronous=FULL`), whose `fsync` failures surface as a generic `UNAVAILABLE`. Therefore any error
raised by `Supervisor.admit` during D3 is treated as `DURABILITY_UNKNOWN` (§7), except `ALREADY_ADMITTED`
raised before anything is written because a home already exists: the controller then compares that home
with the expected bytes; equal, it is the operation's own home from an earlier attempt (recovery rules
apply); different, it is `HOME_CONFLICT` (a bypass of the controller, blocked, non-terminal). A home
created by a bypass with exactly the expected bytes cannot be told apart from the operation's own; it is
the same individual (declared, §13). Removing these limits needs
a `colony_lab` amendment, which makes Sentinel's R8 and the pilot's PC2 stale (§11, T7).

### 6.5 States, transitions and outcomes

The state is recomputed on every call from the operation log, the ledger, the admission record, the stored
envelopes and the home. When a durable fact contradicts the log (a `DONE D1` without its ledger line, a
ledger line without `PREPARED`, a home without `DONE D2`), the operation is `OPERATION_STATE_INCONSISTENT`,
blocked.

Transitions (operator actions in italics):

- `PREPARED` → `BEGIN D1` | `REFUSED` | *`ABANDONED`* (only while the ledger has no line for it).
- `BEGIN Dk` → `DONE Dk` | `DURABILITY_FAULT` (blocked, §7) | *`INTERRUPTED_RECOVERED Dk`* with result
  `ABSENT` → `BEGIN Dk` again (same k), `PRESENT` → `BEGIN Dk+1` (or `COMMITTED` after D3), `PARTIAL` →
  for D2 `BEGIN D2` again writing only the missing files, for D3 *quarantine* (§8.1) then `BEGIN D3`.
- `DONE D1` or later → next `BEGIN` | `FAILED_CONSUMED` (terminal code, §6.6) | *`TERMINATED`* then
  `FAILED_CONSUMED`.
- `BLOCKED_DURABILITY` → *`terminate`*: `FAILED_CONSUMED` or `ABANDONED` by the ledger finding, written in
  the log or, when the log is the faulty file, recorded externally (§7.3).
- `BEGIN Dk` → `BEGIN_CANCELLED Dk` (registrar refusal before any write, §6.4) → back to the last `DONE`.
- `DONE D3` → `COMMITTED`.
- `PREPARED` after `INTERRUPTED_RECOVERED D1 ABSENT` may still be *`ABANDONED`*.

No state goes back before D1 once a ledger line bound to the operation exists.

Outcome classes, reported distinctly; "no effect" is claimed only for the first:

| Class | When | Persistent traces |
|---|---|---|
| `REFUSED_BEFORE_DURABLE_EFFECT` | refused before `PREPARED` | nothing of this operation; only infrastructure that may already exist or be created empty (`registrar.lock`, `registrar-admissions/`, `admission-ops/`, `admission-envelopes/`) |
| `REFUSED_AFTER_PREPARE` | refused after `PREPARED`, before `BEGIN D1` | the `PREPARED` and `REFUSED` lines; nothing spent; a new attempt is allowed |
| `INTERRUPTED` | an open `BEGIN Dk`, or a torn tail | what the interrupted step wrote (a ledger line, admission files, a partial home); blocked until the operator acts (§7, §6.3); while open it also blocks every other birth (§6.1) |
| `FAILED_CONSUMED` | a terminal code after `DONE D1`, or `TERMINATED` | the ledger line (authorization spent); after D2 the admission record and stored files (the child identity is spent: `ADMISSION_CONFLICT` for any other admission); after `BEGIN D3` the child's home, complete or partial, counted as `UNAUTHENTICATED`, so every later birth is refused until the operator sets it aside (§8.2) |
| `COMMITTED` | `COMMITTED` written | the birth; a later identical call returns the established result without running anything again |

### 6.6 Terminal and non-terminal codes

After `DONE D1`, exactly two codes end the operation (the controller writes `FAILED_CONSUMED`):
`TRUST_REVOKED_AFTER_CONSUMPTION` (an applicable revocation, §5.2) and `OPERATOR_TERMINATED` (the
operator's explicit `terminate(operation_sha256)`, which writes `TERMINATED` then `FAILED_CONSUMED`, or
records the termination externally when the log is faulty, §7.3).

Every other refusal leaves the operation where it is and writes nothing for it, except the
`BEGIN_CANCELLED Dk` line when it is raised by the registrar inside `commit` after `BEGIN Dk` (§6.4): `TRUST_CURRENT_UNAVAILABLE`,
`LAB_STOPPED` (wherever it is raised, including by the registrar at `commit`), `REGISTRAR_BUSY`,
`OPERATION_DIVERGENT` (the divergent call is refused, the open operation is untouched), `OPERATION_PENDING`,
`POPULATION_UNAUTHENTICATED`, `POPULATION_CHANGED`, `HOME_CONFLICT`, any other registrar refusal at
`commit`, `LAB_IO_ERROR`, `RECOVERY_REFUSED`, `COLD_READ_REQUIRED`, `STORED_FILE_DIVERGENT`,
`OPERATION_LOG_FULL`, `OPERATION_LOG_FAULTY`, and the blocked states `DURABILITY_UNKNOWN`, `LEDGER_DURABILITY_UNKNOWN`, `TORN_TAIL`,
`OPERATION_STATE_INCONSISTENT`, `OPERATION_LOG_CORRUPT`, `LEDGER_CORRUPT`. Those that only a bypass of the
controller can cause leave the decision to the operator (`terminate`, or removing the cause). An
unavailable trust policy or a STOP never burns a legitimate birth.

### 6.7 Resume

A call for the child of the open operation compares its presented inputs with the frozen ones (§6.2):

- **identical**: every frozen item is verified again against the current trust; once D1 is done, the child
  admission is checked as `CONSUMED_BY_THIS_OPERATION`, which is never an acceptance and never a new
  authentication success. The call continues only from a `DONE` line (or an operator recovery result).
  P3 `commit(plan)` takes the frozen plan from the `PREPARED` line and never calls `prepare` again. It
  is idempotent per step: at D2 an existing admission record equal to the frozen one is accepted; at D3
  an existing complete home equal to the expected bytes is accepted. The population is classified again
  with the operation's own home as `OWN_OPERATION` (§3.2); its counts, own child excluded, must equal the
  counts frozen in the plan, otherwise `POPULATION_CHANGED` (only a bypass can cause it; non-terminal).
  The operation's own child, admission and home are excluded from `ALREADY_ADMITTED`.
- **divergent**: `OPERATION_DIVERGENT`, nothing written.

### 6.8 Directories

`admission-ops/`, `admission-envelopes/`, `admission-quarantine/` and `registrar-admissions/` are created in
mode 0700 by the operator account, must be real directories (never links), and are checked on every call
(`LAB_IO_ERROR` otherwise). Their permissions are the only protection of their content (§13).

## 7. Durability faults and interrupted steps (correction A)

After an `fsync` error, reading the same bytes back from the same running system proves nothing about
their durability. Rules:

1. On an `fsync`, short-write or `Supervisor.admit` error during a step, the controller writes nothing more
   to the faulty file, does not call `fsync` again on it, records the fault in the operator's fault log
   (outside the lab root, preferably another filesystem) and, only if the operation log is not the faulty
   file, appends `DURABILITY_FAULT` to it. It returns `DURABILITY_UNKNOWN`.
2. A fault on the **ledger** (shared by the colony) blocks every birth, not only this operation: every call
   reads the fault log and refuses while a ledger fault is recorded (`LEDGER_DURABILITY_UNKNOWN`). Refused:
   `admit_authenticated`, `recover`, `abandon`, `quarantine_partial_home`. Still allowed, because they
   only read the ledger or do not touch it: `terminate`, `set_aside_terminal_home`, `acknowledge_torn_tail`,
   `install_trust`, `store_individual_attestation`, the status report. The block is lifted only by the
   restore gate (§13), which this contract does not define; no call of this contract clears it.
3. An operation with a recorded fault is `BLOCKED_DURABILITY`. It is never resumed on the presence of its
   bytes. Its exits are an operator restore of verified copies (backup and restore are a separate gate) or
   the operator's `terminate(operation_sha256)`, which ends it without resuming it:
   - if the operation log is writable (the fault was elsewhere), `TERMINATED` then `FAILED_CONSUMED` are
     appended there when a ledger line bound to the operation exists, or `ABANDONED` when none exists;
   - if the operation log itself is the faulty file, the termination is recorded in the operator's fault
     log (`TERMINATED_EXTERNALLY`, with the operation and the ledger finding), never in the faulty file;
     the controller reads the fault log on every call and treats that operation as terminal, which
     releases `OPERATION_PENDING` (§6.1). Its later set-aside (§8.2) is journaled in the fault log too.
     That child `agent_id` cannot be attempted again (`OPERATION_LOG_FAULTY`) until the restore gate; a
     new birth uses another child id.
   The ledger finding needs no cold read: a line absent from the page cache is absent from the disk, so
   "no ledger line" safely leaves the envelope unspent; a line present makes it `FAILED_CONSUMED` whether
   or not it is durable, so a spent authorization never becomes available again. If the fault log itself
   cannot be written, every birth stays blocked until the restore gate (§13).
4. An `INTERRUPTED` step without a recorded fault is not resumed automatically. The operator runs
   `recover(operation_sha256, k)` under L1. It refuses if a fault is recorded. It classifies each artefact
   of step k as absent, equal to what the operation expects, or divergent (any divergent → `RECOVERY_REFUSED`;
   for D1 the ledger must hold zero or one line for the operation). Then:
   - `ABSENT` may be decided in the same boot: the page cache holds at least what is on disk, so a file
     absent from it is absent from disk;
   - `PRESENT` and `PARTIAL` require a **cold read**: the current boot id must differ from the one recorded
     in the `BEGIN Dk` line (a reboot discarded the page cache, so the bytes read come from the device).
     In the same boot they are refused (`COLD_READ_REQUIRED`). The boot id is read from
     `/proc/sys/kernel/random/boot_id`; the operator API has no parameter to supply it. Tests replace it
     through a test-only seam that is absent from every operator entry point.
   It writes `INTERRUPTED_RECOVERED Dk` with the result.
5. Declared NOT PROVEN (§13): a device or controller cache that acknowledges writes it has not persisted;
   a fault whose two records both failed (it then looks like a crash, and rule 4 still requires a cold read
   for `PRESENT`).
6. A torn ledger line is `LEDGER_CORRUPT` (existing rule): every birth stops. Its handling is a manual
   operator procedure, never automated by this contract.

## 8. Quarantine and setting aside (correction F)

Both are explicit operator actions under L1, journaled in the operation log, limited to one operation,
blocked by any unexpected entry, link or divergent byte (`QUARANTINE_REFUSED`, nothing moved), and never
delete anything. Homes moved this way leave `individuals/`, so they are no longer loaded or counted; they
stay for audit. A `QUARANTINE_BEGIN` or `SET_ASIDE_BEGIN` without its `DONE` line is resolved by calling the
same action again: the home must be in exactly one of its source and destination (otherwise refused); the
rename is done if still needed, both directories are `fsync`ed and the `DONE` line written. An `fsync` or
`rename` error during either action follows §7.1: fault recorded, nothing retried on the faulty directory,
`DURABILITY_UNKNOWN`, and the action is refused while the fault is recorded (restore gate, §13).

The journal is checked only by `quarantine_partial_home` (§8.1); `set_aside_terminal_home` moves it
without checking its content (§8.2). The journal directory cannot be compared byte for byte (its bytes are
not reproducible) and opening it with SQLite could replay or create WAL files. It is checked on a byte copy
made outside the lab root; the originals are never opened by SQLite. Its entries must be only the store
file `activity.sqlite3` and its `-wal`, `-shm` and `-journal` companions. A kill during `ActivityStore.create` (`sentinel_activity/store.py`)
can leave the store file empty, or a WAL whose transaction never committed, so the copy is accepted in
exactly three states: no store file; a store file of zero bytes (companions, if any, of zero bytes); or a
copy whose committed content, as SQLite reads it on the copy, is either empty of any table (the creating
transaction never committed) or verifies as an empty journal of this individual with this budget. Anything
else is `QUARANTINE_REFUSED`.

### 8.1 Partial home of an open operation

`quarantine_partial_home(operation_sha256)` runs only for an operation whose log shows `DONE D2` and
`INTERRUPTED_RECOVERED D3 PARTIAL` (cold read, §7.4), with no fault recorded. Every entry must be a known
name of `Supervisor.admit` (`tasks/`, `results/`, `j01-lab-memory/`, `spec.json`, `record.json`,
`birth_qualification.json`, `usage.json`) and every present file equal to the expected bytes (journal:
above). It writes `QUARANTINE_BEGIN`, renames the home to `admission-quarantine/<operation_sha256>/<attempt>`
on the same filesystem, `fsync`s both directories and writes `QUARANTINE_DONE`. D3 may then run again for
the same operation.

### 8.2 Home of a terminal operation

`set_aside_terminal_home(operation_sha256)` runs only for an operation ended `FAILED_CONSUMED` (or
`TERMINATED_EXTERNALLY`, §7.3) after `BEGIN D3`, whether D3 completed, was interrupted or faulted, and
whether or not a cold read was made: it grants no trust and only moves the home out of the population. It
is refused while a fault is recorded on `individuals/`, on the home or on `admission-quarantine/`, the
directories it would `fsync` (§7.1); that home then stays `UNAUTHENTICATED` until the restore gate (§13). Such
a home may have been run before it ended or since (§13), so its run artefacts are not compared. Each of
`spec.json`, `record.json` and `birth_qualification.json` must be absent, or a prefix (possibly empty) of
its expected bytes, or equal to them: a short or missing write cannot be a different identity, while any
other content can. Every other entry must be a name `Supervisor.admit` or `Supervisor.run` creates
(`tasks/`, `tasks/*.json`, `tasks/*.json.tmp`, `results/`, `results/*.json`, `usage.json`,
`usage.json.tmp`, `inflight.json`, `j01-lab-memory/` and the journal files `activity.sqlite3` with its
`-wal`, `-shm` and `-journal` companions), with no link anywhere in the tree; the run
artefacts and the journal are moved intact, as evidence. Any unknown name, link or divergent identity file is `QUARANTINE_REFUSED`, nothing
moved. It writes `SET_ASIDE_BEGIN`, renames the home to
`admission-quarantine/<operation_sha256>/terminal`, `fsync`s both directories and writes `SET_ASIDE_DONE`.
Until then that home is counted `UNAUTHENTICATED` and refuses every birth. Between `DONE D3` and
`COMMITTED`, and after `FAILED_CONSUMED` until it is set aside, the home can still be run through
`Supervisor.run` or `Registrar.run`: nothing in this contract guards execution (§13, T7).

## 9. STOP, concurrency, resources

- The operator's `STOP` is read at the start of a call, after `PREPARED`, before `BEGIN D1` and before
  `BEGIN D3`. The registrar reads it once more inside `commit`; raised there, after `BEGIN Dk`, it is
  closed by `BEGIN_CANCELLED Dk` (§6.4). STOP leaves the operation at its last `DONE` line (non-terminal); it continues after the
  operator's `resume()`. STOP undoes nothing.
- One commit at a time under L1; one open operation per lab (§6.1).
- Bounds: §3.4 and §6.3.

## 10. Population ceilings and planned roles (correction D)

The controller never raises a ceiling: policy g0 (`max_generation = 2`, `max_population = 6`,
`max_children_per_parent = 2`, `max_concurrent_runs = 1`, `colony_budget` summed over every admitted
individual) applies as frozen; any other policy needs its own reviewed pin. Under g0, at most, in this
order, each birth being a separate operator authorization:

1. a first child of Sentinel (generation 1), then its own qualification (external, before any child of it);
2. a second child of Sentinel (generation 1) — Sentinel's last place; a real birth of the pilot would take
   one of these two places;
3. grandchildren (generation 2, the last generation: a generation-3 birth is `GENERATION_LIMIT`) only from
   a qualified child, at most two per child, within `max_population = 6` and the colony budget.

A plan listing four roles is not an authorization for four direct descendants: roles three and four can
only be grandchildren, or wait for a separately reviewed policy. Which role each birth carries is the
operator's choice at each authorization. With `max_concurrent_runs = 1`, the colony's runs are serialized.

## 11. Qualification scope (correction E)

Unchanged hashes (Sentinel subject `2c926421…`, evaluator `41b78971…`, pilot `97fb6b04…` at `7b4b2ef6`)
mean that the existing evidence still covers the same bytes. They do not qualify the new composition. The
controller gets its own qualification over its exact dependencies: `admission_code_sha256` hashes the
transitive closure, computed by AST, of the repository modules imported from `colony_admission/` (which
includes `colony_trust/`, `colony_registrar/`, `colony_lab/__init__.py`, `a1_identity`, `a1_ref/`,
`lineage`, `supervisor` and the `sentinel_activity` modules they import), plus `POLICY_G0.json`; the
evidence records the `cryptography` and Python versions. Its criteria are pinned before any trial, its
record is emitted only after a favourable review by an evaluator outside the colony, and a change to any
file of the closure makes it stale. A change to `colony_lab/` or `sentinel_activity/` also makes Sentinel's
R8 and the pilot's PC2 stale.

## 12. Interfaces the later slices must provide (requirements, not code)

- **P2, `colony_trust` amendment 4** (amendment pushed alone before code): `check_bundle` (verify without
  spending); `consume(…, operation_sha256)` (verify again and append in one locked section;
  `CONSUMED_BY_THIS_OPERATION` when already spent by this operation, never an acceptance);
  `verify_consumed(envelope, ledger, operation_sha256)`; ledger `colony-trust.consumed/1` carrying the
  operation (lines `/0` stay readable, bound to no operation, never resumable); completeness keyed by
  (kind, subject, record SHA-256); the kind `colony-admission.attestation-statement/0` (flat subject and
  author fields, purpose `QUALIFICATION_STATEMENT_ATTESTED`, external issuers, durable); a per-envelope
  classification "genuine but revoked"; whole writes, directory `fsync` on creation, a distinct
  `LEDGER_DURABILITY_UNKNOWN` on `fsync` error with no retry. `verify_bundle` keeps its behaviour.
- **P3, `colony_registrar` amendment 3**: `prepare(…) → BirthPlan` (no write, frozen, hashed);
  `commit(plan)` under an L1 held by the caller, idempotent per step and excluding its own operation's
  artefacts (§6.7); `prepare` refuses `ADMISSION_CONFLICT` when an admission record already exists for the
  child and differs from the one presented, so that conflict is seen before any consumption; every `RegistrarError` of
  `commit` raised before any write of its step, and write errors raised distinctly (§6.4); its own
  writer for the admission record (whole write, `fsync`, directory `fsync`);
  `exclusive()`; `birth()` = `exclusive` + `prepare` + `commit`, behaviour unchanged.
- **P4–P6, `colony_admission`**: `required_attestations`, `Controller.admit_authenticated`,
  `install_trust`, `store_individual_attestation`, `recover`, `acknowledge_torn_tail`, `abandon`,
  `terminate`, `quarantine_partial_home`, `set_aside_terminal_home`, a population status report (including
  `SUSPENDED` and `EXECUTION_SUSPENDED`), the operation log, verdicts; the crash matrix; the controller's
  campaign.

None of P2–P6 changes `colony_lab/`, `sentinel_activity/` or `colony_pilot/`.

## 13. Limits (NOT PROVEN)

- The operator account holds the trust directory, keys, code and lab root; whoever controls it controls
  admission. The pin stored with its root does not protect against it.
- No trusted clock; `RETIRED` relies on declared root versions; only `REVOKED` stops a compromised key.
- A revocation reaches the controller only when installed; its latency is the operator's.
- A writer of the lab root can truncate or poison the ledger and the operation logs (fail closed, or a
  replay bounded by identity uniqueness), and can delete homes to evade population ceilings: there is no
  trusted counter.
- Locks are advisory; deleting `registrar.lock` lets a second birth run. Direct calls to
  `Registrar.birth`, `Supervisor.admit`, `Supervisor.run` or `Registrar.run` bypass the controller until T7.
- D3 durability (§6.4): single `os.write`, late directory `fsync`, SQLite faults indistinguishable; device
  caches; a fault whose two records failed (§7.5); a fault log that cannot be written blocks every birth
  until the restore gate (§7.3). A home created by a bypass with exactly the expected bytes is accepted as
  the operation's own (§6.4).
- Restoring an older ledger, operation log or trust history would make spent admissions or revoked keys
  usable again: backup and restore are a separate gate and must never move them backwards.
- Execution bans after a revocation need the lab (T7).
- An `OPERATION_LOG_CORRUPT` log blocks every birth (§6.3) and, since it cannot be read strictly, also
  `terminate` for that operation, except a log already recorded as faulty, which is terminated externally
  (§7.3) whatever it reads like; like `LEDGER_CORRUPT`, only a manual operator procedure outside this
  contract can end it. The same holds for a child whose reserve is exhausted by a third torn tail.
- A kill inside `_write_new` between opening and writing, in D2 or D3, leaves an empty or short file;
  a run during an interrupted D3 changes `usage.json`. `recover` classifies these as divergent
  (`RECOVERY_REFUSED`) and the quarantine needs equal files, so the only exit is `terminate` (then, for D3,
  `set_aside_terminal_home`), which spends a legitimate birth; after D2 the admission record stays.
- A home whose D3 faulted on `individuals/`, the home or `admission-quarantine/` cannot be set aside
  without the restore gate (§8.2), and blocks every birth until then.
- A run between `DONE D3` and `COMMITTED` is not prevented. The resume then compares only the identity
  files (§3.2, `OWN_OPERATION`), so the birth can still be committed; the run's artefacts stay in the home
  as evidence. That individual has run before being authenticated.
- `LAB_TEST` only; a non-test root needs a code change under a separate gate. Test keys are derived from
  public labels and authenticate nothing outside the tests.

## 14. Amendment history

- `colony-admission/0`, written before any code after the operator's decision of 2026-10-23
  (present-scope attestation of R8, revocation before `COMMITTED`, corrections A–F). Revised in the same
  pull request, before any pin, after the independent review of `016fdc75` (unfavourable): frozen operation
  identity and item list, one open operation per lab, population status and suspension model, terminal
  home set aside, D2 partial recovery and full transitions, D3 durability limits, cold-read recovery,
  monotonic trust installation, terminal and non-terminal codes, transitive dependency closure, torn tail
  rule, flat statement fields, envelope storage and naming, journal checked on a copy, colony-wide ledger
  faults, role order under g0, trust directory, scenarios made specific. Revised again, before any pin,
  after the independent review of `62d686a3` (favourable with conditions): applicable revocation defined
  on decision items, `SUSPENDED` stated as non-authentication, `OWN_OPERATION` status, complete frozen
  plan, external termination after a fault on the operation log, setting aside of a run terminal home,
  terminal codes reduced to two, torn-tail format, install monotonicity on every key field, read bounds,
  reserved log lines, `ADMISSION_CONFLICT` before consumption, boot id seam, declared differences with #487
  and the registrar contract. Revised again, before any pin, after the independent review of `32c16311`
  (favourable with conditions): journal checked only for quarantine, and in the states a killed creation
  leaves; set-aside of a partial or faulted terminal home; reserved lines for set-aside; one revocation code
  before D1; `BEGIN_CANCELLED` for a registrar refusal after `BEGIN`; ledger-fault scope and lifting;
  corrupt log blocks every birth; no retroactive retirement; temporary run files; run before `COMMITTED`.
  Last textual corrections after the review of `5c552f63` (favourable with minor conditions): P3 guarantee
  in §12, `ALREADY_ADMITTED` outside `BEGIN_CANCELLED`, externally terminated logs out of the scan, faults
  during quarantine and set-aside, journal and result file names, declared limits for corrupt logs and
  empty or short files; then set-aside refused on a faulty directory, Supervisor errors outside
  `BEGIN_CANCELLED`, faulty logs terminated externally whatever they read like.
