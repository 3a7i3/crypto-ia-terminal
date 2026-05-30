"""
P12-A — Exchange Reality Layer.

Valide que l'état local reste cohérent avec l'état exchange dans tous
les scénarios d'anomalie réels :

  A1 — Orphan position (exchange sans interne)
  A2 — Ghost position (interne sans exchange)
  A3 — Partial fill (ordre partiellement exécuté)
  A4 — Cancelled order (annulé côté exchange)
  A5 — Expired order (non exécuté après TTL)
  A6 — Network loss (perte réseau pendant exécution)
  A7 — Boot gate (aucun trading avant réconciliation propre)
  A8 — Order state machine (transitions valides / invalides)
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from system.boot_gate import BootGate, TradingBlockedError
from system.pending_order_tracker import PendingOrder, PendingOrderTracker

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_tracker(ttl_s: float = 300.0) -> PendingOrderTracker:
    return PendingOrderTracker(ttl_s=ttl_s)


def _make_reconciler(exchange_positions=None, internal_positions=None, clean=True):
    """Mock de PositionReconciler."""
    from system.position_reconciler import ReconcileReport

    rec = MagicMock()
    report = ReconcileReport()
    if exchange_positions is not None:
        report.exchange_positions = exchange_positions
    if internal_positions is not None:
        report.internal_positions = internal_positions
    if not clean:
        report.ghost_positions = ["BTC/USDT"]
    rec.reconcile.return_value = report
    return rec


def _make_exchange_for_order(
    order_id: str,
    status: str = "open",
    filled: float = 0.0,
) -> MagicMock:
    """Mock d'exchange retournant un statut d'ordre."""
    exchange = MagicMock()
    exchange.fetch_order.return_value = {
        "id": order_id,
        "status": status,
        "filled": filled,
        "side": "buy",
    }
    return exchange


# ══════════════════════════════════════════════════════════════════════════════
# A3 — Partial Fill Detection
# ══════════════════════════════════════════════════════════════════════════════


class TestA3PartialFill:
    """Un ordre partiellement exécuté est détecté et tracké correctement."""

    def test_partial_fill_detected_from_exchange(self):
        """Exchange retourne filled < requested → statut PARTIAL_FILL."""
        tracker = _make_tracker()
        tracker.register("ord-001", "BTC/USDT", "BUY", qty=1.0)

        exchange = _make_exchange_for_order("ord-001", status="open", filled=0.3)
        report = tracker.reconcile_with_exchange(exchange)

        assert "ord-001" in report.partial_fills
        assert report.has_anomaly

    def test_partial_fill_fill_ratio_computed(self):
        """fill_ratio = filled_qty / requested_qty."""
        tracker = _make_tracker()
        order = tracker.register("ord-002", "ETH/USDT", "SELL", qty=2.0)

        tracker.update_from_exchange("ord-002", "open", filled_qty=0.5)

        assert order.status == "PARTIAL_FILL"
        assert abs(order.fill_ratio - 0.25) < 1e-9
        assert abs(order.unfilled_qty - 1.5) < 1e-9

    def test_partial_fill_then_filled(self):
        """PARTIAL_FILL → FILLED est une transition valide."""
        tracker = _make_tracker()
        order = tracker.register("ord-003", "BTC/USDT", "BUY", qty=1.0)

        tracker.update_from_exchange("ord-003", "open", filled_qty=0.5)
        assert order.status == "PARTIAL_FILL"

        tracker.update_from_exchange("ord-003", "closed", filled_qty=1.0)
        assert order.status == "FILLED"
        assert order.is_terminal

    def test_partial_fill_then_cancelled(self):
        """PARTIAL_FILL → CANCELLED : l'exchange annule un ordre partiel."""
        tracker = _make_tracker()
        order = tracker.register("ord-004", "BTC/USDT", "BUY", qty=1.0)

        tracker.update_from_exchange("ord-004", "open", filled_qty=0.3)
        assert order.status == "PARTIAL_FILL"

        tracker.update_from_exchange("ord-004", "canceled", filled_qty=0.3)
        assert order.status == "CANCELLED"
        assert abs(order.filled_qty - 0.3) < 1e-9

    def test_full_fill_not_partial(self):
        """filled == requested → FILLED, pas PARTIAL_FILL."""
        tracker = _make_tracker()
        order = tracker.register("ord-005", "ETH/USDT", "BUY", qty=1.0)

        tracker.update_from_exchange("ord-005", "closed", filled_qty=1.0)

        assert order.status == "FILLED"
        assert "ord-005" not in tracker.get_partial_fills()

    def test_multiple_partial_fills_all_detected(self):
        """Plusieurs ordres partiels simultanés sont tous détectés."""
        tracker = _make_tracker()
        for i in range(5):
            tracker.register(f"ord-{i}", "BTC/USDT", "BUY", qty=1.0)
            tracker.update_from_exchange(f"ord-{i}", "open", filled_qty=0.5)

        partials = tracker.get_partial_fills()
        assert len(partials) == 5


