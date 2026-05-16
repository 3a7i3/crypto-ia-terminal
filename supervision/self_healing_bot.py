"""
self_healing_bot.py — Auto-restart ciblé sans tuer tout le système (Idée #8).

Si :
  - websocket dead      → reconnecte le stream
  - API timeout         → reset le client CCXT
  - DB locked           → attente + retry
  - memory leak détecté → restart du composant fautif uniquement

Auto-restart ciblé par composant, pas un restart global.

Usage:
    bot = SelfHealingBot()
    bot.register("websocket", ws_component, health_fn=lambda: ws.is_alive())
    bot.register("db", db_component, health_fn=lambda: db.ping())
    bot.start()
"""

from __future__ import annotations

import enum
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

_DEFAULT_CHECK_INTERVAL = 15.0  # secondes
_DEFAULT_MAX_RESTARTS = 5  # par fenêtre de 10 minutes

_BACKOFF_INITIAL_S = 60.0  # premier cooldown après restart_limit_reached
_BACKOFF_MAX_S = 600.0  # plafond du backoff (10 min)
_DISABLED_PROBE_S = 600.0  # période de sonde en état DISABLED


class ComponentState(enum.Enum):
    HEALTHY = "healthy"  # aucune anomalie
    UNSTABLE = "unstable"  # défaillances sporadiques, recovery probable
    DEGRADED = "degraded"  # restart limit atteinte, backoff exponentiel
    DISABLED = "disabled"  # trop de tentatives, sonde périodique seulement


try:
    from errors.error_bus import ErrorCategory as _ErrCat
    from errors.error_bus import ErrorSeverity as _ErrSev
    from errors.error_bus import error_bus as _error_bus
    from system.module_registry import ModuleStatus as _ModuleStatus
    from system.module_registry import module_registry as _module_registry

    _OBS_AVAILABLE = True
except Exception:
    _OBS_AVAILABLE = False


@dataclass
class ComponentHealth:
    name: str
    component: Any
    health_fn: Callable[[], bool]
    restart_fn: Callable[[], None]
    check_interval_s: float = _DEFAULT_CHECK_INTERVAL
    max_restarts_per_window: int = _DEFAULT_MAX_RESTARTS

    # État interne
    is_healthy: bool = True
    last_check: float = field(default_factory=time.time)
    restart_count: int = 0
    restart_window_start: float = field(default_factory=time.time)
    total_restarts: int = 0
    last_error: str = ""
    consecutive_failures: int = 0
    # Machine d'états HEALTHY → UNSTABLE → DEGRADED → DISABLED
    state: ComponentState = field(default=ComponentState.HEALTHY)
    backoff_until: float = 0.0  # skip check jusqu'à ce timestamp
    backoff_delay_s: float = _BACKOFF_INITIAL_S  # délai courant (double chaque cycle)

    def reset_window_if_needed(self) -> None:
        """Reset le compteur de restart toutes les 10 minutes."""
        if time.time() - self.restart_window_start > 600:
            self.restart_count = 0
            self.restart_window_start = time.time()

    def can_restart(self) -> bool:
        self.reset_window_if_needed()
        return self.restart_count < self.max_restarts_per_window


