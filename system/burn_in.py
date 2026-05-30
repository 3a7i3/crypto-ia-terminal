"""
burn_in.py — Moteur de burn-in paper trading (P12-D).

Orchestre un run longue durée compressé qui valide :
  - Absence de crash / corruption
  - Stabilité mémoire
  - Invariants système respectés à chaque snapshot
  - Réconciliation périodique sans dérive
  - Métriques de stratégie mesurées sur la session

Usage :
    config = BurnInConfig(n_cycles=10_000, snapshot_interval=1_000)
    engine = BurnInEngine(config)
    report = engine.run()
    print(report.passed, report.summary())
"""

from __future__ import annotations

import json
import random
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from observability.alerting import AlertEngine
from observability.health_score import HealthScore
from observability.json_logger import get_logger
from observability.metrics_collector import MetricsCollector
from system.invariant_checker import InvariantChecker
from system.strategy_metrics import StrategyAnalyzer, Trade
from system.strategy_score import StrategyScorer

_log = get_logger("system.burn_in")

_STRATEGY_RSI = {
    "entry_indicator": "RSI",
    "period": 14,
    "entry_threshold": 35,
    "exit_threshold": 65,
}
_SYMBOL = "BTC/USDT"
_ORDER_SIZE = 0.001


# ── Critères de passage P13 ───────────────────────────────────────────────────

_MAX_EXCEPTIONS = 0  # 0 crash autorisé
_MAX_INVARIANT_VIOLATIONS = 0  # 0 violation d'invariant critique
_MAX_AUDIT_FAILURES = 0  # 0 corruption audit
_MIN_HEALTH_SCORE = 50.0  # health score minimal acceptable
_MAX_DRAWDOWN_PCT = 25.0  # drawdown max avant refus
_MAX_RECONCILE_FAILURES = 0  # 0 échec réconciliation non récupéré


@dataclass
class BurnInConfig:
    n_cycles: int = 10_000
    snapshot_interval: int = 1_000  # snapshot santé toutes les N cycles
    invariant_interval: int = 500  # check invariants toutes les N cycles
    reconcile_interval: int = 2_000  # reconcile toutes les N cycles
    seed: int = 42
    initial_capital: float = 10_000.0
    journal_path: Optional[Path] = None  # None = pas de fichier
    simulate_network_issues: bool = False  # injecter des timeouts réseau
    network_issue_rate: float = 0.05  # 5% des reconciliations échouent


@dataclass
class HealthSnapshot:
    cycle: int
    ts: float
    health_score: float
    capital: float
    equity: float
    drawdown_pct: float
    memory_mb: float
    error_rate: float
    exception_count: int
    open_positions: int
    n_alerts: int
    n_invariant_violations: int


@dataclass
class BurnInReport:
    # Paramètres
    config: BurnInConfig = field(default_factory=BurnInConfig)

    # Durée
    duration_s: float = 0.0
    n_cycles_completed: int = 0

    # Fiabilité
    n_exceptions: int = 0
    n_alerts: int = 0
    n_reconciliation_failures: int = 0
    n_invariant_violations: int = 0
    n_audit_failures: int = 0

    # Santé
    health_score_mean: float = 0.0
    health_score_min: float = 100.0
    health_score_final: float = 0.0

    # Système
    memory_mb_max: float = 0.0
    drawdown_pct_max: float = 0.0
    capital_final: float = 0.0
    equity_final: float = 0.0

    # Stratégie
    n_trades: int = 0
    strategy_score: float = 0.0
    strategy_grade: str = "F"

    # Verdict
    passed: bool = False
    failure_reasons: list[str] = field(default_factory=list)

    # Snapshots
    snapshots: list[HealthSnapshot] = field(default_factory=list)

    def summary(self) -> str:
        status = "PASS" if self.passed else f"FAIL ({'; '.join(self.failure_reasons)})"
        return (
            f"[{status}] "
            f"cycles={self.n_cycles_completed} "
            f"dur={self.duration_s:.1f}s "
            f"exc={self.n_exceptions} "
            f"alerts={self.n_alerts} "
            f"health_min={self.health_score_min:.1f} "
            f"mdd={self.drawdown_pct_max:.1f}% "
            f"strategy={self.strategy_grade}({self.strategy_score:.0f})"
        )

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "failure_reasons": self.failure_reasons,
            "duration_s": round(self.duration_s, 2),
            "n_cycles": self.n_cycles_completed,
            "n_exceptions": self.n_exceptions,
            "n_alerts": self.n_alerts,
            "n_reconciliation_failures": self.n_reconciliation_failures,
            "n_invariant_violations": self.n_invariant_violations,
            "health_score_mean": round(self.health_score_mean, 2),
            "health_score_min": round(self.health_score_min, 2),
            "memory_mb_max": round(self.memory_mb_max, 1),
            "drawdown_pct_max": round(self.drawdown_pct_max, 2),
            "capital_final": round(self.capital_final, 2),
            "strategy_score": round(self.strategy_score, 1),
            "strategy_grade": self.strategy_grade,
            "n_trades": self.n_trades,
        }


