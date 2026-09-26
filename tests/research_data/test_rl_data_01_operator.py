"""RL-DATA-01 isolated tests for the clean-Git operator boundary."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from research_data.operator import (
    OperatorError,
    load_source_statuses,
    resolve_clean_repo_head,
)


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _clean_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "RL-DATA Test")
    _git(repo, "config", "user.email", "rl-data@example.invalid")
    (repo / "tracked.txt").write_text("baseline\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "baseline")
    return repo, _git(repo, "rev-parse", "HEAD")


def _status_document() -> dict:
    return {
        "dip": {
            "status": "NOT_AVAILABLE",
            "reason": "NOT_STARTED",
            "evidence": ["runtime_provenance_snapshot:NOT_STARTED"],
        },
        "regret": {
            "status": "UNRESOLVED_PROVENANCE",
            "reason": "no explicit F00 authority binding",
        },
        "rejection_store": {
            "status": "UNBOUND",
            "reason": "no explicit F00 experiment binding",
        },
        "admission_ledger": {
            "status": "UNBOUND",
            "reason": "no packet/trace/epoch identity",
        },
    }


def test_resolve_clean_repo_head_returns_exact_git_commit(tmp_path):
    repo, expected = _clean_repo(tmp_path)

    assert resolve_clean_repo_head(repo) == expected


def test_resolve_clean_repo_head_rejects_dirty_tracked_file(tmp_path):
    repo, _ = _clean_repo(tmp_path)
    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")

    with pytest.raises(OperatorError, match="worktree is not clean"):
        resolve_clean_repo_head(repo)


def test_resolve_clean_repo_head_rejects_untracked_file(tmp_path):
    repo, _ = _clean_repo(tmp_path)
    (repo / "untracked.txt").write_text("evidence\n", encoding="utf-8")

    with pytest.raises(OperatorError, match="worktree is not clean"):
        resolve_clean_repo_head(repo)


def test_resolve_clean_repo_head_requires_git_top_level(tmp_path):
    repo, _ = _clean_repo(tmp_path)
    nested = repo / "nested"
    nested.mkdir()

    with pytest.raises(OperatorError, match="Git top-level"):
        resolve_clean_repo_head(nested)


def test_load_source_statuses_preserves_explicit_states(tmp_path):
    path = tmp_path / "statuses.json"
    path.write_text(json.dumps(_status_document()), encoding="utf-8")

    statuses = load_source_statuses(path)

    assert statuses["dip"].status == "NOT_AVAILABLE"
    assert statuses["dip"].reason == "NOT_STARTED"
    assert statuses["regret"].status == "UNRESOLVED_PROVENANCE"
    assert statuses["rejection_store"].status == "UNBOUND"
    assert statuses["admission_ledger"].status == "UNBOUND"


def test_load_source_statuses_rejects_missing_required_source(tmp_path):
    document = _status_document()
    document.pop("dip")
    path = tmp_path / "statuses.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(OperatorError, match="keys mismatch"):
        load_source_statuses(path)


def test_load_source_statuses_rejects_duplicate_json_key(tmp_path):
    path = tmp_path / "statuses.json"
    path.write_text(
        '{"dip":{"status":"NOT_AVAILABLE","reason":"NOT_STARTED"},'
        '"dip":{"status":"NOT_AVAILABLE","reason":"NOT_STARTED"},'
        '"regret":{"status":"UNRESOLVED_PROVENANCE","reason":"x"},'
        '"rejection_store":{"status":"UNBOUND","reason":"x"},'
        '"admission_ledger":{"status":"UNBOUND","reason":"x"}}',
        encoding="utf-8",
    )

    with pytest.raises(OperatorError, match="duplicate JSON key"):
        load_source_statuses(path)


def test_repository_f00_status_contract_is_loadable():
    repo_root = Path(__file__).resolve().parents[2]
    path = repo_root / "docs" / "contracts" / "RL_DATA_01_F00_SOURCE_STATUSES.json"

    statuses = load_source_statuses(path)

    assert statuses["dip"].status == "NOT_AVAILABLE"
    assert statuses["dip"].reason == "NOT_STARTED"
    assert statuses["regret"].status == "UNRESOLVED_PROVENANCE"
    assert statuses["rejection_store"].status == "UNBOUND"
    assert statuses["admission_ledger"].status == "UNBOUND"