# ══════════════════════════════════════════════════════════════════════════════
# A4 — Cancelled Order Detection
# ══════════════════════════════════════════════════════════════════════════════


class TestA4CancelledOrder:
    """Un ordre annulé côté exchange est détecté immédiatement."""

    def test_cancelled_order_detected(self):
        """Exchange status='canceled' → ordre CANCELLED."""
        tracker = _make_tracker()
        tracker.register("ord-c01", "BTC/USDT", "SELL", qty=0.5)

        exchange = _make_exchange_for_order("ord-c01", status="canceled", filled=0.0)
        report = tracker.reconcile_with_exchange(exchange)

        assert "ord-c01" in report.cancelled

    def test_cancelled_order_is_terminal(self):
        """Un ordre CANCELLED ne peut plus être mis à jour."""
        tracker = _make_tracker()
        order = tracker.register("ord-c02", "ETH/USDT", "BUY", qty=1.0)

        tracker.update_from_exchange("ord-c02", "canceled", filled_qty=0.0)
        assert order.is_terminal

        # Tentative de mise à jour sur ordre terminal → ignorée
        tracker.update_from_exchange("ord-c02", "open", filled_qty=0.5)
        assert order.status == "CANCELLED"

    def test_cancelled_after_partial_fill(self):
        """Annulation partielle (0.3/1.0 exécuté) → CANCELLED avec filled=0.3."""
        tracker = _make_tracker()
        order = tracker.register("ord-c03", "BTC/USDT", "BUY", qty=1.0)

        tracker.update_from_exchange("ord-c03", "open", filled_qty=0.3)
        tracker.update_from_exchange("ord-c03", "canceled", filled_qty=0.3)

        assert order.status == "CANCELLED"
        assert abs(order.filled_qty - 0.3) < 1e-9
        assert abs(order.unfilled_qty - 0.7) < 1e-9

    def test_report_separates_cancelled_from_expired(self):
        """Cancelled et expired sont dans des listes distinctes du rapport."""
        # TTL long pour ord-cancelled (il sera traité via exchange)
        # ord-expired a un TTL court → expire_stale() le marque avant fetch
        tracker_cancelled = _make_tracker(ttl_s=300.0)
        tracker_expired = _make_tracker(ttl_s=0.001)

        tracker_cancelled.register("ord-cancelled", "BTC/USDT", "BUY", qty=1.0)
        tracker_expired.register("ord-expired", "ETH/USDT", "SELL", qty=1.0)

        exchange_c = MagicMock()
        exchange_c.fetch_order.return_value = {"status": "canceled", "filled": 0.0}

        time.sleep(0.01)  # laisser TTL de tracker_expired expirer

        report_c = tracker_cancelled.reconcile_with_exchange(exchange_c)
        report_e = tracker_expired.reconcile_with_exchange(MagicMock())

        assert "ord-cancelled" in report_c.cancelled
        assert "ord-expired" in report_e.expired


# ══════════════════════════════════════════════════════════════════════════════
# A5 — Expired Order Detection
# ══════════════════════════════════════════════════════════════════════════════


