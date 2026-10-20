# Colony lab nursery: contract `colony-lab.individual/0`

Status: **SOURCE_ONLY / LAB_ONLY.** Nothing in `colony_lab/` is deployed, registered in A1,
reachable from the Advisor, the Operator API or the VPS, or bound to a model, a credential
or an exchange. `RUNTIME_DEPLOYED = False`. #286 is unaffected: no strategy, signal, risk,
sizing, `PB_MAX_POSITIONS`, PPL, FIN, config or epoch code is imported or changed.

## 1. Reconciliation with A0/A1 (no competing identity)

| Need | Source of truth | What the lab does |
|---|---|---|
| Persistent identity | A1 `agent_id` (`agent-econ.a1.agent-identity.v1`) | Recomputed, never stored as trusted. A restart or a spec revision keeps it. |
| Versioned spec | A1 `AGENT_SPEC_V1`, `agent_spec_id`, AW-03 `spec_artifact_hash` | Validated and recomputed by the A1 code itself; equal to the golden vectors of PR #374 (head `c21e1a83`). |
| Capabilities, levels, class ceilings, AS-01 … AS-13 | A1 capability catalogue, schema and validator | `colony_lab/a1_ref/` is an unchanged copy of `canonical.py`, `capabilities.py` and `spec.py` from #374 @ `c21e1a83`; their sha256 and git blob ids are pinned and tested. Same rule order, same rejection codes. |
| Registry state (`REGISTERED/SUSPENDED/RETIRED`) | A1 registry, **NON_DEPLOYED**, registrar **UNRESOLVED** | Never claimed: every lab record says `registry = {NON_DEPLOYED, NOT_AVAILABLE}`. |

The lab adds exactly one rule, applied only after A1 has accepted the spec: secret-shaped text
(J01 frozen profile) is refused with `LAB_SECRET_TEXT_REJECTED`, a lab code that is not an A1 code.
The copy is replaced by an import when #374 lands; it never diverges silently (pinned hashes).

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
  `EXTERNAL_HUMAN` or `EXTERNAL_REVIEW_PROCESS`, a lowercase name, and must not contain (even as a
  16-character prefix) the id of the individual, its founder, its parent or the child being born.
  The record is **not authenticated**: whoever can write the lab root can write one. It is checked
  for shape and self-reference at birth and again on every load, not proven to come from a reviewer.
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
used once: the same id with the same content is `DUPLICATE_TASK`, with other content `TASK_ID_CONFLICT`), capability check against the record, run and journal budgets checked,
the run claimed (`inflight.json`) then charged (a crash at any point never refunds), then one child in:

- user + network + mount + pid namespaces; no network interface; abstract UNIX sockets of the host
  unreachable (they belong to the host network namespace);
- a **new root** (`pivot_root`) holding only an allowlist bound read-only: `/usr`, the interpreter's
  prefixes, the repository, the host `bin`/`lib`/`sbin` links, `/dev/{null,zero,random,urandom}` and a
  fresh `/proc`; the repository's `.git`, `.env*` and `docs/colony_lab` (criteria, golden answers,
  evidence) hidden under empty mounts. Child and init run every module from source (`-X
  pycache_prefix` outside the root) with the repository last on `sys.path`. The old root is
  detached, so the lab root, `/tmp`, the home directory and every UNIX socket path outside the
  allowlist are absent; the new root itself is read-only (creation fails with `EROFS`);
- all capabilities dropped, `no_new_privs`, empty environment, so the child cannot undo the mounts;
- `colony_lab/sandbox_init.py` as namespace init (trusted, starts before any individual code):
  per-process rlimits (address space, file size 0, 64 descriptors, no core, at most `MAX_PROCESSES = 8`
  processes in the namespace, init included), a CPU budget **summed over every process** of the
  namespace (live, zombie and reaped), and a lifeline pipe: its EOF (stop, wall timeout, output cap,
  supervisor death) makes the init kill every process. `PR_SET_PDEATHSIG` and `--kill-child` stay as
  second layers;
- the outcome is classified from the init's own status pipe (CPU total, signal, setup failure). The
  child cannot write it or trace the init, and a signal it sends to the init has no effect (the
  kernel ignores signals without a handler sent to a namespace init from inside), so it cannot claim `CPU_EXCEEDED` or a sandbox
  failure by choosing an exit code or a signal (`CHILD_FAILED` then). Its only self-reported outcome
  is `MEMORY_EXCEEDED` (exit 70 on `MemoryError`), which can only cost the individual itself.

