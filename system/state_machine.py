"""
system/state_machine.py — Machine d'états globale du système.

Persiste l'état courant dans databases/system_state.json.
Source de vérité pour le debugging forensic et la recovery.

États :
  NORMAL        — trading actif, aucun problème
  DEGRADED      — trading actif mais avec contraintes (taille réduite, etc.)
  HALTED        — trading arrêté (risk limit, gouvernance)
  RECOVERY      — post-HALT, trading prudemment repris
  SAFE_MODE     — mode lecture seule (signaux seulement, pas d'ordres)

Usage :
    from system.state_machine import get_state_machine
    sm = get_state_machine()
    sm.transition("HALTED", reason="drawdown > 5%", halt_source="AutoDecisionEngine")
    sm.update_heartbeat(n_signals=2, n_orders=0, exchange_ok=True)
    sm.transition("RECOVERY")
    sm.to_normal_if_stable(n_consecutive_ok=3)
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_STATE_PATH = os.getenv("SYSTEM_STATE_FILE", "databases/system_state.json")

_VALID_STATES = {"NORMAL", "DEGRADED", "HALTED", "RECOVERY", "SAFE_MODE"}

# Après N heartbeats sans incident en RECOVERY → retour NORMAL
_RECOVERY_STABLE_THRESHOLD = int(os.getenv("RECOVERY_STABLE_CYCLES", "10"))

# Alerte si aucun ordre depuis N secondes malgré signaux actionnables
_STALL_ALERT_SECONDS = int(os.getenv("STALL_ALERT_SECONDS", "1800"))  # 30 min


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_state() -> dict:
    return {
        "state": "NORMAL",
        "previous_state": None,
        "transitioned_at": _now_iso(),
        "halt_reason": None,
        "halt_source": None,
        "halted_at": None,
        "recovery_consecutive_ok": 0,
        "trading_enabled": True,
        "open_positions_count": 0,
        "exchange_sync_ok": True,
        "last_successful_order_at": None,
        "last_exchange_ping": None,
        "last_heartbeat_at": None,
        "n_signals_last_cycle": 0,
        "n_orders_last_cycle": 0,
        "stall_alert_active": False,
        "updated_at": _now_iso(),
    }


class SystemStateMachine:
    """Machine d'états persistée pour le système de trading."""

    def __init__(self, path: str = _STATE_PATH) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    # ── Lecture ───────────────────────────────────────────────────────────────

    @property
    def state(self) -> str:
        return self._state["state"]

    @property
    def trading_enabled(self) -> bool:
        return self._state.get("trading_enabled", True)

    @property
    def is_halted(self) -> bool:
        return self._state["state"] == "HALTED"

    def get(self, key: str, default=None):
        return self._state.get(key, default)

    def snapshot(self) -> dict:
        return dict(self._state)

    # ── Transitions d'état ────────────────────────────────────────────────────

    def transition(
        self,
        new_state: str,
        reason: str = "",
        halt_source: str = "",
    ) -> bool:
        if new_state not in _VALID_STATES:
            return False

        old = self._state["state"]
        if old == new_state:
            return False

        self._state["previous_state"] = old
        self._state["state"] = new_state
        self._state["transitioned_at"] = _now_iso()

        if new_state == "HALTED":
            self._state["trading_enabled"] = False
            self._state["halt_reason"] = reason
            self._state["halt_source"] = halt_source
            self._state["halted_at"] = _now_iso()
            self._state["recovery_consecutive_ok"] = 0
        elif new_state in ("NORMAL", "RECOVERY"):
            self._state["trading_enabled"] = True
            if new_state == "NORMAL":
                self._state["halt_reason"] = None
                self._state["halt_source"] = None
                self._state["halted_at"] = None
                self._state["recovery_consecutive_ok"] = 0
        elif new_state == "SAFE_MODE":
            self._state["trading_enabled"] = False
        elif new_state == "DEGRADED":
            self._state["trading_enabled"] = True

        self._save()
        return True

    def to_normal_if_stable(
        self, n_consecutive_ok: int = _RECOVERY_STABLE_THRESHOLD
    ) -> bool:
        """En état RECOVERY : passe à NORMAL après N cycles propres."""
        if self._state["state"] != "RECOVERY":
            return False
        ok = self._state.get("recovery_consecutive_ok", 0)
        if ok >= n_consecutive_ok:
            self.transition("NORMAL", reason=f"Stable after {ok} clean cycles")
            return True
        return False

    # ── Heartbeat ─────────────────────────────────────────────────────────────

    def update_heartbeat(
        self,
        n_signals: int = 0,
        n_orders: int = 0,
        exchange_ok: bool = True,
        open_positions: int = 0,
    ) -> dict:
        """
        Appelé à chaque cycle d'advisor_loop.
        Retourne un dict avec les alertes actives.
        """
        now_ts = time.time()
        now_iso = _now_iso()

        self._state["last_heartbeat_at"] = now_iso
        self._state["n_signals_last_cycle"] = n_signals
        self._state["n_orders_last_cycle"] = n_orders
        self._state["exchange_sync_ok"] = exchange_ok
        self._state["open_positions_count"] = open_positions

        if n_orders > 0:
            self._state["last_successful_order_at"] = now_iso
            # Incrémenter compteur de stabilité si en RECOVERY
            if self._state["state"] == "RECOVERY":
                self._state["recovery_consecutive_ok"] = (
                    self._state.get("recovery_consecutive_ok", 0) + 1
                )

        # ── Stall detection ───────────────────────────────────────────────────
        stall = False
        last_order_iso = self._state.get("last_successful_order_at")
        if (
            n_signals > 0
            and n_orders == 0
            and last_order_iso
            and self._state["state"] == "NORMAL"
        ):
            try:
                last_ts = datetime.fromisoformat(
                    last_order_iso.replace("Z", "+00:00")
                ).timestamp()
                elapsed = now_ts - last_ts
                if elapsed > _STALL_ALERT_SECONDS:
                    stall = True
            except Exception:
                pass

        self._state["stall_alert_active"] = stall
        self._state["updated_at"] = now_iso
        self._save()

        alerts = {}
        if stall:
            alerts["STALL"] = (
                f"No order despite {n_signals} signal(s)"
                " — check governance/risk pipeline"
            )
        if not exchange_ok:
            alerts["EXCHANGE_DOWN"] = "Exchange connectivity issue"
        if self.is_halted:
            alerts["HALTED"] = self._state.get("halt_reason", "unknown")

        return alerts

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return _default_state()

    def _save(self) -> None:
        tmp = str(self._path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, ensure_ascii=False)
        os.replace(tmp, str(self._path))


# ── Singleton ─────────────────────────────────────────────────────────────────

_sm: Optional[SystemStateMachine] = None


def get_state_machine() -> SystemStateMachine:
    global _sm
    if _sm is None:
        _sm = SystemStateMachine()
    return _sm