class TestA5ExpiredOrder:
    """Un ordre non résolu passé le TTL devient EXPIRED automatiquement."""

    def test_order_expired_past_ttl(self):
        """Ordre non résolu > TTL → expire_stale() le marque EXPIRED."""
        tracker = _make_tracker(ttl_s=0.001)
        order = tracker.register("ord-e01", "BTC/USDT", "BUY", qty=1.0)

        time.sleep(0.01)  # dépasser TTL
        expired = tracker.expire_stale()

        assert "ord-e01" in expired
        assert order.status == "EXPIRED"
        assert order.is_terminal

    def test_order_not_expired_within_ttl(self):
        """Ordre récent → non expiré."""
        tracker = _make_tracker(ttl_s=300.0)
        order = tracker.register("ord-e02", "BTC/USDT", "BUY", qty=1.0)

        expired = tracker.expire_stale()

        assert "ord-e02" not in expired
        assert order.status == "NEW"

    def test_expired_order_not_re_expired(self):
        """Un ordre EXPIRED n'est pas ré-expiré."""
        tracker = _make_tracker(ttl_s=0.001)
        tracker.register("ord-e03", "BTC/USDT", "BUY", qty=1.0)

        time.sleep(0.01)
        first_expire = tracker.expire_stale()
        second_expire = tracker.expire_stale()

        assert "ord-e03" in first_expire
        assert "ord-e03" not in second_expire

    def test_filled_order_not_expired_even_past_ttl(self):
        """Un ordre FILLED n'expire pas même après le TTL."""
        tracker = _make_tracker(ttl_s=0.001)
        order = tracker.register("ord-e04", "BTC/USDT", "BUY", qty=1.0)
        order.transition("FILLED", filled_qty=1.0)

        time.sleep(0.01)
        expired = tracker.expire_stale()

        assert "ord-e04" not in expired
        assert order.status == "FILLED"

    def test_reconcile_flags_expired_in_report(self):
        """reconcile_with_exchange() inclut les expirés dans le rapport."""
        tracker = _make_tracker(ttl_s=0.001)
        tracker.register("ord-e05", "ETH/USDT", "SELL", qty=1.0)

        exchange = MagicMock()
        exchange.fetch_order.side_effect = ConnectionError("timeout")

        time.sleep(0.01)
        report = tracker.reconcile_with_exchange(exchange)

        assert "ord-e05" in report.expired or report.has_anomaly

    def test_multiple_orders_mixed_expiry(self):
        """Parmi 5 ordres, seuls ceux > TTL expirent."""
        tracker_short = _make_tracker(ttl_s=0.001)
        tracker_long = _make_tracker(ttl_s=300.0)

        for i in range(3):
            tracker_short.register(f"short-{i}", "BTC/USDT", "BUY", qty=1.0)
        for i in range(2):
            tracker_long.register(f"long-{i}", "BTC/USDT", "BUY", qty=1.0)

        time.sleep(0.01)

        expired_short = tracker_short.expire_stale()
        expired_long = tracker_long.expire_stale()

        assert len(expired_short) == 3
        assert len(expired_long) == 0


# ══════════════════════════════════════════════════════════════════════════════
# A6 — Network Loss During Execution
# ══════════════════════════════════════════════════════════════════════════════


