"""
supervision/recovery_playbooks.py — E-05 Auto-Recovery Playbooks

Playbooks de reprise prédéfinis pour chaque type de panne.

Playbooks intégrés :
  1. advisor_loop_crash       : crash → cold start + restart
  2. exchange_connection_lost : perte connexion → reconnexion + warmup partiel
  3. lm_studio_failure        : LM Studio down → fallback rules + retry périodique
  4. database_error           : erreur DB → backup + reconstitution

Fonctionnement :
  - execute(name, dry_run=False) → PlaybookResult
  - simulate(name) → PlaybookResult  (dry_run=True, ne modifie rien)
  - recovery_time mesuré (objectif : < 30s pour crash, < 60s pour exchange)

Usage :
    pb = RecoveryPlaybooks()
    result = pb.simulate("advisor_loop_crash")
    print(result.success, result.duration_s)

    result = pb.execute("lm_studio_failure")
    assert result.success
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from observability.json_logger import get_logger

_log = get_logger("supervision.recovery_playbooks")


# ── Types ─────────────────────────────────────────────────────────────────────


@dataclass
class StepResult:
    name: str
    success: bool
    duration_s: float
    message: str = ""
    error: str = ""
    skipped: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "success": self.success,
            "duration_s": round(self.duration_s, 3),
            "message": self.message,
            "error": self.error,
            "skipped": self.skipped,
        }


@dataclass
class PlaybookResult:
    playbook_name: str
    success: bool
    duration_s: float
    steps_executed: list[StepResult] = field(default_factory=list)
    failure_step: Optional[str] = None
    dry_run: bool = False
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "playbook_name": self.playbook_name,
            "success": self.success,
            "duration_s": round(self.duration_s, 3),
            "failure_step": self.failure_step,
            "dry_run": self.dry_run,
            "steps": [s.to_dict() for s in self.steps_executed],
            "ts": round(self.ts, 3),
        }


@dataclass
class PlaybookStep:
    name: str
    fn: Callable[[dict], bool]  # contexte → bool (True = succès)
    timeout_s: float = 30.0
    retry: int = 1
    required: bool = True  # si required=True et échec → playbook FAIL
    description: str = ""


@dataclass
class RecoveryPlaybook:
    name: str
    failure_type: str
    steps: list[PlaybookStep]
    max_duration_s: float = 120.0
    description: str = ""


# ── Registre de playbooks ─────────────────────────────────────────────────────


class RecoveryPlaybooks:
    """
    Registre et exécuteur de playbooks de récupération.
    Chaque playbook est une séquence d'étapes avec timeout et retry.
    """

    def __init__(self) -> None:
        self._playbooks: dict[str, RecoveryPlaybook] = {}
        self._last_results: dict[str, PlaybookResult] = {}
        self._register_defaults()

    def register(self, playbook: RecoveryPlaybook) -> None:
        self._playbooks[playbook.name] = playbook
        _log.debug("[RecoveryPlaybooks] Enregistré: %s", playbook.name)

    def available(self) -> list[str]:
        return list(self._playbooks.keys())

    def simulate(self, name: str, context: Optional[dict] = None) -> PlaybookResult:
        """Exécution à blanc (dry_run=True) — sans modification réelle."""
        return self.execute(name, context=context, dry_run=True)

    def execute(
        self,
        name: str,
        context: Optional[dict] = None,
        dry_run: bool = False,
    ) -> PlaybookResult:
        """Exécute un playbook par son nom."""
        ctx = context or {}
        ctx["dry_run"] = dry_run

        playbook = self._playbooks.get(name)
        if playbook is None:
            result = PlaybookResult(
                playbook_name=name,
                success=False,
                duration_s=0.0,
                failure_step="playbook_not_found",
                dry_run=dry_run,
            )
            return result

        _log.info(
            "[RecoveryPlaybooks] %s '%s'",
            "Simulation" if dry_run else "Exécution",
            name,
        )
        t0 = time.perf_counter()
        steps_done: list[StepResult] = []
        overall_success = True
        failure_step = None

        for step in playbook.steps:
            step_result = self._run_step(step, ctx, dry_run)
            steps_done.append(step_result)

            if not step_result.success and not step_result.skipped and step.required:
                overall_success = False
                failure_step = step.name
                _log.error(
                    "[RecoveryPlaybooks] %s — étape requise '%s' échouée: %s",
                    name,
                    step.name,
                    step_result.error,
                )
                break  # stoppe à la première étape critique échouée

            elapsed_total = time.perf_counter() - t0
            if elapsed_total > playbook.max_duration_s:
                _log.warning(
                    "[RecoveryPlaybooks] %s — max_duration_s dépassé (%.0f > %.0f)",
                    name,
                    elapsed_total,
                    playbook.max_duration_s,
                )
                overall_success = False
                failure_step = f"timeout_global ({elapsed_total:.0f}s)"
                break

        duration_s = time.perf_counter() - t0
        result = PlaybookResult(
            playbook_name=name,
            success=overall_success,
            duration_s=duration_s,
            steps_executed=steps_done,
            failure_step=failure_step,
            dry_run=dry_run,
        )
        self._last_results[name] = result

        _log.info(
            "[RecoveryPlaybooks] '%s' → %s (%.2fs)%s",
            name,
            "OK" if overall_success else "FAIL",
            duration_s,
            " [dry_run]" if dry_run else "",
        )
        return result

    def last_result(self, name: str) -> Optional[PlaybookResult]:
        return self._last_results.get(name)

    def measure_recovery_time(self, name: str, context: Optional[dict] = None) -> float:
        """Exécute le playbook et retourne le temps de récupération en secondes."""
        result = self.execute(name, context=context)
        return result.duration_s

    # ── Étape individuelle ─────────────────────────────────────────────────────

    def _run_step(
        self,
        step: PlaybookStep,
        ctx: dict,
        dry_run: bool,
    ) -> StepResult:
        if dry_run:
            return StepResult(
                name=step.name,
                success=True,
                duration_s=0.0,
                message=f"[dry_run] {step.description}",
                skipped=True,
            )

        last_error = ""
        for attempt in range(max(1, step.retry)):
            t0 = time.perf_counter()
            try:
                success = step.fn(ctx)
                duration_s = time.perf_counter() - t0
                if success:
                    return StepResult(
                        name=step.name,
                        success=True,
                        duration_s=duration_s,
                        message=step.description,
                    )
                last_error = "action retourné False"
            except Exception as exc:
                duration_s = time.perf_counter() - t0
                last_error = str(exc)
                _log.warning(
                    "[RecoveryPlaybooks] %s tentative %d/%d: %s",
                    step.name,
                    attempt + 1,
                    step.retry,
                    exc,
                )

        return StepResult(
            name=step.name,
            success=False,
            duration_s=time.perf_counter() - time.perf_counter(),
            error=last_error,
        )

    # ── Playbooks par défaut ───────────────────────────────────────────────────

    def _register_defaults(self) -> None:
        self.register(_pb_advisor_loop_crash())
        self.register(_pb_exchange_connection_lost())
        self.register(_pb_lm_studio_failure())
        self.register(_pb_database_error())


# ── 4 Playbooks certifiés ─────────────────────────────────────────────────────


def _pb_advisor_loop_crash() -> RecoveryPlaybook:
    """Playbook 1 : crash de advisor_loop → restart cold start."""

    def step_log_crash(ctx: dict) -> bool:
        _log.critical("[Playbook:AdvisorCrash] Crash détecté — démarrage récupération")
        ctx["crash_logged_at"] = time.time()
        return True

    def step_kill_zombie(ctx: dict) -> bool:
        pid = ctx.get("pid")
        if pid:
            try:
                import os
                import sys

                if sys.platform == "win32":
                    import ctypes

                    ctypes.windll.kernel32.TerminateProcess(
                        ctypes.windll.kernel32.OpenProcess(1, False, pid), 1
                    )
                else:
                    os.kill(pid, 9)
                _log.info("[Playbook:AdvisorCrash] Zombie PID %d tué", pid)
            except Exception:
                pass
        return True  # best effort

    def step_purge_lock_files(ctx: dict) -> bool:
        import pathlib

        for pattern in ["*.lock", "*.pid"]:
            for f in pathlib.Path("cache").rglob(pattern):
                try:
                    f.unlink()
                    _log.debug("[Playbook:AdvisorCrash] Lock supprimé: %s", f)
                except Exception:
                    pass
        return True

    def step_cold_start_reset(ctx: dict) -> bool:
        try:
            cold_start = ctx.get("cold_start_manager")
            if cold_start is not None:
                cold_start_cls = type(cold_start)
                ctx["new_cold_start"] = cold_start_cls()
                _log.info("[Playbook:AdvisorCrash] ColdStartManager réinitialisé")
            return True
        except Exception as exc:
            _log.error("[Playbook:AdvisorCrash] cold_start_reset: %s", exc)
            return False

    def step_notify_restart(ctx: dict) -> bool:
        notify = ctx.get("notify_fn")
        if notify:
            try:
                notify("[Playbook] Advisor loop redémarré après crash")
            except Exception:
                pass
        return True

    return RecoveryPlaybook(
        name="advisor_loop_crash",
        failure_type="crash",
        description="Crash advisor_loop → cold start + restart",
        max_duration_s=30.0,
        steps=[
            PlaybookStep(
                "log_crash",
                step_log_crash,
                timeout_s=2.0,
                description="Journaliser le crash",
            ),
            PlaybookStep(
                "kill_zombie",
                step_kill_zombie,
                timeout_s=5.0,
                required=False,
                description="Tuer processus zombie",
            ),
            PlaybookStep(
                "purge_lock_files",
                step_purge_lock_files,
                timeout_s=5.0,
                description="Supprimer fichiers lock",
            ),
            PlaybookStep(
                "cold_start_reset",
                step_cold_start_reset,
                timeout_s=10.0,
                description="Réinitialiser cold start",
            ),
            PlaybookStep(
                "notify_restart",
                step_notify_restart,
                timeout_s=5.0,
                required=False,
                description="Notifier redémarrage",
            ),
        ],
    )


def _pb_exchange_connection_lost() -> RecoveryPlaybook:
    """Playbook 2 : perte connexion exchange → reconnexion + warmup partiel."""

    def step_detect_exchange(ctx: dict) -> bool:
        exchange_name = ctx.get("exchange_name", "unknown")
        _log.warning("[Playbook:ExchangeLost] Exchange '%s' perdu", exchange_name)
        ctx["detection_ts"] = time.time()
        return True

    def step_close_stale_connection(ctx: dict) -> bool:
        conn = ctx.get("exchange_connection")
        if conn:
            try:
                conn.close()
                _log.info("[Playbook:ExchangeLost] Connexion stale fermée")
            except Exception:
                pass
        return True

    def step_reconnect(ctx: dict) -> bool:
        factory = ctx.get("exchange_factory")
        exchange_name = ctx.get("exchange_name", "")
        if factory is None or not exchange_name:
            _log.warning(
                "[Playbook:ExchangeLost] Pas de factory — impossible de reconnecter"
            )
            return False
        try:
            new_conn = factory(exchange_name)
            ctx["exchange_connection"] = new_conn
            _log.info("[Playbook:ExchangeLost] %s reconnecté", exchange_name)
            return True
        except Exception as exc:
            _log.error("[Playbook:ExchangeLost] Reconnexion échouée: %s", exc)
            return False

    def step_partial_warmup(ctx: dict) -> bool:
        # Signal que les données de marché doivent être re-fetchées
        ctx["warmup_required"] = True
        _log.info("[Playbook:ExchangeLost] Warmup partiel requis")
        return True

    return RecoveryPlaybook(
        name="exchange_connection_lost",
        failure_type="exchange",
        description="Perte connexion exchange → reconnexion + warmup partiel",
        max_duration_s=60.0,
        steps=[
            PlaybookStep(
                "detect_exchange",
                step_detect_exchange,
                timeout_s=2.0,
                description="Détecter exchange perdu",
            ),
            PlaybookStep(
                "close_stale",
                step_close_stale_connection,
                timeout_s=5.0,
                required=False,
                description="Fermer connexion stale",
            ),
            PlaybookStep(
                "reconnect",
                step_reconnect,
                timeout_s=30.0,
                retry=3,
                description="Reconnecter exchange",
            ),
            PlaybookStep(
                "partial_warmup",
                step_partial_warmup,
                timeout_s=5.0,
                description="Déclencher warmup partiel",
            ),
        ],
    )


def _pb_lm_studio_failure() -> RecoveryPlaybook:
    """Playbook 3 : LM Studio down → fallback rules + retry périodique."""

    def step_detect_lm_down(ctx: dict) -> bool:
        _log.warning("[Playbook:LMStudioDown] LM Studio inaccessible")
        ctx["lm_down_ts"] = time.time()
        return True

    def step_activate_fallback(ctx: dict) -> bool:
        router = ctx.get("ai_router")
        if router is not None:
            router.mode = "fallback"
            _log.info("[Playbook:LMStudioDown] Fallback activé sur AIRouter")
            return True
        # Marquer via fichier si pas de router
        import json
        from pathlib import Path

        flag = Path("cache/startup/lm_fallback_active.json")
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text(
            json.dumps({"active": True, "ts": time.time()}), encoding="utf-8"
        )
        _log.info("[Playbook:LMStudioDown] Flag fallback écrit")
        return True

    def step_schedule_retry(ctx: dict) -> bool:
        ctx["lm_retry_after_s"] = time.time() + 300  # réessayer dans 5 min
        _log.info("[Playbook:LMStudioDown] Retry LM Studio planifié dans 5 min")
        return True

    def step_notify_degraded(ctx: dict) -> bool:
        notify = ctx.get("notify_fn")
        if notify:
            try:
                notify("[Playbook] LM Studio down — fallback rules actif")
            except Exception:
                pass
        return True

    return RecoveryPlaybook(
        name="lm_studio_failure",
        failure_type="lm_studio",
        description="LM Studio down → fallback rules + retry périodique",
        max_duration_s=30.0,
        steps=[
            PlaybookStep(
                "detect_lm_down",
                step_detect_lm_down,
                timeout_s=2.0,
                description="Détecter LM Studio down",
            ),
            PlaybookStep(
                "activate_fallback",
                step_activate_fallback,
                timeout_s=5.0,
                description="Activer fallback rules",
            ),
            PlaybookStep(
                "schedule_retry",
                step_schedule_retry,
                timeout_s=2.0,
                description="Planifier retry LM Studio",
            ),
            PlaybookStep(
                "notify_degraded",
                step_notify_degraded,
                timeout_s=5.0,
                required=False,
                description="Notifier dégradation",
            ),
        ],
    )


def _pb_database_error() -> RecoveryPlaybook:
    """Playbook 4 : erreur base de données → backup + reconstitution."""

    def step_detect_db_error(ctx: dict) -> bool:
        error = ctx.get("db_error", "inconnu")
        _log.error("[Playbook:DBError] Erreur DB: %s", error)
        ctx["db_error_ts"] = time.time()
        return True

    def step_backup_current(ctx: dict) -> bool:
        import shutil
        from pathlib import Path

        db_paths = ctx.get("db_paths", ["databases/positions_snapshot.json"])
        backed_up = 0
        for p in db_paths:
            src = Path(p)
            if src.exists():
                backup = src.with_suffix(f".bak_{int(time.time())}")
                try:
                    shutil.copy2(src, backup)
                    backed_up += 1
                    _log.info("[Playbook:DBError] Backup: %s → %s", src, backup)
                except Exception as exc:
                    _log.warning("[Playbook:DBError] Backup échoué %s: %s", src, exc)
        _log.info("[Playbook:DBError] %d fichiers sauvegardés", backed_up)
        return True

    def step_rebuild_from_backup(ctx: dict) -> bool:
        import shutil
        from pathlib import Path

        db_paths = ctx.get("db_paths", ["databases/positions_snapshot.json"])
        rebuilt = 0
        for p in db_paths:
            src = Path(p)
            # Chercher le backup le plus récent
            backups = sorted(src.parent.glob(f"{src.stem}.bak_*"), reverse=True)
            if backups:
                try:
                    shutil.copy2(backups[0], src)
                    rebuilt += 1
                    _log.info("[Playbook:DBError] Reconstitué depuis %s", backups[0])
                except Exception as exc:
                    _log.warning("[Playbook:DBError] Reconstitution échouée: %s", exc)
            else:
                # Créer un fichier vide valide
                try:
                    src.parent.mkdir(parents=True, exist_ok=True)
                    src.write_text("{}", encoding="utf-8")
                    rebuilt += 1
                    _log.info("[Playbook:DBError] Fichier DB vide créé: %s", src)
                except Exception as exc:
                    _log.warning("[Playbook:DBError] Création vide échouée: %s", exc)
        return rebuilt > 0

    def step_verify_db_health(ctx: dict) -> bool:
        import json
        from pathlib import Path

        db_paths = ctx.get("db_paths", ["databases/positions_snapshot.json"])
        for p in db_paths:
            src = Path(p)
            try:
                if src.exists():
                    data = json.loads(src.read_text(encoding="utf-8"))
                    assert isinstance(data, (dict, list))
                    _log.info("[Playbook:DBError] DB %s vérifiée OK", src)
            except Exception as exc:
                _log.error("[Playbook:DBError] DB %s invalide: %s", src, exc)
                return False
        return True

    return RecoveryPlaybook(
        name="database_error",
        failure_type="database",
        description="Erreur DB → backup + reconstitution",
        max_duration_s=60.0,
        steps=[
            PlaybookStep(
                "detect_db_error",
                step_detect_db_error,
                timeout_s=2.0,
                description="Détecter erreur DB",
            ),
            PlaybookStep(
                "backup_current",
                step_backup_current,
                timeout_s=15.0,
                required=False,
                description="Sauvegarder DB courante",
            ),
            PlaybookStep(
                "rebuild_from_backup",
                step_rebuild_from_backup,
                timeout_s=15.0,
                description="Reconstituer depuis backup",
            ),
            PlaybookStep(
                "verify_db_health",
                step_verify_db_health,
                timeout_s=5.0,
                description="Vérifier santé DB",
            ),
        ],
    )
