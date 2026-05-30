"""
boot_gate.py — Verrou de démarrage (P12-A).

Garantit :
  reconciliation propre AVANT toute autorisation de trading.

Principe :
  BootGate.check() est appelé dans ColdStartManager avant de passer
  en LIVE_READY. Si la réconciliation retourne has_drift=True ou si
  des ordres en anomalie existent, le gate BLOQUE le trading.

  Aucun ordre n'est soumis tant que is_cleared() == False.

Usage :
    gate = BootGate(reconciler, order_tracker)
    report = gate.check()
    if gate.is_cleared():
        advisor_loop.start()
    else:
        log.critical("Boot gate NOT cleared: %s", report.reason)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from observability.json_logger import get_logger

_log = get_logger("system.boot_gate")


@dataclass
class BootGateReport:
    cleared: bool
    timestamp: float = field(default_factory=time.time)
    position_reconcile_clean: bool = False
    order_reconcile_clean: bool = False
    reason: Optional[str] = None
    ghost_positions: list = field(default_factory=list)
    orphan_positions: list = field(default_factory=list)
    partial_orders: list = field(default_factory=list)
    cancelled_orders: list = field(default_factory=list)
    expired_orders: list = field(default_factory=list)
    unknown_orders: list = field(default_factory=list)
    exchange_reachable: bool = True

    def summary(self) -> str:
        if self.cleared:
            return "CLEARED — trading autorisé"
        parts = []
        if not self.exchange_reachable:
            parts.append("EXCHANGE_UNREACHABLE")
        if self.ghost_positions:
            parts.append(f"GHOST={self.ghost_positions}")
        if self.orphan_positions:
            parts.append(f"ORPHAN={self.orphan_positions}")
        if self.partial_orders:
            parts.append(f"PARTIAL_ORDERS={self.partial_orders}")
        if self.cancelled_orders:
            parts.append(f"CANCELLED={self.cancelled_orders}")
        if self.expired_orders:
            parts.append(f"EXPIRED={self.expired_orders}")
        if self.unknown_orders:
            parts.append(f"UNKNOWN={self.unknown_orders}")
        if self.reason:
            parts.append(f"reason={self.reason}")
        return " | ".join(parts) if parts else "NOT_CLEARED"


class TradingBlockedError(RuntimeError):
    """Levée si un ordre est tenté avant que le boot gate soit levé."""


class BootGate:
    """
    Verrou de démarrage.

    reconciler    : PositionReconciler
    order_tracker : PendingOrderTracker (optionnel)
    """

    def __init__(self, reconciler, order_tracker=None) -> None:
        self._reconciler = reconciler
        self._tracker = order_tracker
        self._cleared = False
        self._last_report: Optional[BootGateReport] = None

    # ── API publique ─────────────────────────────────────────────────────────

    def check(self, exchange=None) -> BootGateReport:
        """
        Lance la vérification complète et met à jour le statut du gate.

        1. Réconciliation des positions (exchange vs interne)
        2. Réconciliation des ordres pending (si order_tracker fourni)

        Retourne BootGateReport.
        """
        report = BootGateReport(cleared=False)

        # ── 1. Position reconciliation ────────────────────────────────────────
        try:
            pos_report = self._reconciler.reconcile(force=True)
            report.exchange_reachable = pos_report.exchange_reachable

            if not pos_report.exchange_reachable:
                report.reason = f"Exchange inaccessible: {pos_report.error}"
                _log.critical("[BootGate] %s", report.reason)
                self._last_report = report
                return report

            report.ghost_positions = pos_report.ghost_positions
            report.orphan_positions = pos_report.orphan_positions
            report.position_reconcile_clean = pos_report.is_clean

        except Exception as exc:
            report.exchange_reachable = False
            report.reason = f"Position reconcile exception: {exc}"
            _log.critical("[BootGate] %s", report.reason)
            self._last_report = report
            return report

        # ── 2. Order reconciliation ───────────────────────────────────────────
        if self._tracker is not None and exchange is not None:
            try:
                order_report = self._tracker.reconcile_with_exchange(exchange)
                report.partial_orders = order_report.partial_fills
                report.cancelled_orders = order_report.cancelled
                report.expired_orders = order_report.expired
                report.unknown_orders = order_report.unknown
                report.order_reconcile_clean = order_report.is_clean
            except Exception as exc:
                report.reason = f"Order reconcile exception: {exc}"
                _log.critical("[BootGate] %s", report.reason)
                self._last_report = report
                return report
        else:
            report.order_reconcile_clean = True

        # ── 3. Décision finale ────────────────────────────────────────────────
        has_drift = bool(
            report.ghost_positions
            or report.orphan_positions
            or report.partial_orders
            or report.cancelled_orders
            or report.expired_orders
            or report.unknown_orders
        )

        if has_drift:
            report.reason = f"Anomalies détectées: {report.summary()}"
            _log.critical("[BootGate] BLOQUÉ — %s", report.reason)
        else:
            report.cleared = True
            self._cleared = True
            _log.info("[BootGate] LEVÉ — trading autorisé")

        self._last_report = report
        return report

    def is_cleared(self) -> bool:
        """True seulement après un check() propre."""
        return self._cleared

    def require_clearance(self) -> None:
        """
        À appeler avant tout ordre.
        Lève TradingBlockedError si le gate n'est pas levé.
        """
        if not self._cleared:
            reason = self._last_report.reason if self._last_report else "non initialisé"
            raise TradingBlockedError(f"Trading bloqué — boot gate non levé: {reason}")

    def revoke(self) -> None:
        """Révoque le gate (ex: nouvelle anomalie détectée en cours de session)."""
        if self._cleared:
            _log.critical("[BootGate] RÉVOQUÉ — trading suspendu")
        self._cleared = False

    def last_report(self) -> Optional[BootGateReport]:
        return self._last_report
