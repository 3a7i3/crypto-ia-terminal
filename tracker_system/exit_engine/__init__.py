"""exit_engine — Règles de sortie modulaires et composables."""
from tracker_system.exit_engine.base     import ExitRule
from tracker_system.exit_engine.tp_sl    import TPSLRule
from tracker_system.exit_engine.trailing import TrailingStopRule
from tracker_system.exit_engine.breakeven import BreakEvenRule
from tracker_system.exit_engine.engine   import ExitEngine

__all__ = ["ExitRule", "TPSLRule", "TrailingStopRule", "BreakEvenRule", "ExitEngine"]
