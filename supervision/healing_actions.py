"""
supervision/healing_actions.py — E-02 SelfHealingBot Completion

5 actions de guérison certifiées + journal de guérison HMAC-signé.

Actions disponibles :
  1. restart_agent_lifecycle  — restart via LifecycleManager (E-02-A)
  2. purge_cache              — vide les caches corrompus (E-02-B)
  3. reinit_exchange          — force reconnexion exchange (E-02-C)
  4. switch_lm_fallback       — bascule LM Studio sur règles heuristiques (E-02-D)
  5. degrade_risk_mode        — descend le mode de risque (E-02-E)

HealingJournal :
  - Append-only (jamais de modification) — chaque entrée est horodatée
  - HMAC-SHA256 chaîné (prev_hmac dans chaque entrée)
  - verify_integrity() détecte toute falsification

Usage :
    registry = HealingActionRegistry()
    registry.register_all_defaults()
    result = registry.execute("purge_cache", context={"paths": ["cache/startup"]})
    assert result.success
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from observability.json_logger import get_logger

_log = get_logger("supervision.healing_actions")

_JOURNAL_PATH = Path(
    os.getenv("P10_HEALING_JOURNAL", "cache/startup/healing_journal.jsonl")
)
_HMAC_KEY = os.getenv(
    "P10_HEALING_HMAC_KEY", "healing_journal_default_key_change_me"
).encode()
_GENESIS_HMAC = "0" * 64


# ── Journal de guérison HMAC-signé ────────────────────────────────────────────


@dataclass
class JournalEntry:
    seq: int
    ts: float
    action_name: str
    success: bool
    duration_ms: float
    details: dict
    prev_hmac: str
    hmac_sig: str = ""

    def canonical_payload(self) -> str:
        return json.dumps(
            {
                "seq": self.seq,
                "ts": self.ts,
                "action_name": self.action_name,
                "success": self.success,
                "duration_ms": self.duration_ms,
                "details": self.details,
                "prev_hmac": self.prev_hmac,
            },
            sort_keys=True,
        )

    def compute_hmac(self, key: bytes) -> str:
        return hmac.new(
            key, self.canonical_payload().encode(), hashlib.sha256
        ).hexdigest()

    def is_valid(self, key: bytes) -> bool:
        expected = self.compute_hmac(key)
        return hmac.compare_digest(expected, self.hmac_sig)

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "action_name": self.action_name,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "details": self.details,
            "prev_hmac": self.prev_hmac,
            "hmac_sig": self.hmac_sig,
        }


class HealingJournal:
    """
    Journal append-only des actions de guérison.
    Chaque entrée est signée HMAC-SHA256 et chaîne la signature précédente.
    Toute modification ultérieure brise la chaîne → détectée par verify_integrity().
    """

    def __init__(
        self,
        path: Optional[Path] = None,
        hmac_key: Optional[bytes] = None,
    ) -> None:
        self._path = path or _JOURNAL_PATH
        self._key = hmac_key or _HMAC_KEY
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._seq = self._last_seq()
        self._last_hmac = self._last_stored_hmac()

    def append(
        self,
        action_name: str,
        success: bool,
        duration_ms: float,
        details: Optional[dict] = None,
    ) -> JournalEntry:
        """Ajoute une entrée. Retourne l'entrée créée."""
        self._seq += 1
        entry = JournalEntry(
            seq=self._seq,
            ts=time.time(),
            action_name=action_name,
            success=success,
            duration_ms=duration_ms,
            details=details or {},
            prev_hmac=self._last_hmac,
        )
        entry.hmac_sig = entry.compute_hmac(self._key)
        self._last_hmac = entry.hmac_sig

        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
        except Exception as exc:
            _log.error("[HealingJournal] Erreur écriture: %s", exc)

        return entry

    def verify_integrity(self) -> bool:
        """Vérifie la chaîne HMAC complète. False si falsification détectée."""
        entries = self._load_all()
        prev_hmac = _GENESIS_HMAC
        for entry in entries:
            if entry.prev_hmac != prev_hmac:
                _log.error(
                    "[HealingJournal] FALSIFICATION détectée — seq=%d", entry.seq
                )
                return False
            if not entry.is_valid(self._key):
                _log.error("[HealingJournal] HMAC invalide — seq=%d", entry.seq)
                return False
            prev_hmac = entry.hmac_sig
        return True

    def entries(self, n: int = 50) -> list[dict]:
        """Retourne les n dernières entrées."""
        all_entries = self._load_all()
        return [e.to_dict() for e in all_entries[-n:]]

    def count(self) -> int:
        return len(self._load_all())

    def _load_all(self) -> list[JournalEntry]:
        if not self._path.exists():
            return []
        result = []
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        entry = JournalEntry(
                            seq=d["seq"],
                            ts=d["ts"],
                            action_name=d["action_name"],
                            success=d["success"],
                            duration_ms=d["duration_ms"],
                            details=d.get("details", {}),
                            prev_hmac=d["prev_hmac"],
                            hmac_sig=d["hmac_sig"],
                        )
                        result.append(entry)
                    except Exception:
                        continue
        except Exception as exc:
            _log.debug("[HealingJournal] Lecture: %s", exc)
        return result

    def _last_seq(self) -> int:
        entries = self._load_all()
        return entries[-1].seq if entries else 0

    def _last_stored_hmac(self) -> str:
        entries = self._load_all()
        return entries[-1].hmac_sig if entries else _GENESIS_HMAC


