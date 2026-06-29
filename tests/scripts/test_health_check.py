"""
tests/scripts/test_health_check.py — Tests de régression pour scripts/health_check.py.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import scripts.health_check as hc

# ── _read_pid ─────────────────────────────────────────────────────────────────


def test_read_pid_absent(tmp_path: Path) -> None:
    lock = tmp_path / "advisor.lock"
    with patch.object(hc, "LOCK_FILE", lock):
        assert hc._read_pid() is None


def test_read_pid_valid(tmp_path: Path) -> None:
    lock = tmp_path / "advisor.lock"
    lock.write_text("12345\n")
    with patch.object(hc, "LOCK_FILE", lock):
        assert hc._read_pid() == 12345


def test_read_pid_invalid_content(tmp_path: Path) -> None:
    lock = tmp_path / "advisor.lock"
    lock.write_text("not_a_pid\n")
    with patch.object(hc, "LOCK_FILE", lock):
        assert hc._read_pid() is None


def test_read_pid_current_process(tmp_path: Path) -> None:
    lock = tmp_path / "advisor.lock"
    lock.write_text(f"{os.getpid()}\n")
    with patch.object(hc, "LOCK_FILE", lock):
        assert hc._read_pid() == os.getpid()


# ── _check_log_activity ───────────────────────────────────────────────────────


def test_log_activity_absent(tmp_path: Path) -> None:
    with patch.object(hc, "LOG_FILE", tmp_path / "nonexistent.log"):
        result = hc._check_log_activity()
    assert result["exists"] is False
    assert result["lag_s"] is None


def test_log_activity_recent(tmp_path: Path) -> None:
    log = tmp_path / "advisor.log"
    log.write_text("2026-06-29 10:00:00 [INFO] Cycle OK\n")
    with patch.object(hc, "LOG_FILE", log):
        result = hc._check_log_activity()
    assert result["exists"] is True
    assert result["lag_s"] is not None
    assert result["lag_s"] < 60  # fichier venant d'être créé
    assert "Cycle OK" in result["last_line"]


def test_log_activity_extracts_last_line(tmp_path: Path) -> None:
    log = tmp_path / "advisor.log"
    log.write_text("line1\nline2\nline3 final\n")
    with patch.object(hc, "LOG_FILE", log):
        result = hc._check_log_activity()
    assert "final" in result["last_line"]


# ── _fd_inheritance_risk ─────────────────────────────────────────────────────


def test_fd_inheritance_no_children() -> None:
    proc_info = {"children": 0, "fd_count": 10}
    warnings = hc._fd_inheritance_risk(proc_info)
    assert warnings == []


def test_fd_inheritance_children_detected() -> None:
    proc_info = {"children": 2, "children_pids": [100, 200], "fd_count": 10}
    warnings = hc._fd_inheritance_risk(proc_info)
    assert len(warnings) == 1
    assert "child" in warnings[0].lower()


def test_fd_inheritance_high_fd_count() -> None:
    proc_info = {"children": 0, "fd_count": 150}
    warnings = hc._fd_inheritance_risk(proc_info)
    assert any("FD" in w for w in warnings)


def test_fd_inheritance_both_triggers() -> None:
    proc_info = {"children": 1, "children_pids": [42], "fd_count": 200}
    warnings = hc._fd_inheritance_risk(proc_info)
    assert len(warnings) == 2


# ── main — process absent ─────────────────────────────────────────────────────


def test_main_no_lock_file(tmp_path: Path) -> None:
    with (
        patch.object(hc, "LOCK_FILE", tmp_path / "no.lock"),
        patch.object(hc, "LOG_FILE", tmp_path / "no.log"),
    ):
        result = hc.main()
    assert result == 2  # CRITICAL — process non trouvé


def test_main_dead_pid(tmp_path: Path) -> None:
    lock = tmp_path / "advisor.lock"
    lock.write_text("999999999\n")  # PID inexistant
    with (
        patch.object(hc, "LOCK_FILE", lock),
        patch.object(hc, "LOG_FILE", tmp_path / "no.log"),
    ):
        result = hc.main()
    assert result == 2


def test_main_json_output(tmp_path: Path) -> None:
    lock = tmp_path / "advisor.lock"
    lock.write_text("999999999\n")
    import io
    import json
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with (
        patch.object(hc, "LOCK_FILE", lock),
        patch.object(hc, "LOG_FILE", tmp_path / "no.log"),
        redirect_stdout(buf),
    ):
        hc.main(as_json=True)

    output = json.loads(buf.getvalue())
    assert "pid" in output
    assert "timestamp" in output
    assert output["pid"] == 999999999
