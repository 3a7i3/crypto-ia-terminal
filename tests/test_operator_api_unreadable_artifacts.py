"""Operator API readers keep absent / refused / not-a-file apart, without leaks.

``Path.exists()`` raises ``PermissionError`` when a parent directory is not
traversable.  Before this contract that escaped as an unstructured HTTP 500;
now it is a structured 503 ``*_UNREADABLE`` whose message carries neither the
artifact path nor the exception text.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from observability.operator_api import app as api_app
from observability.operator_api.burn_in_status_reader import BurnInStatusSnapshotReader
from observability.operator_api.financial_reconciliation_reader import (
    FinancialReconciliationSnapshotReader,
)
from observability.operator_api.market_reader import MarketSnapshotReader
from observability.operator_api.path_probe import probe_artifact_path
from observability.operator_api.ppl_comparison_reader import PplComparisonSnapshotReader
from observability.operator_api.research_lab_reader import ResearchLabSnapshotReader

SECRET_DIR = "private-operator-dir"

# (reader class, app attribute, route, error-code prefix)
CASES = [
    (
        BurnInStatusSnapshotReader,
        "_burn_in_status_reader",
        "/api/operator/v1/burn-in",
        ("BURN_IN_STATUS_MISSING", "BURN_IN_STATUS_INVALID_PATH", "BURN_IN_STATUS_UNREADABLE"),
    ),
    (
        MarketSnapshotReader,
        "_market_reader",
        "/api/operator/v1/market",
        ("MARKET_SNAPSHOT_MISSING", "MARKET_SNAPSHOT_INVALID_PATH", "MARKET_SNAPSHOT_UNREADABLE"),
    ),
    (
        FinancialReconciliationSnapshotReader,
        "_financial_reconciliation_reader",
        "/api/operator/v1/financial-reconciliation",
        (
            "FINANCIAL_RECONCILIATION_SNAPSHOT_MISSING",
            "FINANCIAL_RECONCILIATION_INVALID_PATH",
            "FINANCIAL_RECONCILIATION_UNREADABLE",
        ),
    ),
    (
        PplComparisonSnapshotReader,
        "_ppl_comparison_reader",
        "/api/operator/v1/ppl-comparison",
        (
            "PPL_COMPARISON_SNAPSHOT_MISSING",
            "PPL_COMPARISON_INVALID_PATH",
            "PPL_COMPARISON_UNREADABLE",
        ),
    ),
    (
        ResearchLabSnapshotReader,
        "_research_lab_reader",
        "/api/operator/v1/research-lab",
        (
            "RESEARCH_LAB_SNAPSHOT_MISSING",
            "RESEARCH_LAB_INVALID_PATH",
            "RESEARCH_LAB_UNREADABLE",
        ),
    ),
]
IDS = [case[1].strip("_") for case in CASES]


def _deny_access(monkeypatch: pytest.MonkeyPatch, target: Path) -> None:
    original = Path.exists

    def exists(self, *args, **kwargs):  # noqa: ANN001
        if self == target:
            raise PermissionError(13, "Permission denied", str(target))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", exists)


def _get(monkeypatch, attr, reader, route):
    monkeypatch.setattr(api_app, attr, reader)
    with TestClient(api_app.app) as client:
        return client.get(route)


def test_probe_keeps_four_outcomes_distinct(tmp_path, monkeypatch):
    regular = tmp_path / "file.json"
    regular.write_text("{}", encoding="utf-8")
    assert probe_artifact_path(regular) is None
    assert probe_artifact_path(tmp_path / "absent.json") == "MISSING"
    assert probe_artifact_path(tmp_path) == "INVALID_PATH"
    link = tmp_path / "link.json"
    link.symlink_to(regular)
    assert probe_artifact_path(link) is None
    assert probe_artifact_path(link, reject_symlink=True) == "INVALID_PATH"
    _deny_access(monkeypatch, regular)
    assert probe_artifact_path(regular) == "UNREADABLE"


@pytest.mark.parametrize(("reader_cls", "attr", "route", "codes"), CASES, ids=IDS)
def test_permission_denied_is_structured_503_not_500(
    tmp_path, monkeypatch, reader_cls, attr, route, codes
):
    target = tmp_path / SECRET_DIR / "artifact.json"
    _deny_access(monkeypatch, target)

    result = reader_cls(path=target).read()
    assert result.ok is False
    assert result.error_code == codes[2]

    response = _get(monkeypatch, attr, reader_cls(path=target), route)
    assert response.status_code == 503
    body = response.text
    assert response.json()["error_code"] == codes[2]
    assert SECRET_DIR not in body
    assert str(tmp_path) not in body
    assert "Errno" not in body
    assert "Permission denied" not in body


@pytest.mark.parametrize(("reader_cls", "attr", "route", "codes"), CASES, ids=IDS)
def test_absent_and_not_a_file_stay_distinct_and_path_free(
    tmp_path, monkeypatch, reader_cls, attr, route, codes
):
    missing = tmp_path / SECRET_DIR / "absent.json"
    response = _get(monkeypatch, attr, reader_cls(path=missing), route)
    assert response.status_code == 503
    assert response.json()["error_code"] == codes[0]
    assert SECRET_DIR not in response.text
    assert str(tmp_path) not in response.text

    directory = tmp_path / SECRET_DIR
    directory.mkdir()
    response = _get(monkeypatch, attr, reader_cls(path=directory), route)
    assert response.status_code == 503
    assert response.json()["error_code"] == codes[1]
    assert str(tmp_path) not in response.text


@pytest.mark.parametrize(("reader_cls", "attr", "route", "codes"), CASES, ids=IDS)
def test_read_time_oserror_is_unreadable_without_exception_text(
    tmp_path, monkeypatch, reader_cls, attr, route, codes
):
    target = tmp_path / SECRET_DIR / "artifact.json"
    target.parent.mkdir()
    target.write_text("{}", encoding="utf-8")

    def refuse(self, *args, **kwargs):  # noqa: ANN001
        raise OSError(13, "Permission denied", str(target))

    monkeypatch.setattr(Path, "read_text", refuse)
    monkeypatch.setattr(Path, "open", refuse)
    monkeypatch.setattr("os.open", refuse)

    response = _get(monkeypatch, attr, reader_cls(path=target), route)
    assert response.status_code == 503
    assert response.json()["error_code"] == codes[2]
    assert SECRET_DIR not in response.text
    assert "Errno" not in response.text
