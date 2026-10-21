# Pilot descendant of Sentinel (step 6): `sentinel_pilot_01`

Status: **SOURCE_ONLY / LAB_ONLY, simulated and deterministic.** Nothing here is deployed,
registered in A1, bound to a model, a credential or an exchange, or reachable from the Advisor, the
Operator API or the VPS. #286 is unaffected: no strategy, signal, risk, sizing, PPL, FIN, config or
epoch code is imported or changed.

## What the pilot is

| | Sentinel 01 (parent) | Sentinel Pilot 01 (pilot) |
|---|---|---|
| A1 `agent_id` | `4279e165…` | `1eb3baaf0bf1ec4ddc6559e128b8685e4a1d91da49f417ff33cc0fa196c0a22a` |
| `agent_spec_id` | `b74ab696…` | `660ec9a818fc3c3c41b432520dbcc881cc8c840cdb1a5a80318488ee0e22d986` |
| Role, generation | FOUNDER, 0 | DESCENDANT, 1 (same lineage) |
| Declared diff | none | `purpose` (the A1 identity fields `canonical_name` and `display_name` make it another individual) |
| Lab permissions | `DIAGNOSTIC_PRODUCE`, `GOVERNED_ARTIFACT_READ` | `DIAGNOSTIC_PRODUCE` only |
| Memory | own J01 journal | own J01 journal, empty at birth, never the parent's |
| Credentials, authority | `NONE`, `DENIED` | `NONE`, `DENIED` |
| Code | `colony_lab/workers/sentinel.py` | the same worker, unchanged |

