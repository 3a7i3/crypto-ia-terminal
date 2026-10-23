# Colony authenticated admission: composition and transaction contract (`colony-admission/0`)

Status: **SOURCE_ONLY / LAB_ONLY / CONTRACT BEFORE CODE.** This document is normative for the slices that
implement it (P2 `colony_trust` amendment 4, P3 `colony_registrar` amendment 3, P4–P6 `colony_admission`).
It creates no code, no record, no envelope, no key and no individual. Every future trial stays
`LAB_TEST`. Nothing here is deployed, wired into `colony_lab.Supervisor`, or reachable from the Advisor,
the Operator API or the VPS. #286 is unaffected: no strategy, signal, risk, sizing, PPL, FIN, config or
epoch code is imported or changed.

Baseline read for this contract: `main` @ `7b4b2ef6fcdaab0ba9d3db81e2a2b28481a7a2ef` (merges of #485 and
#486). The scenarios that the implementation must pass are in `SCENARIOS_A0.json` in this directory,
pinned by its SHA-256 in the pull request that introduces both files; a later change to the scenarios is a
new file, never an edit of that one.

## 1. Why, and what already exists

`colony_trust` (#485) authenticates records and spends single-use `BIRTH_ADMITTED` envelopes in a
ledger. `colony_registrar` (#486) checks ceilings, lineage, exclusions and writes the admission record and
the child. They are independent: calling one after the other is not a transaction. A crash after the
ledger append loses a legitimate birth (`ENVELOPE_REPLAYED` on retry); the reverse order can leave an
admitted individual whose authentication is unknown. `Supervisor.admit` enforces neither.

This contract defines the composition: one owner, the attestations it derives itself, the separation
between historical proofs and current trust, the durable boundaries, and how an interrupted operation is
recovered or ended. It does **not** claim multi-file atomicity: no mechanism here demonstrates it. Each
durable step is written once, identifies itself and its operation, and the state is recomputed from those
durable facts on every call.

### Relation to #487 (draft, unchanged by this contract)

#487 (`docs/colony_registrar/STEP7_AUTHENTICATED_ADMISSION_PLAN.md`, head `e9f989a6`) is a checkpoint and a
plan. This contract takes from its §4 and makes normative: the controller called by the operator outside
the sandbox; trust root, minimum version, `lab_id` and policy pin supplied from outside the lab; the
required set derived from the records of the decision, never supplied by the individual; ancestors'
admissions verified as already spent without being spent again; the four properties evaluated separately;
the six result requirements (refusal without new consumption, no rollback of a consumption, explicit
recoverable state, exact-operation resume only, one commit under concurrency, no silent repair); and its
S7.2–S7.4 slicing. It adds what #487 leaves open: the owner and lock order (§6), the operation identity
(§6.2), the boundary markers and state machine (§6.3–6.5), durability faults (§7), revocation against
current trust (§5), quarantine (§8), the bundle bound (§3.4), ceilings (§10), the qualification scope
(§11), the present-scope attestation of an existing qualification (§3.5), and the interfaces the later
slices must provide (§12). #487 can be merged, closed or kept independently of this contract.

## 2. Owner, authorities, inputs and outputs

The single owner of an authenticated birth is a new operator package, `colony_admission`
(`Controller`). It imports `colony_trust`, `colony_registrar` and `colony_lab` and is imported by none of
them, by no worker, no task type and no lab module (AST test, extending the existing separation tests).
A new package is needed because the reviewed separation tests forbid `colony_registrar` to import
`colony_trust` (`tests/colony_registrar/test_registrar.py`) and `colony_trust` to import the registrar
(`tests/colony_trust/test_trust.py`).

| Input | Supplied by | Never from |
|---|---|---|
| Current trust policy: root, its SHA-256 pin, minimum `root_version`, `lab_id` (§5) | The operator, through `install_trust` (§5.3), stored outside the lab root | An individual's output, the lab root |
| Policy and its pin (g0 by default, `1226d889…`) | Code, or the operator with its own pin | An individual |
| Child spec, lab permissions, budget, declared diff | The operator | An individual's output taken as is |
| Parent qualification record, its statement (§3.5) and their envelopes | An external issuer | The lineage |
| Child admission record and its `BIRTH_ADMITTED` envelope | An external admitter | The lineage |
| Ancestors' and population records and their envelopes | **Read by the controller from the lab root** (§3.3) | A list supplied by the caller |

Outputs: the operation log (§6.3), one ledger line bound to the operation (P2), the registrar admission
record and the stored envelopes (D2), the child's home (D3), a coded verdict naming the operation state.
Consumers: the operator; a future read-only status projection (metadata only, no lab-root read by
Governance Tower; separate gate); qualification campaigns.

The operator account that holds the trust policy, the keys, the code and the lab root stays inside the
trust model; resistance to its compromise is not claimed (§13).

## 3. Attestations the controller derives

### 3.1 Rule

`required_attestations(lab, parent_agent_id, child_ids)` walks the lab with `lab.load` and returns the
exact list of (record kind, subject, record SHA-256) the decision needs. The caller supplies envelopes and
the two presented records (parent qualification with its statement, child admission); it never supplies
the list. An envelope not in the derived list is `ATTESTATION_UNEXPECTED`; a derived item without an
envelope is `ATTESTATION_MISSING`.

The existing completeness key of `verify_bundle` is (kind, subject). It is not sufficient here: two
children of the same parent each store a qualification of that parent, so two qualification records may
share (kind, subject). The derived items are therefore keyed by (kind, subject, record SHA-256); P2
provides that key (or the controller verifies each item in its own bundle). Identical records (same
SHA-256) are one item.

### 3.2 Required items

| Subject | Record | Kind / purpose | Authorized issuer | Use |
|---|---|---|---|---|
| Every individual of the population, founders included | `individuals/<id>/record.json` | `colony-lab.individual/0`, `INDIVIDUAL_ADMITTED` | `LAB_OPERATOR` | Durable, re-verified on every call |
| Every descendant of the population | `registrar-admissions/<id>.json` | `colony-registrar.admission/0`, `BIRTH_ADMITTED` | External | **Already spent** by an operation whose log is `COMMITTED` for that same individual; verified without being spent again (P2 `verify_consumed`) |
| Every descendant of the population | its `birth_qualification.json` (a qualification of its parent) | `colony-lab.qualification/0`, `QUALIFICATION_ATTESTED` | External | Durable |
| Every qualification above and the presented one | its statement (§3.5) | `colony-admission.attestation-statement/0`, `QUALIFICATION_STATEMENT_ATTESTED` (new kind, P2) | The same external issuer as the qualification | Durable |
| Parent | presented qualification | `colony-lab.qualification/0` | External | Durable |
| Child | presented admission | `colony-registrar.admission/0` | External | **Fresh**, spent once, bound to the operation |
| Child, after `COMMITTED` | `record.json` | `colony-lab.individual/0` | `LAB_OPERATOR` | A separate operator step outside the transaction; until it exists, the child cannot be a parent or an ancestor (completeness fails) |

The ancestors are a subset of the population, so the population rule covers them.

### 3.3 Storage

Envelopes and statements are stored outside the homes, in
`admission-envelopes/<agent_id>/<role>-<record_sha256>.json` (roles: `individual`, `admission`,
`birth-qualification`, `birth-statement`, plus each statement's own envelope). A home moved to quarantine
(§8) never takes them along. Files are written once (`O_EXCL`, no link followed, regular single-link file,
≤ 16 KiB each); a stored file that differs from what an operation expects blocks that operation.

### 3.4 Bound of a decision

With `P` the population before the birth (`P ≤ max_population − 1`) and `F ≥ 1` its founders, the derived
list holds at most:

- `P` individual attestations;
- `3 (P − F)` for the descendants: admission (spent), birth qualification and its statement;
- `2` for the presented parent qualification and its statement;
- `1` for the child admission;

that is `N ≤ 4P − 3F + 3 ≤ 4·max_population − 4`. The depth alone does not bound the list: siblings in
other branches and other founders add population attestations whatever the depth. Under g0
(`max_population = 6`) `N ≤ 20`; under the code's hard ceiling (`max_population ≤ 64`) `N ≤ 252`. Each
envelope file is ≤ 16 KiB and each record ≤ 64 KiB (`MAX_FILE_BYTES`), so one decision reads at most
`N × 80 KiB`. A list longer than the bound is refused (`BUNDLE_TOO_LARGE`) before any signature is
checked.

### 3.5 Present-scope attestation of an existing qualification (operator decision of 2026-10-23)

Sentinel's `SENTINEL_QUALIFICATION_RECORD_R8.json` stays **unchanged and historically unauthenticated**.
It names `reviewer_id = colony-review-481-r8`, and `colony_trust` requires the record's author to be the
envelope's issuer (`AUTHOR_NOT_ISSUER`). No issuer named `colony-review-481-r8` is created to satisfy that
rule. Instead, a present-day statement is made by an identified, authorized external issuer:

1. A **new** qualification record `colony-lab.qualification/0`, with the same `agent_id`, `agent_spec_id`,
   `state`, `scope`, `criteria_sha256`, `evidence_sha256`, `subject_code_sha256`,
   `evaluator_code_sha256` as R8, and `reviewer_kind`/`reviewer_id` equal to the issuer's kind and id in
   the trust root. Its SHA-256 differs from R8's by construction. (The `qualification/0` schema has
   closed fields, so it cannot carry the references below; changing it would change `colony_lab` and
   Sentinel's evaluator hash.)
2. A statement `colony-admission.attestation-statement/0` with closed fields:
   `statement_schema`; `subject {agent_id, agent_spec_id}`; `qualification_record_sha256` (the new
   record); `historical_record {path, sha256}` (R8) or `null` for a fresh campaign;
   `evidence [{path, sha256}]` (the verified R8 evidence, C9); `criteria_sha256`,
   `subject_code_sha256`, `evaluator_code_sha256` as verified; `verified_at_source_sha` (the `main` SHA
   at which the hashes were recomputed); `issuer {issuer_id, issuer_kind, root_version}`;
   `scope` ∈ `PRESENT_ATTESTATION_OF_EXISTING_EVIDENCE`, `FRESH_CAMPAIGN`; `campaign_replayed` (boolean)
   and `campaign_evidence_sha256` (`null` when not replayed); `historical_signature_claimed`, which must
   be the literal `false`.
3. One envelope on each, by the same external issuer, under the current root.

The statement says what is attested now and its limits: it does not claim that a signature existed when
R8 was written, and when no campaign is replayed it says so (`campaign_replayed: false`). The controller
refuses a qualification whose statement is missing, names another record, issuer or hash, or sets
`historical_signature_claimed` to anything but `false` (`STATEMENT_INVALID`). The same procedure applies to
every qualification used by the controller, fresh or not. This contract emits no record and no signature;
the procedure is executed only under the operator's separate authorization, with `LAB_TEST` keys in
trials.

## 4. Four properties, then the registrar

| Property | Question | A valid signature alone proves it? |
|---|---|---|
| Integrity | Is this exactly the record the envelope names? | No |
| Authenticity | Did a key of the current root, not revoked, sign it? | Only this, relative to that root |
| Authorization | May this issuer state this, for this lab, subject, record kind and birth; was the admission not spent by another operation? | No |
| Completeness | Is each derived item present once, and nothing else? | No |

Only all four PASS lets the operation continue; `NOT_EVALUATED` is never PASS. Then the registrar checks
(qualification under admissible criteria, admission bound to this birth, distinct identity, lineage,
depth, population, children, concurrency, costs, permissions, STOP) apply unchanged (P3 `prepare`). Any
refusal stops the operation.

## 5. Historical proofs and current trust; revocation (operator decision of 2026-10-23)

### 5.1 Two different things

- **Historical root of an operation**: the root (SHA-256, version) under which its envelopes were
  verified at D0 and spent at D1. The operation log records it. It is evidence of what was verified, not
  a trust decision for later steps.
- **Current trust policy**: the root the controller admits now, with its pin and minimum version,
  installed by the operator (§5.3). It is re-read and re-checked at the start of every call and before
  every durable step. The historical pin never hides a revocation the current policy carries.

At each of these points, every envelope of the operation is verified again against the current root
(revoked keys, `revoked_envelopes`, scopes); the signatures still verify under their declared
`root_version` (rotation keeps older envelopes valid with a `RETIRED` key; `REVOKED` stops them).

### 5.2 Effect of a revocation

| When the applicable revocation is seen | Effect |
|---|---|
| Before D1 (nothing spent) | Refused without consumption (`TRUST_REVOKED_BEFORE_CONSUMPTION`); the operation log records `REFUSED` |
| After D1, before `COMMITTED` | Terminal `FAILED_CONSUMED` (`TRUST_REVOKED_AFTER_CONSUMPTION`); the authorization stays spent; no further step runs |
| After `COMMITTED` | The birth stays a historical fact and is never erased. Its effects are handled separately: the individual is counted for ceilings but cannot be a parent or an ancestor (`FILIATION_SUSPENDED`, because its attestations fail at the next birth that needs them); an execution ban (`EXECUTION_SUSPENDED`) needs the lab itself (T7, separate gate) and is reported, not enforced, before that |

If the current policy cannot be established (file missing, unreadable, pin mismatch, version below the
floor, not `LAB_TEST`), the operation does not continue (`TRUST_CURRENT_UNAVAILABLE`).

### 5.3 How the controller learns a revocation, and serialization

The controller learns a revocation **only** from a new root installed by the operator with
`Controller.install_trust(root, pin, minimum_version)`. That call takes the colony admission lock L1
(§6.1), checks the root (`check_root`), refuses a version below the highest version ever installed or
recorded in any operation log (monotonic floor), writes the policy file outside the lab root (temporary
file, `fsync`, `rename`, `fsync` of the directory) and releases L1. A birth holds L1 from its first check
to its last line of the call, so an update installed through `install_trust` is ordered either before the
call (the call sees it) or after it (a later call or resume sees it).

This ordering removes no other race and is not presented as doing so: a revocation that is not yet
installed, an edit of the policy file made without `install_trust`, and a revocation installed after
`COMMITTED` are not covered by it. A check "just before" a step does not, by itself, remove any race.

## 6. The transaction

### 6.1 Locks

Fixed order, never reversed:

1. **L1** `registrar.lock` (existing advisory `flock`, never deleted), taken non-blocking by the controller
   at the start of a call and held until its last operation-log line. A second caller gets `REGISTRAR_BUSY`.
   P3 provides a registrar entry point for "L1 already held by the controller", so the controller does not
   lock itself out.
2. **L2** the ledger `flock`, short, inside `colony_trust` (existing).

L1 is never taken while L2 is held. `install_trust` takes L1 only. Run slots (`registrar-slots`) are
independent of births.

### 6.2 Operation identity

`operation_sha256` = SHA-256 of the canonical encoding of: child `agent_id` and `agent_spec_id`, parent
`agent_id`, policy pin, `lab_id`, historical root SHA-256 and version, SHA-256 of every derived record and
envelope, SHA-256 of the presented admission, qualification and statement, the budget, lab permissions,
declared diff, and the attempt number. Any change to any of these is another operation.

### 6.3 Operation log

`admission-ops/<child agent_id>.log` in the lab root: append-only, one canonical JSON object per line,
each line written whole then `fsync`ed (and the directory `fsync`ed when the file is created). Read
strictly: a torn, non-canonical or foreign line is `OPERATION_LOG_CORRUPT`, never repaired. Lines:
`PREPARED`, `BEGIN Dk`, `DONE Dk`, `REFUSED`, `INTERRUPTED_RECOVERED Dk`, `ABANDONED`,
`FAILED_CONSUMED`, `QUARANTINE_BEGIN`, `QUARANTINE_DONE`, `DURABILITY_FAULT`, `COMMITTED`, each with the
`operation_sha256`, the attempt, the current-root SHA-256 and version used, and a code. At most 64 lines
per child.

### 6.4 Durable boundaries

Each step `Dk` (k = 1…3) is bracketed: `BEGIN Dk` is written, the step's artefact is written and
`fsync`ed, then `DONE Dk` is written. `DONE Dk` is written only after every `fsync` of the step returned
success.

| Boundary | Artefact | Before it, re-checked |
|---|---|---|
| D0 `PREPARED` | the `PREPARED` line, after a complete dry run (trust without spending, P2 `check_bundle`; registrar `prepare`, P3) | current trust, STOP |
| D1 `CONSUMED` | one ledger line `colony-trust.consumed/1` carrying `operation_sha256` (P2 `consume`) | current trust, STOP |
| D2 `ADMISSION_RECORDED` | `registrar-admissions/<child>.json` and the stored envelopes and statements (§3.3) | current trust |
| D3 `HOME_WRITTEN` | the child's home through `Supervisor.admit` (several files) | current trust, STOP |
| D4 `COMMITTED` | the `COMMITTED` line, with the SHA-256 of the child record | current trust |

### 6.5 States and outcomes

The state is recomputed on every call from the operation log, the ledger, the admission record, the stored
envelopes and the home; the log alone is never trusted when a durable fact contradicts it
(`OPERATION_STATE_INCONSISTENT`, blocked).

Five outcome classes are reported distinctly; "no effect" is claimed only for the first:

| Class | When | Persistent traces |
|---|---|---|
| `REFUSED_BEFORE_DURABLE_EFFECT` | refused during the dry run, before `PREPARED` | none of this operation; only infrastructure files that may already exist or be created empty (`registrar.lock`, `registrar-admissions/`, `admission-ops/`, `admission-envelopes/`), never a record, line or envelope |
| `REFUSED_AFTER_PREPARE` | refused after `PREPARED`, before `BEGIN D1` | the operation-log lines `PREPARED` and `REFUSED`; nothing spent; a new attempt is allowed |
| `INTERRUPTED` | a `BEGIN Dk` without its `DONE Dk`, or a torn line | whatever the interrupted step wrote; blocked until the operator's verified recovery (§7) |
| `FAILED_CONSUMED` | refused or ended after `DONE D1` (or after a D1 whose ledger line is proven present) | the ledger line (the authorization stays spent); after D2, the admission record too, so that child identity is spent as well (`ADMISSION_CONFLICT` for any other admission); a new birth needs a new signed admission (and, after D2, another child) |
| `COMMITTED` | `COMMITTED` written | the whole birth; a later call returns the established result without running anything again |

Allowed transitions: `PREPARED → BEGIN D1 → DONE D1 → BEGIN D2 → DONE D2 → BEGIN D3 → DONE D3 → COMMITTED`;
`PREPARED → REFUSED`; `PREPARED → ABANDONED` (operator, only while the ledger has no line for this
operation); an open `BEGIN Dk` → `INTERRUPTED_RECOVERED Dk` (operator, §7) or `DURABILITY_FAULT`;
`INTERRUPTED_RECOVERED D3` `PARTIAL` → `QUARANTINE_BEGIN → QUARANTINE_DONE → BEGIN D3` (§8); any state
after `DONE D1` → `FAILED_CONSUMED`. No state goes back before D1 once a ledger line
bound to the operation exists. `ABANDONED` and `REFUSED_AFTER_PREPARE` leave the envelope unspent.

### 6.6 Resume

A call for a child whose log holds an open operation recomputes `operation_sha256` from what it is given:

- **identical**: everything is verified again against the current trust (§5), except that the child's
  admission is checked as `CONSUMED_BY_THIS_OPERATION` when D1 is done. That answer is never an
  acceptance and never a new authentication success. The call continues from the first step without its
  `DONE` line, and only from a `DONE` line (an open `BEGIN` is `INTERRUPTED`, §7).
- **divergent** (any field of §6.2): `OPERATION_DIVERGENT`, nothing written. Before D1 only `ABANDONED`
  frees the child; after D1 only `FAILED_CONSUMED` ends the operation.

## 7. Durability faults and interrupted steps (correction A)

After an `fsync` error, reading the same bytes back from the same system proves nothing about their
durability (the kernel may have dropped the dirty pages and report success afterwards). Rules:

1. On an `fsync` (or short-write) error, the controller writes nothing more for this operation in this
   call, does not call `fsync` again on that file hoping for success, and tries to record the fault twice:
   a `DURABILITY_FAULT` line in the operation log (best effort) and a line in the operator's fault log
   outside the lab root (path given at construction, preferably on another filesystem). It returns
   `DURABILITY_UNKNOWN`.
2. An operation with a `DURABILITY_FAULT` line or listed in the fault log is `BLOCKED_DURABILITY`. It is
   **never** resumed automatically and never "recovered" by re-reading its artefact. Its only exits are an
   operator procedure that restores verified copies (§13: backup and restore are a separate gate) or, after
   D1, `FAILED_CONSUMED`.
3. An `INTERRUPTED` step without a recorded fault (a crash, a kill) is not resumed automatically either.
   The operator runs `recover(operation_sha256, k)`, which, under L1: checks that no fault is recorded in
   either log; checks that every artefact of step k is either absent or byte-for-byte equal to what the
   operation expects (for D1: the ledger has exactly zero or one line for this operation, bound to it);
   requires a successful `syncfs` of the filesystem; then writes `INTERRUPTED_RECOVERED Dk` with the result:
   `PRESENT` (complete, counts as `DONE Dk`), `ABSENT` (the step did not happen), or, for D3 only,
   `PARTIAL` (some files missing, every present one equal; only the quarantine of §8 may follow). Any
   unexpected or divergent artefact blocks (`RECOVERY_REFUSED`).
4. If both fault records failed, a fault and a crash cannot be told apart; rule 3 then rests on the
   operator's check of the controller's error output. This is declared NOT PROVEN (§13).
5. A torn ledger line makes the whole ledger `LEDGER_CORRUPT` (existing rule): every birth of the colony
   stops (fail closed). Its handling is a manual operator procedure (copy, analysis, decision), never
   automated by this contract.

## 8. Quarantine of a partial home (correction F)

`Supervisor.admit` creates the home directory, then several files; a crash between them leaves a partial
home, which makes `load` fail and every later birth `POPULATION_UNVERIFIABLE`. Quarantine is an explicit
operator action, journaled and limited to one operation:

- `quarantine_partial_home(operation_sha256)` runs only under L1, only for an operation whose log shows
  `DONE D2` and an open `BEGIN D3` recovered as `PARTIAL` (§7.3), and only with no fault recorded.
- It lists the home. Every entry must be a known name of `Supervisor.admit` (`tasks/`, `results/`,
  `j01-lab-memory/`, `spec.json`, `record.json`, `birth_qualification.json`, `usage.json`, journal files
  of an empty journal) and every present file must be byte-for-byte equal to what the operation expects;
  the journal's bytes are not reproducible, so it must instead verify, through its own integrity check, as
  an empty journal of this individual with this budget, and nothing else.
  Any unexpected entry, link, divergent byte or extra content blocks (`QUARANTINE_REFUSED`): nothing is
  moved, deleted or repaired.
- If all checks pass it writes `QUARANTINE_BEGIN`, renames the home to
  `admission-quarantine/<operation_sha256>/<attempt>` on the same filesystem, `fsync`s both directories and
  writes `QUARANTINE_DONE`. D3 may then run again for the same operation. Nothing is ever deleted;
  quarantined homes stay for audit.

## 9. STOP, concurrency, resources

- The operator's `STOP` is read at the start of a call, after `PREPARED`, before `BEGIN D1` and before
  `BEGIN D3`. STOP set after D1 leaves the operation at its last `DONE` line; it continues after the
  operator's `resume()`. STOP undoes nothing.
- Under L1 one operation commits at a time and the ceilings are counted under L1, at `prepare` and again
  at `commit` (P3). Declared limit: a direct call to `Supervisor.admit` or `Registrar.birth` bypasses the
  controller until the lab enforces it (T7, separate gate).
- Bounds: derived list ≤ `4·max_population − 4` (§3.4); envelope and statement files ≤ 16 KiB; operation
  log ≤ 64 lines per child; the ledger is read once per locked section.

## 10. Population ceilings and planned roles (correction D)

The controller never raises a ceiling: policy g0 (`max_generation = 2`, `max_population = 6`,
`max_children_per_parent = 2`, `max_concurrent_runs = 1`) applies as frozen, and any other policy needs its
own reviewed pin. Under g0 Sentinel can have **two** direct children. A plan listing four future roles is
not an authorization for four direct descendants: roles three and four can only be grandchildren of a
qualified child (generation 2, within `max_population`) or wait for a separately reviewed policy. A real
birth of the pilot would take one of Sentinel's two places.

## 11. Qualification scope (correction E)

Unchanged hashes (Sentinel subject `2c926421…`, evaluator `41b78971…`, pilot `97fb6b04…` at `7b4b2ef6`)
mean that the existing evidence still covers the same bytes. They do not qualify the new composition.
The controller gets its own qualification over its exact dependencies: `admission_code_sha256` hashes
`colony_admission/`, `colony_trust/`, `colony_registrar/`, the `colony_lab` modules it imports
(`a1_identity`, `lineage`, `supervisor`, `a1_ref/`) and `POLICY_G0.json`; the evidence records the
`cryptography` and Python versions. Its criteria are pinned before any trial, its record is emitted only
after a favourable review by an evaluator outside the colony, and any change to one of those files makes
that qualification stale (new campaign). A change to `colony_lab/` or `sentinel_activity/` also makes
Sentinel's R8 and the pilot's PC2 stale.

## 12. Interfaces the later slices must provide (requirements, not code)

- **P2, `colony_trust` amendment 4** (contract amendment pushed alone before code): `check_bundle` (verify
  without spending); `consume(…, operation_sha256)` (verify again and append in one locked section;
  `CONSUMED_BY_THIS_OPERATION` when already spent by this operation, never an acceptance);
  `verify_consumed(envelope, ledger, operation_sha256)`; ledger `colony-trust.consumed/1` carrying the
  operation (lines `/0` stay readable, bound to no operation, never resumable); completeness keyed by
  (kind, subject, record SHA-256); the new kind `colony-admission.attestation-statement/0`; whole writes,
  directory `fsync` on creation, a distinct `LEDGER_DURABILITY_UNKNOWN` on `fsync` error with no retry.
  `verify_bundle` keeps its behaviour.
- **P3, `colony_registrar` amendment 3**: `prepare(…) → BirthPlan` (no write, frozen, hashed);
  `commit(plan)` under an L1 held by the caller, re-checking the plan against the population;
  `exclusive()`; `birth()` = `exclusive` + `prepare` + `commit`, behaviour unchanged.
- **P4–P6, `colony_admission`**: `required_attestations`, `Controller.admit_authenticated`, `install_trust`,
  `recover`, `abandon`, `quarantine_partial_home`, the operation log, coded verdicts per state; the crash
  matrix; the controller's campaign.

None of P2–P6 changes `colony_lab/`, `sentinel_activity/` or `colony_pilot/`.

## 13. Limits (NOT PROVEN)

- The operator account holds the trust policy, keys, code and lab root; whoever controls it controls
  admission.
- No trusted clock; `RETIRED` relies on declared root versions; only `REVOKED` stops a compromised key.
- A revocation reaches the controller only when installed (§5.3); its latency is the operator's.
- A writer of the lab root can truncate or poison the ledger and the operation logs (fail closed, or
  replay bounded by identity uniqueness), and can delete homes to evade population ceilings: there is no
  trusted counter.
- Locks are advisory; deleting `registrar.lock` during a birth lets a second one run.
- Durability rests on the filesystem's `fsync`/`syncfs` reports; if both fault records fail, a fault looks
  like a crash (§7.4).
- Restoring an older ledger or operation log would make spent admissions usable again: backup and restore
  are a separate gate and must never move them backwards.
- Execution bans after a revocation need the lab (T7).
- `LAB_TEST` only; a non-test root needs a code change under a separate gate. Test keys are derived from
  public labels and authenticate nothing outside the tests.

## 14. Amendment history

- `colony-admission/0`, first version, written before any code, after the operator's decision of
  2026-10-23 (present-scope attestation of R8, revocation before `COMMITTED`, corrections A–F).