class TestA6NetworkLoss:
    """Perte réseau pendant ou après soumission → état UNKNOWN tracké."""

    def test_fetch_order_timeout_marks_unknown(self):
        """fetch_order() lève → ordre marqué UNKNOWN dans le rapport."""
        tracker = _make_tracker()
        tracker.register("ord-n01", "BTC/USDT", "BUY", qty=1.0)

        exchange = MagicMock()
        exchange.fetch_order.side_effect = TimeoutError("network timeout")

        report = tracker.reconcile_with_exchange(exchange)

        assert "ord-n01" in report.unknown
        assert not report.exchange_reachable

    def test_network_loss_report_never_raises(self):
        """reconcile_with_exchange() ne lève jamais d'exception."""
        tracker = _make_tracker()
        tracker.register("ord-n02", "ETH/USDT", "SELL", qty=2.0)

        exchange = MagicMock()
        exchange.fetch_order.side_effect = RuntimeError("unexpected crash")

        try:
            report = tracker.reconcile_with_exchange(exchange)
        except Exception as exc:
            pytest.fail(f"reconcile_with_exchange a levé: {exc}")

    def test_ccxt_unknown_status_mapped_to_unknown(self):
        """Statut CCXT non reconnu → UNKNOWN."""
        tracker = _make_tracker()
        order = tracker.register("ord-n03", "BTC/USDT", "BUY", qty=1.0)

        tracker.update_from_exchange("ord-n03", "suspended", filled_qty=0.0)

        assert order.status == "UNKNOWN"

    def test_partial_network_loss_some_orders_unknown(self):
        """Exchange répond pour certains ordres, pas d'autres."""
        tracker = _make_tracker()
        tracker.register("ord-ok", "BTC/USDT", "BUY", qty=1.0)
        tracker.register("ord-fail", "ETH/USDT", "SELL", qty=1.0)

        def fetch_order(order_id, symbol):
            if order_id == "ord-ok":
                return {"status": "closed", "filled": 1.0}
            raise ConnectionError("timeout")

        exchange = MagicMock()
        exchange.fetch_order.side_effect = fetch_order

        report = tracker.reconcile_with_exchange(exchange)

        assert "ord-fail" in report.unknown
        assert "ord-ok" not in report.unknown

    def test_order_remains_new_without_exchange_response(self):
        """Sans réponse exchange, l'ordre reste NEW (pas de transition forcée)."""
        tracker = _make_tracker(ttl_s=300.0)
        order = tracker.register("ord-n04", "BTC/USDT", "BUY", qty=1.0)

        # Pas de reconcile → ordre reste NEW
        assert order.status == "NEW"
        assert not order.is_terminal

    def test_unknown_order_is_terminal(self):
        """Un ordre UNKNOWN est terminal (on ne peut plus le mettre à jour)."""
        tracker = _make_tracker()
        order = tracker.register("ord-n05", "BTC/USDT", "BUY", qty=1.0)

        tracker.update_from_exchange("ord-n05", "unknown_status", filled_qty=0.0)
        assert order.is_terminal

        # Tentative de mise à jour → ignorée
        tracker.update_from_exchange("ord-n05", "closed", filled_qty=1.0)
        assert order.status == "UNKNOWN"


# ══════════════════════════════════════════════════════════════════════════════
# A7 — Boot Gate
# ══════════════════════════════════════════════════════════════════════════════