class SelfHealingBot:
    """
    Superviseur auto-guérisseur.

    Vérifie périodiquement la santé de chaque composant enregistré et
    déclenche un restart ciblé si nécessaire.
    """

    def __init__(self, global_check_interval_s: float = 5.0) -> None:
        self._global_interval = global_check_interval_s
        self._components: dict[str, ComponentHealth] = {}
        self._running: bool = False
        self._thread: threading.Thread | None = None
        self._event_log: list[dict] = []

    # ── Enregistrement ─────────────────────────────────────────────────────────

    def register(
        self,
        name: str,
        component: Any,
        health_fn: Callable[[], bool],
        restart_fn: Callable[[], None],
        check_interval_s: float = _DEFAULT_CHECK_INTERVAL,
        max_restarts: int = _DEFAULT_MAX_RESTARTS,
    ) -> None:
        """
        Enregistre un composant à surveiller.

        Args:
            name           : identifiant unique (ex. "websocket", "db")
            component      : objet Python à surveiller
            health_fn      : callable → bool (True si sain)
            restart_fn     : callable → None (action de restart)
            check_interval_s : fréquence de vérification en secondes
            max_restarts   : limite de restarts par fenêtre de 10 min
        """
        self._components[name] = ComponentHealth(
            name=name,
            component=component,
            health_fn=health_fn,
            restart_fn=restart_fn,
            check_interval_s=check_interval_s,
            max_restarts_per_window=max_restarts,
        )
        logger.info("[SelfHealing] Composant enregistré: %s", name)

    def register_simple(
        self, name: str, health_fn: Callable[[], bool], restart_fn: Callable[[], None]
    ) -> None:
        """Alias simplifié sans composant objet."""
        self.register(name, None, health_fn, restart_fn)

    # ── Cycle de vie ───────────────────────────────────────────────────────────

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(
            target=self._watch_loop, daemon=True, name="SelfHealingBot"
        )
        self._thread.start()
        logger.info(
            "[SelfHealing] Démarré — %d composant(s) surveillé(s)",
            len(self._components),
        )

    def stop(self) -> None:
        self._running = False
        logger.info("[SelfHealing] Arrêté")

    def force_check(self, name: str | None = None) -> dict[str, bool]:
        """Vérifie immédiatement la santé (utile pour les tests)."""
        targets = (
            {name: self._components[name]}
            if name and name in self._components
            else self._components
        )
        results = {}
        for n, comp in targets.items():
            results[n] = self._check_one(comp)
        return results

    def status(self) -> dict:
        """Retourne l'état de santé de tous les composants."""
        return {
            name: {
                "healthy": c.is_healthy,
                "consecutive_failures": c.consecutive_failures,
                "total_restarts": c.total_restarts,
                "restart_count_this_window": c.restart_count,
                "last_error": c.last_error,
                "last_check": c.last_check,
            }
            for name, c in self._components.items()
        }

    def event_log(self, n: int = 20) -> list[dict]:
        return self._event_log[-n:]

    # ── Boucle interne ─────────────────────────────────────────────────────────

    def _watch_loop(self) -> None:
        while self._running:
            now = time.time()
            for comp in list(self._components.values()):
                if now - comp.last_check >= comp.check_interval_s:
                    self._check_one(comp)
            time.sleep(self._global_interval)

    def _check_one(self, comp: ComponentHealth) -> bool:
        now = time.time()

        # DISABLED : sonde périodique seulement (évite le spam de logs/retry)
        if comp.state == ComponentState.DISABLED:
            if now < comp.backoff_until:
                return False  # encore en cooldown, on ne touche à rien
            # Tentative de récupération périodique
            logger.info(
                "[SelfHealing] %s — sonde périodique (état DISABLED)", comp.name
            )

        # DEGRADED : backoff exponentiel entre chaque sonde
        elif comp.state == ComponentState.DEGRADED:
            if now < comp.backoff_until:
                return False  # encore en backoff

        comp.last_check = now
        try:
            healthy = comp.health_fn()
        except Exception as exc:
            healthy = False
            # repr() inclut le nom de la classe de l'exception + message,
            # ce qui évite les messages vides ("health_check_failed: ").
            comp.last_error = repr(exc)
            # logger.exception() écrit la stacktrace complète → enfin visible.
            logger.exception("[SelfHealing] %s — exception dans health_fn", comp.name)

        if healthy:
            if not comp.is_healthy or comp.state != ComponentState.HEALTHY:
                logger.info(
                    "[SelfHealing] %s — RÉCUPÉRÉ (était %s)",
                    comp.name,
                    comp.state.value,
                )
                self._log_event(comp.name, "recovered")
                if _OBS_AVAILABLE:
                    try:
                        _module_registry.heartbeat(comp.name)
                        _module_registry.set_status(comp.name, _ModuleStatus.HEALTHY)
                    except Exception:
                        pass
            comp.is_healthy = True
            comp.consecutive_failures = 0
            comp.state = ComponentState.HEALTHY
            comp.backoff_delay_s = (
                _BACKOFF_INITIAL_S  # reset backoff pour prochaine fois
            )
            comp.backoff_until = 0.0
            return True

        # Composant malade
        comp.is_healthy = False
        comp.consecutive_failures += 1
        logger.warning(
            "[SelfHealing] %s — DÉFAILLANT (échec #%d) erreur: %s",
            comp.name,
            comp.consecutive_failures,
            comp.last_error,
        )
        if _OBS_AVAILABLE:
            try:
                _module_registry.report_error(
                    comp.name, comp.last_error or "health_check_failed"
                )
                _module_registry.set_status(comp.name, _ModuleStatus.UNHEALTHY)
                _error_bus.emit_raw(
                    module=f"self_healing_bot.{comp.name}",
                    message=(
                        "health_check_failed: "
                        f"{comp.last_error or '(voir stacktrace log)'}"
                    ),
                    category=_ErrCat.SYSTEM,
                    severity=(
                        _ErrSev.HIGH
                        if comp.consecutive_failures < 3
                        else _ErrSev.CRITICAL
                    ),
                )
            except Exception:
                pass

        # ── Transition d'état selon le nombre de failures ──────────────────
        if comp.consecutive_failures <= 2:
            comp.state = ComponentState.UNSTABLE
        elif comp.can_restart():
            comp.state = ComponentState.UNSTABLE
            self._restart(comp)
        else:
            # Restart limit atteinte → DEGRADED avec backoff exponentiel
            if comp.state not in (ComponentState.DEGRADED, ComponentState.DISABLED):
                # Première fois → DEGRADED
                comp.state = ComponentState.DEGRADED
                comp.backoff_until = time.time() + comp.backoff_delay_s
                logger.error(
                    "[SelfHealing] %s → DEGRADED — backoff %.0fs "
                    "(restarts=%d/%d erreur=%s)",
                    comp.name,
                    comp.backoff_delay_s,
                    comp.restart_count,
                    comp.max_restarts_per_window,
                    comp.last_error,
                )
                self._log_event(
                    comp.name,
                    "state_degraded",
                    extra={"backoff_s": comp.backoff_delay_s},
                )
            elif comp.state == ComponentState.DEGRADED:
                # Backoff exponentiel : doubler jusqu'au plafond
                comp.backoff_delay_s = min(comp.backoff_delay_s * 2, _BACKOFF_MAX_S)
                comp.backoff_until = time.time() + comp.backoff_delay_s
                if comp.backoff_delay_s >= _BACKOFF_MAX_S:
                    # Passage en DISABLED : sonde périodique uniquement
                    comp.state = ComponentState.DISABLED
                    comp.backoff_until = time.time() + _DISABLED_PROBE_S
                    logger.error(
                        "[SelfHealing] %s → DISABLED — "
                        "sonde périodique toutes les %.0fs. "
                        "Intervention requise si le problème persiste.",
                        comp.name,
                        _DISABLED_PROBE_S,
                    )
                    self._log_event(comp.name, "state_disabled")
                    if _OBS_AVAILABLE:
                        try:
                            _error_bus.emit_raw(
                                module=f"self_healing_bot.{comp.name}",
                                message=(
                                    "component_disabled: "
                                    f"{comp.last_error or '(voir stacktrace log)'}"
                                ),
                                category=_ErrCat.SYSTEM,
                                severity=_ErrSev.CRITICAL,
                            )
                        except Exception:
                            pass
                    self._emit_critical_alert(comp)
                else:
                    logger.warning(
                        "[SelfHealing] %s — DEGRADED, prochaine sonde dans %.0fs",
                        comp.name,
                        comp.backoff_delay_s,
                    )
            elif comp.state == ComponentState.DISABLED:
                # Encore DISABLED après sonde → replanifier
                comp.backoff_until = time.time() + _DISABLED_PROBE_S

        return False

    def _restart(self, comp: ComponentHealth) -> None:
        logger.warning(
            "[SelfHealing] %s — Tentative de restart #%d",
            comp.name,
            comp.restart_count + 1,
        )
        try:
            comp.restart_fn()
            comp.restart_count += 1
            comp.total_restarts += 1
            self._log_event(
                comp.name, "restarted", extra={"attempt": comp.restart_count}
            )
            logger.info("[SelfHealing] %s — Restart effectué", comp.name)
        except Exception as exc:
            comp.last_error = f"restart_failed: {exc}"
            logger.error("[SelfHealing] %s — Echec du restart: %s", comp.name, exc)
            self._log_event(comp.name, "restart_failed", extra={"error": str(exc)})

    def _log_event(self, name: str, event: str, extra: dict | None = None) -> None:
        entry = {
            "ts": time.time(),
            "component": name,
            "event": event,
            **(extra or {}),
        }
        self._event_log.append(entry)
        if len(self._event_log) > 500:
            self._event_log = self._event_log[-500:]

    def _emit_critical_alert(self, comp: ComponentHealth) -> None:
        try:
            from event_bus.bus import EventBus
            from event_bus.events import SessionHaltEvent

            EventBus.get().emit(
                SessionHaltEvent(
                    reason=f"SelfHealingBot: {comp.name} restart_limit_reached",
                    halt_duration_seconds=0.0,
                    source="self_healing_bot",
                )
            )
        except Exception:
            pass


