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
sandbox, that a descendant can be born only from a qualified parent, has its own identity, memory
and narrower permissions, and leaves its parent untouched. The worker answers in its parent's voice
(output `agent_id` `SENTINEL-01`); the pilot's lab identity is its record's `agent_id`.

## Method

1. Criteria `PILOT_CRITERIA_P0.json` (sha256 `065e0777…`) were written from the lineage contract and
   committed and pushed (`c4216ed4`) **before any trial ran**. One expectation was corrected from code
   reading before that push, not after a result: a grandchild cannot be made at all (B11 expects
   `LINEAGE_INVALID`, not a qualification code).
2. The evaluator is `colony_pilot/campaign.py`, outside `colony_lab`, so Sentinel's record still names
   the evaluator code that produced its evidence (`41b78971…`). It reuses Sentinel's reviewed gates
   (`tree_state`, `sandbox_view`, `evaluator_runtime`, `code_irregular`, the r8 predicates and golden
   answers) and adds its own hash (`pilot_code_sha256` `b6ca2b49…`).
3. The parent qualification is the real record `SENTINEL_QUALIFICATION_RECORD_R8.json`. The lab
   checks only its shape; the campaign also checks that it names the C9 evidence file, criteria r8 and
   the current subject and Sentinel evaluator hashes (`PARENT_QUALIFICATION_STALE` otherwise).
4. Every trial runs twice, each in a fresh lab root; the campaign refuses to start unless isolated
   (`-I -S -B`, no repository bytecode), as for Sentinel.

## Trials and campaign PC1

PC1, at `c4216ed4`, launched with `launch_command`: **27/27 trials passed in both rounds**,
deterministic, sandbox `VERIFIED`, sandbox view equal to the subject (46 files), checkout clean,
evaluator isolated, no irregular code, parent record current. Proposed state
`PROPOSED_QUALIFIED_SIMULATED`. Evidence `evidence/PC1_pilot_evidence.json`, sha256
`36f4e30dc33d27df8e56483cef654ab7282a7af6245dc576f6c2e01ee07fa10b`.

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
| B11 | grandchild made from the pilot | `LINEAGE_INVALID` |
| Q00–Q14 | every Sentinel r8 trial with the pilot as the individual, judged by the r8 predicates and golden answers | all pass; parent's files byte-identical after each |
| P01 | same question as a task needing `GOVERNED_ARTIFACT_READ` | parent `COMPLETED`, pilot `REFUSED CAPABILITY_NOT_GRANTED`; no parent event in the pilot's journal; parent's journal unchanged by the pilot |

One deviation from r8, declared in p0: `no_qualification_written` lists the files the run creates,
because `birth_qualification.json` is written by the supervisor at admission, before any run.

## Not claimed, limits

- No new métier: the pilot runs its parent's code. A pilot with its own behaviour needs its own code,
  criteria and review.
- Narrower lab permissions restrict which task types the supervisor admits; they do not restrict what
  the worker could do inside the sandbox (tools are declared by the worker, not traced).
- **No grandchild can be made** (B11): `make_descendant` verifies a descendant parent without its own
  parent. Step 7 (widening) needs that changed, criteria and a review first.
- Lab records, including the r8 record and a future pilot record, are not authenticated: whoever
  writes the lab root or the checkout is the authority. An attacker who writes the checkout is out of
  scope, as for Sentinel (see `SENTINEL_QUALIFICATION_REPORT.md`, reviews 8 and 9).
- Sandbox tests may skip on GitHub runners (AppArmor); the sandbox evidence is from local runs.
- A simulated, deterministic trial is not a full qualification and grants no runtime permission.

## Before any pilot record

An independent review of p0, the PC1 evidence and `colony_pilot/`, with mutants the author has not
seen (reviewer kind `EXTERNAL_REVIEW_PROCESS` or `EXTERNAL_HUMAN`). Until then the pilot is **not
qualified**.

Rerun: `python -m colony_pilot.campaign --out DIR` refuses and prints the isolated command to run.
