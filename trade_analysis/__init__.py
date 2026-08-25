"""
trade_analysis — Module d'observation Live Market Interaction (LMI).

Observe le marche AVANT qu'il ne soit resume par le prix :
  intention -> interaction -> execution -> reaction

Quatre dimensions :
  1. Flux agressif   (FlowAnalyzer)       — ce qui s'execute
  2. Liquidite       (LiquidityTracker)    — ce qui change dans le book
  3. Resistance      (ResistanceMeter)     — reponse du prix a la pression
  4. Etat structurel (classify_state)      — synthese en etat lisible

Produit un PressureField = champ de pression du marche.

Strictement passif (ADR-0007) — aucune influence sur les decisions.
"""

from trade_analysis.flow_analyzer import FlowAnalyzer
from trade_analysis.lmi_engine import LMIEngine
from trade_analysis.liquidity_tracker import LiquidityTracker
from trade_analysis.market_state import classify_state
from trade_analysis.models import (
    AggressiveFlow,
    LiquidityDynamics,
    MarketResistance,
    MarketStateLabel,
    PressureField,
)
from trade_analysis.recorder import LMIRecorder
from trade_analysis.resistance_meter import ResistanceMeter

__all__ = [
    "LMIEngine",
    "FlowAnalyzer",
    "LiquidityTracker",
    "ResistanceMeter",
    "LMIRecorder",
    "classify_state",
    "AggressiveFlow",
    "LiquidityDynamics",
    "MarketResistance",
    "MarketStateLabel",
    "PressureField",
]