class TestA7BootGate:
    """Aucun trading avant réconciliation propre."""

    def _clean_reconciler(self):
        from system.position_reconciler import ReconcileReport

        rec = MagicMock()
        report = ReconcileReport()
        rec.reconcile.return_value = report
        return rec

    def _dirty_reconciler(self, ghost=None, orphan=None):
        from system.position_reconciler import ReconcileReport

        rec = MagicMock()
        report = ReconcileReport()
        report.ghost_positions = ghost or []
        report.orphan_positions = orphan or []
        rec.reconcile.return_value = report
        return rec

    # ── Gate levé ────────────────────────────────────────────────────────────

    def test_gate_cleared_on_clean_reconcile(self):
        """Réconciliation propre → gate levé."""
        gate = BootGate(self._clean_reconciler())
        report = gate.check()

        assert report.cleared
        assert gate.is_cleared()

    def test_require_clearance_passes_when_cleared(self):
        """require_clearance() ne lève rien si le gate est levé."""
        gate = BootGate(self._clean_reconciler())
        gate.check()

        gate.require_clearance()  # doit passer sans exception

    def test_gate_cleared_report_summary(self):
        """Le rapport cleared contient 'CLEARED'."""
        gate = BootGate(self._clean_reconciler())
        report = gate.check()

        assert "CLEARED" in report.summary()

    # ── Gate bloqué ───────────────────────────────────────────────────────────

    def test_gate_blocked_on_ghost_position(self):
        """Ghost position → gate non levé."""
        gate = BootGate(self._dirty_reconciler(ghost=["BTC/USDT"]))
        report = gate.check()

        assert not report.cleared
        assert not gate.is_cleared()
        assert "BTC/USDT" in report.ghost_positions

    def test_gate_blocked_on_orphan_position(self):
        """Orphan position → gate non levé."""
        gate = BootGate(self._dirty_reconciler(orphan=["ETH/USDT"]))
        report = gate.check()

        assert not report.cleared
        assert "ETH/USDT" in report.orphan_positions

    def test_require_clearance_raises_when_blocked(self):
        """require_clearance() lève TradingBlockedError si gate non levé."""
        gate = BootGate(self._dirty_reconciler(ghost=["BTC/USDT"]))
        gate.check()

        with pytest.raises(TradingBlockedError):
            gate.require_clearance()

    def test_require_clearance_raises_before_any_check(self):
        """require_clearance() lève si check() n'a jamais été appelé."""
        gate = BootGate(self._clean_reconciler())

        with pytest.raises(TradingBlockedError):
            gate.require_clearance()

    def test_gate_blocked_on_exchange_unreachable(self):
        """Exchange inaccessible → gate bloqué."""
        from system.position_reconciler import ReconcileReport

        rec = MagicMock()
        report = ReconcileReport()
        report.exchange_reachable = False
        report.error = "ConnectionError"
        rec.reconcile.return_value = report

        gate = BootGate(rec)
        result = gate.check()

        assert not result.cleared
        assert not result.exchange_reachable

    # ── Révocation ────────────────────────────────────────────────────────────

    def test_gate_revocable_after_clearance(self):
        """Un gate levé peut être révoqué (ex: anomalie en cours de session)."""
        gate = BootGate(self._clean_reconciler())
        gate.check()
        assert gate.is_cleared()

        gate.revoke()
        assert not gate.is_cleared()

    def test_revoked_gate_blocks_trading(self):
        """Après révocation, require_clearance() lève à nouveau."""
        gate = BootGate(self._clean_reconciler())
        gate.check()
        gate.revoke()

        with pytest.raises(TradingBlockedError):
            gate.require_clearance()

    # ── Boot gate avec order tracker ──────────────────────────────────────────

    def test_gate_blocked_on_pending_partial_order(self):
        """Ordre partiel pendant au boot → gate bloqué."""
        tracker = _make_tracker()
        order = tracker.register("ord-boot-01", "BTC/USDT", "BUY", qty=1.0)
        order.transition("PARTIAL_FILL", filled_qty=0.3)

        exchange = MagicMock()
        exchange.fetch_order.return_value = {"status": "open", "filled": 0.3}

        gate = BootGate(self._clean_reconciler(), order_tracker=tracker)
        report = gate.check(exchange=exchange)

        assert not report.cleared
        assert report.partial_orders or report.has_anomaly

    def test_gate_cleared_with_no_pending_orders(self):
        """Tracker vide → gate levé (pas d'ordres en anomalie)."""
        tracker = _make_tracker()
        gate = BootGate(self._clean_reconciler(), order_tracker=tracker)
        report = gate.check()

        assert report.cleared

    def test_gate_blocked_on_unknown_order_at_boot(self):
        """Ordre NEW non fetchable (réseau coupé) → statut UNKNOWN → gate bloqué."""
        tracker = _make_tracker()
        tracker.register("ord-boot-02", "ETH/USDT", "SELL", qty=2.0)
        # L'ordre reste NEW — au boot, l'exchange est inaccessible

        exchange = MagicMock()
        exchange.fetch_order.side_effect = ConnectionError("offline")

        gate = BootGate(self._clean_reconciler(), order_tracker=tracker)
        report = gate.check(exchange=exchange)

        # L'exchange est inaccessible → order_reconcile marque UNKNOWN → gate bloqué
        assert not report.cleared


# ══════════════════════════════════════════════════════════════════════════════
# A8 — Order State Machine
# ══════════════════════════════════════════════════════════════════════════════


