# Colony lab nursery: contract `colony-lab.individual/0`

Status: **SOURCE_ONLY / LAB_ONLY.** Nothing in `colony_lab/` is deployed, registered in A1,
reachable from the Advisor, the Operator API or the VPS, or bound to a model, a credential
or an exchange. `RUNTIME_DEPLOYED = False`. #286 is unaffected: no strategy, signal, risk,
sizing, `PB_MAX_POSITIONS`, PPL, FIN, config or epoch code is imported or changed.

## 1. Reconciliation with A0/A1 (no competing identity)

| Need | Source of truth | What the lab does |
|---|---|---|
| Persistent identity | A1 `agent_id` (`agent-econ.a1.agent-identity.v1`) | Recomputed, never stored as trusted. A restart or a spec revision keeps it. |
| Versioned spec | A1 `AGENT_SPEC_V1`, `agent_spec_id`, AW-03 `spec_artifact_hash` | Recomputed by `colony_lab/a1_identity.py`; equal to the golden vectors of PR #374 (head `c21e1a83`). |
| Capabilities, levels, class ceilings | A1 capability catalogue and schema | Same sets (checked against the schema file by test). Forbidden → reserved → unknown order and A1 rejection codes. |
| Registry state (`REGISTERED/SUSPENDED/RETIRED`) | A1 registry, **NON_DEPLOYED**, registrar **UNRESOLVED** | Never claimed: every lab record says `registry = {NON_DEPLOYED, NOT_AVAILABLE}`. |

The lab is stricter than A1 where it reuses J01 canonicalization: secret-shaped text is refused
in a spec. It does not replace the A1 validator of PR #374, which stays parked.

## 2. Extensions proposed by the lab (`colony_lab/lineage.py`)

- **Lineage**: `lineage_id = SHA256(canonical{lineage_schema, founder_agent_id})`; `founder_agent_id`,
  `parent_agent_id`, `parent_agent_spec_id`, `generation` (founder 0).
- **Genotype**: `base_agent_spec_id` (the parent's spec) and `declared_diff`, the spec identity fields
  the child changes. An undeclared mutation is refused (`UNDECLARED_MUTATION`).
- **Own identity**: a descendant has its own `canonical_name`, hence its own `agent_id`
  (`SAME_IDENTITY_AS_PARENT` otherwise).
- **Lab permissions**: A1 capability tokens declared explicitly for each individual, ⊆ its spec,
  ≤ F2, and ⊆ the parent's lab permissions. Never copied from the parent
  (`PERMISSIONS_NOT_DECLARED`, `PERMISSION_OUTSIDE_SPEC`, `PERMISSION_ESCALATION`).
- **Budget**: CPU seconds, wall seconds, address space, output bytes, total runs, journal events,
  each bounded by `BUDGET_MAX`.
- **Memory**: its own J01 journal; `inherits_parent_memory = false`. Credentials `NONE`,
  `operational_authority = DENIED`.
- **Qualification is separate** (`colony-lab.qualification/0`): states `UNQUALIFIED`, `IN_TRIAL`,
  `QUALIFIED_SIMULATED`, `FAILED`, `REVOKED`; scope `SIMULATED_DETERMINISTIC`; reviewer must be
  `EXTERNAL_HUMAN` or `EXTERNAL_REVIEW_PROCESS` and differ from the individual and its founder.
  **No descendant can be made or admitted while its parent's current spec is not
  `QUALIFIED_SIMULATED`.** A lab qualification is not an A1 state and not a runtime permission.
- Founder, coordinator or "reine" are names; none adds a capability.

## 3. Separation (`colony_lab/supervisor.py`)

| Plane | Where | Can it reach the others? |
|---|---|---|
| Quant machine (Advisor, PPL, FIN) | VPS | Not imported (AST test). |
| Filtered observation | Governance Tower fixtures only in the lab | Read-only fixtures, fixed clock. |
| Agent lab | `colony-lab-*` root, 0700, never created implicitly | One sandboxed child per run. |
| External permission control | Supervisor + operator `STOP` file | The child cannot see the lab root, the records or `STOP`. |

Each run: typed task `colony-lab.task/0` (closed fields, admitted mission, known task type, task id
deduplicated by content hash), capability check against the record, run and journal budgets charged
before the start (a crash never refunds), then one child in:

- user + network + mount + pid namespaces; no network interface; dies with the supervisor
  (`PR_SET_PDEATHSIG`) and with the namespace init (`--kill-child`);
- root filesystem remounted read-only; lab root, `/mnt`, `/run`, `/dev/shm`, `/media`, the repository's
  `.git` and `.env*` and the home secret dotfiles hidden under empty read-only mounts;
- all capabilities dropped, `no_new_privs`, empty environment, so the child cannot undo the mounts;
- rlimits: CPU, address space, file size 0, 64 descriptors, no core; wall timeout, output cap and
  stop kill the process group.

A `verify_sandbox()` probe runs before the first task; if any check fails, or `unshare`/`setpriv`
is missing, every run is refused with `SANDBOX_UNAVAILABLE` (fail closed). The child's output is
an untrusted claim: it is redacted (frozen profile `j01-secret-patterns/1`), stored with
`claims_are_untrusted = true`, and changes no record, permission or qualification.

Journal events (J01, `SIMULATED`): `POLICY_DENIED`, `BUDGET_EXHAUSTED`, `RUN_INTERRUPTED`
(`EXTERNAL_STOP`, `WALL_TIMEOUT`, `CHILD_FAILED`, `SUPERVISOR_CRASH`), `OBSERVATION_RECORDED`
(`RUN_COMPLETED`, result hash as evidence). A run left in flight by a crashed supervisor is
recorded as interrupted on the next start, never as done.

## 4. Acceptance evidence (tests/colony_lab, 71 tests)

- Refusals: forbidden/reserved/unknown capabilities, class ceilings, policies, scope coupling,
  identity forgery, tampered records, unknown mission or task type, missing capability, secret in a task.
- Quotas: CPU, memory, output, wall time, total runs, journal events.
- External stop: `STOP` file interrupts a running child and refuses new runs; `stop()` latches until
  `resume()`.
- Hostile child: no network, no write anywhere, lab root seen empty, records unreadable, cannot
  signal the supervisor, cannot unmount; orphans die; fake verdicts change nothing.
- Crash: supervisor SIGKILLed mid-run → sandbox gone, identity unchanged, run recorded as
  `SUPERVISOR_CRASH`, task id not reusable.
- Sandbox tests skip only when the host itself refuses unprivileged namespaces (checked without the
  supervisor); the fail-closed test never skips.

## 5. Limits (NOT PROVEN)

- Reads of files outside the hidden list remain possible (for example sibling checkouts); there is
  no allowlisted root filesystem.
- The child runs under the operator's UNIX account mapped to namespace root; a distinct account per
  individual and per plane is **BLOQUÉ** on a separate gate (it needs host administration).
- CPU budget is per run; there is no cumulative CPU account across runs.
- The sandbox depends on Linux unprivileged user namespaces; elsewhere the lab refuses to run.
- A simulated, deterministic trial is not a full qualification.
