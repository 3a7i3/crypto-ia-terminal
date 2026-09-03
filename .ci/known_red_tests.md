# Known-red tests (CI-00B)

Tests marked `xfail(strict=False)` in the suite are tracked here so CI can
distinguish "known-red, tracked" from "new regression". A test must never
be silently skipped — every exception in the suite must appear in this
file with a mission id and a reason.

| Test | Location | Reason | Follow-up mission |
|---|---|---|---|
| `TestTier2GoldenSnapshot::test_backtest_matches_golden` | `tests/test_phase_a_replay_invariants.py` | `BacktestEngine.run()` force-closes every position exactly one bar after entry regardless of strategy exit signal, collapsing PnL to the synthetic candles' constant intrabar spread instead of the golden's multi-bar, all-winning trades. Classified `BACKTEST_ENGINE_DEFECT` by CI-00B investigation (not fixed — investigate-only per mission scope). See CI-00B remediation report §9. | `BT-00` |

Removing an entry from this table must be paired with removing the
matching `xfail` marker in the same PR (the test is expected to pass
again), never the other way around.
