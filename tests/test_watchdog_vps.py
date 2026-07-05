"""
tests/test_watchdog_vps.py — Simulation à blanc des 3 états critiques du
watchdog VPS, jamais exécutée contre le vrai process (DS-002, ADR-0007).

Couvre : moteur vivant, moteur absent des process, fichier moteur absent
du disque — sans jamais appeler pgrep/pkill réellement (subprocess mocké).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import watchdog_vps as wd


def _fake_run(returncode: int) -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = ""
    result.stderr = ""
    return result


class TestIsEngineRunning:
    def test_engine_alive_returncode_0(self):
        with patch.object(wd.subprocess, "run", return_value=_fake_run(0)) as m:
            assert wd._is_engine_running() is True
            # motif ancré — jamais de sous-chaîne (DS-002)
            assert m.call_args[0][0] == ["pgrep", "-f", r"core/advisor_loop\.py$"]

    def test_engine_absent_returncode_1(self):
        with patch.object(wd.subprocess, "run", return_value=_fake_run(1)):
            assert wd._is_engine_running() is False

    def test_pgrep_exception_treated_as_absent(self):
        with patch.object(wd.subprocess, "run", side_effect=OSError("no pgrep")):
            assert wd._is_engine_running() is False


class TestEngineFileOk:
    def test_missing_file_refused(self, tmp_path, monkeypatch):
        monkeypatch.setattr(wd, "ENGINE_SCRIPT", tmp_path / "core" / "advisor_loop.py")
        ok, reason = wd._engine_file_ok()
        assert ok is False
        assert "introuvable" in reason

    def test_valid_syntax_accepted(self, tmp_path, monkeypatch):
        script = tmp_path / "advisor_loop.py"
        script.write_text("def main():\n    pass\n", encoding="utf-8")
        monkeypatch.setattr(wd, "ENGINE_SCRIPT", script)
        ok, reason = wd._engine_file_ok()
        assert ok is True
        assert reason == "ok"

    def test_invalid_syntax_refused(self, tmp_path, monkeypatch):
        script = tmp_path / "advisor_loop.py"
        script.write_text("def main(:\n    pass\n", encoding="utf-8")
        monkeypatch.setattr(wd, "ENGINE_SCRIPT", script)
        ok, reason = wd._engine_file_ok()
        assert ok is False
        assert "syntaxe invalide" in reason


class TestRestartDisabled:
    def test_default_is_disabled(self, monkeypatch):
        monkeypatch.delenv("RESTART_DISABLED_UNTIL_RECONCILIATION", raising=False)
        assert wd._restart_disabled() is True

    def test_explicit_1_is_disabled(self, monkeypatch):
        monkeypatch.setenv("RESTART_DISABLED_UNTIL_RECONCILIATION", "1")
        assert wd._restart_disabled() is True

    def test_explicit_0_is_enabled(self, monkeypatch):
        monkeypatch.setenv("RESTART_DISABLED_UNTIL_RECONCILIATION", "0")
        assert wd._restart_disabled() is False


class TestTickThreeStates:
    """Les 3 états demandés : moteur vivant / absent de ps / fichier absent."""

    def test_state_engine_alive_no_action(self, monkeypatch):
        monkeypatch.setattr(wd, "_is_engine_running", lambda: True)
        with patch.object(wd, "_alert_dead_no_restart") as alert, patch.object(
            wd, "_restart_advisor"
        ) as restart:
            wd._tick()
            alert.assert_not_called()
            restart.assert_not_called()

    def test_state_engine_absent_disabled_triggers_alert_only(self, monkeypatch):
        monkeypatch.setattr(wd, "_is_engine_running", lambda: False)
        monkeypatch.setenv("RESTART_DISABLED_UNTIL_RECONCILIATION", "1")
        with patch.object(wd, "_alert_dead_no_restart") as alert, patch.object(
            wd, "_restart_advisor"
        ) as restart:
            wd._tick()
            alert.assert_called_once()
            restart.assert_not_called()

    def test_state_engine_absent_enabled_triggers_restart_attempt(self, monkeypatch):
        monkeypatch.setattr(wd, "_is_engine_running", lambda: False)
        monkeypatch.setenv("RESTART_DISABLED_UNTIL_RECONCILIATION", "0")
        with patch.object(wd, "_alert_dead_no_restart") as alert, patch.object(
            wd, "_restart_advisor"
        ) as restart:
            wd._tick()
            restart.assert_called_once()
            alert.assert_not_called()

    def test_state_file_absent_refuses_restart_even_when_enabled(
        self, tmp_path, monkeypatch
    ):
        """3e état : réconciliation faite (disabled=0) mais le fichier cible
        a disparu — doit refuser bruyamment, jamais relancer un fantôme."""
        monkeypatch.setattr(wd, "_is_engine_running", lambda: False)
        monkeypatch.setenv("RESTART_DISABLED_UNTIL_RECONCILIATION", "0")
        monkeypatch.setattr(wd, "ENGINE_SCRIPT", tmp_path / "core" / "advisor_loop.py")
        monkeypatch.setattr(wd, "_last_restart", 0.0)
        with patch.object(wd, "_send_telegram") as telegram, patch.object(
            wd.subprocess, "run"
        ) as run:
            wd._tick()
            run.assert_not_called()  # jamais de vps_restart.sh sur un fichier absent
            telegram.assert_called_once()
            assert "introuvable" in telegram.call_args[0][0]
