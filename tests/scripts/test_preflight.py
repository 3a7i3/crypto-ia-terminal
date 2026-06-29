"""
tests/scripts/test_preflight.py — Tests de régression pour scripts/preflight.py.

Teste les fonctions de check individuellement via manipulation de l'état global.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import scripts.preflight as pf


def _reset_state() -> None:
    """Remet à zéro l'état global du module entre les tests."""
    pf._ok = True
    pf._warnings.clear()
    pf._errors.clear()


# ── check_python ──────────────────────────────────────────────────────────────


def test_check_python_passes_current_version() -> None:
    _reset_state()
    pf.check_python()
    assert pf._ok is True
    assert not pf._errors


def test_check_python_fails_old_version() -> None:
    _reset_state()
    with patch.object(sys, "version_info", (2, 7, 0)):
        pf.check_python()
    assert not pf._ok
    assert any("requis" in e for e in pf._errors)


# ── check_env ─────────────────────────────────────────────────────────────────


def test_check_env_passes_with_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_state()
    monkeypatch.setenv("MEXC_API_KEY", "key123")
    monkeypatch.setenv("MEXC_API_SECRET", "secret123")
    pf.check_env()
    assert pf._ok is True
    assert not pf._errors


def test_check_env_fails_missing_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_state()
    monkeypatch.delenv("MEXC_API_KEY", raising=False)
    monkeypatch.delenv("MEXC_API_SECRET", raising=False)
    pf.check_env()
    assert not pf._ok
    assert any("manquantes" in e for e in pf._errors)


# ── check_disk ────────────────────────────────────────────────────────────────


def test_check_disk_passes_enough_space() -> None:
    _reset_state()
    import shutil

    usage = shutil.disk_usage(pf.ROOT)
    if usage.free / 1024 / 1024 < pf.MIN_DISK_MB:
        pytest.skip("Disque réellement insuffisant — skip")
    pf.check_disk()
    assert pf._ok is True


def test_check_disk_fails_low_space() -> None:
    _reset_state()

    # Simuler un usage retournant 0 bytes libres
    class _FakeDiskUsage:
        free = 0
        total = 1_000_000_000
        used = 1_000_000_000

    with patch("shutil.disk_usage", return_value=_FakeDiskUsage()):
        pf.check_disk()
    assert not pf._ok
    assert any("insuffisant" in e for e in pf._errors)


# ── check_permissions ─────────────────────────────────────────────────────────


def test_check_permissions_creates_missing_dirs(tmp_path: Path) -> None:
    _reset_state()
    fake_root = tmp_path / "project"
    fake_root.mkdir()
    logs = fake_root / "logs"
    databases = fake_root / "databases"
    # Ni logs/ ni databases/ n'existent encore

    with patch.object(pf, "ROOT", fake_root):
        pf.check_permissions()

    assert logs.exists()
    assert databases.exists()
    assert pf._ok is True


# ── check_stale_lock ─────────────────────────────────────────────────────────


def test_stale_lock_absent(tmp_path: Path) -> None:
    _reset_state()
    lock = tmp_path / "logs" / "advisor.lock"
    with patch.object(pf, "ROOT", tmp_path):
        pf.check_stale_lock()
    assert pf._ok is True
    assert not pf._errors


def test_stale_lock_dead_pid(tmp_path: Path) -> None:
    _reset_state()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    lock = logs_dir / "advisor.lock"
    lock.write_text("999999999\n")  # PID inexistant

    with patch.object(pf, "ROOT", tmp_path):
        pf.check_stale_lock()

    assert pf._ok is True  # lock périmé → warning seulement
    assert any("périmé" in w for w in pf._warnings)


def test_stale_lock_live_pid(tmp_path: Path) -> None:
    _reset_state()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    lock = logs_dir / "advisor.lock"
    live_pid = os.getpid()
    lock.write_text(f"{live_pid}\n")

    with patch.object(pf, "ROOT", tmp_path):
        pf.check_stale_lock()

    assert not pf._ok  # PID vivant → erreur
    assert any(str(live_pid) in e for e in pf._errors)


# ── check_data_quality ───────────────────────────────────────────────────────


def test_data_quality_absent_file(tmp_path: Path) -> None:
    _reset_state()
    with patch.object(pf, "ROOT", tmp_path):
        pf.check_data_quality()
    assert pf._ok is True  # pas de fichier = démarrage propre


def test_data_quality_clean_json(tmp_path: Path) -> None:
    _reset_state()
    import json as _json

    db = tmp_path / "databases"
    db.mkdir()
    jsonl = db / "paper_trades.jsonl"
    jsonl.write_text(_json.dumps({"event": "OPEN", "trade_id": "T1"}) + "\n")

    with patch.object(pf, "ROOT", tmp_path):
        pf.check_data_quality()
    assert pf._ok is True


def test_data_quality_corrupt_json(tmp_path: Path) -> None:
    _reset_state()
    db = tmp_path / "databases"
    db.mkdir()
    jsonl = db / "paper_trades.jsonl"
    jsonl.write_text("{not valid\n")

    with patch.object(pf, "ROOT", tmp_path):
        pf.check_data_quality()
    assert not pf._ok


# ── main ─────────────────────────────────────────────────────────────────────


def test_main_go(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEXC_API_KEY", "k")
    monkeypatch.setenv("MEXC_API_SECRET", "s")
    with patch.object(pf, "ROOT", tmp_path):
        result = pf.main()
    assert result == 0


def test_main_abort_missing_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("MEXC_API_KEY", raising=False)
    monkeypatch.delenv("MEXC_API_SECRET", raising=False)
    with patch.object(pf, "ROOT", tmp_path):
        result = pf.main()
    assert result == 1
