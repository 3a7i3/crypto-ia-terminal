# 3C-5 — Fault scopes, action correspondences and the public PopulationObserver

SOURCE_ONLY / LAB_ONLY / NO_AUTHORITY.
Based on main `efe1fa71` (3C-4 #516 merged and closed after its own merge CI).
3C-3 (#515) was closed with a recorded one-off reservation: its exact merge CI stayed
red (pytest 9.2, fixed by #517). No prior green transfers to this tree.

References: [3C contract](P4_3C_POPULATION_AND_CEILINGS_V0.md) §2–3, §10–12;
[classification/OWN](P4_3C_CLASSIFICATION_OWN_DELIVERY_V0.md),
[counts](P4_3C_POPULATION_COUNTS_DELIVERY_V0.md).
The 107 matrix cases remain SPECIFICATION_ONLY_NOT_EXECUTED, not a test count.

## Fault scopes (§10)

`_population_faults.faults` is a private pure function called once by the single
owner on the fault bytes it already retained. Every recorded fault claim gets one
scope; none is cleared (`cleared` stays NE):

- **GLOBAL** (always blocking, STICKY_FAULT): LAB scope, ledger/lab/individuals/
  operation-log/admission/envelope directories, quarantine root.
- **UNBOUND** (blocking, TARGET_BINDING_UNAVAILABLE): a home or envelope entry
  whose path is outside the closed mapping, an operation not known to U, or a
  claim whose child or attempt differs from those its operation digest designates
  (the digest alone never binds).
- **OPERATION_UNRESOLVED** (blocking, EXTERNAL_TERMINATION_UNPROVEN): the faulty
  log of an external termination whose linkage is not PASS.
- **OPERATION_CURRENT** (blocking, STICKY_FAULT): a fault of the latest open attempt.
- **OPERATION_HISTORICAL** (non-blocking): a closed attempt or a proven linkage.

A controller FSYNC/RENAME fault on a home directory adds ACTION_RESTRICTED.

## Quarantine and set-aside correspondences (§11)

`_population_faults.actions` pairs every quarantine destination of the owner's
inventory with exactly one claim from the strict readable logs (QUARANTINE_BEGIN/
DONE, SET_ASIDE_BEGIN/DONE) or the external set-aside lines:

- A destination without any claim is ACTION_EVIDENCE_NOT_EVALUATED/blocking; a
  claim DONE without destination is ACTION_LOCATION_DIVERGENT/blocking.
- After QUARANTINE_DONE the source home may exist only if a new effective BEGIN D3
  (not cancelled) started a new incarnation; a new incarnation before its first
  write is location PASS.
- Quarantined identity bytes must equal the plan storage bytes exactly; a prefix is
  not tolerated for a quarantine (FAIL). Set-aside identity is NE when no plan is
  readable (external lines).
- A BEGIN without DONE is located but its completion stays NE and blocking.

Journal semantics, durability and permission of every action stay NE. No action is
performed, recommended or permitted.

## Public PopulationObserver

`population_observer.PopulationObserver(PopulationConfig).scan_population()`
returns `PopulationEvidence` (schema `colony-admission.population-evidence/0`).
It wraps the one owner acquisition; any acquisition failure gives a BLOCKED
evidence with no homes. `HomeFact.role`, parent, founder and generation are exposed
only once the home structure is PASS (role in FOUNDER/DESCENDANT), never as raw
values. `OperationPopulation.needs` lists the 3B DECISION needs extended with the
POPULATION needs, sorted by the 3B key (DECISION: 3B namespaces and frozen envelope
digests; POPULATION: one namespace/envelope-digest pair per copy; none while the
partition is CLASSIFICATION_NOT_EVALUATED), and `items` the frozen PREPARED items,
all as immutable tuples. It aggregates home facts, operation facts (CURRENT_OPEN
counts, plan match, ceilings), external terminations, fault bindings and action
facts. NOT_APPLICABLE_FOUNDER, HISTORICAL_POPULATION_NOT_EVALUATED,
NO_CURRENT_OPEN_OPERATION and NO_RUNTIME_OBSERVATION are warnings, never
blockers. OBSERVED also needs snapshot_completeness PASS, else
CLASSIFICATION_NOT_EVALUATED. Global identity exclusions: FAIL dominates; any unstructured or
unclassified home, any present individual left unchecked or a current decision
not PASS keeps it NE.

`OBSERVED` is a diagnostic status only. `accepted=false`; completeness,
authorization, durability, rotation, recovery, source revision provenance and
operational completeness are permanently NE. The observer is not re-exported by
the package and no caller is wired to it.

## Still blocking for step 3/7

PC2/p1 remains SCIENTIFIC_PROFILE_UNSUPPORTED/NE blocking: a candidate under it
stays NE, never OWN, and the observer is BLOCKED for it. #510 not adopted; p1 in
g0. Human scientific proof and the normative PC2 decision are outside this scope.

## Validation and gates

Review follow-up for 3C-3 (tests only, no 3C-3 source change): the owner wires every
home ID, the branch, the child and the candidate envelopes into the candidate
contradiction. The 3C-4 follow-ups (SUSPENDED counted, children of the candidate
parent, bundle-bound preconditions) were merged with 3C-4 (#516).

Temporary LAB_TEST fixtures and public test keys only, through the real owner:
complete OWN observed without authority; no current open operation; unsupported
profile blocks; global ledger/directory and trust-install faults; historical
linked fault non-blocking; current operation fault; target outside mapping;
quarantine then new incarnation; incarnation before first write; source present
without incarnation (no re-BEGIN, cancelled); lying DONE; BEGIN without DONE;
quarantine identity prefix refused; orphan destination; external set-aside
identity NE; self-issued individual making global exclusions FAIL; failed branch
attestations blocking with decision codes; plan divergence, ceiling FAIL and
counts NE blocking at the observer; fault of an operation unknown to U UNBOUND;
quarantine-root fault GLOBAL; LAB/operation-log/admission/envelope directory faults
GLOBAL; envelope entry outside mapping UNBOUND; ACTION_RESTRICTED only for a home
directory FSYNC/RENAME fault; unproven (/0) and divergent external terminations
OPERATION_UNRESOLVED and blocking; log-based SET_ASIDE DONE with equal or prefix
identity PASS, with divergent identity or a still-present source FAIL; BEGIN without
DONE with zero or two locations FAIL; global identity exclusions NE for an
unsupported profile or a current decision not PASS; raw role never exposed; fault of a closed readable operation
historical and non-blocking; fault naming a closed operation with another child
or attempt UNBOUND; invalid config; acquisition failure; no
public export. External pending set-aside BEGIN is located but incomplete and blocking.
Exact values are pinned for the complete OWN snapshot (both homes' FileFacts
recomputed from disk bytes, proof fields, layout and lineage; every scalar
OperationPopulation field, with needs/items/counts/ceilings pinned by their own
tests; sources, metadata sources and ledger batch bytes as passed through from the
single acquisition, ledger coverage and log coverage PASS), a superseded attempt (historical, not latest, NE
decision, no own home), a closed operation's descendant proofs, specific population
and decision codes carried instead of the generic fallback, EXECUTION_SUSPENDED as a
warning only, and the references of current/historical FaultBindings and of
QUARANTINE/UNKNOWN/identity-NE ActionFacts. Still untested (values only, status stays
BLOCKED): quarantine cycle reset, faults bound to a superseded attempt, observer-level
ledger coverage code, and SCIENTIFIC_PROFILE_UNSUPPORTED dropped from the operation codes
alone (the home codes or, without a child home, the decision blockers still carry it). Exact counts,
-O runs, mutants and independent exact-tree agent review are recorded in the PR.

P1/pins/scenarios/formats/g0 and colony_lab/sentinel_activity/colony_pilot are
unchanged. #286 ACTIVE, accepted=false. No VPS/runtime/systemd/PPL/FIN/epoch/
production/TESTNET/LIVE/exchange/secret/replay/campaign/birth/installation/
recovery or operational writer. Rollback is source only.
