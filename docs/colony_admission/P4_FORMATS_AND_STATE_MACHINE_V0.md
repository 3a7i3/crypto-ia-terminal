# P4: operation formats and state-machine design, version 0

Status: SOURCE_ONLY / DESIGN_FOR_REVIEW / NO_IMPLEMENTATION. Base: main
`512a1493b7bc673093ef2bfd9d872b5dbfff2971` (P2, P3 and ledger inspection integrated).
This document refines the pinned `ADMISSION_CONTRACT.md`; it does not replace it or change
`SCENARIOS_A0.json`. If a conflict is found, P1 controls and this draft must be corrected
before any implementation. No runtime, key, record, individual or writer is introduced.
#286 remains ACTIVE.

## 1. Scope and delivery boundaries

The first P4 code slice will contain closed formats, a bounded canonical decoder and a pure
operation-log projector. It receives bytes, never paths. It neither opens a ledger nor calls
`consume`, `Registrar.commit`, `Supervisor.admit` or a recovery action. It cannot certify a
birth. Filesystem observation, current-trust validation, derivation of attestations, durable
writers and operator actions are later slices of P4.

`P4_TRANSITIONS_V0.json` is a reviewable decision table, not executable authorization policy.
Its guards are obligations for the future controller. A log projector cannot satisfy them
merely because a line claims they passed. No default transition exists. Unknown events,
unknown fields, unsupported versions and invalid transitions are refused, never ignored.

## 2. Shared wire rules

All format names below end in `/0`; no implicit migration. UTF-8 JSON objects, sorted keys,
compact separators, no duplicate keys, floats, NaN, infinity, trailing whitespace or BOM.
Strings with invalid Unicode scalars are refused. The canonical encoder permits only null,
bool, integers, strings, lists and string-keyed objects. Type checks distinguish bool from int.
SHA-256 values are exactly 64 lowercase hexadecimal characters. Counters are nonnegative
integers, root versions and attempts positive integers. Identifiers use their existing A1,
registrar or trust validator; no new identity algorithm is introduced.

Every object has a closed key set. Optional values use explicit null when specified, not an
omitted key. No parser coerces strings into numbers, normalizes identifiers or sorts an input
list to make it valid. Lists of attestations are sorted by `(kind, subject, record_sha256)`;
identical keys are refused after the controller has deduplicated identical records at derivation.

Each physical log line is at most 262144 bytes INCLUDING its newline. Each operation log is
at most 64 physical lines and 16777216 bytes. These conservative byte bounds do not enlarge
P1's capacity. A final unterminated fragment counts towards both limits. Check input size
before decoding; reject nesting beyond 32 containers and integer tokens longer than 128
characters. Overflow yields an explicit limit error, never a projection of a prefix.

## 3. Frozen operation: `colony-admission.operation/0`

Closed fields:

| Field | Value |
|---|---|
| `schema` | `colony-admission.operation/0` |
| `lab_id` | Existing trust lab identifier |
| `child_agent_id`, `child_agent_spec_id`, `parent_agent_id` | Existing A1 identities |
| `policy_sha256` | Reviewed policy pin |
| `historical_root_sha256`, `historical_root_version` | Root at preparation |
| `items` | Canonically ordered frozen attestation items below |
| `presented` | Closed object with `qualification`, `statement`, `admission`; each contains `record_sha256`, `envelope_sha256` |
| `budget`, `permissions`, `declared_diff` | Exact canonical values checked by the registrar; no permissive replacement validators |
| `birth_plan` | Complete P3 `BirthPlan.data`, not only its digest |
| `attempt` | Positive integer; frozen for this operation |
| `boot_id` | Boot UUID obtained by trusted host reader at preparation |

An item has exactly `role`, `kind`, `subject`, `record_sha256`, `envelope_sha256`.
`role` is `DECISION` or `POPULATION`. An item needed in both sets is represented once as
`DECISION`, and retains its population use in the controller's derived classification.
This is not a caller-supplied required list: the future controller derives it under L1.
The future semantic validator cross-checks child, parent, policy, budget, permissions and diff
against the sealed P3 plan and records. Merely matching a digest is insufficient.

`operation_sha256 = SHA256(canonical(operation))`. Current trust is deliberately excluded.
Changing any frozen byte, including attempt or historical boot, changes this identity.
A resume never reconstructs the frozen operation from today's population or root. It compares
the presented inputs with these frozen digests and uses the original complete BirthPlan.

## 4. Operation-log entry: `colony-admission.operation-entry/0`

