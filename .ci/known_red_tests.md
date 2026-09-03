# Known-red tests (CI-00B)

Tests marked `xfail` in the suite are tracked here so CI can distinguish
"known-red, tracked" from "new regression". A test must never be silently
skipped — every exception in the suite must appear in this file with a
mission id and a reason.

| Test | Location | Reason | Follow-up mission |
|---|---|---|---|
| `TestTier2GoldenSnapshot::test_backtest_matches_golden` | `tests/test_phase_a_replay_invariants.py` | `BacktestEngine.run()` force-closes every position exactly one bar after entry regardless of strategy exit signal, collapsing PnL to the synthetic candles' constant intrabar spread instead of the golden's multi-bar, all-winning trades. Classified `BACKTEST_ENGINE_DEFECT` by CI-00B investigation (not fixed — investigate-only per mission scope). Marked `xfail(strict=True)`: an unexpected PASS (e.g. the engine gets fixed incidentally by unrelated work) fails the suite instead of silently disappearing — the marker must be removed in the same PR that actually fixes it. See CI-00B remediation report §9. | `BT-00` |

Removing an entry from this table must be paired with removing the
matching `xfail` marker in the same PR (the test is expected to pass
again), never the other way around.

## Coverage: two separate, independent signals (CI-00B)

`TEST REGRESSION GATE` (test correctness) and `COVERAGE REGRESSION
BASELINE` (coverage level) are two independent CI jobs (`tests` and
`coverage-baseline` in `ci.yml`), each its own named GitHub check, each
`needs: []` of the other. They are never conflated: a coverage number is
not evidence of test correctness, and a test failure is not a coverage
regression.

`COVERAGE REGRESSION BASELINE`'s gate (`--cov-fail-under=…` on
`supervision/`, `quant_hedge_ai/agents/{market,execution,risk,quant}`)
never actually ran on `main` before CI-00B — it was blocked by
`needs: lint` (the structural defect Phase 2 of CI-00B fixes). Once
decoupled, actual coverage measured **≈4.09%**, reproduced twice in CI on
this PR (deterministic, not a one-off).

**`COVERAGE_TARGET = 60%` is the historical target and remains
UNRESOLVED, TRACKED DEBT** — this job does **not** claim 4% satisfies it.
`--cov-fail-under` is set to `4`: a regression floor, not a target. It
fails only if coverage drops *below* the established baseline (a genuine
new coverage regression); it does not, and must not be read to, certify
that 60% coverage exists. Raising the real number back toward 60% by
adding tests for `execution_engine.py`, `market_scanner.py`, the risk
gates, etc. is out of CI-00B scope (functional freeze, ADR-0007
passivity) — separate follow-up work.

## Known test-isolation debt: Scientific Data Guard baseline (CI-00B)

Running the complete `tests/` suite in one pytest session (added by
CI-00B Phase 8) touches `databases/`/`cache/` paths that pre-existing,
non-CI-00B-owned modules write without going through the DS-001
isolation env vars (`OBS_LOG_ROOT`, `REJECTION_STORE_DIR`, etc.):
`signal/evolution/evolution_memory.py`,
`quant_hedge_ai/ai_evolution/strategy_memory.py`, `dip/core/store.py`,
`infra/startup_cache.py`, `infra/monitoring/daily_analyzer.py`,
`system/state_machine.py`, `src/storage/run_repository.py`,
`src/telegram/sim_bot.py`, `core/bootstrap_integration.py`,
`supervision/healing_actions.py`, `visualization/api/scientific_api.py`,
`scripts/final_validation.py`, `pieuvre/tentacles/{resilience,performance}.py`.

This was never visible before CI-00B because the `tests` job never ran
the full suite in CI. Several of these modules are in signal/strategy
territory (`signal/evolution/`, `quant_hedge_ai/ai_evolution/`) that
CI-00B is expressly forbidden from modifying — this needs a dedicated
follow-up mission (test-isolation hardening, tentatively `TI-00`), not an
opportunistic CI-00B fix.

**The guard itself is untouched in behavior and stays fully intact and
blocking** — a normal pytest invocation, and this full-suite CI run
alike, still fail on any contamination of `databases/`/`cache/`. What
changed (CI-00B, master-review-directed): the guard now compares changed
paths against an explicit, versioned, auditable baseline
(`.ci/scientific_data_guard_baseline.json`, generated via
`SCIENTIFIC_DATA_GUARD_GENERATE=1 pytest -q tests/`, a visible diff in
this PR) instead of failing unconditionally on any change:

- A changed/added path **in** the baseline → printed as known debt,
  never fails the run.
- A changed/added path **NOT** in the baseline (a genuinely NEW
  contaminated path) → **fails the session**, exactly as before.
- `session.exitstatus` is otherwise left untouched by the guard — real
  pytest test failures/errors still fail the run through pytest's own
  ordinary exit code, with no bypass, no `|| true`, no separate
  JUnit-only acceptance layer.

Fixing the ~13 offending modules' path isolation so the baseline can
shrink to empty is separate follow-up work (`TI-00`), not CI-00B.

## Security permissions: tracked deployment-enforcement debt (CI-00B)

`tests/test_confidential_files_perms.py` exercises
`scripts/confidential_files_perms.py::set_secure_permissions()` directly
— it proves the *helper* enforces 0600 correctly when called, but does
**not** prove the real invariant CI-00 asked about (that runtime secrets
actually end up non-world-readable after a real deployment). Nothing in
`scripts/deploy_vps.sh` or any other deployment path currently calls
`set_secure_permissions()` — the helper exists but is **unused** in the
real enforcement boundary.

CI-00B does not claim this closes the security invariant. This is
**explicit, tracked debt for a separate security/deployment mission**:
wiring `set_secure_permissions()` (or equivalent) into the actual
deployment path (`scripts/deploy_vps.sh`, or wherever secrets are staged)
and testing *that* boundary — not the standalone helper. No VPS change
was made or is in scope here.
