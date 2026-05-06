# Tracker System Handoff For Claude

## Current validation status

- `validate_vault_dashboard.py` passes end to end.
- `python -m unittest tests.test_tracker_dashboard tests.test_tracker_system_builder` passes.
- `c:/Users/WINDOWS/crypto_ai_terminal/.venv/Scripts/python.exe -m pytest tests -q` passes with `1003 passed, 18 skipped` after warning cleanup and visualization import-side-effect cleanup.
- `c:/Users/WINDOWS/crypto_ai_terminal/.venv/Scripts/python.exe -m pytest tests/test_lm_studio.py -q` passes with `14 passed` after fixing LM Studio loaded-model auto-detection.
- Scheduler helper validation is green: `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test_tracker_scheduler_helper.ps1` passes.
- Manual benchmark runner is currently healthy: `c:/Users/WINDOWS/crypto_ai_terminal/.venv/Scripts/python.exe scripts/performance_benchmarks.py` completed successfully in this environment.

## Commit focus: keep vs ignore

Keep before commit:

- scheduler helper improvements in `tracker_scheduler.ps1`, `launch_tracker_scheduler.ps1`, `scripts/test_tracker_scheduler_helper.ps1`, `.vscode/tasks.json`, `QUICKSTART.md`, and `TRACKER_SCHEDULER_WINDOWS_README.md`
- LM Studio test-hygiene fix in `lm_studio/client.py`
- test migration and validator-script moves already staged in `tests/`, `scripts/`, and supporting docs
- warning cleanup in `tests/test_full_integration.py`

Do not commit unless intentionally desired:

- generated runtime/cache artifacts under `cache/startup/*`
- evolving strategy memory data under `databases/ai_evolution/strategy_memory.json`
- generated checkpoint contents under `checkpoints/pop_*.json`

## Professional delegated plan for Claude

Claude should take only bounded, reviewable tasks with a clear deliverable. Priority order:

### 1. Tracker schema consolidation

Goal:

- make structured tracker events and legacy tracker readers interoperate without silent field drift

Deliverables:

- one canonical event schema note for `entry` and `exit`
- compatibility handling in either writers or readers
- focused regression tests for both paths

Acceptance:

- one round-trip test proves structured open/close events are consumed by legacy tracker readers without data loss

### 2. Duplicate tracker surface reduction

Goal:

- reduce maintenance drift across duplicate tracker, backtester, and engine layers

Deliverables:

- short ownership matrix naming authoritative modules versus compatibility wrappers
- small refactor or wrapper alignment patch where duplication is currently causing ambiguity

Acceptance:

- ownership is explicit in docs and backed by a smoke test on each compatibility seam

### 3. Test taxonomy hardening

Goal:

- finish separating collected pytest coverage from manual validators and operator scripts

Deliverables:

- classify remaining root-level `test_*.py` files
- move pytest-suitable tests under `tests/`
- rename manual runners under `scripts/` so they stop looking like collected tests
- update one short test policy note

Acceptance:

- `pytest tests -q` stays green and no new manual script is implicitly collected

### 4. CI and workflow hygiene

Goal:

- remove avoidable CI/editor noise without changing runtime behavior

Deliverables:

- verify `.github/workflows/testnet-integration.yml` secret-handling shape
- either eliminate current validator warnings or document why they are benign

Acceptance:

- GitHub workflow diagnostics are either clean or intentionally documented

### 5. Operator tooling polish

Goal:

- keep Windows tracker operations scriptable and predictable for non-developer operators

Deliverables:

- optional JSON tasks in VS Code for any remaining helper actions
- one compact operator runbook with start, once, status, stop, clean, logs, and JSON examples

Acceptance:

- an operator can run the full scheduler lifecycle from VS Code tasks or PowerShell without code edits

## Claude working rules

- work on one bounded slice at a time and validate it locally before moving on
- do not change trading behavior and risk defaults without adding a focused regression test
- do not commit generated cache, checkpoint, or memory data unless the task explicitly targets fixture refresh
- prefer wrappers and documentation over broad refactors when two live implementations already exist

## Highest-priority work

### 1. Unify event schema between structured and legacy tracker layers

Validated mismatch:

- `tracker_system/core/trade_logger.py` currently emits modern `entry` events with keys like `side` and `size`.
- `tracker_system/trade_tracker.py` legacy sync expects fields like `direction`, `size_usd`, `stop_loss`, `take_profit`, `signal_type`, `atr_pct`, and `paper`.
- `tracker_system/core/trade_logger.py` currently emits modern `exit` events with keys like `side`, `size`, and `duration_min`.
- `tracker_system/tracker.py` and `tracker_system/trade_tracker.py` legacy consumers expect or rely on fields like `direction`, `signal_type`, `size_usd`, `duration_minutes`, and `win`.

