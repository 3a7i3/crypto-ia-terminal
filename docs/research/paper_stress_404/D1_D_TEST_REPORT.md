# D1-D V2 — source validation, 2026-10-12 UTC

Repository: `3a7i3/crypto-ia-terminal`; mission #408; Draft #409.
Initial remote HEAD `8f9ddc317821edb51f8685bbb802c516633158e4` and
`main@2015a88f10c31e3379b569f864696d62c282b0f0` were verified from GitHub.
The initial #409 workflow inventory was paginated through REST: 21 workflows,
17 success and 4 in progress, no final all-CI PASS claim. #407 remained Draft
at `9e4bed4393caadc8f328f698c806f82fd91271e7`; no source dependency on it.

## Reproducible local evidence

Code under test: `349eebe5` (native attempt plan, boundary validator, 37 new tests).
Python **3.12.14**, pytest **9.1.1**, Ruff **0.15.8**, dependencies installed
from `requirements-ci.txt` in a separate development venv. GitHub CI uses Python
3.11; local Python-version difference is explicit, not waived by local PASS.

| Check | Observed result |
|---|---|
| V1 + V2 targeted accounting tests | **56 passed** (19 existing + 37 new) |
| Ruff on new source and tests | PASS |
| Repository Ruff baseline gate | PASS, 0 new violations (945 current / 957 baseline) |
| Whole correctness corpus, dedicated worktree | **7,050 passed, 19 skipped, 13 deselected, 2 xfailed**, 2,139 warnings, exit 0, 251.23 s |
| Python cross-stack corpus | **96 passed**, 1 warning, exit 0 |
| Python compilation / `git diff --check` | PASS |
| Historical/real producer roster | NOT_OBSERVED, no new dataset accessed |
| Independent external review | PENDING; author review is not independent certification |

Commands, with `<venv>/bin` on PATH:

```bash
python -m pytest -q tests/research_data/test_stress_d1_producer_denominator.py tests/research_data/test_stress_d1_producer_attempts.py
python scripts/ci/ruff_baseline_gate.py check
BINANCE_TESTNET=true MARKET_SCANNER_SYNTHETIC=true \
  PYTHONPATH="$PWD/tests/research_stress/offline_guard" \
  python -m pytest -q -m 'not performance and not slow' tests/
python -m pytest -q tests/cross_stack/
python -m compileall -q research_data/stress_d1_evidence_contract.py research_data/stress_d1_producer_attempts.py
git diff --check
```

The existing Python audit-hook network guard was enabled for the full corpus;
it denies non-loopback DNS/connect events in Python, including Python children.
It is not an OS sandbox for hostile/native code. The corpus printed existing
Universe refresh failures referring to a MEXC GET; this is not evidence of
successful market access, nor a claim of no attempted network operation.
No exchange mutation, production read/export, VPS access or current process
attestation was performed. Development dependency downloads and GitHub source
access are separate from production and market access.

The first baseline invocation could not find `ruff` on inherited PATH; it was
rerun with the venv's bin directory on PATH and passed. The baseline was not
edited. A subsequent documentation commit does not change tested Python bytes;
the final PR SHA and CI must nevertheless be checked independently on GitHub.

## Author review findings addressed

- Preserved V1 unchanged; a separate V2 removes its cycle-symbol uniqueness
  assumption using explicit native plans, not IDs inferred from captures.
- Empty selected plans remain unresolved; observed extra attempts and duplicates
  abort. Late terminal receipts are retained through capture cutoff.
- Packet IDs cannot alias across attempts; hash pins and matching declarations
  explicitly do not certify independent acquisition or epoch binding.
- No production consumer, service, strategy, configuration or active epoch file
  is changed. All code remains Research-owned and source-only.

`D1_D_PRODUCER_COMPLETENESS=NOT_PROVEN`
`COUNTERFACTUAL_PERFORMANCE_ELIGIBILITY=NOT_PROVEN`
`PAPER_STRESS_RUNTIME_GO=DENIED`
`ACTIVE_BURN_IN_IMMUTABILITY_GUARD=ACTIVE`
