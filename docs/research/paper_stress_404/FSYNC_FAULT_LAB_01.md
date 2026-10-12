# FSYNC-FAULT-LAB-01 — native refusal qualification only

Mission #426, dependent on #424/PR #425, parents #420/#404/#285.
Separate operator-authorized synthetic laboratory, never a VPS deployment.

## Scope and expected outcomes

[Harness](../../../scripts/research/qualify_fsync_fault_lab.py) launches six
owned Python children under external strace, one at a time in fresh directories.
It reuses the strict binding parser without changing its production authority.

| Case | Actual worker operation | Required parser result |
|---|---|---|
| normal | Three exact writes, fsync after two, close | ACCEPT |
| partial_record | Successful write of only half the first record | REFUSE |
| seek | lseek to zero before the third write | REFUSE |
| truncate | ftruncate to zero before the third write | REFUSE |
| rotation | Close, rename, recreate path, write third record | REFUSE |
| second_fsync | Second fsync after third record | REFUSE |

The partial-record case is **not an injected kernel short-write return**: the
worker deliberately submits a smaller buffer, successfully written. Tests of a
short return, dropped transcript line or corrupted identity are parser fixtures
only, not evidence of a native tracer drop or kernel failure. Rotation refusal
does not qualify rotation support, inode reuse protection or an adversarial
generation detector. No retry adapter or group-fsync schema is admitted.

## Evidence and limits

Raw per-PID traces include openat/rename alongside the #425 syscall vocabulary.
Those two operations are retained in original traces; the explicitly derived
`binding-input.trace` removes only openat/rename lines to exercise the unchanged
#425 parser. A refusal demonstrates the strict parser's reaction in that
controlled case, not full visibility of all possible filesystem operations.
Worker stdout joins PID and initial FD to the corresponding external trace;
it is not an independent trust root. Each file and transcript has a SHA-256.
Normal acceptance and all five refusals are required for workflow success.

Preflight failure or missing strace yields NOT_OBSERVED. No sudo, attachment to
existing processes, capability/seccomp/Yama changes or bypass. Ten-second waits
per own child; timeout cleanup kills only its owned process group. Six fixed
workers and three fixed small records each; Linux initialization traces are
outside target-file binding and overall workflow limited to five minutes.
No workload capacity admission, privacy certification, crash/power-loss or
directory durability follows from these results.

[Workflow](../../../.github/workflows/fsync-fault-lab-01.yml) uses a fresh hosted
Ubuntu runner, contents:read and checkout without persistent credentials.
No secrets, Advisor, exchange, epoch, PPL/FIN or production files are consumed.
Artifact retention seven days; durable preservation is a separate evidence gate.
[Tests](../../../tests/research_data/test_fsync_fault_lab.py) are fixture tests.

## Disposition before acquisition

NATIVE_FAULT_REFUSAL_QUALIFICATION=NOT_OBSERVED until actual run and bytes verified.
C2_NATIVE_INSTRUMENT_QUALIFICATION=INCOMPLETE.
D1_D_PRODUCER_COMPLETENESS=NOT_PROVEN.
D1_E_PER_PACKET_DURABILITY=NOT_PROVEN.
REAL_DECISION_FILE_RANGE_BINDING=NOT_PROVEN.
FUTURE_CAPTURE_ACTIVATION=DENIED; PAPER_STRESS_RUNTIME_GO=DENIED; #286 ACTIVE.

Rollback: revert these four source laboratory files only. No production
configuration, restart, deploy, collection or feedback toward the active epoch.
