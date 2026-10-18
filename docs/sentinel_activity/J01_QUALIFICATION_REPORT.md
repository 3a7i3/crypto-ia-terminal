# J01 — Source qualification and review handoff

2026-10-18. Verdict: **READY_FOR_INDEPENDENT_SOURCE_REVIEW**.
Not SOURCE_CERTIFIED, not deployed, not Sentinel autonomous.
#286 ACTIVE; #315 Gate O OPEN; #374 parked and unchanged.

## Mandate and provenance

The operator approved the plan in Work after the read-only audit of PR #465,
HEAD `811c2feda8dfe4439c77ec23bd8e88d4248aedef`, on 2026-10-18.
Implementation base: `main@a49eedfcd683145cf8ae6e38c6dc38cff8ea698e`.
No implementation permission was inferred from the documentary PR itself.

M1–M4 are review slices, all DRAFT and unmerged:

| Slice | PR | Remote HEAD | Tested/published tree |
|---|---|---|---|
| M1 contract | #466 | f16a2c78ce188b9adf385fe1857311aa996840bf | dfca5ec9197a77ed45cb27dcd9d1c517329cfb39 |
| M2 storage | #467 | 95d1b0916872b0c89cbf28662416c2a662007b8e | 61a174e6e4e5680296bf4c6015a74fc0e6fdee6e |
| M3 quests | #468 | 98a9764e7ff82aed0f6719a0b89986c6d4bdffcc | f2cf89cb32623f57885bb168fb2098fb40912893 |
| M4 recovery | #469 | c73e7813a1d0dcbb504c9f1bc44ead8439d30855 | 93dc3d1877cb55a39170894aca02d904700a4f07 |

Local commits and connector-created commits have different commit metadata;
the entire Git trees match exactly. M5 includes the qualification changes,
runbook and this report. Its PR targets main to expose the complete J01
composition to the normal main-targeted PR gates, including cross-stack.
M1–M4 remain unmerged review slices; no five-way merge sequence is authorized.
The exact M5 remote commit/tree and live CI state are in its PR metadata.

## Delivered scope

- `sentinel_activity/`: pure contract/canonicalization, fixture policy binding,
  isolated SQLite store, pure integrity and quest replay, paginated local
  reader, explicit backup/restore, one-shot synthetic demo.
- `tests/sentinel_activity/`: contracts, negative admission/state tests,
  concurrency, real process exits/restarts, integrity, storage and isolation.
- `docs/sentinel_activity/`: versioned event schema, contract, storage ADR,
  runbook, qualification report and machine-readable validation summary.

All paths are new relative to main. No existing Tower audit, runtime, ledger,
API/frontend, Agent Registry, workflow, requirements or baseline changed.
No source hook imports J01 into an existing component. No manual workflow
was dispatched; GitHub checks follow source branch/PR events automatically.
No merge, deployment, SSH/VPS operation, real model call or credential change.

## Validation actually performed

Python 3.11.17, Ruff 0.15.8, repository CI dependencies; no dependency file edited.

| Validation | Result and scope |
|---|---|
| Final focused run | **939 passed**, one deprecation warning: 109 J01 + 830 Governance Tower/cross-stack tests |
| Prior J01-only coverage run | 108 passed, **98%** combined statement/branch report (rounded); supplementary config outside repo, no baseline change |
| Ruff direct + regression gate | PASS, **0 new findings** |
| Broad local regression | 8,470 passed, **11 failed**, 21 skipped, 13 deselected, 2 xfailed; not a global PASS |
| Baseline publishers comparison | On unmodified main, **same 11 failed node IDs**, 64 passed; no candidate-only failure in the observed failure set |
| Full event hash formula | Independent stdlib JSON/SHA-256 calculation over the entire recorder envelope and two linked records |
| Diff scope | No change under .github, core, PAPER/PPL/FIN, risk/signal, observability, Tower or frontend |

The broad regression ran on an earlier M5 qualification snapshot with 99 J01
tests. Final focused tests cover the later verifier hard bound, stronger
corruption assertions and additional tests. Do not relabel the earlier broad
run a final-HEAD global PASS. Exact final-HEAD GitHub CI is still required.

Reproduce commands from the source root:

```bash
python -m pytest -q tests/sentinel_activity/ tests/governance_tower/ tests/cross_stack/
python scripts/ci/ruff_baseline_gate.py check
python -m pytest -q -m 'not performance and not slow' tests/
```

The existing .coveragerc includes historical modules but excludes J01 from its
report. The supplemental J01 coverage configuration was outside the repository;
no existing coverage target or gate was weakened. The last independent envelope
hash test was added after that coverage run and passes in the final focused run.

