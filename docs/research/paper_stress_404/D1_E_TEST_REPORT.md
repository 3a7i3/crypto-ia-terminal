# D1-E — source validation and test isolation

Mission #410, Draft #411; source-only, no runtime authority.
Pure verifier source: `58059ec41ca7fc0d11c0e5b1d996f26266015386`.
Test-isolation/synthetic-method composition: `a68a775ae335913154b87847a8c43d6e9c0da84d`.
The three Research modules retain the exact hashes in
[the independent review handoff](D1_D_D1_E_CHATGPT_HANDOFF.md).
Python local **3.12.14**, pytest **9.1.1**, Ruff **0.15.8**;
dependencies from `requirements-ci.txt` in a development venv. CI uses Python 3.11.

## Checks and captured results

| Check | Observation |
|---|---|
| D1-E synthetic tests | **109 passed**, 0.37 s |
| Research/no-feedback + Python cross-stack composition | **446 passed**, 400 warnings, 2.52 s (includes 96 cross-stack tests) |
| Isolated source check `python -I -B` | PASS; explicit module SHA256 pins; synthetic output exact; no production/runtime modules; open/socket operations denied during calls |
| Ruff baseline | PASS, 0 new violations, 945 current / 957 baseline |
| Compilation / `git diff --check` | PASS |
| Explicit D1-E module coverage report | **99%**, 218 statements, 3 missed, 60 branches, 1 partial branch; not a runtime-proof metric |
| First whole correctness corpus at `58059ec4` | **1 failed, 7,159 passed, 19 skipped, 13 deselected, 2 xfailed**, 2,139 warnings, exit 1, 249.65 s |
| Clean-worktree whole-corpus repeat at the same SHA | **1 failed, 7,159 passed, 19 skipped, 13 deselected, 2 xfailed**, 2,139 warnings, exit 1, 256.08 s |
| Targeted MarketScanner + D1-E, before isolation fix | 115 passed; isolated execution did not reproduce cross-test contamination |
| Parent D1-D MarketScanner control | 6 passed; D1-D whole corpus had already passed 7,050 tests |
| Ordered smoke → MarketScanner diagnostic | **1 failed, 21 passed**, 38.33 s, exact foreign-thread factory calls captured |
| Ordered smoke → MarketScanner → D1-E after fixture fix | **131 passed**, 1.84 s, no assertion relaxed |
| Whole correctness corpus after fixture fix at `a68a775a` | **7,160 passed, 19 skipped, 13 deselected, 2 xfailed**, 2,139 warnings, exit 0, 94.24 s |
| Real native producer/stage/fsync receipts | NOT_OBSERVED; no real bytes accessed |

The initial pytest-cov report used repository `.coveragerc`, whose report include
list excludes Research modules; it emitted “No data to report”. The collected
coverage was then reported with explicit `--include='*/stress_d1_durability.py'`,
giving the 99% result above. No coverage config or baseline was changed.

## Reproduced failure and bounded correction

Both full runs failed only
`tests/test_market_scanner_migration.py::test_market_scanner_preloads_markets_once_per_shared_exchange`:
`len(created)` was 2 rather than 1. The MarketScanner assertion and fake CCXT
factory were unchanged. A diagnostic profile enabled only for that test captured
constructor calls in **PerpUniverseService** threads with this source stack:

```
core/perp_universe_service.py::_run
  → _do_refresh
tools/perp_universe_builder.py::discover
  → _get_exchange → _build_exchange
tests/test_market_scanner_migration.py::fake_ccxt.mexc
  → _FakeExchange.__init__
```

The preceding smoke tests inject scanner/runtime fakes but still started real
local Universe refresh threads. Those threads survived `main()` and reached the
later test's process-global monkeypatch of `sys.modules['ccxt']`. The extra fake
exchange therefore did not establish a duplicate MarketScanner pool instance.
The direct ordered reproduction failed and the trace identified the caller;
this is stronger than labeling the failure “flaky” from a passing isolated rerun.

The fix adds four lines to `_isolate_smoke_writes` in
`tests/test_advisor_loop_smoke.py`: explanation and pytest-local
`monkeypatch.setenv('UNIVERSE_ENABLED', 'false')`. Those tests do not exercise
Universe discovery. Test bodies can still explicitly override the flag if a
future test needs it. No MarketScanner assertion, baseline, test selection,
runtime source, production configuration or active epoch is modified.
Dedicated Universe tests remain in the full regression corpus.

All full runs used the existing opt-in Python offline network guard. Existing
Universe/MEXC refresh failures are preserved in the first two logs; the guard
denies non-loopback Python DNS/connects, not arbitrary hostile native code.
No successful market/exchange operation or mutation is claimed. Fixture isolation
prevents this particular background activity rather than weakening the guard.

## Reproduction commands

With the development venv's bin directory on PATH:

```bash
python -m pytest -q tests/research_data/test_stress_d1_durability.py
python -m pytest -q tests/research_data/ tests/research_replay/ tests/research_diag/ tests/research_candidate/ tests/research_stress/ tests/cross_stack/
BINANCE_TESTNET=true MARKET_SCANNER_SYNTHETIC=true \
  PYTHONPATH="$PWD/tests/research_stress/offline_guard" \
  python -m pytest -q tests/test_advisor_loop_smoke.py tests/test_market_scanner_migration.py tests/research_data/test_stress_d1_durability.py
BINANCE_TESTNET=true MARKET_SCANNER_SYNTHETIC=true \
  PYTHONPATH="$PWD/tests/research_stress/offline_guard" \
  python -m pytest -q -m 'not performance and not slow' tests/
python -I -B tests/research_data/d1_isolated_source_check.py
python scripts/ci/ruff_baseline_gate.py check
python -m compileall -q research_data/stress_d1_durability.py tests/research_data/d1_isolated_source_check.py
git diff --check
```

The standalone isolation checker is explicitly synthetic-only. It loads verified
source bytes without the package initializer or checkout runtime imports, checks
the committed synthetic example, then denies file/socket events during calls.
It is not a custody verifier or authorized real-data execution procedure.

## CI and scientific disposition

At source `58059ec41ca7fc0d11c0e5b1d996f26266015386`, the four required GitHub gates
were observed SUCCESS: integrity, LINT REGRESSION GATE, TEST REGRESSION GATE,
CROSS-STACK COMPATIBILITY GATE. This does not erase the two local failures and
does not prove the subsequent fixture/documentation HEAD passed CI. Check the
exact final HEAD in #411 and its paginated checks/workflows. Pending and skipped
checks are not PASS. #409's final four required gates were also observed SUCCESS
at `d2a1cfa997d46c7d09ceffe93918df2ffeb9ca5b`; four ancillary jobs were still running.

Author review covered identities, transitions, physical byte joins, unknowns,
midnight partition races, worker/counter ordering, ignored persist bool, trust
limits and source passivity. External independent review is still required.
No new scientific certification or real per-packet persistence verdict is issued.

`ACTUAL_PERSISTENCE_PROOF=NOT_OBSERVED`
`D1_E_PER_PACKET_DURABILITY=NOT_PROVEN`
`D1_D_PRODUCER_COMPLETENESS=NOT_PROVEN`
`D1_NATIVE_EPOCH_BOUNDARY_BINDING=NOT_PROVEN`
`COUNTERFACTUAL_PERFORMANCE_ELIGIBILITY=NOT_PROVEN`
`PAPER_STRESS_RUNTIME_GO=DENIED`
`ACTIVE_BURN_IN_IMMUTABILITY_GUARD=ACTIVE`
