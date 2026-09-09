"""observability/process_identity.py — O-02W-C: single canonical
process_instance_id per advisor process lifetime.

Per docs/contracts/O-02W-B_CANONICAL_OPERATOR_API_CONTRACT.md §15
(RUNTIME_IDENTITY_CONTRACT, R4.2 "sole identity authority is the advisor
bootstrap"): exactly one `process_instance_id` is generated per process
lifetime, before the main loop begins, and every other component (S-03's
RuntimeProvenanceSnapshotWriter, the canonical operator snapshot, the
operator runtime manifest) is a passive propagator of this one value —
never a second generator, never a reconciliation point.

R1 correction (MASTER review, correction D): the previous eager
module-level UUID plus an independently-callable global getter
(`get_process_instance_id()`) let more than one call site "discover" the
identity on its own, which does not prove real dependency-injected
ownership. The advisor bootstrap (`core/advisor_loop.py::main()`) is now
the SOLE call site of `generate_process_instance_id()` — called exactly
once, before the main loop begins — and the resulting value is passed
explicitly (as a parameter) into every consumer: S-03's
`_runtime_provenance_inputs()`, the operator runtime manifest writer, and
the operator snapshot builder/writer. No writer or projection may call
this generator itself, nor may it read a module-level cached identity.

This module remains a distinct, unrelated identity axis from S-03's
`_EXPOSURE_EPOCH_ID` (observability/runtime_provenance_snapshot.py),
never aliased to this value (§15).
"""

from __future__ import annotations

import uuid


def generate_process_instance_id() -> str:
    """Generate a fresh canonical process identity.

    MUST be called exactly once per process lifetime, at the advisor
    bootstrap, before the main loop begins (§15). The single string this
    returns is then threaded explicitly, as a parameter, into every
    consumer — never regenerated, never independently re-derived, never
    reconciled against another source.
    """

    return str(uuid.uuid4())


__all__ = ["generate_process_instance_id"]
