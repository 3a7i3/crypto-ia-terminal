# 3C-3 — Private home classification and exact OWN in the one owner

SOURCE_ONLY / LAB_ONLY / PARTIAL_IMPLEMENTATION / NO_PUBLIC_POPULATION_SCAN.
Prepared on the reviewed #514 external-bindings tree
`b8d5580c187536f9c41051885c39ec8663d51570` (HEAD `251b0f45b46e92e4c952413f70f2f9c2f5edaa43`).
This dependent delivery cannot merge before #514's private closure after its own
complete merge CI. No prior green transfers to this tree.

References: [3C contract](P4_3C_POPULATION_AND_CEILINGS_V0.md) §2–3, §5–6, §10;
[plan](P4_3C_PLAN_AND_REUSE_V0.md) §8; [owner](P4_3C_ACQUISITION_OWNER_DELIVERY_V0.md),
[preflight](P4_3C_PREFLIGHT_DELIVERY_V0.md), [external bindings](P4_3C_EXTERNAL_BINDINGS_DELIVERY_V0.md).
The 107 matrix cases remain SPECIFICATION_ONLY_NOT_EXECUTED, not a test count.

## Property integrated in the one owner

`_population_proof.prove` is a private pure function. The owner calls it once,
inside the same ExitStack/InventorySource, after the global preflight and the one
shared scientific checkout, and before checkout/source revalidation, unlock and
close. It is the first signature verification of the scan. It receives only the
owner's retained snapshot: readable attempts and their materials, the one ledger
batch, the external bindings and the current trust/policy bytes. It opens nothing
and runs no second scan. Any error or later verify/close/unlock failure erases the
whole Acquisition, proofs included.

Snapshots for birth proofs are built from every readable attempt of U with its
row in the single batch. Each CURRENT_OPEN operation (from the preflight scope)
gets the existing 3B `attestation_evidence.project` DECISION projection on its
acquired branch/envelopes; historical attempts stay HISTORICAL_POPULATION_NOT_EVALUATED.

Every acquired home is classified by the reviewed 3C-1 `own_proofs` (priority
table §5), then three cases are refined:

- **Externally terminated child** (log faulty and unread): linkage PASS or FAIL
  with a present home => UNAUTHENTICATED/BLOCKING; /0, legacy or otherwise
  unproven linkage => NE/EXTERNAL_TERMINATION_UNPROVEN. The unread log cannot
  prove absence of a COMMITTED, so no false contradiction is asserted there.
- **Home of an open operation**: compared with 3A `compare_d3` on the exact plan
  bytes. Present identity content (or initial usage before DONE D3) that is
  neither equal nor a strict prefix => UNAUTHENTICATED/HOME_CONFLICT. No D3 ever
  begun, BEGIN D3 cancelled, quarantine done without a new effective BEGIN D3,
  operator TERMINATED, or DONE D3 with non-identical identity =>
  UNAUTHENTICATED/OPERATION_STATE_INCONSISTENT.
  A strict prefix of an interrupted (not completed) D3, a partial D3 awaiting
  quarantine, or a missing initial usage/layout => NE/OWN_HOME_INCOMPLETE.
  A structurally unbound candidate (e.g. missing parent) => UNAUTHENTICATED.
  A forged/divergent candidate presented proof (own admission/qualification/
  statement items, own statement/science, own consumption, a candidate envelope
  issued by an excluded identity: any home, the branch or the child itself)
  => UNAUTHENTICATED; ancestors' problems and genuine revocation stay NE.
- **OWN_OPERATION/EXCLUDED_OWN** only if all hold: the preflight's unique
  potential own candidate (unique open, no unresolved external claim, exact
  identity storage bytes, complete layout, exact D2 material, initial usage
  `{runs:0}` before DONE D3); effective BEGIN D3 not cancelled or DONE D3;
  DECISION branch_attestations PASS (science included); candidate admission
  CONSUMED_BY_THIS_OPERATION with an exact /1 row; whole ledger coverage MATCH.
  Never by ID alone. After DONE D3 usage stays unread. A COMMITTED child is a
  member classified by its own proofs, never excluded by its old operation.

`ProofSet.classification` is FAIL if any UNAUTHENTICATED, else NE if any NE, else
PASS (an empty stable inventory is PASS per INV-01). It is only the §2 population
classification aggregate. ProofSet/OperationProof keep population, snapshot and
frozen completeness, partitions, counts, plan_match, ceilings, global exclusions
and authorization permanently NE, accepted=false. The Acquisition top fields
remain NE. No public PopulationObserver/PopulationConfig is exported.

## Still required

POPULATION partition and all copies, COMP-08/COMP-10, global identity exclusions
on the whole universe, classified counts, plan_match and ceilings; fault scopes
(global/operation/action); quarantine/action/incarnation correspondences;
aggregation and the public API. PC2/p1 remains SCIENTIFIC_PROFILE_UNSUPPORTED/NE
blocking (a candidate under it stays NE, never OWN); #510 not adopted; p1 in g0.

## Validation and gates

Temporary LAB_TEST fixtures and public test keys only, through the real owner:
founder classification; operator TERMINATED after DONE D3; divergent initial
usage; FAIL dominating NE; OWN after BEGIN D3 and after DONE D3 (mutable usage and
runtime content never read); incomplete home, strict prefix vs conflict; no/
cancelled/quarantined D3; partial D3 awaiting quarantine; missing or substituted
/1; forged candidate signature; unsupported science; COMMITTED child AWAITING vs
AUTHENTICATED and HISTORICAL; ABANDONED/REFUSED terminal home; external /1 PASS,
/0 and divergent with unread faulty log; unresolved external claim prevents OWN;
unbound ledger line prevents OWN; DONE D3 without layout; missing parent; empty
inventory; erasure on mutation/error after classification; signature ordering
after preflight and checkout; pure-module and no public export checks. Exact
counts, -O runs, mutants and independent exact-tree agent review are recorded in
the PR, not promised here.

P1/pins/scenarios/formats/g0 and colony_lab/sentinel_activity/colony_pilot are
unchanged. #286 ACTIVE, accepted=false, 3C and step 3/7 open. No VPS/runtime/
systemd/PPL/FIN/epoch/production/TESTNET/LIVE/exchange/secret/replay/campaign/
birth/installation/recovery or operational writer. Rollback is source only.
