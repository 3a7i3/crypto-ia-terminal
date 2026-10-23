# Trust amendment 4 — operation-bound consumption
SOURCE_ONLY / LAB_ONLY / LAB_TEST. Contract before code, implementing P1 #488.
Normative parent: docs/colony_admission/ADMISSION_CONTRACT.md (sha256 e8a125bd67964a01f8a06a5f2d3c50f34e9a154e521dce201cb4fb6d1a40bfcd).
Scenarios A0 sha256 4e518bfec6faaa582c2c42633d80e989b8204708b554f74b0eb1bbee6eaa59a1. These pinned files are not edited.

## Interfaces
- check_bundle(items, required, root, *, pin_sha256, minimum_version, lab_id, ledger=None):
  all four properties, replay checked, never creates or consumes. Required items use
  (kind, subject, record_sha256); legacy pairs remain supported by verify_bundle.
- consume(..., ledger, operation_sha256): reverify the full bundle under the ledger
  lock, then append /1 entries. A fresh successful bundle returns accepted true and
  consumption CONSUMED. Exact existing entries for this operation return
  CONSUMED_BY_THIS_OPERATION with accepted false (not fresh authentication/admission).
  A mixture of fresh and own-spent envelopes is OPERATION_STATE_INCONSISTENT,
  never completed silently. Changed operation is ENVELOPE_REPLAYED; changed bytes under
  the same issuer/id are ENVELOPE_ID_REUSED. Own-spent envelopes still undergo current
  root verification; a revocation is not bypassed.
- verify_consumed(envelope, ledger, operation_sha256): read-only evidence of exact
  /1 consumption, not authenticity, authorization or proof of controller COMMITTED.
  The controller must establish those independently.
- classify_envelope: genuine-but-revoked is true only with integrity/authorization
  PASS and failures exclusively KEY_REVOKED/ENVELOPE_REVOKED, including a valid signature.
- qualification statement kind: flat fields defined by P1; cryptographic binding
  here, semantic statement coherence enforced by the future controller.

## Storage
consumed/1 adds operation_sha256 to the exact /0 fields. Mixed /0 and /1 remain
strictly readable, unique (issuer_id,envelope_id); /0 can never authorize resume.
verify_bundle keeps its single-use behavior, including /0 writes, and rejects
previous /1 consumptions as replays.
Files must be private regular single-link files, opened without following the last
component. Parent paths are operator-controlled. Nonblocking open refuses FIFOs before read.
Full-write loop rejects zero progress. Fsync error is LEDGER_DURABILITY_UNKNOWN;
no retry/repair. Directory fsync after append ensures filename persistence.
A failed write may leave a torn ledger; no automatic retry. The future controller
records the external fault and blocks the colony. No standalone API claims persistent
blocking after process loss; filesystem writers and parent replacement remain trusted.
No lab wiring, keys, credentials or actual birth. #286 ACTIVE.
