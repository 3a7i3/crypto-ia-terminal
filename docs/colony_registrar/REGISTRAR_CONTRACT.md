# Colony registrar: a descendant may become a parent (`colony-registrar/0`)

Status: **SOURCE_ONLY / LAB_ONLY.** This contract and the frozen policy `POLICY_G0.json` were
pushed before any registrar code. This change **creates no individual**: births happen only in
temporary test labs. It is separate from record authentication (`colony_trust`, its own PR) and does
not depend on it. #286 is unaffected.

## 1. Why a separate registrar

Today `colony_lab.lineage.make_descendant` verifies the parent as a founder, so it cannot make a
grandchild (pilot trial B11), while `Supervisor.admit` would accept a hand-sealed generation-2
record with a shape-valid qualification and **no limit** on depth, population, children, concurrency or
cost. Changing `colony_lab/` would change Sentinel's evaluator code hash and make its R8 qualification
stale, so the gate lives in a new package, `colony_registrar/`, which uses the lab as it is.

## 2. Conditions for a birth (all must hold, checked by `Registrar.birth`)

| Condition | Rule | Refusal |
|---|---|---|
| Prior qualification, criteria fixed before trials | the parent's qualification passes the lab rules (`check_qualification`, state `QUALIFIED_SIMULATED`, scope `SIMULATED_DETERMINISTIC`, external reviewer) and names a criteria hash listed in the frozen policy | lab codes, `CRITERIA_NOT_ADMISSIBLE` |
| Admission outside the agent | an admission decision `colony-registrar.admission/0` by an `EXTERNAL_HUMAN` or `EXTERNAL_REVIEW_PROCESS`, naming this child, this parent and the policy hash; its admitter id contains no prefix of the child or of any ancestor | `ADMISSION_INVALID`, `ADMISSION_NOT_FOR_THIS_BIRTH`, `SELF_ADMISSION_DENIED` |
| Distinct identity | the child's A1 `agent_id` differs from every ancestor and from every admitted individual | `CYCLE_DENIED`, `ALREADY_ADMITTED` |
| Verifiable lineage without cycle | the parent is loaded and re-verified from the founder down; the child's lineage, genotype and declared diff are recomputed | lab codes, `UNDECLARED_MUTATION` |
| Depth | child generation ≤ `max_generation` | `GENERATION_LIMIT` |
| Population | admitted individuals after the birth ≤ `max_population` | `POPULATION_LIMIT` |
| Children per parent | ≤ `max_children_per_parent` | `CHILDREN_LIMIT` |
| Concurrency | one admission at a time (exclusive lock); runs through the registrar limited to `max_concurrent_runs` slots | `REGISTRAR_BUSY`, `CONCURRENCY_LIMIT` |
| Costs | each budget field of the child ≤ its parent's; the sum of every admitted individual's budget plus the child's ≤ `colony_budget` | `BUDGET_ESCALATION`, `COLONY_BUDGET_EXCEEDED` |
| No transmission of credentials, no added permission | lab permissions declared explicitly, ⊆ the child's spec and ⊆ the parent's; credentials `NONE`, authority `DENIED` (lab record rules) | `PERMISSIONS_NOT_DECLARED`, `PERMISSION_ESCALATION`, … |
| No autonomous reproduction | the registrar is called by the operator only: no task type, worker or lab module imports it; an individual cannot see the lab root | (AST test) |

The policy is frozen: `POLICY_G0.json` is pinned by its SHA-256 in the code. A caller may supply another
policy only with its own pin, and every limit must stay within the hard ceilings of the code
(generation ≤ the lab's `MAX_LINEAGE_DEPTH`, population ≤ 64, children ≤ 8, concurrency ≤ 4, budgets ≤
64 × the lab's per-individual maximum).

Admissible parent criteria in g0: Sentinel's r8 (`22528f16…`) and the pilot's p1 (`dcc3fe71…`). A
generation-1 parent still needs its own qualification record by an external reviewer: none exists for
the pilot, so no real grandchild can be born from this change.

## 3. Records written

On success the registrar admits the child through `Supervisor.admit` (which re-checks the parent's
qualification and the child record) and writes `admission.json` next to the child's record. Nothing
is written on refusal except the lock, which is removed.

## 4. Limits (NOT PROVEN)

- `Supervisor.admit` itself still has none of these limits: the registrar is the gate callers use, not
  a property of the lab, until the lab is changed and Sentinel requalified under a separate gate.
- Qualification and admission records are not authenticated here (see `colony_trust`).
- Population, children and budgets are counted from the lab root, which the operator account can
  write; a crash while holding the lock leaves `REGISTRAR_BUSY` until the operator removes it (fail
  closed).
- Run slots only bound runs started through the registrar.