Every entry has exactly:
`schema`, `operation_sha256`, `attempt`, `current_root_sha256`, `current_root_version`,
`boot_id`, `event`, `step`, `code`, `data`.

The first entry must be PREPARED, with `data = {"operation": <frozen object>}`. Its digest,
attempt, historical root and boot must match the entry. Subsequent entries retain operation
identity and attempt; current-root metadata and boot may change. Root metadata is an
observation claim, not a root or signature proof. The controller independently checks the
installed current policy and monotone history. Every entry has a nonempty coded reason.

| Event | `step` | Closed `data` |
|---|---|---|
| PREPARED | null | `operation` |
| BEGIN, DONE, BEGIN_CANCELLED | D1, D2 or D3 | empty object |
| INTERRUPTED_RECOVERED | D1, D2 or D3 | `result`: ABSENT, PRESENT or PARTIAL |
| TORN_TAIL_ACKNOWLEDGED | null | `fragment_sha256` |
| REFUSED, ABANDONED, TERMINATED, FAILED_CONSUMED | null | empty object |
| DURABILITY_FAULT | D1, D2, D3 or null | `fault_sha256` (external fault record digest) |
| QUARANTINE_BEGIN, QUARANTINE_DONE | D3 | empty object |
| SET_ASIDE_BEGIN, SET_ASIDE_DONE | D3 | empty object |
| COMMITTED | null | `record_sha256` (must equal frozen child record hash) |

The field list encodes line meaning only. The projector rejects PARTIAL D1, orphan DONE,
step skips, duplicate PREPARED, mismatching operation ids and events after terminal states
except the explicit set-aside pair after FAILED_CONSUMED. It keeps an independent
`d3_started` flag; losing this history must never authorize setting aside another home.
SET_ASIDE retains the terminal result. QUARANTINE retains the consumed authorization.

Line positions 57–64 accept only P1's reserve events: TERMINATED, FAILED_CONSUMED, ABANDONED,
SET_ASIDE_BEGIN, SET_ASIDE_DONE (each at most once in the reserve), and
TORN_TAIL_ACKNOWLEDGED (at most twice in the reserve). Reserve accounting is physical,
including ignored torn fragments. No writer may pre-spend these slots with normal events.

## 5. Pure projection versus verified controller state

Proposed pure API: `project_log(raw: bytes) -> LogProjection`.
No directory, ledger, root, clock, boot reader, callback or action argument is accepted.

Projection fields: `schema = colony-admission.log-projection/0`, `status`,
`operation_sha256` (null before a valid PREPARED), `attempt` (likewise nullable),
`last_completed_step` (D0 through D3 or null), `pending_step` (D1–D3 or null),
`d3_started`, `terminal_claim` (null, REFUSED, ABANDONED, FAILED_CONSUMED or COMMITTED),
`physical_lines`, `code`, `accepted = false`, `external_facts = NOT_EVALUATED`.
The result is immutable, detached from decoder-owned mutable data.

`status` is EMPTY, OPEN, INTERRUPTED, RECOVERED, QUARANTINING, TERMINATING,
BLOCKED_DURABILITY, TERMINAL_CLAIM, SETTING_ASIDE, TORN_TAIL or CORRUPT.
A COMMITTED line yields TERMINAL_CLAIM, not an authenticated or durable admission.
Fault-log overrides, ledger consistency, current trust, cold-read provenance and home bytes
remain NOT_EVALUATED. A corrupt log cannot be projected as terminal from an early prefix.
A torn tail reports the valid prefix only as diagnostic context; no terminal result is usable.
An empty log is EMPTY, never REFUSED_BEFORE_DURABLE_EFFECT: proving that outcome also needs
external observations. Every result has `accepted=false`, including a complete claimed birth.

The later controller joins this projection with independently acquired evidence under L1:
strict external fault log, installed trust and history, inspection of the entire ledger,
stored attestations, admission record, home and ceilings. Contradictions produce
OPERATION_STATE_INCONSISTENT. Unavailable evidence remains unavailable, never absent.
`CONSUMED_BY_OPERATION` from #492 is observation only. `LEDGER_MISSING` does not establish
an unused authorization. Unknown/corrupt/busy inspection cannot satisfy an absence guard.

## 6. Transition guards and ordering

See the companion table. Every listed transition is additionally subject to bounds, exact
identity, fault-log precedence and the guards of its referenced P1 section. Controller writes
hold L1; ledger operations take L2 only inside L1. No reverse lock order. At most one open
operation per lab; scan bounds remain 256 logs. Direct API bypass remains a declared T7 limit.

