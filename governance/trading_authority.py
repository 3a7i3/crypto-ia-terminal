"""
governance/trading_authority.py — G1 : Autorité Unique de Trading.

UNE seule instance décide si le système peut trader.

Règles (Constitution, Article 1) :
    - Tout agent qui veut stopper le trading appelle request_halt()
    - Tout agent qui veut reprendre appelle request_resume()
    - Tout moteur d'exécution appelle can_trade() avant de placer un ordre
    - L'état courant est le MINIMUM (plus restrictif) de toutes les demandes actives

Niveaux (du plus restrictif au plus permissif) :
    EMERGENCY → SAFE_MODE → RESTRICTED → WARNING → CLEAR

Usage:
    from governance.trading_authority import trading_authority

    # Demande d'arrêt (n'importe quel agent)
    trading_authority.request_halt(
        source="ExchangeMonitor",
        level=AuthorityLevel.SAFE_MODE,
        reason="exchange_timeout",
    )

    # Vérification avant ordre
    if not trading_authority.can_trade():
        return  # bloqué

    # Reprise (l'agent annule sa propre demande)
    trading_authority.request_resume(source="ExchangeMonitor", reason="exchange_back_online")

    # Snapshot complet pour dashboard G3
    snapshot = trading_authority.status_snapshot()
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from governance.authority_state import TRADING_POLICY, AuthorityLevel, TradingPolicy
from observability.json_logger import get_logger

_log = get_logger("governance.trading_authority")

_AUDIT_LOG = Path("logs/governance_audit.jsonl")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class HaltRequest:
    source: str
    level: AuthorityLevel
    reason: str
    timestamp_utc: str = field(default_factory=_utc_now)


@dataclass
class AuthoritySnapshot:
    """Snapshot complet lisible par le dashboard G3."""

    current_level: AuthorityLevel
    policy: TradingPolicy
    active_halts: List[HaltRequest]
    last_change_utc: str
    since_utc: str

    def as_dict(self) -> dict:
        return {
            "current_level": self.current_level.value,
            "policy": {
                "can_trade": self.policy.can_trade,
                "can_fetch_data": self.policy.can_fetch_data,
                "can_place_orders": self.policy.can_place_orders,
                "size_factor": self.policy.size_factor,
                "description": self.policy.description,
            },
            "active_halts": [
                {
                    "source": h.source,
                    "level": h.level.value,
                    "reason": h.reason,
                    "timestamp_utc": h.timestamp_utc,
                }
                for h in self.active_halts
            ],
            "last_change_utc": self.last_change_utc,
            "since_utc": self.since_utc,
        }

    def format_dashboard(self) -> str:
        """Affichage texte lisible en < 10 secondes (Constitution, Article G3)."""
        lines = [
            "═══════════════════════════════════════",
            f"  SYSTEM STATUS : {self.current_level.value}",
            f"  {self.policy.description}",
            "───────────────────────────────────────",
        ]
        if self.active_halts:
            lines.append("  Sources :")
            for h in self.active_halts:
                lines.append(f"    • [{h.level.value}] {h.source}")
                lines.append(f"      Reason : {h.reason}")
                lines.append(f"      Since  : {h.timestamp_utc}")
        else:
            lines.append("  Sources : none (nominal)")
        lines += [
            "───────────────────────────────────────",
            f"  Last change : {self.last_change_utc}",
            "═══════════════════════════════════════",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# TradingAuthority
# ---------------------------------------------------------------------------


class TradingAuthority:
    """
    Autorité unique de trading (singleton).

    Thread-safe. Toutes les lectures/écritures sont protégées par un verrou.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # source → HaltRequest actif
        self._halts: Dict[str, HaltRequest] = {}
        self._current_level = AuthorityLevel.CLEAR
        self._since_utc = _utc_now()
        self._last_change_utc = _utc_now()

        _AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def can_trade(self) -> bool:
        """
        Retourne True uniquement si l'état courant autorise les ordres.
        À appeler AVANT tout placement d'ordre (Constitution, Article 1).
        """
        with self._lock:
            return TRADING_POLICY[self._current_level].can_trade

    def can_fetch_data(self) -> bool:
        with self._lock:
            return TRADING_POLICY[self._current_level].can_fetch_data

    def current_level(self) -> AuthorityLevel:
        with self._lock:
            return self._current_level

    def policy(self) -> TradingPolicy:
        with self._lock:
            return TRADING_POLICY[self._current_level]

    def request_halt(
        self,
        source: str,
        level: AuthorityLevel,
        reason: str,
    ) -> AuthorityLevel:
        """
        Enregistre une demande d'arrêt depuis `source` au niveau `level`.

        L'état résultant est le MINIMUM de toutes les demandes actives.
        Retourne le nouveau niveau effectif.
        (Constitution, Article 1 + Article 4)
        """
        if not reason or not reason.strip():
            raise ValueError(
                f"[TradingAuthority] request_halt depuis '{source}' sans raison explicite "
                "(Constitution, Article 4)."
            )
        with self._lock:
            halts_before = list(self._halts.keys())
            halt = HaltRequest(source=source, level=level, reason=reason)
            self._halts[source] = halt
            new_level = self._compute_level()
            changed = new_level != self._current_level
            if changed:
                self._since_utc = _utc_now()
            self._current_level = new_level
            self._last_change_utc = _utc_now()

        self._audit(
            event="halt_requested",
            source=source,
            level=level.value,
            reason=reason,
            active_halts_before=halts_before,
            effective_level=new_level.value,
        )
        _log.warning(
            "halt_requested",
            source=source,
            requested_level=level.value,
            effective_level=new_level.value,
            reason=reason,
        )
        return new_level

    def request_resume(self, source: str, reason: str) -> AuthorityLevel:
        """
        Annule la demande d'arrêt de `source`.

        L'état résultant est recalculé depuis les demandes restantes.
        Retourne le nouveau niveau effectif.
        (Constitution, Article 1 + Article 3)
        """
        with self._lock:
            previous_level = self._current_level
            removed = self._halts.pop(source, None)
            if removed is None:
                return self._current_level
            new_level = self._compute_level()
            changed = new_level != previous_level
            if changed:
                self._since_utc = _utc_now()
            self._current_level = new_level
            self._last_change_utc = _utc_now()

        self._audit(
            event="resume_requested",
            source=source,
            reason=reason,
            previous_level=previous_level.value,
            effective_level=new_level.value,
        )
        _log.info(
            "resume_requested",
            source=source,
            previous_level=previous_level.value,
            new_level=new_level.value,
            reason=reason,
        )
        return new_level

    def force_emergency(self, source: str, reason: str) -> None:
        """
        Passage immédiat en EMERGENCY, toutes sources confondues.
        Utilisé par les kill switches Telegram et les circuit breakers critiques.
        """
        self.request_halt(source=source, level=AuthorityLevel.EMERGENCY, reason=reason)

    def status_snapshot(self) -> AuthoritySnapshot:
        """Retourne un snapshot complet pour le dashboard G3."""
        with self._lock:
            return AuthoritySnapshot(
                current_level=self._current_level,
                policy=TRADING_POLICY[self._current_level],
                active_halts=list(self._halts.values()),
                last_change_utc=self._last_change_utc,
                since_utc=self._since_utc,
            )

    def active_sources(self) -> List[str]:
        """Retourne la liste des sources ayant un arrêt actif."""
        with self._lock:
            return list(self._halts.keys())

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _compute_level(self) -> AuthorityLevel:
        """Niveau effectif = minimum (plus restrictif) de toutes les demandes."""
        if not self._halts:
            return AuthorityLevel.CLEAR
        return min(h.level for h in self._halts.values())

    def _audit(self, event: str, **kwargs: object) -> None:
        """Écrit une entrée dans le journal d'audit de gouvernance."""
        record = {"event": event, "timestamp_utc": _utc_now(), **kwargs}
        try:
            with _AUDIT_LOG.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            _log.error("audit_write_failed", error=str(exc))


# ---------------------------------------------------------------------------
# Singleton global
# ---------------------------------------------------------------------------

#: Instance unique — importer et utiliser directement.
trading_authority: TradingAuthority = TradingAuthority()
