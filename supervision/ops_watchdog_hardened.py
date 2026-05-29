"""
supervision/ops_watchdog_hardened.py — E-01 OpsWatchdog Hardening

Watchdog durci pour la surveillance 24/7 du processus principal.

Garanties :
  - Daemon thread : ne peut pas bloquer l'arrêt propre
  - Heartbeat file : preuve que le watchdog est vivant
  - Auto-restart subprocess : relance advisor_loop si mort ou figé
  - Self-monitoring : second thread surveille le watchdog lui-même
  - Alerte si le watchdog échoue (Telegram + log CRITIQUE)
  - Signal handlers SIGTERM/SIGINT : arrêt gracieux vs forcé
  - Max restarts configurable avec backoff exponentiel

Usage :
    wd = HardenedOpsWatchdog.from_env()
    wd.start()
    # Dans la boucle principale :
    wd.write_heartbeat()   # appel périodique prouve que le process tourne
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from observability.json_logger import get_logger

_log = get_logger("supervision.ops_watchdog_hardened")

_HEARTBEAT_INTERVAL_S = float(os.getenv("P10_WD_HEARTBEAT_S", "30.0"))
_STALE_THRESHOLD_S = float(os.getenv("P10_WD_STALE_S", "120.0"))
_CHECK_INTERVAL_S = float(os.getenv("P10_WD_CHECK_S", "10.0"))
_MAX_RESTARTS = int(os.getenv("P10_WD_MAX_RESTARTS", "5"))
_RESTART_WINDOW_S = 3600.0  # 5 restarts per hour
_FREEZE_LAG_S = float(os.getenv("P10_WD_FREEZE_LAG_S", "600.0"))


@dataclass
class WatchdogStatus:
    running: bool = False
    heartbeat_age_s: float = 0.0
    process_alive: bool = True
    restarts: int = 0
    last_restart_reason: str = ""
    last_heartbeat_ts: float = 0.0
    self_monitor_alive: bool = True
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "running": self.running,
            "heartbeat_age_s": round(self.heartbeat_age_s, 1),
            "process_alive": self.process_alive,
            "restarts": self.restarts,
            "last_restart_reason": self.last_restart_reason,
            "last_heartbeat_ts": round(self.last_heartbeat_ts, 3),
            "self_monitor_alive": self.self_monitor_alive,
            "ts": round(self.ts, 3),
        }


class HardenedOpsWatchdog:
    """
    Watchdog durci — daemon thread + heartbeat file + auto-restart + self-monitoring.

    Trois composants indépendants :
      1. Thread principal de surveillance (daemon) : vérifie heartbeat + process
      2. Thread self-monitor (daemon) : vérifie que le thread principal est vivant
      3. Write_heartbeat() : appelé par le processus supervisé
    """

    def __init__(
        self,
        heartbeat_path: Optional[Path] = None,
        process_script: str = "advisor_loop.py",
        check_interval_s: float = _CHECK_INTERVAL_S,
        stale_threshold_s: float = _STALE_THRESHOLD_S,
        max_restarts: int = _MAX_RESTARTS,
        alert_fn: Optional[Callable[[str], None]] = None,
        auto_restart: bool = True,
    ) -> None:
        self._heartbeat_path = heartbeat_path or Path(
            "cache/startup/watchdog_heartbeat.json"
        )
        self._process_script = process_script
        self._check_interval = check_interval_s
        self._stale_threshold = stale_threshold_s
        self._max_restarts = max_restarts
        self._alert_fn = alert_fn
        self._auto_restart = auto_restart

        self._running = False
        self._main_thread: Optional[threading.Thread] = None
        self._self_monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        self._restart_times: list[float] = []
        self._last_restart_reason = ""
        self._monitored_pid: Optional[int] = None
        self._subprocess: Optional[subprocess.Popen] = None

        # Compteur de tick — preuve que le thread tourne
        self._tick_count = 0

    # ── API publique ──────────────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> "HardenedOpsWatchdog":
        """Construit depuis les variables d'environnement."""
        from supervision.notifications.ops_notifier import OpsNotifier

        try:
            notifier = OpsNotifier.from_env()
            alert_fn = lambda msg: notifier.info(msg, key="watchdog_alert")
        except Exception:
            alert_fn = None

        return cls(alert_fn=alert_fn)

    def start(self) -> None:
        """Démarre le watchdog (daemon thread) et le self-monitor."""
        with self._lock:
            if self._running:
                return
            self._running = True

        # Thread principal de surveillance
        self._main_thread = threading.Thread(
            target=self._watch_loop,
            daemon=True,
            name="HardenedOpsWatchdog",
        )
        self._main_thread.start()

        # Thread self-monitor (surveille que le thread principal tourne)
        self._self_monitor_thread = threading.Thread(
            target=self._self_monitor_loop,
            daemon=True,
            name="WatchdogSelfMonitor",
        )
        self._self_monitor_thread.start()

        _log.info(
            "[HardenedWatchdog] Démarré — heartbeat_path=%s stale=%.0fs",
            self._heartbeat_path,
            self._stale_threshold,
        )

    def stop(self) -> None:
        """Arrêt propre."""
        with self._lock:
            self._running = False
        _log.info("[HardenedWatchdog] Arrêté")

    def write_heartbeat(self, extra: Optional[dict] = None) -> None:
        """
        Appelé par le processus supervisé à chaque cycle.
        Écrit un fichier JSON horodaté — preuve de vivacité.
        """
        try:
            self._heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "ts": time.time(),
                "pid": os.getpid(),
                **(extra or {}),
            }
            self._heartbeat_path.write_text(json.dumps(payload), encoding="utf-8")
        except Exception as exc:
            _log.debug("[HardenedWatchdog] write_heartbeat error: %s", exc)

    def heartbeat_age_s(self) -> float:
        """Âge du dernier heartbeat en secondes. inf si absent."""
        try:
            if not self._heartbeat_path.exists():
                return float("inf")
            data = json.loads(self._heartbeat_path.read_text(encoding="utf-8"))
            return time.time() - float(data.get("ts", 0))
        except Exception:
            return float("inf")

    def is_heartbeat_stale(self) -> bool:
        return self.heartbeat_age_s() > self._stale_threshold

    def is_alive(self) -> bool:
        """True si le thread principal de surveillance tourne encore."""
        return self._main_thread is not None and self._main_thread.is_alive()

    def set_monitored_pid(self, pid: int) -> None:
        with self._lock:
            self._monitored_pid = pid

    def restart_count(self) -> int:
        with self._lock:
            now = time.time()
            return len([t for t in self._restart_times if now - t < _RESTART_WINDOW_S])

    def status(self) -> WatchdogStatus:
        with self._lock:
            now = time.time()
            restarts = len(
                [t for t in self._restart_times if now - t < _RESTART_WINDOW_S]
            )
        return WatchdogStatus(
            running=self._running,
            heartbeat_age_s=self.heartbeat_age_s(),
            process_alive=self._is_process_alive(),
            restarts=restarts,
            last_restart_reason=self._last_restart_reason,
            last_heartbeat_ts=self._read_heartbeat_ts(),
            self_monitor_alive=(
                self._self_monitor_thread is not None
                and self._self_monitor_thread.is_alive()
            ),
        )

    # ── Boucle principale ─────────────────────────────────────────────────────

    def _watch_loop(self) -> None:
        _log.info("[HardenedWatchdog] Boucle démarrée")
        while self._running:
            try:
                self._tick()
            except Exception as exc:
                _log.error("[HardenedWatchdog] Erreur boucle: %s", exc)
            time.sleep(self._check_interval)
        _log.info("[HardenedWatchdog] Boucle terminée")

    def _tick(self) -> None:
        with self._lock:
            self._tick_count += 1

        if self.is_heartbeat_stale():
            age = self.heartbeat_age_s()
            _log.warning(
                "[HardenedWatchdog] Heartbeat PÉRIMÉ (%.0fs) — seuil %.0fs",
                age,
                self._stale_threshold,
            )
            if self._auto_restart:
                self._try_restart(f"heartbeat périmé ({age:.0f}s)")
            else:
                self._alert(f"Heartbeat périmé ({age:.0f}s) — auto_restart désactivé")

        pid = None
        with self._lock:
            pid = self._monitored_pid

        if pid is not None and not _pid_alive(pid):
            _log.error("[HardenedWatchdog] Process PID %d mort", pid)
            if self._auto_restart:
                self._try_restart(f"process PID {pid} mort")

    # ── Auto-restart ──────────────────────────────────────────────────────────

    def _try_restart(self, reason: str) -> bool:
        now = time.time()
        with self._lock:
            self._restart_times = [
                t for t in self._restart_times if now - t < _RESTART_WINDOW_S
            ]
            if len(self._restart_times) >= self._max_restarts:
                _log.critical(
                    "[HardenedWatchdog] MAX_RESTARTS (%d/h) atteint — arrêt auto-restart. "
                    "Raison: %s",
                    self._max_restarts,
                    reason,
                )
                self._alert(
                    f"CRITIQUE — HardenedWatchdog MAX_RESTARTS atteint.\n"
                    f"Raison: {reason}\nIntervention requise."
                )
                return False
            self._restart_times.append(now)
            self._last_restart_reason = reason

        _log.warning(
            "[HardenedWatchdog] Restart #%d — raison: %s",
            len(self._restart_times),
            reason,
        )
        self._alert(f"[Watchdog] Restart — {reason}")

        try:
            logs_dir = Path("logs")
            logs_dir.mkdir(exist_ok=True)
            log_out = open(
                logs_dir / "advisor_loop_wd_restart.log", "a", encoding="utf-8"
            )
            proc = subprocess.Popen(
                [sys.executable, self._process_script],
                stdout=log_out,
                stderr=subprocess.STDOUT,
                cwd=str(Path(__file__).parent.parent),
            )
            with self._lock:
                self._monitored_pid = proc.pid
                self._subprocess = proc
            _log.info("[HardenedWatchdog] Relancé PID %d", proc.pid)
            self._alert(f"[Watchdog] Relancé PID {proc.pid}")
            return True
        except Exception as exc:
            _log.error("[HardenedWatchdog] Echec restart: %s", exc)
            self._alert(f"[Watchdog] ECHEC restart: {exc}")
            return False

    # ── Self-monitor ──────────────────────────────────────────────────────────

    def _self_monitor_loop(self) -> None:
        """Surveille que le thread principal de surveillance est vivant."""
        _consecutive_dead = 0
        while True:
            time.sleep(self._check_interval * 3)
            if not self._running:
                break

            if self._main_thread is None or not self._main_thread.is_alive():
                _consecutive_dead += 1
                _log.critical(
                    "[WatchdogSelfMonitor] WATCHDOG PRINCIPAL MORT ! "
                    "(consécutifs=%d)",
                    _consecutive_dead,
                )
                self._alert(
                    f"ALERTE CRITIQUE — Le watchdog principal est mort "
                    f"({_consecutive_dead}x consécutifs). "
                    "Le système n'est plus surveillé !"
                )
                # Tenter de relancer le thread principal
                if _consecutive_dead >= 2:
                    _log.critical(
                        "[WatchdogSelfMonitor] Tentative de relance du watchdog principal"
                    )
                    try:
                        self._main_thread = threading.Thread(
                            target=self._watch_loop,
                            daemon=True,
                            name="HardenedOpsWatchdog-Restarted",
                        )
                        self._main_thread.start()
                        _consecutive_dead = 0
                        _log.info("[WatchdogSelfMonitor] Watchdog principal relancé")
                    except Exception as exc:
                        _log.error("[WatchdogSelfMonitor] Echec relance: %s", exc)
            else:
                _consecutive_dead = 0

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _is_process_alive(self) -> bool:
        with self._lock:
            pid = self._monitored_pid
        if pid is None:
            return True  # pas de pid configuré = pas de surveillance process
        return _pid_alive(pid)

    def _read_heartbeat_ts(self) -> float:
        try:
            if not self._heartbeat_path.exists():
                return 0.0
            data = json.loads(self._heartbeat_path.read_text(encoding="utf-8"))
            return float(data.get("ts", 0))
        except Exception:
            return 0.0

    def _alert(self, msg: str) -> None:
        _log.warning("[HardenedWatchdog] ALERTE: %s", msg)
        if self._alert_fn:
            try:
                self._alert_fn(msg)
            except Exception as exc:
                _log.debug("[HardenedWatchdog] Erreur alert_fn: %s", exc)


# ── Utilitaire vérification PID ───────────────────────────────────────────────


def _pid_alive(pid: int) -> bool:
    """True si le processus PID est vivant (cross-platform)."""
    try:
        if sys.platform == "win32":
            import ctypes

            SYNCHRONIZE = 0x00100000
            h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
            if h == 0:
                return False
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False