Recovery is an explicit operator command. PRESENT/PARTIAL require a different actual host
boot from the matching BEGIN; ABSENT can use the same boot. The projector can reject equal
boot metadata for PRESENT/PARTIAL, but cannot prove that a claimed boot came from the host.
DONE is never synthesized from PRESENT. The projection advances its logical completed step
on the explicit recovered result, preserving that its source was recovery, not a DONE write.
PARTIAL D2 authorizes only a later guarded rewrite of missing files; PARTIAL D3 requires
QUARANTINE_BEGIN/DONE before a new BEGIN D3. Repeated BEGIN without intervening DONE,
BEGIN_CANCELLED or recovery is invalid. BEGIN_CANCELLED returns to the preceding completed
step and never rolls back a consumption.

TERMINATED is an intermediate state; it is not sufficient to release OPERATION_PENDING.
Its next ending line is FAILED_CONSUMED or ABANDONED according to a verified ledger finding.
ABANDONED without TERMINATED is permitted only before consumption (including recovered D1
ABSENT). A recorded durability fault cannot be cleared by parsing intact bytes or a new BEGIN.
No new trust check, STOP, unavailable policy or unrelated refusal becomes FAILED_CONSUMED.
Only P1's two terminal codes after consumption are accepted there:
TRUST_REVOKED_AFTER_CONSUMPTION and OPERATOR_TERMINATED.

An entry with a claimed good code cannot substitute for the actual external guard.
Refusals that P1 says write nothing have no event in the table. BEGIN_CANCELLED is the
specific registrar pre-write exception, not a generic error-to-state adapter.

## 7. Torn tails, faults and trust: separate formats

A final fragment is TORN_TAIL even if its JSON would otherwise be canonical. An explicit
acknowledgement must refer to exactly the fragment bytes. An arbitrary valid complete event
must never be retroactively erased by a later acknowledgement. P1 only permits ignoring a
non-canonical physical line immediately followed by its matching acknowledgement; a
canonical-looking fragment followed by an acknowledgement is conservatively CORRUPT.
This preserves safety at the cost of an operator restore gate for that edge case; it does not
invent automatic repair. No fragment is truncated or deleted by a reader.

External fault-log and installed-trust wire schemas are intentionally NOT assigned by this
slice. They must be separately specified before their writers are implemented. P4's projector
must not accept an operator-provided boolean such as `fault_log_ok` as authenticated evidence.

The fault-log format must cover step-only Supervisor errors, exact controller file/directory
errors, operation/child identity, ledger finding, TERMINATED_EXTERNALLY and external set-aside
brackets. The controller must honor external termination without reading the faulty log.
Fault-log unavailability blocks all births; a ledger fault blocks P1's restricted actions.
Directory faults conservatively retain P1's L1–L3 reading notes. No restore operation is in scope.

Trust policy/history formats must keep the installed root, pin, minimum version and lab scope
outside the lab. History must equal the installed policy's last entry, enforce monotonicity
and preserve retirement/revocation rules. Historical root remains frozen in the operation;
current root can rotate. Root/history installation is never inferred from log metadata.

## 8. Acceptance for the first code slice

- Closed formats reject every unknown/missing/wrong-type field; canonical round trips are exact.
- Operation identity binds every frozen input; current-root rotation leaves it unchanged.
- Each legal table edge has a positive fixture, and each guard has an adverse case. Generated
  forbidden event/state pairs must be rejected; no fallback to a nearby state.
- Full positive sequence and recovery variants; step skips, duplicate endings, wrong operation,
  incorrect record hash, same-boot PRESENT/PARTIAL, PARTIAL D1, incomplete quarantine,
  incomplete termination, log limits, reserved slots and torn-tail acknowledgements covered.
- Corruption after COMMITTED invalidates the whole log. Neither a torn tail nor a fault is
  silently repaired. An empty/missing observation is not a successful refusal or admission.
- Pure modules have no filesystem/network/process/clock APIs and no trust/registrar/lab calls.
  Tests prevent an accepted=true or external-facts=PASS result.
- P1 pins unchanged, no modifications to colony_lab, sentinel_activity or colony_pilot.
  Existing trust/registrar regression and differential Ruff gate remain green.
- Independent review and CI at exact final SHA before merge. These criteria qualify neither
  the controller nor Sentinel; P5 crash injection and P6 qualification are still outstanding.

Next source order: formats/decoder/projector; external fault/trust formats; read-only evidence
join; durable writers and orchestration; explicit recovery/quarantine/termination; P5; P6.
Rollback of this documentation is a source revert only. No data format has been written.
