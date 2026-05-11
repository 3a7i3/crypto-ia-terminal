from __future__ import annotations

from tracker_system.config.exit_config import get_exit_config
from tracker_system.engine.exit_engine import ExitEngine
from tracker_system.engine.rules.breakeven import BreakEvenRule
from tracker_system.engine.rules.tp_sl import TPSLRule
from tracker_system.engine.rules.trailing import TrailingStopRule


def build_exit_engine(regime: str | None, confidence: float | None = None) -> ExitEngine:
    config = get_exit_config(regime, confidence)
    return ExitEngine(
        [
            TPSLRule(tp=config["tp"], sl=config["sl"]),
            TrailingStopRule(trail_pct=config["trailing"]),
            BreakEvenRule(trigger_pct=max(config["sl"], config["trailing"])),
        ]
    )
