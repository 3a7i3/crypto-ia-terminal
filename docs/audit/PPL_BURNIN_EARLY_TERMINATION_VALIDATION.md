# PPL-BURNIN-EARLY-TERMINATION — validation source, 2026-10-10 UTC

Verdict: **READY_FOR_REVIEW**, limited to candidate source and synthetic proofs.
Production activation and scientific finalization: **BLOCKED**, no runtime gate
or fresh runtime proof exists in this mission. No certification is claimed.

## Provenance

Base: `main@8c0dc27fbe456834423e8543c8ff30d657ec2d86`, confirmed again by
`git ls-remote origin refs/heads/main` before publication. Historical runtime
`116634be0d3c015cce1cfa58be7da7255414fbfd` is its ancestor (244 commits,
256 changed paths). Scope/deltas and contracts are in the
[pre-implementation audit](../contracts/PPL_BURNIN_EARLY_TERMINATION.md).

Branch: `feat/ppl-burnin-early-termination`. Review the PR's exact head commit;
these file hashes bind the tested implementation independently of documentation.

| Tested file | SHA-256 |
|---|---|
| paper_trading/burn_in_admission.py | a83f2acc816b06bd51b8307fedc11ccb65ed1d2b528561b8e3d14af81102e989 |
| paper_trading/durable_event_store.py | f0254a754ec3164a8c074794aab5168907d9d1e6320e230e218bbc74a62edbe5 |
| paper_trading/mexc_simulator.py | 795e4191e3c5bad2d93bb54629f57f25f6ab5e17879651b60fa3d88e627f7d90 |
| tests/paper_trading/test_burn_in_early_termination.py | 90807a4c7e88136c4eab8b850cbf6909c6e66f67efc8f6336b4913c6da11c090 |

## Local results

Local environment: Linux, Python 3.12.14, pytest 9.1.1, ruff 0.15.8;
dependencies installed from requirements-ci.txt. CI targets Python 3.11:
local success is not proof of the GitHub CI result or production deployment.

- `python scripts/ci/ruff_baseline_gate.py check`: PASS, zero new findings;
  existing baseline unchanged (957 baseline / 945 current, 12 fixed).
- `python -m pytest -q tests/paper_trading/test_burn_in_early_termination.py`:
  **18 passed**, 0.52 s at final implementation.
- `python -m pytest -q -m 'not performance and not slow' tests/`:
  **6,975 passed, 19 skipped, 13 deselected, 2 xfailed, 2,138 warnings**,
  99.33 s, exit status 0.
- `python -m pytest -q tests/cross_stack/`: **96 passed**, 1 warning, 1.10 s.
- `git diff --check`: PASS.

The full suite includes the existing PPL authority/cutover/SHADOW/legacy bridge,
FIN replay and Research tests. No baseline changes, test removal or new xfail.
Performance/slow tests are excluded by the correctness command and have their
separate existing CI gate. Cross-stack here is the Python integration corpus;
no frontend modification or new browser visual certification is claimed.

Warnings/skips/xfails remain explicit. They include existing deprecated datetime
and Starlette/httpx usage, async mock coroutine warnings and public market refresh
failures in the broad corpus. They do not constitute observed production faults.

## Governance and review limits

GitHub #285/#286 and #286 comments inspected; latest guard comment
[#286 pause](https://github.com/3a7i3/crypto-ia-terminal/issues/286#issuecomment-6010579372)
maintains immutability. Historical exceptions are consumed and not reused.
Branch-protection API returned HTTP 403 `Resource not accessible by integration`;
current required protection settings could not be independently read. Do not
infer permission to merge from the absence of readable settings.

GitHub CI must be assessed at the exact PR head; local reports do not replace it.
PR remains draft, no auto-merge enabled, no deployment dispatched. Workflow
triggers inspected before push: VPS audit requires dispatch or main changes to
its request file; Sphinx publication is main-only/dispatch; testnet integration
is dispatch-only. This branch changes none of those triggers or request files.

No VPS access, Advisor restart, runtime source/config/epoch/capital change,
PB_MAX_POSITIONS change, PPL event rewrite/deletion, FIN activation, TESTNET/LIVE
activation or exchange order was performed. Synthetic history is written only
inside pytest temporary roots to represent pre-existing baseline facts.

## Review decision

Source can be reviewed with its explicit fixed DENY semantics. Reviewers must
accept that installation is the admission activation, while a receipt only
attests a bounded decision. Authentication and deployment provenance belong to
Gate O. Unknown runtime writers, storage guarantees, process quiescence and
financial/scientific closure remain unproved. The
[runbook and rollback](../runbooks/PPL_BURNIN_EARLY_TERMINATION.md) preserve these
limits; the future Research proposal is inactive and non-executable.