## Local regression failures: preserved, not bypassed

All 11 failing node IDs are retained in `J01_VALIDATION.json`, with the exact
comparison against a clean detached main worktree.

- One G2 test calls `shutil.chown(..., user="nobody")`; this execution
  environment raises `OSError: [Errno 22] Invalid argument`. Reproduced on main.
- Ten G1 fixture tests report `CLEANUP REFUSED: processes using ... are still
  running; directory KEPT for inspection`. The same tests fail on main.
  The underlying process-detection cause is not qualified here; neither the
  publisher script nor those tests were changed to hide the failures.

This comparison establishes reproducibility without J01 in this environment;
it does not certify the publishers or claim every environmental difference is
understood. The complete broad suite was not rerun on baseline; its failing
publisher files were rerun independently (75 tests, 64 passed/11 failed).

At the pre-M5 check, M2–M4 exposed no failed/pending checks. M1's four required
code gates succeeded, but the separate Coveralls upload failed after its
coverage corpus succeeded. No successful upload or all-checks-green verdict is
claimed. No rerun/permission/token change was attempted to make it green.

## Demonstration and negative evidence

The one-shot demo emits nine SIMULATED records: Sentinel fixture proposal,
operator fixture approval for publication only, secretary publication, A accepts,
B declines for synthetic budget, A starts and submits a fictitious artifact,
a distinct reviewer fixture passes it, a separate closer fixture completes it.
No actual agent execution or AIC reward is represented.

A separate process reopens the database and obtains the same count, head hash
and quest/participation projections. Retrying the last event adds no record.
The test harness terminates actual child processes with os._exit before commit
and after commit/before acknowledgment. Before commit: zero events; after commit:
one durable event and the original receipt on retry. No production crash hook
is shipped. These are process-crash tests, NOT power-loss/fsync hardware proof.

| Threat/invariant | Executed evidence |
|---|---|
| Duplicate/collision | Identical retry returns original; conflicting id rejected without sequence consumption |
| Concurrent assignment | Two child processes compete; exactly one claim commits |
| Malformed input | Duplicate JSON keys, floats, bool-as-int, invalid UTC, Unicode, enum/field and size errors rejected |
| Role/provenance spoof | Actor mismatch and all non-SIMULATED admission rejected |
| False completion | Acceptance/submission alone cannot complete; publication/review references must match |
| Self-review/collusion | Wrong actor/self-review rejected; distinct identities are not strong epistemic independence |
| Corruption | Hash/body/index/order/deletion/cache/schema changes rejected, including before idempotent retry |
| False integrity claim | Coherent full rewrite/valid prefix can remain structurally valid; authenticity/completeness remain unknown |
| Unavailable/full/busy | Simulated SQLITE_FULL rolls back; budget refusal and bounded lock error are visible |
| Secrets/injection | Known secret patterns rejected without echo; hostile instructions have no execution path |
| Isolation | AST boundary + fresh-process import audit; no network/SQLite/env/write effect at import |
| Recovery | SQLite snapshot backup, new-destination restore, altered manifest refusal, append after recovery |
| Unknown state | NO_DATA / UNAVAILABLE / CORRUPTED distinct; unknown time and cost remain null |

## Bounded local measurement

Sample: 100 synthetic observation events, same local environment:
median append 78.903 ms, maximum append 172.406 ms, full verified snapshot
167.582 ms, files after connections closed 208,896 bytes. No network call.
These are a small local sample, not a latency SLO or a 10,000-event capacity
qualification. Full verification on every append has increasing cost. Do not
optimize it or claim production throughput without a separate measured mandate.

## Residual limitations and next gate

- SIMULATED fixture bindings only; no real producer authentication or registrar.
- No independent anti-rollback head, global completeness, real human authority,
  A1 AVAILABLE state, economic contribution proof or power-loss qualification.
- Adjacent manifest/hash chain are consistency checks, not signatures or a blockchain.
- Trusted local lab parent/OS account assumed; adversarial parent replacement,
  same-account writers, NFS and OS disk-hard-quota enforcement unqualified.
- Known-pattern secret detection is incomplete; never ingest raw sensitive logs.
- No automated rotation, repair or migration; partial recovery files are retained.
- No independent reviewer has certified this implementation in this session.
- No UI, API integration, scheduler, worker, LLM, AIC or runtime deployment.

Next: independent source review at the exact M5 HEAD, required GitHub gates and
operator decision. Do not merge automatically. J02 is a separate mandate.