# ── Wrapper de process advisor_loop.py ───────────────────────────────────────

import os  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import requests as _requests  # noqa: E402

_TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
_PID_FILE = Path("logs/advisor_loop.pid")
_ADVISOR_LOG = Path("logs/advisor_loop.log")
_MAX_RESTARTS = 5
_FREEZE_TIMEOUT = 600  # 10 min sans log = boucle figée


def _tg(text: str) -> None:
    if not _TELEGRAM_TOKEN or not _TELEGRAM_CHAT:
        return
    try:
        _requests.post(
            f"https://api.telegram.org/bot{_TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": _TELEGRAM_CHAT, "text": text},
            timeout=10,
        )
    except Exception:
        pass


def _pid_alive(pid: int) -> bool:
    try:
        if sys.platform == "win32":
            import ctypes

            h = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)
            if h == 0:
                return False
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


def _log_lag() -> float:
    if not _ADVISOR_LOG.exists():
        return float("inf")
    try:
        return time.time() - _ADVISOR_LOG.stat().st_mtime
    except Exception:
        return float("inf")


def _start_advisor_process() -> tuple[subprocess.Popen, "Any"]:
    log_out = open("logs/advisor_loop_stdout.log", "a", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "advisor_loop.py"],
        stdout=log_out,
        stderr=subprocess.STDOUT,
        cwd=str(Path(__file__).parent.parent),
    )
    _PID_FILE.write_text(str(proc.pid))
    logger.info("[ProcessWrap] Démarré PID %d", proc.pid)
    return proc, log_out


