"""observability/process_identity.py — O-02W-C: single canonical
process_instance_id per advisor process lifetime.

Per docs/contracts/O-02W-B_CANONICAL_OPERATOR_API_CONTRACT.md §15
(RUNTIME_IDENTITY_CONTRACT, R4.2 "sole identity authority is the advisor
bootstrap"): exactly one `process_instance_id` is generated per process
lifetime, before the main loop begins, and every other component (S-03's
RuntimeProvenanceSnapshotWriter, the canonical operator snapshot, the
operator runtime manifest) is a passive propagator of this one value —
never a second generator, never a reconciliation point.

This module owns that single generation: a module-level UUID created once
at import time, analogous to
`observability/runtime_provenance_snapshot.py::_EXPOSURE_EPOCH_ID` (which
remains a distinct, unrelated identity axis — S-03's process/exposure
epoch, never aliased to this value, §15).

A process restart is, by construction, a fresh Python interpreter — this
module is re-imported and a new UUID is generated, satisfying the
"a simulated restart must produce a different process ID" requirement
(§6/§22 test 29) without any explicit restart-detection logic here.
"""

from __future__ import annotations

import uuid

_PROCESS_INSTANCE_ID = str(uuid.uuid4())


def get_process_instance_id() -> str:
    """Return this process's single canonical identity.

    Always returns the same value for the lifetime of the interpreter —
    never regenerated, never reconciled against another source. Every
    consumer (S-03, the operator snapshot, the operator runtime manifest)
    must call this function rather than minting its own UUID (§15 binding
    rule: "no writer, no manifest, and no consumer may independently
    regenerate, infer, or reconcile a second process_instance_id").
    """

    return _PROCESS_INSTANCE_ID


__all__ = ["get_process_instance_id"]
