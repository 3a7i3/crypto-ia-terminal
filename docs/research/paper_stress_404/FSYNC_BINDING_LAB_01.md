# FSYNC-BINDING-LAB-01 — identity and ranges, laboratory only

Mission #424, parents #422/#420/#404 ; operator authorized separate laboratory.
Base source d5af288575cb02644be6f2565de64b5fd1222d93, after #419/#421/#423.
No active epoch, actual decision population or production data is involved.

## Question and native evidence in the laboratory

[Writer/observer harness](../../../scripts/research/qualify_fsync_binding_lab.py)
creates a fresh owned directory and file. Its child writes three actual JSONL
records with LAB attempt/packet/trace/decision IDs. A single fsync occurs after
two writes, before the third. All identifiers belong to this controlled synthetic
producer, not the deployed Advisor or a true eligible population.

Two bounded pipe handshakes pause the child with the target fd held open. The
parent independently reads /proc/PID/fd/N path/stat and the file path stat before
writes and after the third write, while the child still holds the same fd.
Both device/inode pairs must match. strace -ff gives a per-PID trace file; the
actual observer trace filename must match that child's pid. Only this newly
launched child is traced, never a preexisting process. On exception, only the
owned subprocess group is killed to avoid a paused orphan, never any service.

Raw trace captures write/pwrite64/lseek/ftruncate/dup/dup2/dup3/fsync/close, bounded
string size 65536. The target records are ASCII, below that bound; unsupported
or truncated target trace aborts. Only exact full sequential write results and
one successful fsync followed by a final close are admitted. Any target seek,
pwrite, truncate or duplication aborts this mono-writer contract. No silent
repair of short writes or trace missing steps. Unrelated Python initialization
fd activity is outside the inspected target file's lifetime.

Record ranges start at zero because the file is newly exclusively created and
empty. Exact ordered syscall buffers must equal the expected writer bytes and
final captured file bytes. Their cumulative byte counts define half-open ranges;
each record's hash and native LAB identities are preserved. The fsync-return
covers only preceding completed writes on that fd; the third record has no
fsync-return witness, despite its bytes existing after the process exits.
An unsynchronized record is not a demonstrated lost record.

This qualifies a **controlled, no-reopen, single-thread, single-writer lifetime**
with native parent fd inspections and syscall transcript. Parent snapshots
bracket syscalls, not atomic inspections at each kernel entry. The trusted
reviewed child code and trace permit this laboratory interpretation; a hostile
writer, parallel mutation, inode reuse, process restart, unobserved syscall,
tracer drop or distributed clocks are not covered. No blanket generation or
custody guarantee follows from dev/inode/path equality alone.

## Workflow and fault handling

[Workflow](../../../.github/workflows/fsync-binding-lab-01.yml) uses an ephemeral
Ubuntu GitHub runner, contents:read, no checkout credentials persisted, no
secrets, VPS or production environment. Five-minute timeout; ten-second protocol
handshakes/process waits; tiny fixed records and a fixed number of workers.
Absent strace or failed ptrace preflight => NOT_OBSERVED, job failure. No sudo,
capability/Yama/seccomp change or bypass. Raw trace/report/files are uploaded for
seven days; durable custody must be handled separately before expiration.

Local [tests](../../../tests/research_data/test_fsync_binding_lab.py) validate
non-coverage of the third record, wrong fd, unsupported fake claim, fsync errno,
missing close, write after close, wrong packet bytes and captured-file mismatch.
They use synthetic transcript fixtures, not acquired syscall evidence.
CI/lab native result must be read at the exact HEAD before observation is claimed.

The ranges mapping is group-fsync raw evidence; it is not flattened into D1-E V1's
one-call witness model by inventing independent fsync_call_id values. Future
adapter/versioning remains a separate contract. No claim about admission roster
exhaustiveness or causal market data accompanies these LAB records.

## Current disposition

LAB_FD_FILE_RANGE_BINDING_RESULT=NOT_OBSERVED until runner evidence is verified.
REAL_DECISION_FILE_RANGE_BINDING=NOT_PROVEN.
C2_NATIVE_INSTRUMENT_QUALIFICATION remains INCOMPLETE.
FUTURE_CAPTURE_ACTIVATION=DENIED; PAPER_STRESS_RUNTIME_GO=DENIED; #286 ACTIVE.
No crash/power-loss or directory-durability guarantee, independent custody,
actual future epoch, runtime/PPL/FIN/risk/sizing change or trading authority.

Rollback: revert only laboratory workflow/harness/tests/documentation. No
restart, deploy, production export, secrets, permissions, Watchdog/TESTNET/LIVE,
exchange action or feedback to active burn-in. VPS reconnect was checked via
Desktop Commander list/ping and remained unavailable at this work's start.
