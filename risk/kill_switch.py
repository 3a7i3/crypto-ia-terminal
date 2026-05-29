"""Kill switch centralise — matrice de declenchement."""

from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional


class KillAction(Enum):
    FREEZE_TRADING = auto()
    CANCEL_ORDERS = auto()
    HALT_EXECUTION = auto()
    LOCK_SYMBOL = auto()
    REJECT_TRADE = auto()
    REDUCE_LEVERAGE = auto()
    SAFE_MODE = auto()


class Severity(Enum):
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()


@dataclass(frozen=True)
class KillRule:
    trigger: str
    action: KillAction
    severity: Severity
    module: str
    description: str


KILL_MATRIX: list[KillRule] = [
    KillRule("drawdown > 5%", KillAction.FREEZE_TRADING, Severity.CRITICAL, "drawdown_guard", "Freeze toutes les positions"),
    KillRule("exchange stale > 30s", KillAction.CANCEL_ORDERS, Severity.HIGH, "exchange_monitor", "Annule les ordres ouverts"),
    KillRule("position mismatch", KillAction.HALT_EXECUTION, Severity.CRITICAL, "position_manager", "Arrêt immédiat"),
    KillRule("duplicate order", KillAction.LOCK_SYMBOL, Severity.HIGH, "order_deduplicator", "Vérouille le symbole"),
    KillRule("missing stop", KillAction.REJECT_TRADE, Severity.MEDIUM, "execution_engine", "Refus local"),
    KillRule("latency > 5s", KillAction.REDUCE_LEVERAGE, Severity.MEDIUM, "performance_watchdog", "Réduit levier 50%"),
    KillRule("risk timeout", KillAction.SAFE_MODE, Severity.CRITICAL, "circuit_breaker", "Mode safe global"),
]
