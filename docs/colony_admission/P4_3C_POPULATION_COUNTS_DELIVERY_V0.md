# 3C-4 — Private POPULATION partition, classified counts, plan match and ceilings

SOURCE_ONLY / LAB_ONLY / PARTIAL_IMPLEMENTATION / NO_PUBLIC_POPULATION_SCAN.
Stacked on the 3C-3 classification tranche ([delivery](P4_3C_CLASSIFICATION_OWN_DELIVERY_V0.md)).
It cannot merge before 3C-3's private closure after its own merge CI.
References: [3C contract](P4_3C_POPULATION_AND_CEILINGS_V0.md) §2, §6–9, §12.
The 107 matrix cases remain SPECIFICATION_ONLY_NOT_EXECUTED, not a test count.

## Property

`_population_counts.current` is pure and runs inside `_population_proof.prove`,
hence inside the one owner, only for a CURRENT_OPEN operation whose preflight has
no OPERATION_PENDING. Other operations keep an all-NE `CurrentPopulation`
(historical: HISTORICAL_POPULATION_NOT_EVALUATED; pending: OPERATION_PENDING).

- **POPULATION partition** (§7): needs are built from every INCLUDED home outside
  the DECISION branch and other than OWN: its individual if its envelope is
  present, plus the admission/qualification/statement triple of a descendant,
  each with every namespace copy. A K already required by DECISION keeps that
  single role and every POPULATION copy must name the frozen DECISION envelope.
  Compared with PREPARED without rewriting it: ATTESTATION_MISSING,
  ATTESTATION_UNEXPECTED, FROZEN_ITEM_DIVERGENT, POPULATION_ROLE_MISMATCH.
  COMP-08: a frozen individual now stably absent stays MISSING. COMP-10: a
  descendant's individual present now but absent from PREPARED gives NE/
  HISTORICAL_POPULATION_ATTESTATION_UNAVAILABLE (blocking), never for founders,
  triples or DECISION items. The partition is NE unless the DECISION branch
  structure passed and every home is INCLUDED or EXCLUDED_OWN.
  `frozen_completeness` aggregates the 3B DECISION partition and this one.
- **Counts** (§8): exact only if every home is INCLUDED or EXCLUDED_OWN; P, F,
  direct children of the candidate parent, the six budget sums (strict int within
  lineage bounds, Python integers) and sorted H(records INCLUDED). OWN is excluded
  (never +1); SUSPENDED stays counted. Any BLOCKING/NE home gives complete FAIL/NE
  with null exact values.
- **plan_match**: H(records), population_count, children_count and budget_totals
  of the frozen BirthPlan must all be equal; otherwise FAIL/POPULATION_CHANGED.
  NE when counts are not exact. No new prepare.
- **Ceilings** (§9): population, children, generation, colony budget per
  component, parent budget, permissions subset plus exact declared diff
  (registrar codes kept), and the P/F bundle bound only when P+1 is within policy
  and F>=1. Equality allowed, first excess refused. A bundle excess raises the
  named `item_references` limit (whole-context erasure), never a capacity FAIL.
  concurrency_enforcement stays NE/NO_RUNTIME_OBSERVATION; ceilings carry no
  authorization.

All objects are frozen, accepted=false, authorization NE. No public API.

## Still required

Fault scopes (global ledger/trust, operation, action), quarantine/action/
incarnation correspondences, global identity exclusions on the whole universe,
snapshot completeness, aggregation, invalidation of the final object and the
public `PopulationObserver`. PC2/p1 remains SCIENTIFIC_PROFILE_UNSUPPORTED/NE
blocking; #510 not adopted; p1 in g0. #286 ACTIVE, 3C and step 3/7 open.

## Validation

Real-owner LAB_TEST fixtures: exact OWN with P=1/F=1 and plan PASS; plan
divergence per field; second founder POPULATION item exact, omitted, substituted,
moved to DECISION, surplus; unclassified home nulls counts; OPERATION_PENDING.
Detached pure checks: population 5+1 then 6+1, children 1+1 then 2+1, each of the
six colony budgets at cap then cap+1, strict budget integers, parent budget,
permission escalation, undeclared diff, generation, bundle bound exact then +1,
COMP-08, COMP-10 including the triple exception, founder individual missing,
DECISION copy from a POPULATION home. Exact counts, -O runs, mutants and the
independent exact-tree review are recorded in the PR. No VPS/runtime/secret/
writer/campaign; rollback source only.
