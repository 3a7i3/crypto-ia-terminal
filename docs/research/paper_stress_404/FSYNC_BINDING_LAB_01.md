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

## Observation effective, 2026-10-12 — périmètre laboratoire seulement

Run [38313808068](https://github.com/3a7i3/crypto-ia-terminal/actions/runs/38313808068),
job 115025546193 SUCCESS au HEAD `14eb08add8187c78f08360cbd6ab253dd7d653e1`.
PID traceur-enfant observé 2422, fd 3, device 2049, inode 8947383, identiques
aux deux inspections externes avant/après writes. Un seul fsync natif, deux
records couverts et un record sans fsync-return. Plages [0,120), [120,240),
[240,360) ; identités LAB-A/P/T/D 1–3 préservées. Aucune perte déduite du troisième.

[Rapport](fsync_binding_lab_01_evidence_20261012/report.json),
[trace syscall raw](fsync_binding_lab_01_evidence_20261012/writer.trace.2422),
[bytes exacts](fsync_binding_lab_01_evidence_20261012/records.jsonl),
[provenance](fsync_binding_lab_01_evidence_20261012/provenance.json).
Artifact 11775991140 téléchargé ; ZIP SHA256 recalculé MATCH
`260577b83d093a6be83c450650ac7feb9bd81428604b1db9cdfb39f3b3f27bfc`.
Script SHA c7c61d17e29160a56e266297ee660884e5debf6991a0e6d1c169b763dfbb2ac2,
trace SHA f72333147c529632b49ba9c3f4df32a25a8bb7cd15a6295e789b8f5619582222,
file SHA 197f0e58e3f914f7a440e8df5e602402adf6da6e5947767eaed0baae678af44d,
et chaque sous-range record : hashes revérifiés MATCH.
Les six fichiers d'artefact et provenance sont conservés pour l'expiration
GitHub du 2026-10-19. Le script expérimenté reste inchangé ; commit de
conservation documentaire distinct du HEAD mesuré, CI au nouveau HEAD à vérifier.

LAB_FD_FILE_RANGE_FSYNC_BINDING_OBSERVED, scénario contrôlé mono-writer/no-reopen
seulement. REAL_DECISION_FILE_RANGE_BINDING/D1_E_PER_PACKET_DURABILITY restent
NOT_PROVEN ; custody indépendante, adversarial/restart/rotation/group-fsync
adapter, coût et vraie population restent à qualifier. Activation/stress DENIED.
Aucune observation VPS fraîche : list/ping Desktop Commander ont encore signalé
Offline ; ne pas en déduire santé Advisor, position ou état PPL actuel.
