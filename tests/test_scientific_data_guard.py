"""tests/test_scientific_data_guard.py — CI-00B (master review): deterministic
unit tests for conftest.py's Scientific Data Guard (pytest_sessionfinish).

The guard is a pytest hook, not a regular importable module, so it is loaded
here directly from the root conftest.py file via importlib (a fresh module
object per import — this does not re-register it as a pytest plugin, it
only gives us the plain functions to call and assert on in isolation).

Covers exactly the invariant required by CI-00B master review:
  - a MODIFIED/ADDED path already in the baseline -> tolerated, exitstatus
    untouched (PASS);
  - a MODIFIED/ADDED path NOT in the baseline -> FAIL;
  - ANY removed scientific-data path, baselined or not -> FAIL (deletions
    are never baseline-tolerated, by design);
  - an existing pytest failure (exitstatus already 1 for unrelated reasons)
    is never reset to 0 by the guard, regardless of guard state.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_CONFTEST_PATH = Path(__file__).resolve().parents[1] / "conftest.py"


def _load_guard_module():
    spec = importlib.util.spec_from_file_location(
        "ci00b_scientific_data_guard_under_test", _CONFTEST_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def guard(monkeypatch):
    """A freshly loaded guard module with the real baseline file ignored.

    Tests supply their own `before`/`after` snapshots and their own
    baseline set, independent of whatever .ci/scientific_data_guard_baseline.json
    currently contains, so this suite stays deterministic as that file
    evolves.
    """
    module = _load_guard_module()
    return module


class _FakeConfig:
    pass


class _FakeSession:
    def __init__(self, exitstatus: int = 0):
        self.config = _FakeConfig()
        self.exitstatus = exitstatus


def _run_guard(guard, monkeypatch, before: dict, after: dict, baseline: set[str], exitstatus: int = 0):
    session = _FakeSession(exitstatus=exitstatus)
    session.config._scientific_data_before = before
    monkeypatch.setattr(guard, "_snapshot_scientific_data", lambda: after)
    monkeypatch.setattr(guard, "_load_scientific_data_guard_baseline", lambda: baseline)
    monkeypatch.delenv("SCIENTIFIC_DATA_GUARD_GENERATE", raising=False)
    guard.pytest_sessionfinish(session, exitstatus)
    return session


def _p(guard, rel: str) -> str:
    return str(guard._REPO_ROOT / rel)


def test_known_baselined_modification_passes(guard, monkeypatch):
    """A modified/added path already in the baseline must not fail the run."""
    path = _p(guard, "cache/daily_analysis.db")
    session = _run_guard(
        guard,
        monkeypatch,
        before={},
        after={path: "hash-after"},
        baseline={"cache/daily_analysis.db"},
        exitstatus=0,
    )
    assert session.exitstatus == 0


def test_unknown_new_path_fails(guard, monkeypatch):
    """A modified/added path absent from the baseline must fail the run."""
    path = _p(guard, "cache/totally_new_leak.db")
    session = _run_guard(
        guard,
        monkeypatch,
        before={},
        after={path: "hash-after"},
        baseline=set(),
        exitstatus=0,
    )
    assert session.exitstatus == 1


def test_removed_path_fails_even_if_baselined(guard, monkeypatch):
    """A removed scientific-data path must ALWAYS fail, even if its path
    string appears in the baseline (the baseline only ever covers
    modifications/additions, never deletions — no governance mechanism for
    tolerating deletions exists)."""
    path = _p(guard, "databases/system_state.json")
    session = _run_guard(
        guard,
        monkeypatch,
        before={path: "hash-before"},
        after={},
        baseline={"databases/system_state.json"},
        exitstatus=0,
    )
    assert session.exitstatus == 1


def test_removed_path_fails_when_not_baselined(guard, monkeypatch):
    path = _p(guard, "cache/some_untracked_thing.db")
    session = _run_guard(
        guard,
        monkeypatch,
        before={path: "hash-before"},
        after={},
        baseline=set(),
        exitstatus=0,
    )
    assert session.exitstatus == 1


def test_existing_pytest_failure_is_never_cleared(guard, monkeypatch):
    """A real, pre-existing test failure/error (exitstatus already 1) must
    remain 1 regardless of guard state -- known debt only, no data change
    at all here."""
    session = _run_guard(
        guard,
        monkeypatch,
        before={},
        after={},
        baseline=set(),
        exitstatus=1,
    )
    assert session.exitstatus == 1


def test_existing_pytest_failure_survives_known_baselined_debt(guard, monkeypatch):
    """A real test failure combined with ONLY known, baselined debt must
    still report failure (the guard must never downgrade exitstatus)."""
    path = _p(guard, "cache/daily_analysis.db")
    session = _run_guard(
        guard,
        monkeypatch,
        before={},
        after={path: "hash-after"},
        baseline={"cache/daily_analysis.db"},
        exitstatus=1,
    )
    assert session.exitstatus == 1