The pilot adds **no new behaviour**: it runs its parent's code. It exists to prove, in the real
sandbox, that a descendant can be born only from a parent whose qualification record has the
required shape (the lab does not authenticate it; the campaign checks what Sentinel's names), has its own identity, memory
and narrower permissions, and leaves its parent untouched. The worker answers in its parent's voice
(output `agent_id` `SENTINEL-01`); the pilot's lab identity is its record's `agent_id`.

## Method

1. Criteria `PILOT_CRITERIA_P0.json` (sha256 `065e0777…`) were written from the lineage contract and
   committed and pushed (`c4216ed4`) before any trial ran. One expectation was corrected from code
   reading before that push: `make_descendant` cannot make a grandchild (B11 expects
   `LINEAGE_INVALID`, not a qualification code). Git proves only that criteria and code (pushed
   23:35:19 UTC) precede the evidence (23:37:00 UTC); "before any trial" is the author's declaration.
   After the review of PC1, `PILOT_CRITERIA_P1.json` (sha256 `dcc3fe71…`, pushed at `5790976a` before
   PC2) keeps every p0 expectation (tested) and adds B12 and `birth_qualification_unchanged`.
2. The evaluator is `colony_pilot/campaign.py`, outside `colony_lab`, so Sentinel's record still names
   the evaluator code that produced its evidence (`41b78971…`). It reuses Sentinel's reviewed gates
   (`tree_state`, `sandbox_view`, `evaluator_runtime`, `code_irregular`, the r8 predicates and golden
   answers) and adds its own hash (`pilot_code_sha256`: `b6ca2b49…` at PC1, `97fb6b04…` at PC2).
3. The parent qualification is the real record `SENTINEL_QUALIFICATION_RECORD_R8.json`. The lab
   checks only its shape; the campaign also checks that it names the C9 evidence file, criteria r8 and
   the current subject and Sentinel evaluator hashes (`PARENT_QUALIFICATION_STALE` otherwise).
4. Every trial runs twice, each in a fresh lab root; the campaign refuses to start unless isolated
   (`-I -S -B`, no repository bytecode), as for Sentinel.

## Campaigns

- **PC1** (p0, `c4216ed4`): 27/27 in both rounds, `PROPOSED_QUALIFIED_SIMULATED`, evidence
  `evidence/PC1_pilot_evidence.json` (`36f4e30d…`). Reproduced by the independent review (identical once `git_head` and the checkout path are put back),
  whose verdict was **unfavourable**: 9 evaluator mutants survived outside the hash tripwire (the fact
  comparator `_check` and several facts made constant were caught by no test), no birth from a parent
  with a non-empty journal, an inexact grandchild limit, and the lineage/genotype check of a
  descendant in `verify_record` (L12) covered by nothing.
- **PC2** (p1, `5790976a`, launched with `launch_command`): **28/28 trials passed in both rounds**,
  deterministic, sandbox `VERIFIED`, sandbox view equal to the subject (46 files), checkout clean,
  evaluator isolated, no irregular code, parent record current. Proposed state
  `PROPOSED_QUALIFIED_SIMULATED`. Evidence `evidence/PC2_pilot_evidence.json`, sha256
  `d706928e843275d58cab330426f6745db864194a86ef389fbed1dd93a7bc6b4d`, pilot evaluator
  `97fb6b04…`.
- Review of PC2 (`024ae5b4`): every earlier condition met, PC2 reproduced, but **unfavourable** again
  on tests: 8 of its new mutants survived outside the tripwire (the r8 judgement of the replays
  removable, five B01 facts and B12's parent-journal guard made constant, the replays'
  `parent_unchanged`). Tests now forge the stored record field by field after `load()`, run a replay
  through the real r8 predicates, write into the parent during a replay, run P01 for real (N10/S5),
  and refuse a record claiming inherited memory (L17); none changes `colony_pilot/`, so PC2 stands.
- Tests added after PC2 (no evaluator change) kill the first review's survivors C1, C3, C5 and C12–C17
  and L12 without the hash tripwire: each fact is provoked false (a write into the parent, a rewritten
  birth qualification, an inherited journal, equal permissions, shared journals, a qualification file
  written by a run, an extra expectation failing, resealed generation-2 lineages).

- Review of the tests (`a44e16e2`): every condition of review 2 met, PC2 not in question, but
  **unfavourable** again: 5 survivors outside the tripwire and the campaign (the replays'
  `record_unchanged` and `runs_unchanged` made constant, the parent check without `evidence_sha256` or
  `criteria_sha256`, the `tracked_clean` gate removed), 8 replay mutants killed by the campaign only
  (m10), and four pre-existing lab rules not exercised in refusal (m11). Tests added since, again with
  no change to `colony_pilot/`, provoke each key of the parent check through a forged record file,
  `tracked_clean` false, a replayed run writing the pilot's `spec.json` and `usage.json`, each replay
  setup applied to the pilot (budget spent, output budget, corrupted journal, supervisor killed,
  unadmitted mission), a failed preparatory run, the CLI's output, and the
  rules of m11: a resealed record with a credential (L20), a qualification of another scope (L25), a
  descendant carrying its parent's `agent_id` (L23) and a birth qualification rewritten to name the
  pilot after admission (S17).
- Systematic sweep by the author, as review 3 recommended: every comparison, boolean and `not`
  operator of `campaign.py` mutated in turn, the whole `tests/colony_pilot` run without the hash
  tripwire. First pass: 95 mutants, 21 survivors. After the tests above, the 21 were mutated again:
  11 survive, none of them a verdict path. Seven mutants are in the docstring, a comment or the refusal
  message text (one on line 4, three on line 5, one each on lines 9, 263 and 376). Line 166 (`admit_valid`) is equivalent: the branch it selects then
  does the same thing. Lines 141 and 279 are near-equivalent: they pick another r8 question for B12's
  preparatory run and for P01, which still completes for the parent, so the trial keeps its meaning
  with another question. Line 380 (`--out` not required) only changes how a run without `--out`
  fails. The operators mutated are `==`, `!=`, `<`, `<=`, `not`, `and`, `or`, `is not`, `-`, `True`
  and `False`; constants and arguments were not swept by the author at this stage.
- Review of those tests (`3af9c2dd`): PC2 reproduced and still valid, 1234 tests passed with no skip,
  **unfavourable** again without a blocking defect: 5 survivors among mutants the author had not swept
  (P01 dropped from a round, a single r8 replay, determinism compared on failures instead of facts,
  `_tree` not recursive, the evidence naming Sentinel's evaluator hash as the pilot's), plus minor
  ones (evidence fields, `SUBJECT_CODE_CHANGED`, the Q05 restart, the report's wording, corrected
  above). Tests added since, with no change to `colony_pilot/`: a round runs exactly the criteria's
  12 births, 15 replays and 1 permission trial with their kind, judged with r8's clock and golden
  answers; two passing rounds with different facts are `NOT_DETERMINISTIC`; a write into the parent's
  `journal/` during a birth or a replay is seen; every evidence field written by `qualify` is checked;
  `SUBJECT_CODE_CHANGED` is provoked; Q05's replay is asked of a new supervisor. The author replayed the
  review's 14 named mutants: all killed without the tripwire.
- Statement-deletion sweep by the author: each one-line statement inside a function replaced by `pass`
  (156 mutants). 20 survived; tests then added (a failed parent run before B12, an unknown birth case,
  no lab root left by a replay, P01 or the sandbox probe, `journal_last` of an empty journal, the hash
  being a sha256) leave 12, none on a verdict path: in the `make_*` cases, `child_id` and
  `code = "MADE"` matter only if the lab wrongly made the child, which fails the trial either way
  (8); the record-hash strip before resealing B10 is equivalent (`_seal` overwrites it); admitting the
  pilot before B11 is near-equivalent (`make_descendant` refuses the grandchild either way); the
  `UNREADABLE` branch is never reached by r8 (a corrupted journal is still readable); the
  `__main__` entry is not used by `launch_command`. Constants and arguments were not swept
  systematically; review 4 swept them by hand.

A first launch at the same commit ran but could not write its evidence (output directory not
writable by the lab account); its result was never seen. PC1 is the next launch, unchanged.

| Trial | Case | Outcome |
|---|---|---|
| B01 | valid birth from the r8 record | `ADMITTED_TO_LAB`; generation 1, parent and founder = Sentinel, same lineage id, diff `purpose`, permissions ⊂ parent's, credentials NONE, authority DENIED, journal empty, birth qualification = the record, parent's files byte-identical |
| B02 | admitted without qualification | `QUALIFICATION_INVALID` |
| B03 | record with state FAILED | `PARENT_NOT_QUALIFIED` |
| B04 | reviewer id naming the child | `SELF_QUALIFICATION_DENIED` |
| B05 | reviewer kind SELF | `SELF_QUALIFICATION_DENIED` |
| B06 | record for another spec | `QUALIFICATION_NOT_FOR_THIS_SPEC` |
| B07 | a permission the parent's record lacks (`CI_READ`) | `PERMISSION_ESCALATION` |
| B08 | purpose changed, diff not declared | `UNDECLARED_MUTATION` |
| B09 | parent's own identity | `SAME_IDENTITY_AS_PARENT` |
| B10 | record resealed with an escalated permission, then admitted | `PERMISSION_ESCALATION` |
| B11 | grandchild made from the pilot with `make_descendant` | `LINEAGE_INVALID` |
| B12 (p1) | birth after the parent has run once (journal not empty) | `ADMITTED_TO_LAB`; pilot journal empty, no shared event, parent unchanged by the birth |
| Q00–Q14 | every Sentinel r8 trial with the pilot as the individual, judged by the r8 predicates and golden answers | all pass; parent's files and the pilot's birth qualification byte-identical after each (p1) |
| P01 | same question as a task needing `GOVERNED_ARTIFACT_READ` | parent `COMPLETED`, pilot `REFUSED CAPABILITY_NOT_GRANTED`; no parent event in the pilot's journal; parent's journal unchanged by the pilot |

One deviation from r8, declared in p0: `no_qualification_written` lists the files the run creates,
because `birth_qualification.json` is written by the supervisor at admission, before any run.

## Not claimed, limits

- No new métier: the pilot runs its parent's code. A pilot with its own behaviour needs its own code,
  criteria and review.
- Narrower lab permissions restrict which task types the supervisor admits; they do not restrict what
  the worker could do inside the sandbox (tools are declared by the worker, not traced). No task type
  of the lab's own registry (`colony_lab.supervisor.TASKS`) needs `GOVERNED_ARTIFACT_READ`: P01 uses a
  task type defined by the campaign, running the same worker.
- Generation 2: `make_descendant` cannot make a grandchild (B11), but `Supervisor.admit` accepts a
  hand-sealed generation-2 record with a shape-valid qualification of its parent (shown by the
  review), because records are not authenticated. The gate does not establish that the pilot is
  qualified. Step 7 (widening) needs this addressed, criteria and a review first.
- `parent_unchanged` observes non-interference; no trial attempts an adversarial write into the
  parent from the pilot's sandbox (the sandbox tests of #480 cover the lab root's absence).