class AdvisorProcessWrapper:
    """
    Lance advisor_loop.py comme subprocess et le surveille.
    Redémarre automatiquement si mort ou figé (max 5 fois/h).
    """

    def __init__(self, check_interval: int = 60) -> None:
        self._interval = check_interval
        self._proc: subprocess.Popen | None = None
        self._log_out = None  # handle fichier log du subprocess — fermé à l'arrêt
        self._restarts: list[float] = []

    def run(self) -> None:
        import os

        os.makedirs("logs", exist_ok=True)
        logger.info("[ProcessWrap] Mode wrapper démarré")
        _tg("Self-Healing Wrapper actif — surveillance advisor_loop.py")

        self._proc, self._log_out = _start_advisor_process()
        self._restarts.append(time.time())

        while True:
            try:
                time.sleep(self._interval)
                self._tick()
            except KeyboardInterrupt:
                logger.info("[ProcessWrap] Arrêt — kill process fils")
                if self._proc:
                    self._proc.terminate()
                if self._log_out:
                    self._log_out.close()
                break
            except Exception as exc:
                logger.error("[ProcessWrap] Erreur: %s", exc)

    def _tick(self) -> None:
        if self._proc is None:
            self._restart("process absent")
            return

        ret = self._proc.poll()
        if ret is not None:
            logger.error("[ProcessWrap] Process mort (code %d)", ret)
            self._restart(f"process terminé (code {ret})")
            return

        lag = _log_lag()
        if lag > _FREEZE_TIMEOUT:
            logger.error("[ProcessWrap] Boucle figée (%.0fs) — kill", lag)
            self._proc.terminate()
            time.sleep(3)
            self._restart(f"boucle figée ({lag:.0f}s sans log)")

    def _restart(self, reason: str) -> None:
        now = time.time()
        self._restarts = [t for t in self._restarts if now - t < 3600]
        if len(self._restarts) >= _MAX_RESTARTS:
            logger.critical("[ProcessWrap] MAX_RESTARTS atteint — arrêt du wrapper")
            _tg(
                f"CRITIQUE — Self-Heal MAX_RESTARTS atteint.\n"
                f"Raison: {reason}\nIntervention requise."
            )
            self._proc = None
            return
        _tg(f"Self-Heal: redémarrage advisor_loop.py\nRaison: {reason}")
        if self._log_out:
            try:
                self._log_out.close()
            except Exception as _e:
                logger.debug("[ProcessWrap] Fermeture log_out: %s", _e)
        self._proc, self._log_out = _start_advisor_process()
        self._restarts.append(now)
        _tg(f"Self-Heal: redémarré (PID {self._proc.pid})")


# ── Factories pour cas d'usage courants ──────────────────────────────────────


def make_websocket_watchdog(
    bot: SelfHealingBot,
    ws_component,
    reconnect_fn: Callable[[], None],
    name: str = "websocket",
) -> None:
    """Enregistre un watchdog pour un composant WebSocket."""

    def health() -> bool:
        try:
            return bool(getattr(ws_component, "is_alive", lambda: True)())
        except Exception:
            return False

    bot.register(
        name, ws_component, health, reconnect_fn, check_interval_s=10.0, max_restarts=10
    )


def make_db_watchdog(
    bot: SelfHealingBot,
    db_component,
    ping_fn: Callable[[], bool],
    reconnect_fn: Callable[[], None],
    name: str = "database",
) -> None:
    """Enregistre un watchdog pour une connexion base de données."""
    bot.register(
        name, db_component, ping_fn, reconnect_fn, check_interval_s=30.0, max_restarts=3
    )


def make_api_watchdog(
    bot: SelfHealingBot,
    api_component,
    health_fn: Callable[[], bool],
    reset_fn: Callable[[], None],
    name: str = "exchange_api",
) -> None:
    """Enregistre un watchdog pour un client exchange API."""
    bot.register(
        name, api_component, health_fn, reset_fn, check_interval_s=20.0, max_restarts=5
    )
