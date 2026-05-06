"""
regime_detector.py — Compatibility shim → pointe vers intelligence/regime_detector.py

Ce fichier est conservé pour la rétro-compatibilité des imports existants.
La vraie implémentation est dans agents/intelligence/regime_detector.py.
"""
from quant_hedge_ai.agents.intelligence.regime_detector import AdvancedRegimeDetector as RegimeDetector

__all__ = ["RegimeDetector"]
