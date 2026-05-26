"""
system/position_reconciler.py — Réconciliation positions exchange vs état interne.

Compare toutes les heures :
  - positions réelles sur Binance (source de vérité)
  - positions dans PositionManager (état interne)

Détecte :
  - ghost positions (internes mais fermées sur exchange)
  - orphan positions (exchange mais pas dans l'interne)
  - price drift > seuil

Usage :
    from system.position_reconciler import PositionReconciler
    rec = PositionReconciler(exchange_futures, pos_manager)
    report = rec.reconcile()
    if report.has_drift:
        _log.critical("[RECONCILE] %s", report.summary())
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from observability.json_logger import get_logger

_log = get_logger("system.position_reconciler")
_PRICE_DRIFT_PCT_ALERT = 0.02  # alerte si écart prix > 2%
_MIN_RECONCILE_INTERVAL = 3600  # 1h entre chaque réconciliation complète


@dataclass
class ReconcileReport:
    timestamp: float = field(default_factory=time.time)
    exchange_positions: int = 0
    internal_positions: int = 0
    ghost_positions: list = field(default_factory=list)  # interne mais pas sur exchange
    orphan_positions: list = field(default_factory=list)  # exchange mais pas en interne
    price_drifts: list = field(default_factory=list)  # écart prix > seuil
    exchange_reachable: bool = True
    error: Optional[str] = None

    @property
    def has_drift(self) -> bool:
        return bool(
            self.ghost_positions
            or self.orphan_positions
            or self.price_drifts
            or not self.exchange_reachable
        )

    @property
    def is_clean(self) -> bool:
        return self.exchange_reachable and not self.has_drift

    def summary(self) -> str:
        parts = []
        if not self.exchange_reachable:
            parts.append("EXCHANGE_UNREACHABLE")
        if self.ghost_positions:
            parts.append(f"GHOST={self.ghost_positions}")
        if self.orphan_positions:
            parts.append(f"ORPHAN={self.orphan_positions}")
        if self.price_drifts:
            parts.append(f"DRIFT={self.price_drifts}")
        return " | ".join(parts) if parts else "CLEAN"


class PositionReconciler:
    """
    Compare positions exchange vs PositionManager.

    exchange_futures : objet ccxt exchange (ou compatible) avec fetch_positions()
    pos_manager      : instance de PositionManager
    """

    def __init__(self, exchange_futures: Any, pos_manager: Any) -> None:
        self._exchange = exchange_futures
        self._pm = pos_manager
        self._last_reconcile: float = 0.0

    def should_reconcile(self) -> bool:
        return time.time() - self._last_reconcile >= _MIN_RECONCILE_INTERVAL

    def reconcile(self, force: bool = False) -> ReconcileReport:
        """
        Lance la réconciliation. Retourne un ReconcileReport.
        Ne lève jamais d'exception — toutes les erreurs sont capturées dans le rapport.
        """
        if not force and not self.should_reconcile():
            return ReconcileReport(error="skipped — too soon")

        report = ReconcileReport()
        self._last_reconcile = time.time()

        # ── 1. Positions exchange ─────────────────────────────────────────────
        exchange_pos: dict[str, dict] = {}
        try:
            raw = self._exchange.fetch_positions() if self._exchange else []
            for p in raw:
                contracts = float(p.get("contracts") or p.get("size") or 0)
                if contracts > 0:
                    sym = p.get("symbol", "")
                    exchange_pos[sym] = {
                        "symbol": sym,
                        "side": p.get("side", ""),
                        "contracts": contracts,
                        "mark_price": float(
                            p.get("markPrice")
                            or p.get("info", {}).get("markPrice", 0)
                            or 0
                        ),
                    }
        except Exception as e:
            report.exchange_reachable = False
            report.error = f"exchange.fetch_positions failed: {e}"
            _log.warning("[Reconciler] %s", report.error)
            return report

        # ── 2. Positions internes ──────────────────────────────────────────────
        internal_pos: dict[str, Any] = {}
        try:
            for pos in (
                self._pm.get_open_positions()
                if hasattr(self._pm, "get_open_positions")
                else []
            ):
                sym = getattr(pos, "symbol", "")
                if sym:
                    internal_pos[sym] = pos
        except Exception as e:
            report.error = f"pos_manager.get_open_positions failed: {e}"
            _log.warning("[Reconciler] %s", report.error)

        report.exchange_positions = len(exchange_pos)
        report.internal_positions = len(internal_pos)

        # ── 3. Ghost positions (interne mais pas sur exchange) ─────────────────
        for sym, pos in internal_pos.items():
            if sym not in exchange_pos:
                report.ghost_positions.append(sym)
                _log.warning(
                    "[Reconciler] GHOST position: %s (interne mais absente exchange)",
                    sym,
                )

        # ── 4. Orphan positions (exchange mais pas en interne) ─────────────────
        for sym in exchange_pos:
            if sym not in internal_pos:
                report.orphan_positions.append(sym)
                _log.warning(
                    "[Reconciler] ORPHAN position: %s (exchange mais absente interne)",
                    sym,
                )

        # ── 5. Price drift ─────────────────────────────────────────────────────
        for sym in set(exchange_pos) & set(internal_pos):
            ep = exchange_pos[sym]
            ip = internal_pos[sym]
            mark = ep.get("mark_price", 0)
            entry = float(getattr(ip, "entry_price", 0) or 0)
            if mark > 0 and entry > 0:
                drift = abs(mark - entry) / entry
                if drift > _PRICE_DRIFT_PCT_ALERT:
                    report.price_drifts.append(
                        {
                            "symbol": sym,
                            "entry_price": entry,
                            "mark_price": mark,
                            "drift_pct": round(drift * 100, 2),
                        }
                    )

        if report.has_drift:
            _log.warning("[Reconciler] DRIFT DETECTED: %s", report.summary())
        else:
            _log.info(
                "[Reconciler] CLEAN — %d exchange / %d internal",
                report.exchange_positions,
                report.internal_positions,
            )

        return report