- Lab records, including the r8 record and a future pilot record, are not authenticated: whoever
  writes the lab root or the checkout is the authority. An attacker who writes the checkout is out of
  scope, as for Sentinel (see `SENTINEL_QUALIFICATION_REPORT.md`, reviews 8 and 9).
- Sandbox tests may skip on GitHub runners (AppArmor); the sandbox evidence is from local runs. The
  unit tests of B12 and P01 need the sandbox too: on such a host, memory separation at birth and the
  pilot's own refusal are proven by the campaign only, and so are the replays run for real (the
  setup tests stub the run).
- L23 and S17 are defences in depth: B09 refuses a child with its parent's identity before any
  record exists, and `admit` already refuses a reviewer naming the child (B04). Their tests prove
  the second line holds, not that it is ever reached by the lab's own paths.
- A simulated, deterministic trial is not a full qualification and grants no runtime permission.

## Before any pilot record

An independent review of p1, the PC2 evidence, `colony_pilot/` and the new tests, with mutants the
author has not seen (reviewer kind `EXTERNAL_REVIEW_PROCESS` or `EXTERNAL_HUMAN`). A pilot record
would have to name the pilot evaluator hash as well. Until then the pilot is **not qualified**.

Rerun: `python -m colony_pilot.campaign --out DIR` refuses and prints the isolated command to run.
