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
from quant_hedge_ai.agents.execution.position_manager import ExecutionDomain

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
    # REM-C R1 — domain-safety fields. `comparable=False` means reconciliation
    # was NOT performed (domain incompatible or unproven): ghost/orphan lists
    # are empty in that case by construction, never fabricated findings.
    comparable: bool = True
    pm_domain: str = ExecutionDomain.UNKNOWN.value
    expected_domain: str = ExecutionDomain.REAL.value
    unresolved_domain_positions: list = field(default_factory=list)

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
        return self.comparable and self.exchange_reachable and not self.has_drift

    def summary(self) -> str:
        if not self.comparable:
            return (
                f"NON_COMPARABLE (pm_domain={self.pm_domain} "
                f"expected={self.expected_domain})"
            )
        parts = []
        if not self.exchange_reachable:
            parts.append("EXCHANGE_UNREACHABLE")
        if self.ghost_positions:
            parts.append(f"GHOST={self.ghost_positions}")
        if self.orphan_positions:
            parts.append(f"ORPHAN={self.orphan_positions}")
        if self.price_drifts:
            parts.append(f"DRIFT={self.price_drifts}")
        if self.unresolved_domain_positions:
            parts.append(f"UNRESOLVED_DOMAIN={self.unresolved_domain_positions}")
        return " | ".join(parts) if parts else "CLEAN"


class PositionReconciler:
    """
    Compare positions exchange vs PositionManager.

    exchange_futures : objet ccxt exchange (ou compatible) avec fetch_positions()
    pos_manager      : instance de PositionManager
    """

    def __init__(
        self,
        exchange_futures: Any,
        pos_manager: Any,
        expected_domain: ExecutionDomain = ExecutionDomain.REAL,
    ) -> None:
        self._exchange = exchange_futures
        self._pm = pos_manager
        self._last_reconcile: float = 0.0
        # REM-C R1 — reconciliation only ever means "compare internal state
        # against THIS exchange handle's REAL account" by construction
        # (exchange_futures.fetch_positions() is always a real/testnet
        # account call). expected_domain names what pos_manager must prove
        # itself to be before any comparison is attempted.
        self._expected_domain = expected_domain

    def should_reconcile(self) -> bool:
        return time.time() - self._last_reconcile >= _MIN_RECONCILE_INTERVAL

    def reconcile(self, force: bool = False) -> ReconcileReport:
        """
        Lance la réconciliation. Retourne un ReconcileReport.
        Ne lève jamais d'exception — toutes les erreurs sont capturées dans le rapport.

        REM-C R1 — invariant de sécurité de domaine : la comparaison
        exchange/interne n'est jamais effectuée si `pos_manager.domain`
        n'est pas prouvé égal à `expected_domain` (typiquement REAL). Un
        domaine non prouvé (UNKNOWN) ou incompatible (ex: PAPER contre un
        compte REAL) échoue fermé — `comparable=False`, aucune liste
        ghost/orphan n'est calculée, jamais de faux positif fabriqué.
        """
        if not force and not self.should_reconcile():
            return ReconcileReport(error="skipped — too soon")

        pm_domain = getattr(self._pm, "domain", ExecutionDomain.UNKNOWN)
        report = ReconcileReport(
            pm_domain=getattr(pm_domain, "value", str(pm_domain)),
            expected_domain=self._expected_domain.value,
        )
        self._last_reconcile = time.time()

        if pm_domain != self._expected_domain:
            report.comparable = False
            report.error = (
                f"non-comparable execution domains: pos_manager={report.pm_domain} "
                f"expected={report.expected_domain}"
            )
            _log.warning("[Reconciler] %s", report.error)
            return report

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
        # Canonical PositionManager API is get_open() (get_open_positions()
        # never existed — REM-C R0/R1 finding). Domain compatibility was
        # already proven above at the pos_manager level; individual
        # positions with an unresolved/UNKNOWN domain are still excluded
        # here and reported separately rather than folded into ghost/orphan
        # findings (R1-I4 — UNKNOWN can never produce a ghost/orphan claim).
        internal_pos: dict[str, Any] = {}
        try:
            for pos in self._pm.get_open() if hasattr(self._pm, "get_open") else []:
                sym = getattr(pos, "symbol", "")
                pos_domain = getattr(pos, "domain", ExecutionDomain.UNKNOWN)
                if not sym:
                    continue
                if pos_domain != self._expected_domain:
                    report.unresolved_domain_positions.append(sym)
                    continue
                internal_pos[sym] = pos
        except Exception as e:
            report.error = f"pos_manager.get_open failed: {e}"
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
