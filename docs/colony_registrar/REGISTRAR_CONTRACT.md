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
| Prior qualification, criteria fixed before trials | the parent's qualification passes the lab rules (`check_qualification`, state `QUALIFIED_SIMULATED`, scope `SIMULATED_DETERMINISTIC`, external reviewer) and names a criteria hash listed in the frozen policy; its reviewer id contains no prefix of the child, of any ancestor or of any admitted individual | lab codes, `CRITERIA_NOT_ADMISSIBLE` |
| Admission outside the agent | an admission decision `colony-registrar.admission/0` by an `EXTERNAL_HUMAN` or `EXTERNAL_REVIEW_PROCESS`, naming this child, this parent, the policy hash, the SHA-256 of the parent's qualification and exactly the budget, lab permissions and declared diff granted; its admitter id contains no prefix of the child, of any ancestor or of any admitted individual | `ADMISSION_INVALID`, `ADMISSION_NOT_FOR_THIS_BIRTH`, `SELF_ADMISSION_DENIED` |
| Distinct identity | the child's A1 `agent_id` differs from every ancestor and from every admitted individual | `CYCLE_DENIED`, `ALREADY_ADMITTED` |
| Verifiable lineage without cycle | the parent is loaded and re-verified from the founder down; every descendant ancestor has its own registrar admission record, bound to it; the child's lineage, genotype and declared diff are recomputed | lab codes, `ANCESTOR_NOT_ADMITTED`, `UNDECLARED_MUTATION` |
| Depth | child generation ≤ `max_generation` | `GENERATION_LIMIT` |
| Population | admitted individuals after the birth ≤ `max_population` | `POPULATION_LIMIT` |
| Children per parent | ≤ `max_children_per_parent` | `CHILDREN_LIMIT` |
| Concurrency | one admission at a time (exclusive lock); runs through the registrar limited to `max_concurrent_runs` slots | `REGISTRAR_BUSY`, `CONCURRENCY_LIMIT` |
| Costs | each budget field of the child ≤ its parent's; the sum of every admitted individual's budget plus the child's ≤ `colony_budget` | `BUDGET_ESCALATION`, `COLONY_BUDGET_EXCEEDED` |
| No transmission of credentials, no added permission | lab permissions declared explicitly, ⊆ the child's spec and ⊆ the parent's; credentials `NONE`, authority `DENIED` (lab record rules) | `PERMISSIONS_NOT_DECLARED`, `PERMISSION_ESCALATION`, … |
| No autonomous reproduction | the registrar is called by the operator only: no task type, worker or lab module imports it; an individual cannot see the lab root; no birth while the operator's `STOP` is set | (AST test), `LAB_STOPPED` |
| Malformed inputs | any input of the wrong type is refused with a code, never an uncaught exception; an I/O failure is reported as such | `BIRTH_INPUT_INVALID`, `POLICY_INVALID`, `LAB_IO_ERROR` |

The policy is frozen: `POLICY_G0.json` is pinned by its SHA-256 in the code and copied when the
registrar is built, so a later change to the caller's object has no effect. A caller may supply another
policy only with its own pin, and every limit must stay within the hard ceilings of the code
(generation ≤ the lab's `MAX_LINEAGE_DEPTH`, population ≤ 64, children ≤ 8, concurrency ≤ 4, budgets ≤
64 × the lab's per-individual maximum).

Admissible parent criteria in g0: Sentinel's r8 (`22528f16…`) and the pilot's p1 (`dcc3fe71…`). A
generation-1 parent still needs its own qualification record by an external reviewer: none exists for
the pilot, so no real grandchild can be born from this change.

## 3. Records written

Before admitting the child, the registrar writes the admission decision to
`registrar-admissions/<child agent_id>.json` in the lab root (new file, fsynced). It then admits the
child through `Supervisor.admit`, which re-checks the parent's qualification and the child record. A
crash between the two leaves an admission without a child, never a child without an admission; a
retry with the identical admission proceeds, any other admission for that child is refused
(`ADMISSION_CONFLICT`). Nothing else is written on refusal except the lock, which is removed.

## 4. Limits (NOT PROVEN)

- `Supervisor.admit` itself still has none of these limits: the registrar is the gate callers use, not
  a property of the lab, until the lab is changed and Sentinel requalified under a separate gate.
- Qualification and admission records are not authenticated here (see `colony_trust`).
- Population, children and budgets are counted from the lab root, which the operator account can
  write; a crash while holding the lock leaves `REGISTRAR_BUSY` until the operator removes it (fail
  closed).
- Run slots only bound runs started through the registrar.
- The pin protects the frozen policy g0 only. A caller-supplied policy is pinned by the caller itself,
  so its criteria and limits (within the hard ceilings) are the caller's own decision; each admission
  records the hash of the policy it was made under. Only g0 is the operator's reviewed policy.
- An admission is bound to one child and one birth, but a writer of the lab root who deletes a child's
  home and its admission record can replay the birth; identities stay unique within the colony.
- The 16-character prefix rule for reviewer and admitter ids checks declarations, not identities:
  records are not authenticated here.

## 5. Amendment history

- Amendment 1, pushed alone before its code, after the independent review of `0fca3f46` found the
  ceilings under-tested and the admission weakly bound: admission record written before the child and
  required for every descendant ancestor; admission bound to qualification, budget, permissions and
  diff; reviewers and admitters excluded from the whole colony; `LAB_STOPPED`; coded refusals for
  malformed inputs; policy copied at construction. The admission schema keeps its name
  `colony-registrar.admission/0`: it was never released outside this pull request.