Concrete evidence gathered in this environment:

- `log_entry(...)` produced only: `confidence, entry_price, logged_at, regime, side, size, symbol, timestamp, type`.
- `log_exit(...)` produced only: `confidence, duration_min, entry_price, exit_price, exit_reason, id, logged_at, mae, mfe, pnl_pct, pnl_usd, price_path, regime, side, size, symbol, timestamp, type`.

Expected deliverable:

- Either make the structured logger emit backward-compatible aliases, or make the legacy readers accept both schemas.
- Add focused regression tests that exercise both `entry` and `exit` compatibility.

### 2. Add one round-trip integration test across the split tracker stack

Need a single test that proves this flow works from one log format:

- structured `core.trade_tracker.open_position` or `core.trade_logger.log_entry`
- structured close path via `core.trade_tracker.close_position` or `core.trade_logger.log_exit`
- legacy readers `tracker_system.trade_tracker.sync_from_log`, `tracker_system.tracker.load_exits`, `tracker_system.tracker.create_trade_note`, and `tracker_system.tracker.update_dashboard`

This should fail today unless schema compatibility is fixed.

### 3. Reduce drift between duplicate tracker implementations

There are parallel implementations for the same concerns:

- `tracker_system/trade_tracker.py` and `tracker_system/core/trade_tracker.py`
- `tracker_system/auto_backtester.py` and `tracker_system/backtesting/auto_backtester.py`
- `tracker_system/exit_engine/*` and `tracker_system/engine/*`

Claude should pick one of these paths:

- define one layer as authoritative and turn the other into thin compatibility wrappers
- or document strict ownership boundaries and add smoke tests that keep both surfaces aligned

Without that, behavior will keep diverging silently.

## Secondary work

### 4. Restore runnable pytest validation in the repo environment

Current blocker:

- `python -m pytest ...` fails because `pytest` is not installed in `.venv`.

Claude should either:

- add or update the dev dependency declaration for pytest
- or document the intended test bootstrap command if pytest is intentionally external

### 5. Add a compatibility matrix note

Useful small doc to add near `tracker_system/`:

- which modules are legacy
- which modules are the new structured layer
- which event schema is canonical
- which fields are mandatory in `entry` and `exit` JSONL rows

That will make future follow-up changes much safer.

## Additional repo work for Claude

### 6. Migrate root-level validator scripts into `tests/`

Fresh repo scan found many root-level files named `test_*.py` that still behave like manual scripts rather than stable `pytest` tests.

Examples from the current workspace root:

- `test_boot_system.py`
- `test_fullsuite.py`
- `test_imports_all_modules.py`
- `test_integration_multimodule.py`
- `test_integration_workflow.py`
- `test_performance_benchmarks.py`
- `test_streamlit_dashboard.py`
- `test_visualize_strategy_ecosystem.py`

Expected deliverable:

- classify each root-level `test_*.py` as one of: real pytest test, manual validation script, benchmark, or demo
- move pytest-suitable coverage under `tests/`
- rename manual-only scripts so they no longer look like collected tests
- add markers such as `integration` or `e2e` where appropriate

### 7. Separate manual validation from collected tests

The repo currently mixes two patterns:

- collected tests under `tests/`
- script-style validators in the workspace root and under `scripts/`

Claude should establish one clear policy:

- `tests/` for collected pytest coverage
- `scripts/` or `tools/` for one-shot validators and benchmarks

This should include a small doc note in `TESTS_AUTOMATION.md` or similar.

### 8. Clean the GitHub Actions warning on testnet secrets

Current VS Code diagnostics still flag `.github/workflows/testnet-integration.yml` for:

- `secrets.BINANCE_API_KEY`
- `secrets.BINANCE_API_SECRET`

Even if this is partly a schema-validation false positive, Claude should verify the workflow shape and choose one of these outcomes:

- keep the workflow as-is and document the warning as benign
- or restructure secret handling so the YAML validator stops flagging it

### 9. Extend the optimization-stack pytest migration pattern

A new pytest module now exists for the optimization stack under `tests/` while the root script remains useful for manual execution.

Claude can reuse that migration pattern for other script-style validators:

- extract deterministic setup into fixtures
- keep optional manual runner behavior if it is still useful
- make CI collect the stable slice under `tests/`