class TestA8OrderStateMachine:
    """Transitions d'état valides et invalides pour PendingOrder."""

    def test_new_to_filled_valid(self):
        order = PendingOrder("id", "BTC/USDT", "BUY", requested_qty=1.0)
        order.transition("FILLED", filled_qty=1.0)
        assert order.status == "FILLED"
        assert order.is_terminal

    def test_new_to_cancelled_valid(self):
        order = PendingOrder("id", "BTC/USDT", "BUY", requested_qty=1.0)
        order.transition("CANCELLED")
        assert order.status == "CANCELLED"

    def test_new_to_partial_fill_valid(self):
        order = PendingOrder("id", "BTC/USDT", "BUY", requested_qty=1.0)
        order.transition("PARTIAL_FILL", filled_qty=0.5)
        assert order.status == "PARTIAL_FILL"
        assert abs(order.fill_ratio - 0.5) < 1e-9

    def test_filled_to_any_invalid(self):
        """FILLED est terminal — aucune transition autorisée."""
        order = PendingOrder("id", "BTC/USDT", "BUY", requested_qty=1.0)
        order.transition("FILLED", filled_qty=1.0)

        for status in ("NEW", "PARTIAL_FILL", "CANCELLED", "EXPIRED", "UNKNOWN"):
            with pytest.raises(ValueError):
                order.transition(status)

    def test_cancelled_to_any_invalid(self):
        """CANCELLED est terminal."""
        order = PendingOrder("id", "BTC/USDT", "BUY", requested_qty=1.0)
        order.transition("CANCELLED")

        with pytest.raises(ValueError):
            order.transition("FILLED")

    def test_expired_to_any_invalid(self):
        """EXPIRED est terminal."""
        order = PendingOrder("id", "BTC/USDT", "BUY", requested_qty=1.0)
        order.transition("EXPIRED")

        with pytest.raises(ValueError):
            order.transition("FILLED")

    def test_invalid_status_raises(self):
        """Statut inconnu → ValueError."""
        order = PendingOrder("id", "BTC/USDT", "BUY", requested_qty=1.0)
        with pytest.raises(ValueError):
            order.transition("ZOMBIE")

    def test_filled_qty_capped_at_requested(self):
        """filled_qty ne peut pas dépasser requested_qty."""
        order = PendingOrder("id", "BTC/USDT", "BUY", requested_qty=1.0)
        order.transition("FILLED", filled_qty=999.0)

        assert order.filled_qty <= order.requested_qty

    def test_resolved_at_set_on_terminal(self):
        """resolved_at est défini lors de la transition vers un état terminal."""
        order = PendingOrder("id", "BTC/USDT", "BUY", requested_qty=1.0)
        assert order.resolved_at is None

        order.transition("FILLED", filled_qty=1.0)
        assert order.resolved_at is not None
        assert order.resolved_at <= time.time()

    def test_is_partial_property(self):
        order = PendingOrder("id", "BTC/USDT", "BUY", requested_qty=1.0)
        assert not order.is_partial

        order.transition("PARTIAL_FILL", filled_qty=0.5)
        assert order.is_partial

        order.transition("FILLED", filled_qty=1.0)
        assert not order.is_partial

    def test_duplicate_register_returns_existing(self):
        """register() sur ID déjà connu retourne l'ordre existant (pas de doublon)."""
        tracker = _make_tracker()
        o1 = tracker.register("dup-001", "BTC/USDT", "BUY", qty=1.0)
        o2 = tracker.register("dup-001", "BTC/USDT", "BUY", qty=2.0)

        assert o1 is o2
        assert o1.requested_qty == 1.0  # pas écrasé
        assert tracker.count_pending() == 1

    def test_snapshot_reflects_current_state(self):
        """snapshot() contient les ordres pending actuels."""
        tracker = _make_tracker()
        tracker.register("snap-001", "BTC/USDT", "BUY", qty=1.0)
        tracker.register("snap-002", "ETH/USDT", "SELL", qty=2.0)

        snap = tracker.snapshot()
        assert snap["pending"] == 2
        assert snap["total_tracked"] == 2

    def test_filled_orders_not_in_pending(self):
        """Les ordres FILLED ne sont pas comptés dans get_pending()."""
        tracker = _make_tracker()
        order = tracker.register("fin-001", "BTC/USDT", "BUY", qty=1.0)
        order.transition("FILLED", filled_qty=1.0)

        assert tracker.count_pending() == 0
        assert len(tracker.get_pending()) == 0
