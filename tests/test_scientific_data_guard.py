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
import json
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


# ── GENERATE mode (SCIENTIFIC_DATA_GUARD_GENERATE=1) ─────────────────────────
#
# CI-00B.2 (independent review): an earlier revision derived the generated
# set from `set(before) | set(after)` where hashes differ, which included
# REMOVED paths (present before, absent after -- after.get() returns None,
# differing from the before hash) into the generated baseline, then returned
# before normal deletion enforcement ran. Fixed: generate mode now shares the
# exact same changed/added/removed computation as normal mode, only ever
# writes changed+added into the baseline, and evaluates removed paths for
# failure exactly like normal mode -- it does not return early past that.


def _run_guard_generate(
    guard, monkeypatch, tmp_path, before: dict, after: dict, exitstatus: int = 0
):
    baseline_path = tmp_path / "scientific_data_guard_baseline.json"
    monkeypatch.setattr(guard, "_SCIENTIFIC_DATA_GUARD_BASELINE_PATH", baseline_path)
    monkeypatch.setattr(guard, "_snapshot_scientific_data", lambda: after)
    monkeypatch.setenv("SCIENTIFIC_DATA_GUARD_GENERATE", "1")

    session = _FakeSession(exitstatus=exitstatus)
    session.config._scientific_data_before = before
    guard.pytest_sessionfinish(session, exitstatus)

    written = None
    if baseline_path.exists():
        written = set(json.loads(baseline_path.read_text())["known_leaking_paths"])
    return session, written


def test_generate_known_modification_is_written_to_baseline(guard, monkeypatch, tmp_path):
    path = _p(guard, "cache/daily_analysis.db")
    session, written = _run_guard_generate(
        guard,
        monkeypatch,
        tmp_path,
        before={path: "hash-old"},
        after={path: "hash-new"},
    )
    assert written == {"cache/daily_analysis.db"}
    assert session.exitstatus == 0


def test_generate_new_addition_is_written_to_baseline(guard, monkeypatch, tmp_path):
    path = _p(guard, "databases/new_thing.json")
    session, written = _run_guard_generate(
        guard,
        monkeypatch,
        tmp_path,
        before={},
        after={path: "hash-new"},
    )
    assert written == {"databases/new_thing.json"}
    assert session.exitstatus == 0


def test_generate_with_deletion_fails_session(guard, monkeypatch, tmp_path):
    path = _p(guard, "databases/system_state.json")
    session, _written = _run_guard_generate(
        guard,
        monkeypatch,
        tmp_path,
        before={path: "hash-old"},
        after={},
    )
    assert session.exitstatus == 1


def test_generate_deletion_never_appears_in_generated_baseline(guard, monkeypatch, tmp_path):
    """The core CI-00B.2 regression: a removed path must never be written
    into the baseline. CI-00B.2 (independent review) tightened this
    further -- ANY deletion in the diff blocks writing the baseline file
    at all, even when a legitimate modification is present in the same
    session (no baseline file exists yet here, so "untouched" means it
    stays absent)."""
    kept = _p(guard, "cache/daily_analysis.db")
    deleted = _p(guard, "databases/system_state.json")
    baseline_path = tmp_path / "scientific_data_guard_baseline.json"
    session, written = _run_guard_generate(
        guard,
        monkeypatch,
        tmp_path,
        before={kept: "hash-old", deleted: "hash-old"},
        after={kept: "hash-new"},
    )
    assert written is None
    assert not baseline_path.exists()
    assert session.exitstatus == 1


def test_generate_mode_does_not_clear_existing_pytest_failure(guard, monkeypatch, tmp_path):
    path = _p(guard, "cache/daily_analysis.db")
    session, written = _run_guard_generate(
        guard,
        monkeypatch,
        tmp_path,
        before={path: "hash-old"},
        after={path: "hash-new"},
        exitstatus=1,
    )
    assert session.exitstatus == 1
    assert written == {"cache/daily_analysis.db"}


def test_generate_mode_does_not_clear_existing_pytest_failure_with_deletion(
    guard, monkeypatch, tmp_path
):
    """Belt-and-braces: exitstatus was already 1 for an unrelated reason AND
    a deletion also occurred -- must still be 1 (never accidentally reset
    to 0 by the deletion-handling branch either), and the baseline file
    must not be written (no file existed before, none exists after)."""
    path = _p(guard, "databases/system_state.json")
    baseline_path = tmp_path / "scientific_data_guard_baseline.json"
    session, written = _run_guard_generate(
        guard,
        monkeypatch,
        tmp_path,
        before={path: "hash-old"},
        after={},
        exitstatus=1,
    )
    assert session.exitstatus == 1
    assert written is None
    assert not baseline_path.exists()


def test_generate_zero_diff_clears_preexisting_baseline_to_empty(guard, monkeypatch, tmp_path):
    """CI-00B.2 (independent review): before == after must NOT short-circuit
    generate mode. A successful cleanup that brings the scientific-data
    diff to zero must be able to regenerate the baseline down to an empty
    set, rather than leaving stale historical exemptions frozen forever."""
    baseline_path = tmp_path / "scientific_data_guard_baseline.json"
    baseline_path.write_text(
        json.dumps({"known_leaking_paths": ["cache/some_old_stale_debt.db"]})
    )

    path = _p(guard, "cache/daily_analysis.db")
    session, written = _run_guard_generate(
        guard,
        monkeypatch,
        tmp_path,
        before={path: "same-hash"},
        after={path: "same-hash"},  # identical -> before == after
    )

    assert written == set()
    assert session.exitstatus == 0


def test_generate_with_deletion_leaves_existing_baseline_byte_for_byte_unchanged(
    guard, monkeypatch, tmp_path
):
    """CI-00B.2 (independent review): on a deletion, the previous baseline
    file must not be modified in ANY way -- not truncated, not rewritten,
    not even reformatted. Compares raw bytes before and after."""
    baseline_path = tmp_path / "scientific_data_guard_baseline.json"
    original_bytes = json.dumps(
        {"known_leaking_paths": ["cache/daily_analysis.db"]}, indent=2
    ).encode("utf-8")
    baseline_path.write_bytes(original_bytes)

    kept = _p(guard, "cache/daily_analysis.db")
    deleted = _p(guard, "databases/system_state.json")
    session, _written = _run_guard_generate(
        guard,
        monkeypatch,
        tmp_path,
        before={kept: "hash-old", deleted: "hash-old"},
        after={kept: "hash-old"},  # kept unchanged; deleted is gone
    )

    assert baseline_path.read_bytes() == original_bytes
    assert session.exitstatus == 1
