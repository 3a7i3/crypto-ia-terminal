"""
invariant_checker.py — Vérification périodique des invariants système (P12-D3).

Invariants vérifiés :
  I-CAPITAL   : capital >= 0 (jamais négatif)
  I-EQUITY    : equity cohérente avec capital (pas de divergence > seuil)
  I-POSITIONS : quantités de positions >= 0
  I-RISKSTATE : état risque dans les valeurs connues
  I-AUDIT     : chaîne HMAC TamperLog intacte (si log disponible)

Usage :
    checker = InvariantChecker()
    violations = checker.check_all(capital=9800.0, equity=9750.0)
    if violations:
        log.critical("[INVARIANT] %s", [v.name for v in violations])
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

_VALID_RISK_STATES = frozenset(
    {"NORMAL", "DEGRADED", "CRITICAL", "SAFE_MODE", "RECOVERY", "UNKNOWN"}
)
_MAX_EQUITY_CAPITAL_DIVERGENCE = 0.50  # 50% max entre equity et capital


@dataclass
class InvariantViolation:
    name: str
    severity: str  # "CRITICAL" | "WARNING"
    message: str
    value: Any = None
    ts: float = field(default_factory=time.time)

    def is_critical(self) -> bool:
        return self.severity == "CRITICAL"


@dataclass
class InvariantReport:
    violations: list[InvariantViolation] = field(default_factory=list)
    ts: float = field(default_factory=time.time)
    checks_run: int = 0

    @property
    def is_clean(self) -> bool:
        return not self.violations

    @property
    def has_critical(self) -> bool:
        return any(v.is_critical() for v in self.violations)

    def summary(self) -> str:
        if self.is_clean:
            return f"CLEAN ({self.checks_run} checks)"
        names = [v.name for v in self.violations]
        return f"VIOLATIONS: {names}"


class InvariantChecker:
    """
    Vérifie les invariants fondamentaux du système.

    Peut être appelé à chaque cycle ou périodiquement.
    Ne lève jamais d'exception — toutes les erreurs sont capturées.
    """

    def check_all(
        self,
        capital: float = 0.0,
        equity: float = 0.0,
        positions: Optional[dict] = None,
        risk_state: Optional[str] = None,
        tamper_log: Any = None,
    ) -> InvariantReport:
        """
        Lance tous les checks. Retourne un InvariantReport.

        capital    : capital courant en USD
        equity     : equity totale (capital + PnL positions ouvertes)
        positions  : dict {symbol: qty} ou liste de positions
        risk_state : état du RuntimeStateMachine
        tamper_log : instance de TamperEvidentLog (optionnel)
        """
        report = InvariantReport()
        violations: list[InvariantViolation] = []

        v = self.check_capital(capital)
        if v:
            violations.append(v)
        report.checks_run += 1

        v = self.check_equity(equity, capital)
        if v:
            violations.append(v)
        report.checks_run += 1

        if positions is not None:
            v = self.check_positions(positions)
            if v:
                violations.append(v)
            report.checks_run += 1

        if risk_state is not None:
            v = self.check_risk_state(risk_state)
            if v:
                violations.append(v)
            report.checks_run += 1

        if tamper_log is not None:
            v = self.check_audit_chain(tamper_log)
            if v:
                violations.append(v)
            report.checks_run += 1

        report.violations = violations
        return report

    # ── Checks individuels ────────────────────────────────────────────────────

    @staticmethod
    def check_capital(capital: float) -> Optional[InvariantViolation]:
        """I-CAPITAL : capital >= 0 (jamais négatif)."""
        try:
            capital = float(capital)
        except (TypeError, ValueError):
            return InvariantViolation(
                name="I-CAPITAL",
                severity="WARNING",
                message=f"Capital non-numérique: {capital!r}",
                value=capital,
            )
        if capital < 0:
            return InvariantViolation(
                name="I-CAPITAL",
                severity="CRITICAL",
                message=f"Capital négatif: {capital:.2f}",
                value=capital,
            )
        return None

    @staticmethod
    def check_equity(equity: float, capital: float) -> Optional[InvariantViolation]:
        """I-EQUITY : equity ne peut pas diverger de capital de plus de 50%."""
        try:
            equity = float(equity)
            capital = float(capital)
        except (TypeError, ValueError):
            return None
        if capital <= 0:
            return None
        divergence = abs(equity - capital) / capital
        if divergence > _MAX_EQUITY_CAPITAL_DIVERGENCE:
            return InvariantViolation(
                name="I-EQUITY",
                severity="WARNING",
                message=(
                    f"Divergence equity/capital: {divergence:.1%} "
                    f"(equity={equity:.2f} capital={capital:.2f})"
                ),
                value=divergence,
            )
        return None

    @staticmethod
    def check_positions(positions: Any) -> Optional[InvariantViolation]:
        """I-POSITIONS : toutes les quantités >= 0."""
        if isinstance(positions, dict):
            items = positions.items()
        elif hasattr(positions, "__iter__"):
            items = [
                (getattr(p, "symbol", "?"), getattr(p, "qty", 0.0)) for p in positions
            ]
        else:
            return None

        negatives = [(sym, qty) for sym, qty in items if float(qty or 0) < 0]
        if negatives:
            return InvariantViolation(
                name="I-POSITIONS",
                severity="CRITICAL",
                message=f"Quantités négatives: {negatives}",
                value=negatives,
            )
        return None

    @staticmethod
    def check_risk_state(risk_state: str) -> Optional[InvariantViolation]:
        """I-RISKSTATE : état dans les valeurs connues."""
        if risk_state not in _VALID_RISK_STATES:
            return InvariantViolation(
                name="I-RISKSTATE",
                severity="WARNING",
                message=f"État risque inconnu: {risk_state!r}",
                value=risk_state,
            )
        return None

    @staticmethod
    def check_audit_chain(tamper_log: Any) -> Optional[InvariantViolation]:
        """I-AUDIT : chaîne HMAC TamperLog intacte."""
        try:
            if not tamper_log.verify_all():
                return InvariantViolation(
                    name="I-AUDIT",
                    severity="CRITICAL",
                    message="Chaîne HMAC TamperLog corrompue",
                )
        except Exception as exc:
            return InvariantViolation(
                name="I-AUDIT",
                severity="WARNING",
                message=f"Vérification TamperLog échouée: {exc}",
            )
        return None
