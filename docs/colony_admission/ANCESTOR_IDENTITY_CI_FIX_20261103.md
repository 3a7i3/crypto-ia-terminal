# Ancestor identity: reproducible SOURCE_CHANGED diagnosis

Source-only mission approved by the operator on 2026-11-03 (America/Mexico_City).
Base: `main@9b960aa6e8ccd7500ea74ad9153f0c0be617fbb8`.
No deployment, service operation, data capture, admission or runtime authority.

## Failure and cause

The base's Codecov and Coveralls jobs failed in population observer tests:

- [125132400143](https://github.com/3a7i3/crypto-ia-terminal/actions/runs/41400912636/job/125132400143),
  `test_complete_own_fields_are_exact_values`;
- [125132400573](https://github.com/3a7i3/crypto-ia-terminal/actions/runs/41400912630/job/125132400573),
  `test_plan_divergence_blocks_the_observation`.

In both logs the first refusal is `observer._Acquisition.verify` on `/tmp`:
the acquired directory keeps its device/inode, while its link count and
mtime/ctime differ. Every path component above a bound source root had been
recorded with the same full metadata identity as the selected evidence.
An unrelated sibling entry can therefore discard all provisional evidence.
The checkout walker independently recorded the same overbroad identity.

The regression tests change real filesystem entries immediately before the
real final verifier, without mocking its decision or returned evidence:
create/remove/rename a sibling, create an unrelated file, or change an
ancestor's mtime. Public FileObserver and PopulationObserver calls exercise
the acquisition; checkout acquisition exercises its separate path walker.
Population tests preserve both the valid OWN observation and the existing
plan-divergence refusal, comparing their complete results before/after noise.

**Before the fix:** the new 20-case suite gives 8 failures / 12 passes on the
otherwise unmodified base. **After the fix:** all 20 pass.

## Exact boundary of the change

The distinction follows the acquisition contract's separate treatment of
ancestors above a bound root and selected resources:
[file boundary](P4_FILE_OBSERVER_BOUNDARY_V0.md),
[3A acquisition](P4_3A_PHYSICAL_EVIDENCE_JOIN_V0.md#3-one-bounded-acquisition-not-a-durable-snapshot),
[checkout acquisition](P4_3B_ATTESTATIONS_AND_ANCESTRY_V0.md#93-acquisition-checkout).

| Acquired object | Final FD and no-follow path comparison |
|---|---|
| Strict ancestor above an explicitly bound root | device, inode, mode/type, uid |
| Bound lab, ledger, trust or fault directory; selected directory below it | existing full identity, including nlink/size/mtime/ctime |
| Bound checkout root and acquired directories/files below it | existing full identity and inventories |
| Selected evidence file | existing full identity; file read checks, hashes, locks and limits unchanged |

`remember_directory` registers this distinction for both absolute path walkers.
The existing `checks` list retains full-identity entries (including the L1
descriptor used by population acquisition); ancestor entries use a separate
list. Every component is still opened NOFOLLOW and retained until final
verification. Ancestor replacement, symlink rebinding and mode changes are
tested and refused. Bound-root entry/mtime/mode changes are tested for both
walkers and remain refused. Existing selected-file mutation, permissions,
absence, inventory, capacity and close-failure tests remain applicable.

Ancestor nlink/size/mtime/ctime no longer assert stability of unrelated
namespaces. This does not provide an atomic multi-file snapshot, adversarial
ancestor/OS protection, timestamp-restoration detection or proof of durability.
The contracts' cooperating-writer and ancestor-compromise limits still apply.
No pinned P1 format, policy, profile, acceptance matrix or baseline is changed.

## Validation and limits

Local environment: Linux, Python 3.11.17, pytest 9.2.0, Ruff 0.15.8;
dependencies installed outside the checkout from the tracked requirements.

- New regression suite: 20 passed normally; 20 passed under `python -O`
  with pytest's default assertion rewriting (not `--assert=plain`).
- Direct observer, checkout, population and physical/attestation regressions:
  414 passed (including the new suite).
- Cross-stack Python suite: 113 passed, one Starlette deprecation warning.
- Ruff on changed Python files: pass. Baseline gate: 957 committed findings,
  945 current, zero new findings. `git diff --check`: pass.
- Broader local attempts are **not a full-suite PASS**. The inventory cases
  `mode_000` and `socket_hex64` fail in this environment; an intact base worktree
  reproduces the same two failures (17 other cases pass). Five supervisor
  cases also fail creating AF_UNIX sockets with EPERM on both candidate and
  intact base (12 pass, 23 skip on each). These tests are not altered/skipped
  by the patch. Some extended local runs exit before a final summary, so their
  collected counts are not promoted to successful test counts.

Exact-HEAD CI, including coverage workflows, and independent diff review
remain the source merge gates. No previous green is transferred to this patch.
The patch does not qualify Colony, make `accepted=true`, change PC2/p1 support,
lift #286 or prove any production state.

## Rollback and next action

Rollback is a source revert of this change; no installed or selected release
was modified. Review this boundary and the new positive/negative cases, then
inspect all required and coverage checks at the exact PR HEAD. Merge remains
a separate decision; no automatic merge or activation is configured here.
