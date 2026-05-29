"""
system/state_integrity.py — Truth Arbitration Layer.

Capture un snapshot normalisé de l'état runtime, exécute 5 catégories
de checks d'invariants purs, et produit un IntegrityReport avec score 0-100.

Principe :
  - Détecte seulement. Ne corrige RIEN.
  - Chaque règle est pure, deterministic, sans effet de bord.
  - Un score < 50 (level UNSAFE) doit bloquer les décisions de trading.

Usage :
    audit = StateIntegrityAudit()
    report = audit.run(cycle=42, real_capital=4572.0, ...)
    level = audit.trading_level(report)   # NORMAL|DEGRADED|RESTRICTED|UNSAFE|HALTED
    if level in (IntegrityLevel.UNSAFE, IntegrityLevel.HALTED):
        log.critical("[INTEGRITY] %s", audit.unsafe_reason(report))
"""

from __future__ import annotations

import dataclasses
import json
import os
from collections import deque
from pathlib import Path
from typing import Any, Optional

from observability.json_logger import get_logger
from system.integrity_models import (
    IntegrityIssue,
    IntegrityLevel,
    IntegrityReport,
    IntegritySeverity,
)
from system.integrity_rules import ALL_CHECKS
from system.integrity_snapshot import StateSnapshot

_log = get_logger("system.state_integrity")
_AUDIT_LOG = Path(os.getenv("INTEGRITY_LOG_PATH", "databases/integrity_audit.jsonl"))
_DEFAULT_EVERY = int(os.getenv("INTEGRITY_AUDIT_EVERY", "5"))

# Score en dessous duquel on bloque le trading
_UNSAFE_SCORE_THRESHOLD = int(os.getenv("INTEGRITY_UNSAFE_SCORE", "50"))