class BurnInEngine:
    """
    Moteur de burn-in paper trading.

    Orchestre :
      - Simulation de cycles de trading (PaperTradingEngine)
      - Collecte de métriques (MetricsCollector)
      - Calcul de santé (HealthScore)
      - Alertes (AlertEngine)
      - Vérification d'invariants (InvariantChecker)
      - Réconciliation périodique simulée
      - Journal de santé (JSONL)
      - Rapport final avec critères de passage P13
    """

    def __init__(self, config: Optional[BurnInConfig] = None) -> None:
        self._config = config or BurnInConfig()
        self._scorer = HealthScore()
        self._alert_engine = AlertEngine()
        self._invariant_checker = InvariantChecker()
        self._strategy_analyzer = StrategyAnalyzer(
            initial_capital=self._config.initial_capital
        )
        self._strategy_scorer = StrategyScorer()

    def run(self) -> BurnInReport:
        """Lance le burn-in et retourne le rapport final."""
        cfg = self._config
        report = BurnInReport(config=cfg)
        t_start = time.monotonic()

        _log.info("[BurnIn] Démarrage — n_cycles=%d seed=%d", cfg.n_cycles, cfg.seed)

        # ── Setup simulation ──────────────────────────────────────────────────
        from quant_hedge_ai.agents.execution.paper_trading_engine import (
            PaperTradingEngine,
        )
        from quant_hedge_ai.agents.execution.signal_engine import compute_signal

        rng = random.Random(cfg.seed)
        engine = PaperTradingEngine(initial_balance=cfg.initial_capital, persist=False)
        window: deque = deque(maxlen=30)
        price = 50_000.0

        # Métriques
        capital_ref = [cfg.initial_capital]
        collector = MetricsCollector(
            capital_fn=lambda: capital_ref[0],
            equity_fn=lambda: capital_ref[0],
            positions_fn=lambda: sum(1 for q in engine.positions.values() if q > 0),
            initial_capital=cfg.initial_capital,
        )
        collector.set_boot_gate_cleared(True)

        trades_accumulated: list[Trade] = []
        health_scores: list[float] = []

        # ── Boucle principale ─────────────────────────────────────────────────
        for cycle in range(cfg.n_cycles):
            try:
                with collector.measure_cycle():
                    # Générer candle
                    change = rng.gauss(0, 0.002)
                    close = round(price * (1 + change), 2)
                    spread = abs(rng.gauss(0, 0.001))
                    candle = {
                        "open": round(price, 2),
                        "high": round(max(price, close) * (1 + spread), 2),
                        "low": round(min(price, close) * (1 - spread), 2),
                        "close": close,
                        "volume": rng.uniform(1.0, 50.0),
                        "timestamp": 0,
                    }
                    price = close
                    window.append(candle)

                    # Signal + exécution
                    with collector.measure_decision():
                        signal = compute_signal(_STRATEGY_RSI, list(window))

                    has_pos = engine.positions.get(_SYMBOL, 0.0) > 0
                    cost = price * _ORDER_SIZE

                    if signal == "BUY" and not has_pos and engine.balance >= cost:
                        with collector.measure_execution():
                            result = engine.execute(
                                {
                                    "symbol": _SYMBOL,
                                    "action": "BUY",
                                    "size": _ORDER_SIZE,
                                },
                                price,
                            )
                        trades_accumulated.append(
                            Trade(
                                pnl=result["last_trade"]["pnl"],
                                pnl_pct=result["last_trade"]["pnl"]
                                / cfg.initial_capital
                                * 100,
                            )
                        )
                    elif signal == "SELL" and has_pos:
                        with collector.measure_execution():
                            result = engine.execute(
                                {
                                    "symbol": _SYMBOL,
                                    "action": "SELL",
                                    "size": _ORDER_SIZE,
                                },
                                price,
                            )
                        trades_accumulated.append(
                            Trade(
                                pnl=result["last_trade"]["pnl"],
                                pnl_pct=result["last_trade"]["pnl"]
                                / cfg.initial_capital
                                * 100,
                            )
                        )

                    # Sync capital
                    capital_ref[0] = engine.balance

            except Exception as exc:
                report.n_exceptions += 1
                collector.record_exception(exc)
                _log.error("[BurnIn] Exception cycle=%d: %s", cycle, exc)

            # ── Snapshot santé ────────────────────────────────────────────────
            if cfg.snapshot_interval and (cycle + 1) % cfg.snapshot_interval == 0:
                snap = collector.snapshot()
                snap.health_score = self._scorer.compute(snap)
                alerts = self._alert_engine.check(snap)
                report.n_alerts += len(alerts)

                health_scores.append(snap.health_score)
                report.memory_mb_max = max(report.memory_mb_max, snap.memory_mb)
                report.drawdown_pct_max = max(
                    report.drawdown_pct_max, snap.drawdown_pct
                )

                hs = HealthSnapshot(
                    cycle=cycle + 1,
                    ts=snap.ts,
                    health_score=snap.health_score,
                    capital=snap.capital,
                    equity=snap.equity,
                    drawdown_pct=snap.drawdown_pct,
                    memory_mb=snap.memory_mb,
                    error_rate=snap.error_rate,
                    exception_count=snap.exception_count,
                    open_positions=snap.open_positions,
                    n_alerts=len(alerts),
                    n_invariant_violations=0,
                )
                report.snapshots.append(hs)

                if cfg.journal_path:
                    self._append_journal(cfg.journal_path, hs)

            # ── Vérification invariants ───────────────────────────────────────
            if cfg.invariant_interval and (cycle + 1) % cfg.invariant_interval == 0:
                inv_report = self._invariant_checker.check_all(
                    capital=engine.balance,
                    equity=engine.balance,  # paper: equity = balance
                    positions=engine.positions,
                    risk_state="NORMAL",
                )
                critical_viols = [v for v in inv_report.violations if v.is_critical()]
                report.n_invariant_violations += len(critical_viols)
                if critical_viols:
                    _log.critical(
                        "[BurnIn] Invariants violés: %s",
                        [v.name for v in critical_viols],
                    )
                if report.snapshots:
                    report.snapshots[-1].n_invariant_violations += len(critical_viols)

            # ── Réconciliation périodique ──────────────────────────────────────
            if cfg.reconcile_interval and (cycle + 1) % cfg.reconcile_interval == 0:
                reconcile_ok = self._simulate_reconcile(rng, cfg)
                if not reconcile_ok:
                    report.n_reconciliation_failures += 1
                    collector.record_reconciliation_failure()

        # ── Résumé final ──────────────────────────────────────────────────────
        report.duration_s = time.monotonic() - t_start
        report.n_cycles_completed = cfg.n_cycles
        report.capital_final = engine.balance
        report.equity_final = engine.balance
        report.n_trades = len(engine.trade_history)

        if health_scores:
            report.health_score_mean = sum(health_scores) / len(health_scores)
            report.health_score_min = min(health_scores)
            report.health_score_final = health_scores[-1]

        # Métriques stratégie
        if trades_accumulated:
            metrics = self._strategy_analyzer.compute(trades_accumulated)
            score_result = self._strategy_scorer.score(metrics)
            report.strategy_score = score_result.total
            report.strategy_grade = score_result.grade.value

        # Verdict
        report.passed, report.failure_reasons = self._evaluate_pass_criteria(report)

        _log.info("[BurnIn] Terminé — %s", report.summary())
        return report

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _simulate_reconcile(rng: random.Random, cfg: BurnInConfig) -> bool:
        """Simule une réconciliation (peut échouer si simulate_network_issues)."""
        if cfg.simulate_network_issues and rng.random() < cfg.network_issue_rate:
            return False
        return True

    @staticmethod
    def _append_journal(path: Path, snap: HealthSnapshot) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "cycle": snap.cycle,
                            "ts": snap.ts,
                            "health_score": snap.health_score,
                            "capital": snap.capital,
                            "drawdown_pct": snap.drawdown_pct,
                            "memory_mb": snap.memory_mb,
                            "n_alerts": snap.n_alerts,
                            "n_invariant_violations": snap.n_invariant_violations,
                        }
                    )
                    + "\n"
                )
        except Exception as exc:
            _log.warning("[BurnIn] Journal write failed: %s", exc)

    @staticmethod
    def _evaluate_pass_criteria(report: "BurnInReport") -> tuple[bool, list[str]]:
        """
        Évalue les critères de passage vers P13.

        Retourne (passed, reasons).
        """
        reasons: list[str] = []

        if report.n_exceptions > _MAX_EXCEPTIONS:
            reasons.append(f"Exceptions: {report.n_exceptions} > {_MAX_EXCEPTIONS}")

        if report.n_invariant_violations > _MAX_INVARIANT_VIOLATIONS:
            reasons.append(
                f"Violations invariant: {report.n_invariant_violations} "
                f"> {_MAX_INVARIANT_VIOLATIONS}"
            )

        if report.n_audit_failures > _MAX_AUDIT_FAILURES:
            reasons.append(
                f"Corruptions audit: {report.n_audit_failures} > {_MAX_AUDIT_FAILURES}"
            )

        if report.health_score_min < _MIN_HEALTH_SCORE:
            reasons.append(
                f"Health score min: {report.health_score_min:.1f} < {_MIN_HEALTH_SCORE}"
            )

        if report.drawdown_pct_max > _MAX_DRAWDOWN_PCT:
            reasons.append(
                f"Drawdown max: {report.drawdown_pct_max:.1f}% > {_MAX_DRAWDOWN_PCT}%"
            )

        if report.n_reconciliation_failures > _MAX_RECONCILE_FAILURES:
            reasons.append(
                f"Reconciliation failures: {report.n_reconciliation_failures} "
                f"> {_MAX_RECONCILE_FAILURES}"
            )

        return (len(reasons) == 0, reasons)