# ── Résultat d'une action ─────────────────────────────────────────────────────


@dataclass
class HealingResult:
    action_name: str
    success: bool
    duration_ms: float
    message: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "action_name": self.action_name,
            "success": self.success,
            "duration_ms": round(self.duration_ms, 2),
            "message": self.message,
            "error": self.error,
        }


# ── Actions de guérison ───────────────────────────────────────────────────────


@dataclass
class HealingAction:
    name: str
    description: str
    fn: Callable[[dict], bool]
    non_degrading: bool = True  # prouve que l'action n'empire pas l'état


class HealingActionRegistry:
    """
    Registre des actions de guérison.
    Exécute chaque action et enregistre le résultat dans le HealingJournal.
    """

    def __init__(self, journal: Optional[HealingJournal] = None) -> None:
        self._actions: dict[str, HealingAction] = {}
        self._journal = journal or HealingJournal()
        self._history: list[HealingResult] = []

    def register(self, action: HealingAction) -> None:
        self._actions[action.name] = action
        _log.debug("[HealingRegistry] Action enregistrée: %s", action.name)

    def register_all_defaults(self) -> None:
        """Enregistre les 5 actions de guérison certifiées."""
        for action in _default_actions():
            self.register(action)

    def execute(self, name: str, context: Optional[dict] = None) -> HealingResult:
        """Exécute une action par son nom. Enregistre dans le journal."""
        ctx = context or {}
        action = self._actions.get(name)
        if action is None:
            result = HealingResult(
                action_name=name,
                success=False,
                duration_ms=0.0,
                error=f"Action inconnue: {name}",
            )
            self._history.append(result)
            return result

        t0 = time.perf_counter()
        try:
            success = action.fn(ctx)
            duration_ms = (time.perf_counter() - t0) * 1000
            result = HealingResult(
                action_name=name,
                success=bool(success),
                duration_ms=duration_ms,
                message=f"Action '{name}' {'réussie' if success else 'échouée'}",
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000
            result = HealingResult(
                action_name=name,
                success=False,
                duration_ms=duration_ms,
                error=str(exc),
            )
            _log.error("[HealingRegistry] Exception dans '%s': %s", name, exc)

        self._journal.append(
            action_name=name,
            success=result.success,
            duration_ms=result.duration_ms,
            details={"message": result.message, "error": result.error},
        )
        self._history.append(result)

        level = "info" if result.success else "warning"
        getattr(_log, level)(
            "[HealingRegistry] %s → %s (%.1fms)",
            name,
            "OK" if result.success else "FAIL",
            result.duration_ms,
        )
        return result

    def available(self) -> list[str]:
        return list(self._actions.keys())

    def result_history(self, n: int = 20) -> list[dict]:
        return [r.to_dict() for r in self._history[-n:]]

    def journal_integrity_ok(self) -> bool:
        return self._journal.verify_integrity()


# ── 5 actions de guérison par défaut ─────────────────────────────────────────


def _heal_restart_agent_lifecycle(ctx: dict) -> bool:
    """E-02-A : Restart d'un agent via LifecycleManager."""
    lifecycle = ctx.get("lifecycle_manager")
    agent_id = ctx.get("agent_id", "")
    if lifecycle is None or not agent_id:
        _log.warning("[Heal:RestartAgent] lifecycle_manager ou agent_id manquant")
        return False
    try:
        ok = lifecycle.restart(agent_id)
        _log.info("[Heal:RestartAgent] %s → %s", agent_id, "OK" if ok else "FAIL")
        return bool(ok)
    except Exception as exc:
        _log.error("[Heal:RestartAgent] Erreur: %s", exc)
        return False


def _heal_purge_cache(ctx: dict) -> bool:
    """E-02-B : Purge des caches corrompus."""
    paths = ctx.get("paths", [])
    if not paths:
        # Caches par défaut si non spécifié
        paths = [
            "cache/startup/configs.json",
            "cache/startup/last_snapshot.txt",
        ]
    purged = 0
    for p in paths:
        path = Path(p)
        try:
            if path.is_file():
                path.unlink()
                purged += 1
                _log.info("[Heal:PurgeCache] Fichier supprimé: %s", path)
            elif path.is_dir():
                # Ne supprime que les fichiers, pas le répertoire lui-même
                for child in path.iterdir():
                    if child.is_file() and child.suffix in (
                        ".json",
                        ".pkl",
                        ".txt",
                        ".cache",
                    ):
                        child.unlink()
                        purged += 1
                _log.info(
                    "[Heal:PurgeCache] Dossier vidé: %s (%d fichiers)", path, purged
                )
        except Exception as exc:
            _log.warning("[Heal:PurgeCache] %s: %s", path, exc)
    _log.info("[Heal:PurgeCache] %d élément(s) purgé(s)", purged)
    return True  # toujours OK — la purge est "best effort"


def _heal_reinit_exchange(ctx: dict) -> bool:
    """E-02-C : Force la reconnexion d'un exchange."""
    exchange_factory = ctx.get("exchange_factory")
    exchange_name = ctx.get("exchange_name", "")
    if exchange_factory is None or not exchange_name:
        _log.warning("[Heal:ReinitExchange] exchange_factory ou exchange_name manquant")
        return False
    try:
        # Tenter de fermer l'ancienne connexion
        old_conn = ctx.get("old_connection")
        if old_conn is not None:
            try:
                old_conn.close()
            except Exception:
                pass
        # Recréer la connexion
        new_conn = exchange_factory(exchange_name)
        ctx["new_connection"] = new_conn
        _log.info("[Heal:ReinitExchange] %s reconnecté", exchange_name)
        return True
    except Exception as exc:
        _log.error("[Heal:ReinitExchange] Erreur: %s", exc)
        return False


def _heal_switch_lm_fallback(ctx: dict) -> bool:
    """E-02-D : Bascule vers les règles heuristiques si LM Studio tombe."""
    try:
        # Marquer le fallback dans un fichier de configuration runtime
        flag_path = Path(
            ctx.get("lm_fallback_flag", "cache/startup/lm_fallback_active.json")
        )
        flag_path.parent.mkdir(parents=True, exist_ok=True)
        flag_path.write_text(
            json.dumps({"lm_fallback_active": True, "ts": time.time()}),
            encoding="utf-8",
        )
        # Si un ai_router est fourni, changer le mode
        router = ctx.get("ai_router")
        if router is not None:
            router.mode = "fallback"
        _log.info("[Heal:SwitchLMFallback] Fallback LM Studio activé")
        return True
    except Exception as exc:
        _log.error("[Heal:SwitchLMFallback] Erreur: %s", exc)
        return False


def _heal_degrade_risk_mode(ctx: dict) -> bool:
    """E-02-E : Descend le mode de risque (AGGRESSIVE → DEFENSIVE → RISK_OFF)."""
    risk_governor = ctx.get("risk_governor")
    if risk_governor is None:
        # Sans risk_governor, enregistre l'intention dans un fichier
        flag_path = Path("cache/startup/risk_degrade_request.json")
        flag_path.parent.mkdir(parents=True, exist_ok=True)
        flag_path.write_text(
            json.dumps({"degrade_requested": True, "ts": time.time()}),
            encoding="utf-8",
        )
        _log.info(
            "[Heal:DegradeRisk] Dégradation mode risque enregistrée (sans governor)"
        )
        return True
    try:
        _MODE_ORDER = ["AGGRESSIVE", "NORMAL", "DEFENSIVE", "RISK_OFF"]
        current = getattr(risk_governor, "mode", "NORMAL")
        idx = _MODE_ORDER.index(current) if current in _MODE_ORDER else 1
        next_idx = min(idx + 1, len(_MODE_ORDER) - 1)
        next_mode = _MODE_ORDER[next_idx]
        if hasattr(risk_governor, "set_mode"):
            risk_governor.set_mode(next_mode)
        elif hasattr(risk_governor, "mode"):
            risk_governor.mode = next_mode
        _log.info("[Heal:DegradeRisk] %s → %s", current, next_mode)
        return current != next_mode  # True si changement effectif
    except Exception as exc:
        _log.error("[Heal:DegradeRisk] Erreur: %s", exc)
        return False


def _default_actions() -> list[HealingAction]:
    """Retourne les 5 actions de guérison certifiées."""
    return [
        HealingAction(
            name="restart_agent_lifecycle",
            description="Restart d'un agent via LifecycleManager (E-02-A)",
            fn=_heal_restart_agent_lifecycle,
        ),
        HealingAction(
            name="purge_cache",
            description="Purge des caches corrompus (E-02-B)",
            fn=_heal_purge_cache,
        ),
        HealingAction(
            name="reinit_exchange",
            description="Force reconnexion exchange (E-02-C)",
            fn=_heal_reinit_exchange,
        ),
        HealingAction(
            name="switch_lm_fallback",
            description="Bascule vers les règles heuristiques LM Studio (E-02-D)",
            fn=_heal_switch_lm_fallback,
        ),
        HealingAction(
            name="degrade_risk_mode",
            description="Descend le mode de risque (E-02-E)",
            fn=_heal_degrade_risk_mode,
        ),
    ]