class StateIntegrityAudit:
    """
    Orchestrateur des audits d'intégrité d'état.

    Appelé tous les N cycles. Produit un IntegrityReport.
    L'intégration dans advisor_loop.py décide quoi faire du rapport :
      - log, telegram, block_new_trades selon level (5 états, pas binaire).
    """

    def __init__(
        self,
        every_n_cycles: int = _DEFAULT_EVERY,
        log_path: Optional[Path] = None,
    ) -> None:
        self._every = every_n_cycles
        self._log_path = log_path or _AUDIT_LOG
        self._last_hash = ""
        self._consecutive_issue_cycles = 0
        self._last_report: Optional[IntegrityReport] = None
        self._total_audits = 0
        # Trend rolling — 50 derniers audits
        self._score_history: deque[int] = deque(maxlen=50)
        self._issue_cycle_count = 0  # cycles avec au moins une issue

    # ── API principale ─────────────────────────────────────────────────────────

    def should_run(self, cycle: int) -> bool:
        return cycle % self._every == 0

    def run(
        self,
        cycle: int,
        real_capital: float,
        last_trade_signal: dict[str, str],
        last_loss_time: dict[str, float],
        trades_this_hour: dict[str, list[float]],
        pos_manager: Any,
        portfolio_brain: Any,
        pending_orders: list | None = None,
    ) -> IntegrityReport:
        """
        Exécute un audit complet. Retourne toujours un IntegrityReport.
        Les exceptions internes sont absorbées — l'audit ne doit jamais
        crasher le cycle principal.
        """
        self._total_audits += 1

        snap = StateSnapshot.capture(
            cycle=cycle,
            real_capital=real_capital,
            last_trade_signal=last_trade_signal,
            last_loss_time=last_loss_time,
            trades_this_hour=trades_this_hour,
            pos_manager=pos_manager,
            portfolio_brain=portfolio_brain,
            pending_orders=pending_orders,
        )

        issues: list[IntegrityIssue] = []
        for check_fn in ALL_CHECKS:
            try:
                issues.extend(check_fn(snap))
            except Exception as exc:
                _log.debug(
                    "[StateIntegrity] règle %s a échoué: %s",
                    check_fn.__name__,
                    exc,
                )

        state_hash = snap.compute_hash()

        # Récupérer le trace_id global du cycle courant (Task 3 correlation)
        _tid = ""
        try:
            from observability.json_logger import current_trace_id as _ctid

            _tid = _ctid() or ""
        except Exception:
            pass

        # Enrichir chaque issue avec trace_id, cycle_id, snapshot_hash
        enriched_issues = [
            dataclasses.replace(
                iss,
                trace_id=_tid,
                cycle_id=cycle,
                snapshot_hash=state_hash,
            )
            for iss in issues
        ]

        report = IntegrityReport(
            cycle=cycle,
            issues=enriched_issues,
            state_hash=state_hash,
            trace_id=_tid,
        )

        # ── Tracking ──────────────────────────────────────────────────────────
        hash_changed = state_hash != self._last_hash
        self._last_hash = state_hash
        self._consecutive_issue_cycles = (
            self._consecutive_issue_cycles + 1 if enriched_issues else 0
        )
        if enriched_issues:
            self._issue_cycle_count += 1
        self._last_report = report
        self._score_history.append(report.score)

        # ── Logging ───────────────────────────────────────────────────────────
        _log.info("%s", report.summary_line())
        for issue in enriched_issues:
            log_fn = (
                _log.error
                if issue.severity
                in (IntegritySeverity.UNSAFE, IntegritySeverity.DEGRADED)
                else _log.warning
            )
            log_fn(
                "[INTEGRITY:%s] %s | %s",
                issue.rule,
                issue.description,
                issue.observed,
            )

        if hash_changed and not enriched_issues:
            _log.debug(
                "[StateIntegrity] état modifié, cohérent. hash=%s", state_hash[:8]
            )

        # ── Persistance ───────────────────────────────────────────────────────
        self._persist(report)

        return report

    # ── Décision de trading ───────────────────────────────────────────────────

    def trading_level(self, report: IntegrityReport) -> IntegrityLevel:
        """Niveau de dégradation 5 états pour décision de trading."""
        return report.level

    def blocks_trading(self, report: IntegrityReport) -> bool:
        """Compat v1.0 — True si level UNSAFE ou HALTED (score < 50)."""
        return report.score < _UNSAFE_SCORE_THRESHOLD

    def unsafe_reason(self, report: IntegrityReport) -> Optional[str]:
        """
        Raison principale quand level UNSAFE ou HALTED (score < 50).
        Retourne None si le système est en état acceptable.
        """
        if report.score >= _UNSAFE_SCORE_THRESHOLD:
            return None
        pf = report.primary_failure
        if pf:
            return f"{pf.rule}: {pf.description}"
        return f"score={report.score}/100 level={report.level.value}"

    # ── Trend analytics ───────────────────────────────────────────────────────

    @property
    def integrity_score_rolling_50(self) -> Optional[float]:
        """Score moyen des 50 derniers audits. None avant le premier audit."""
        if not self._score_history:
            return None
        return round(sum(self._score_history) / len(self._score_history), 1)

    @property
    def integrity_issue_frequency(self) -> float:
        """
        Proportion de cycles avec au moins une issue (sur les 50 derniers).
        0.0 = parfaitement stable, 1.0 = toujours dégradé.
        Un système qui dérive lentement est plus dangereux qu'un crash brutal.
        """
        if not self._score_history:
            return 0.0
        n_with_issues = sum(1 for s in self._score_history if s < 100)
        return round(n_with_issues / len(self._score_history), 3)

    @property
    def consecutive_issue_cycles(self) -> int:
        return self._consecutive_issue_cycles

    @property
    def last_report(self) -> Optional[IntegrityReport]:
        return self._last_report

    # ── Helpers ───────────────────────────────────────────────────────────────

    def telegram_summary(self, report: IntegrityReport) -> str:
        """Message Telegram compact pour les rapports dégradés."""
        lines = [f"[INTEGRITY] score={report.score}/100 | level={report.level.value}"]
        for issue in report.issues[:4]:
            icon = "🔴" if issue.severity == IntegritySeverity.UNSAFE else "⚠️"
            lines.append(f"{icon} {issue.rule}: {issue.description[:80]}")
        if len(report.issues) > 4:
            lines.append(f"  ... +{len(report.issues) - 4} autres issues")
        reason = self.unsafe_reason(report)
        if reason:
            lines.append(f"Raison principale: {reason[:100]}")
        return "\n".join(lines)

    def _persist(self, report: IntegrityReport) -> None:
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(report.as_dict()) + "\n")
        except Exception:
            pass
