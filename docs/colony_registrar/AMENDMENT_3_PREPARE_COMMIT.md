# Registrar amendment 3 — prepare and staged commit
SOURCE_ONLY / LAB_ONLY. Contract before code implementing P1 #488.
Parent contract sha256 e8a125bd67964a01f8a06a5f2d3c50f34e9a154e521dce201cb4fb6d1a40bfcd.
Scenarios A0 sha256 4e518bfec6faaa582c2c42633d80e989b8204708b554f74b0eb1bbee6eaa59a1 remain immutable.

## Interfaces
exclusive(): nonblocking L1, per-Registrar reentrancy for the owning thread only;
other threads/processes are refused. Do not delete lock files.
prepare(parent_agent_id, child_spec, *, parent_qualification, admission,
lab_permissions, budget, declared_diff) -> BirthPlan: no filesystem writes.
Returns a canonical, snapshotted, digest-bound plan including the sealed record,
input data, policy pin and exact population/children/budget facts. An existing
divergent admission is ADMISSION_CONFLICT before any consumption.
commit(plan, *, step): requires this Registrar's exclusive lock, revalidates
the policy and plan, current population (excluding the operation's own child),
parent, lineage, all ceilings and STOP before writing.
step ADMISSION (D2) writes only the admission record; step HOME (D3) requires
the exact admission, then calls Supervisor.admit. Whole birth remains a convenience.
D2 identical record is idempotent. D3 complete identical home is accepted; a
partial/divergent home is HOME_CONFLICT and never repaired here. Recovery and
quarantine are the controller's responsibility. No second prepare for a resume:
validate frozen material against current facts instead of replacing the plan.

## Error boundary
RegistrarError from commit is reserved for the registrar's own pre-write refusals.
I/O during writes propagates as OSError (no mapping to a pre-write refusal).
Supervisor.admit errors propagate as LabError, including those before its first
write; the controller handles them as P1 requires. No claim that commit is atomic.
The legacy birth entrypoint keeps its existing coded error mapping.
Admission writes loop until complete, fsync file then directory; zero progress
is an error, fsync is never retried after failure. Existing admission directories
are checked as real private directories. Run-slot I/O becomes LAB_IO_ERROR.
Plafonds only apply through Registrar; direct Supervisor admission/run remain
bypasses until T7. No lab/worker/pilot/J01 change, no requalification or auth claim.
#286 ACTIVE; no actual individual or deployment.
