"""
pending_order_tracker.py — Suivi du cycle de vie des ordres soumis.

Statuts :
  NEW          : soumis, pas encore confirmé par l'exchange
  PARTIAL_FILL : partiellement exécuté (filled_qty < requested_qty)
  FILLED       : complètement exécuté
  CANCELLED    : annulé (exchange ou utilisateur)
  EXPIRED      : non exécuté passé le TTL
  UNKNOWN      : statut non récupérable (perte réseau, timeout fetch)

Invariants :
  - Un ordre FILLED ou CANCELLED ne revient jamais à NEW
  - filled_qty <= requested_qty
  - Un ordre > TTL sans résolution devient EXPIRED automatiquement
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from observability.json_logger import get_logger

_log = get_logger("system.pending_order_tracker")

# Statuts valides et transitions autorisées
_TERMINAL_STATUSES = frozenset({"FILLED", "CANCELLED", "EXPIRED", "UNKNOWN"})
_VALID_STATUSES = frozenset(
    {"NEW", "PARTIAL_FILL", "FILLED", "CANCELLED", "EXPIRED", "UNKNOWN"}
)
_VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "NEW": frozenset({"PARTIAL_FILL", "FILLED", "CANCELLED", "EXPIRED", "UNKNOWN"}),
    "PARTIAL_FILL": frozenset({"FILLED", "CANCELLED", "EXPIRED", "UNKNOWN"}),
    "FILLED": frozenset(),
    "CANCELLED": frozenset(),
    "EXPIRED": frozenset(),
    "UNKNOWN": frozenset(),
}

_DEFAULT_TTL_S = 300  # 5 min


@dataclass
class PendingOrder:
    order_id: str
    symbol: str
    side: str  # "BUY" | "SELL"
    requested_qty: float
    filled_qty: float = 0.0
    status: str = "NEW"
    created_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    rejection_reason: Optional[str] = None
    exchange: str = "unknown"
    mode: str = "paper"

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL_STATUSES

    @property
    def is_partial(self) -> bool:
        return self.status == "PARTIAL_FILL"

    @property
    def unfilled_qty(self) -> float:
        return max(0.0, self.requested_qty - self.filled_qty)

    @property
    def fill_ratio(self) -> float:
        if self.requested_qty <= 0:
            return 0.0
        return self.filled_qty / self.requested_qty

    def age_s(self) -> float:
        return time.time() - self.created_at

    def is_expired(self, ttl_s: float = _DEFAULT_TTL_S) -> bool:
        return not self.is_terminal and self.age_s() > ttl_s

    def transition(self, new_status: str, filled_qty: Optional[float] = None) -> None:
        if new_status not in _VALID_STATUSES:
            raise ValueError(f"Statut invalide: {new_status}")
        allowed = _VALID_TRANSITIONS.get(self.status, frozenset())
        if new_status not in allowed:
            raise ValueError(f"Transition interdite: {self.status} → {new_status}")
        if filled_qty is not None:
            self.filled_qty = min(filled_qty, self.requested_qty)
        self.status = new_status
        if new_status in _TERMINAL_STATUSES:
            self.resolved_at = time.time()

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "requested_qty": self.requested_qty,
            "filled_qty": self.filled_qty,
            "status": self.status,
            "fill_ratio": round(self.fill_ratio, 4),
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "rejection_reason": self.rejection_reason,
            "mode": self.mode,
        }


@dataclass
class OrderReconcileReport:
    timestamp: float = field(default_factory=time.time)
    checked: int = 0
    partial_fills: list = field(default_factory=list)
    cancelled: list = field(default_factory=list)
    expired: list = field(default_factory=list)
    unknown: list = field(default_factory=list)
    unresolved_past_ttl: list = field(default_factory=list)
    exchange_reachable: bool = True
    error: Optional[str] = None

    @property
    def is_clean(self) -> bool:
        return (
            self.exchange_reachable
            and not self.partial_fills
            and not self.cancelled
            and not self.expired
            and not self.unknown
            and not self.unresolved_past_ttl
        )

    @property
    def has_anomaly(self) -> bool:
        return not self.is_clean

    def summary(self) -> str:
        parts = []
        if not self.exchange_reachable:
            parts.append("EXCHANGE_UNREACHABLE")
        if self.partial_fills:
            parts.append(f"PARTIAL={self.partial_fills}")
        if self.cancelled:
            parts.append(f"CANCELLED={self.cancelled}")
        if self.expired:
            parts.append(f"EXPIRED={self.expired}")
        if self.unknown:
            parts.append(f"UNKNOWN={self.unknown}")
        if self.unresolved_past_ttl:
            parts.append(f"UNRESOLVED={self.unresolved_past_ttl}")
        return " | ".join(parts) if parts else "CLEAN"


class PendingOrderTracker:
    """
    Registre central des ordres en vol.

    Cycle de vie d'un ordre :
      register() → [update_from_exchange()] → resolve()

    reconcile_with_exchange() : snapshot de tous les ordres en anomalie.
    expire_stale() : marque EXPIRED les ordres > TTL.
    """

    def __init__(self, ttl_s: float = _DEFAULT_TTL_S) -> None:
        self._orders: dict[str, PendingOrder] = {}
        self._ttl_s = ttl_s

    # ── API publique ─────────────────────────────────────────────────────────

    def register(
        self,
        order_id: str,
        symbol: str,
        side: str,
        qty: float,
        mode: str = "paper",
        exchange: str = "unknown",
    ) -> PendingOrder:
        """Enregistre un nouvel ordre soumis."""
        if order_id in self._orders:
            _log.warning("[PendingOrderTracker] Ordre déjà enregistré: %s", order_id)
            return self._orders[order_id]

        order = PendingOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            requested_qty=qty,
            mode=mode,
            exchange=exchange,
        )
        self._orders[order_id] = order
        _log.debug(
            "[PendingOrderTracker] NEW %s %s %s qty=%.6f",
            order_id,
            symbol,
            side,
            qty,
        )
        return order

    def update_from_exchange(
        self,
        order_id: str,
        exchange_status: str,
        filled_qty: float,
        rejection_reason: Optional[str] = None,
    ) -> Optional[PendingOrder]:
        """
        Met à jour l'état d'un ordre après consultation de l'exchange.

        exchange_status: valeur CCXT ("open", "closed", "canceled", "expired")
        → normalisé vers nos statuts internes.
        """
        order = self._orders.get(order_id)
        if not order:
            _log.warning("[PendingOrderTracker] Ordre inconnu: %s", order_id)
            return None

        if order.is_terminal:
            return order

        normalized = self._normalize_ccxt_status(
            exchange_status, filled_qty, order.requested_qty
        )
        try:
            order.transition(normalized, filled_qty=filled_qty)
            if rejection_reason:
                order.rejection_reason = rejection_reason
            _log.debug(
                "[PendingOrderTracker] UPDATE %s → %s fill=%.4f",
                order_id,
                normalized,
                filled_qty,
            )
        except ValueError as exc:
            _log.warning(
                "[PendingOrderTracker] Transition invalide %s: %s", order_id, exc
            )
        return order

    def resolve(self, order_id: str, final_status: str) -> Optional[PendingOrder]:
        """Force la résolution d'un ordre (FILLED/CANCELLED/EXPIRED/UNKNOWN)."""
        order = self._orders.get(order_id)
        if not order or order.is_terminal:
            return order
        try:
            order.transition(final_status)
        except ValueError as exc:
            _log.warning(
                "[PendingOrderTracker] Résolution invalide %s: %s", order_id, exc
            )
        return order

    def expire_stale(self) -> list[str]:
        """Marque EXPIRED tous les ordres dépassant le TTL. Retourne les IDs expirés."""
        expired_ids = []
        for order_id, order in self._orders.items():
            if order.is_expired(self._ttl_s):
                try:
                    order.transition("EXPIRED")
                    expired_ids.append(order_id)
                    _log.warning(
                        "[PendingOrderTracker] EXPIRED %s %s (age=%.0fs)",
                        order_id,
                        order.symbol,
                        order.age_s(),
                    )
                except ValueError:
                    pass
        return expired_ids

    def get_pending(self) -> list[PendingOrder]:
        """Retourne tous les ordres non-terminaux."""
        return [o for o in self._orders.values() if not o.is_terminal]

    def get_unresolved_past_ttl(self) -> list[PendingOrder]:
        """Ordres non-terminaux dépassant le TTL (avant expire_stale)."""
        return [
            o
            for o in self._orders.values()
            if not o.is_terminal and o.is_expired(self._ttl_s)
        ]

    def get_partial_fills(self) -> list[PendingOrder]:
        return [o for o in self._orders.values() if o.status == "PARTIAL_FILL"]

    def count_pending(self) -> int:
        return len(self.get_pending())

    def reconcile_with_exchange(self, exchange) -> OrderReconcileReport:
        """
        Cross-check tous les ordres pending avec l'exchange.
        Ne lève jamais d'exception.
        """
        report = OrderReconcileReport()

        # D'abord, expirer les ordres trop vieux et les inclure dans le rapport
        newly_expired = self.expire_stale()
        report.expired.extend(newly_expired)

        pending = self.get_pending()
        report.checked = len(pending)

        if not pending:
            return report

        for order in pending:
            try:
                ex_order = exchange.fetch_order(order.order_id, order.symbol)
                status = ex_order.get("status", "unknown")
                filled = float(ex_order.get("filled", 0) or 0)

                self.update_from_exchange(order.order_id, status, filled)

                if order.status == "PARTIAL_FILL":
                    report.partial_fills.append(order.order_id)
                elif order.status == "CANCELLED":
                    report.cancelled.append(order.order_id)
                elif order.status == "EXPIRED":
                    report.expired.append(order.order_id)
                elif order.status == "UNKNOWN":
                    report.unknown.append(order.order_id)

            except Exception as exc:
                report.exchange_reachable = False
                report.error = f"fetch_order({order.order_id}) failed: {exc}"
                report.unknown.append(order.order_id)
                _log.warning("[PendingOrderTracker] %s", report.error)

        report.unresolved_past_ttl = [
            o.order_id for o in self.get_unresolved_past_ttl()
        ]

        if report.has_anomaly:
            _log.warning("[PendingOrderTracker] ANOMALIES: %s", report.summary())

        return report

    def snapshot(self) -> dict:
        pending = self.get_pending()
        return {
            "total_tracked": len(self._orders),
            "pending": len(pending),
            "partial_fills": len(self.get_partial_fills()),
            "unresolved_past_ttl": len(self.get_unresolved_past_ttl()),
            "orders": [o.to_dict() for o in pending],
        }

    # ── Internals ────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_ccxt_status(
        ccxt_status: str, filled_qty: float, requested_qty: float
    ) -> str:
        """Traduit le statut CCXT en statut interne."""
        s = (ccxt_status or "").lower()
        if s in ("closed", "filled"):
            return "FILLED"
        if s in ("canceled", "cancelled"):
            return "CANCELLED"
        if s == "expired":
            return "EXPIRED"
        if s == "open":
            if filled_qty > 0 and filled_qty < requested_qty:
                return "PARTIAL_FILL"
            return "NEW"
        return "UNKNOWN"