A `verify_sandbox()` probe runs before the first task. It must observe: no network; no connection to a
listening UNIX socket outside the allowlist (path and abstract); `mkdir`, exclusive create, `symlink`
and `mkfifo` refused with `EROFS`/`EACCES`/`EPERM` (or the directory absent) in `/`, `/dev`, `/tmp`,
the repository, the home directory, the lab root and its parent, the interpreter prefix and a fresh host
directory; existing repository files not openable for writing; hidden paths empty; no capability; empty
environment; and top-level entries of `/` within the allowlist. If any check fails, or a tool
(`unshare`, `mount`, `umount`, `pivot_root`, `setpriv`, `env`) is missing, every run is refused with
`SANDBOX_UNAVAILABLE` (fail closed). The child's output is
an untrusted claim: it is redacted (frozen profile `j01-secret-patterns/1`), stored with
`claims_are_untrusted = true`, and changes no record, permission or qualification.

Journal events (J01, `SIMULATED`): `POLICY_DENIED`, `BUDGET_EXHAUSTED`, `RUN_INTERRUPTED`
(`EXTERNAL_STOP`, `WALL_TIMEOUT`, `CHILD_FAILED`, `SUPERVISOR_CRASH`), `OBSERVATION_RECORDED`
(`RUN_COMPLETED`, result hash as evidence). A run left in flight by a crashed supervisor is
recorded as interrupted on the next start, never as done.

## 4. Acceptance evidence (tests/colony_lab, 87 tests)

- Refusals: forbidden/reserved/unknown capabilities, class ceilings, policies, scope coupling (A1
  codes, including AS-13 `SCOPE_CAPABILITY_INCOHERENT` and `SUPERSESSION_BREAK`), identity forgery,
  tampered records (also re-hashed descendant records and a self-signed birth qualification on load),
  unknown mission or task type, missing capability, secret in a task.
- Quotas: CPU (one process and four forked processes each under the per-process limit), process count,
  memory, output, wall time, total runs, journal events.
- External stop: `STOP` file interrupts a running child and refuses new runs; `stop()` latches until
  `resume()`. The init alone kills its namespace when the lifeline closes (tested without the
  supervisor).
- Hostile child: no network, no UNIX socket outside the allowlist, no creation anywhere (errno checked,
  `EFBIG` is not accepted), lab root absent, records unreadable, cannot signal the supervisor, cannot
  unmount, cannot forge its classification (exit 97, `SIGKILL`, `SIGXCPU` → `CHILD_FAILED`); orphans
  die; fake verdicts change nothing.
- Crash: supervisor SIGKILLed mid-run → sandbox gone, identity unchanged, run recorded as
  `SUPERVISOR_CRASH`, task id not reusable.
- Mutants checked locally: removing the summed CPU budget, the process limit, the lifeline or the
  final kill each makes a test fail.
- Sandbox tests skip only when the host itself refuses unprivileged namespaces (checked without the
  supervisor); the fail-closed test never skips. **On GitHub's `ubuntu-latest` runners unprivileged
  user namespaces are commonly restricted by AppArmor, so CI may skip them: the sandbox evidence is then
  local runs only.** The JSON-schema check skips when `jsonschema` is absent (it is not in
  `requirements-ci.txt`).

## 5. Limits (NOT PROVEN)

- Files inside the allowlist stay readable: the whole repository checkout (other than `.git` and
  `.env*`) and the interpreter. A secret placed in the checkout would be readable by the child.
- The child runs under the operator's UNIX account mapped to namespace root; a distinct account per
  individual and per plane is **BLOQUÉ** on a separate gate (it needs host administration).
- Memory is bounded per process: at most `MAX_PROCESSES` × the address-space budget, not by a cgroup.
- Lab records, `usage.json` and qualification records are protected only by the lab root's
  permissions: whoever writes the lab root (the operator account) is the authority. They are
  re-verified for consistency on every load, not authenticated.
- Founder admission is not gated: any valid founder record can be admitted by the operator.
- Redaction of results uses the frozen J01 profile; an adversarial child can encode a secret it
  could read so that redaction misses it. With the allowlisted root it can read no secret outside
  the checkout.
- The sandbox depends on Linux unprivileged user namespaces; elsewhere the lab refuses to run.
- A simulated, deterministic trial is not a full qualification.
