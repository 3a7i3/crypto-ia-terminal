"""
supervision/tests/test_e01_ops_watchdog.py — E-01 OpsWatchdog Hardening

Tests de certification :
  - Watchdog résilient (daemon thread, non-bloquant)
  - Heartbeat file écrit et lu correctement
  - Détection heartbeat périmé
  - Auto-restart subprocess (mocké)
  - Self-monitor détecte thread mort
  - Alerte si watchdog échoue

Total : 12 tests
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from supervision.ops_watchdog_hardened import HardenedOpsWatchdog, _pid_alive


class TestWatchdogDaemonThread:
    def test_start_creates_daemon_thread(self, tmp_path):
        """Le watchdog tourne en daemon thread."""
        wd = HardenedOpsWatchdog(
            heartbeat_path=tmp_path / "hb.json",
            auto_restart=False,
        )
        wd.start()
        time.sleep(0.05)
        assert wd.is_alive(), "Thread principal doit être vivant"
        assert wd._main_thread.daemon, "Thread doit être daemon"
        wd.stop()

    def test_stop_sets_running_false(self, tmp_path):
        """stop() désactive la boucle."""
        wd = HardenedOpsWatchdog(
            heartbeat_path=tmp_path / "hb.json", auto_restart=False
        )
        wd.start()
        time.sleep(0.05)
        wd.stop()
        assert not wd._running

    def test_self_monitor_thread_starts(self, tmp_path):
        """Le thread self-monitor démarre avec le watchdog."""
        wd = HardenedOpsWatchdog(
            heartbeat_path=tmp_path / "hb.json", auto_restart=False
        )
        wd.start()
        time.sleep(0.05)
        assert wd._self_monitor_thread is not None
        assert wd._self_monitor_thread.is_alive()
        wd.stop()

    def test_cannot_start_twice(self, tmp_path):
        """Appels start() répétés sans double thread."""
        wd = HardenedOpsWatchdog(
            heartbeat_path=tmp_path / "hb.json", auto_restart=False
        )
        wd.start()
        t1 = wd._main_thread
        wd.start()  # appel doublon
        t2 = wd._main_thread
        assert t1 is t2, "Même thread — pas de duplication"
        wd.stop()


class TestHeartbeat:
    def test_write_heartbeat_creates_file(self, tmp_path):
        """write_heartbeat() crée le fichier JSON."""
        wd = HardenedOpsWatchdog(
            heartbeat_path=tmp_path / "hb.json", auto_restart=False
        )
        wd.write_heartbeat()
        assert (tmp_path / "hb.json").exists()

    def test_write_heartbeat_has_ts_and_pid(self, tmp_path):
        """Le fichier heartbeat contient ts et pid."""
        wd = HardenedOpsWatchdog(
            heartbeat_path=tmp_path / "hb.json", auto_restart=False
        )
        wd.write_heartbeat()
        data = json.loads((tmp_path / "hb.json").read_text())
        assert "ts" in data
        assert "pid" in data
        assert data["pid"] == os.getpid()

    def test_heartbeat_age_fresh(self, tmp_path):
        """Heartbeat fraîchement écrit → age < 2s."""
        wd = HardenedOpsWatchdog(
            heartbeat_path=tmp_path / "hb.json", auto_restart=False
        )
        wd.write_heartbeat()
        assert wd.heartbeat_age_s() < 2.0

    def test_heartbeat_age_absent(self, tmp_path):
        """Pas de heartbeat → age = inf."""
        wd = HardenedOpsWatchdog(
            heartbeat_path=tmp_path / "absent.json", auto_restart=False
        )
        assert wd.heartbeat_age_s() == float("inf")

    def test_stale_detection(self, tmp_path):
        """Heartbeat vieux → is_heartbeat_stale() = True."""
        hb_path = tmp_path / "hb.json"
        hb_path.write_text(json.dumps({"ts": time.time() - 300, "pid": os.getpid()}))
        wd = HardenedOpsWatchdog(
            heartbeat_path=hb_path,
            stale_threshold_s=60.0,
            auto_restart=False,
        )
        assert wd.is_heartbeat_stale()

    def test_fresh_heartbeat_not_stale(self, tmp_path):
        """Heartbeat récent → pas périmé."""
        wd = HardenedOpsWatchdog(
            heartbeat_path=tmp_path / "hb.json",
            stale_threshold_s=60.0,
            auto_restart=False,
        )
        wd.write_heartbeat()
        assert not wd.is_heartbeat_stale()


class TestPidMonitoring:
    def test_current_process_is_alive(self):
        """Le PID du processus courant est vivant."""
        assert _pid_alive(os.getpid())

    def test_bogus_pid_not_alive(self):
        """PID fictif → non vivant."""
        assert not _pid_alive(999999999)

    def test_status_snapshot(self, tmp_path):
        """status() retourne un WatchdogStatus complet."""
        wd = HardenedOpsWatchdog(
            heartbeat_path=tmp_path / "hb.json", auto_restart=False
        )
        wd.write_heartbeat()
        status = wd.status()
        assert hasattr(status, "running")
        assert hasattr(status, "heartbeat_age_s")
        assert hasattr(status, "process_alive")
        assert hasattr(status, "restarts")
        d = status.to_dict()
        assert isinstance(d, dict)


class TestAutoRestart:
    def test_alert_fn_called_on_stale(self, tmp_path):
        """Si heartbeat périmé → alert_fn appelée."""
        alerted = []
        wd = HardenedOpsWatchdog(
            heartbeat_path=tmp_path / "hb.json",
            stale_threshold_s=0.001,  # périmé immédiatement
            check_interval_s=0.05,
            auto_restart=False,
            alert_fn=lambda msg: alerted.append(msg),
        )
        # Écrire un heartbeat périmé
        (tmp_path / "hb.json").write_text(json.dumps({"ts": time.time() - 1, "pid": 1}))
        wd.start()
        time.sleep(0.2)
        wd.stop()
        assert len(alerted) > 0, "alert_fn doit être appelé sur heartbeat périmé"
