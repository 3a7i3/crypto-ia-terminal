"""
scripts/seed_decision_packets.py

Génère des packets de démonstration pour tester le dashboard Decision Trace.
Usage : python scripts/seed_decision_packets.py
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.decision_packet import (
    ConvictionLevel,
    DecisionPacket,
    DecisionSide,
    DecisionState,
    MarketRegime,
    ReasoningCategory,
    ReasoningSeverity,
)

OUT = Path("databases/decision_packets.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

packets = []

# ── Packet 1 : flow nominal complet ──────────────────────────────────────────
p1 = DecisionPacket(
    symbol="BTC/USDT",
    side=DecisionSide.LONG,
    confidence=48.0,
    regime=MarketRegime.TREND_BULL,
)
p1.add_agent("live_signal_engine")
p1.add_reasoning(
    "live_signal_engine",
    "score=82 signal=BUY régime=TREND_BULL confirmé=True",
    confidence_impact=0.0,
    category=ReasoningCategory.SIGNAL_QUALITY,
)
p1.transition_to(
    DecisionState.SIGNAL_GENERATED,
    "live_signal_engine",
    "Signal détecté : score=82 direction=BUY",
)

p1.add_agent("conviction_engine")
p1.add_reasoning(
    "conviction_engine",
    "Signal fort: 82/100",
    confidence_impact=0.0,
    category=ReasoningCategory.SIGNAL_QUALITY,
)
p1.add_reasoning(
    "conviction_engine",
    "MTF confirmé sur 3 timeframes",
    confidence_impact=4.0,
    category=ReasoningCategory.TREND_ALIGNMENT,
)
p1.add_reasoning(
    "conviction_engine",
    "Régime TREND_BULL — adéquat pour BUY",
    confidence_impact=8.0,
    category=ReasoningCategory.TREND_ALIGNMENT,
)
p1.conviction = ConvictionLevel.HIGH
p1.transition_to(
    DecisionState.CONTEXT_ENRICHED, "conviction_engine", "Conviction HIGH score=72/100"
)

p1.add_agent("global_risk_gate")
p1.add_reasoning(
    "global_risk_gate",
    "Score 60.0 insuffisant (seuil=70)",
    confidence_impact=-15.0,
    category=ReasoningCategory.RISK_GOVERNANCE,
    severity=ReasoningSeverity.WARNING,
)
p1.features["risk_drawdown_pct"] = 2.1
p1.transition_to(
    DecisionState.RISK_EVALUATED, "global_risk_gate", "Gate pass — 5/5 conditions OK"
)

p1.add_agent("portfolio_brain")
p1.add_reasoning(
    "portfolio_brain",
    "Exposition totale OK: 22%",
    confidence_impact=2.0,
    category=ReasoningCategory.PORTFOLIO_EXPOSURE,
)
p1.add_reasoning(
    "portfolio_brain",
    "Concentration BTC/USDT OK: 12%",
    confidence_impact=1.0,
    category=ReasoningCategory.PORTFOLIO_CONCENTRATION,
)
p1.add_reasoning(
    "portfolio_brain",
    "Corrélation OK: 0.42",
    confidence_impact=1.0,
    category=ReasoningCategory.PORTFOLIO_CORRELATION,
)
p1.features["pb_exposure_pct"] = 0.22
p1.features["pb_symbol_pct"] = 0.12
p1.features["pb_corr_risk"] = 0.42
p1.metadata["pb_size_factor"] = 1.0
p1.transition_to(
    DecisionState.APPROVED, "portfolio_brain", "Portfolio OK — factor=1.00"
)
packets.append(p1)

# ── Packet 2 : rejeté par risk_gate (score insuffisant) ──────────────────────
p2 = DecisionPacket(
    symbol="ETH/USDT",
    side=DecisionSide.LONG,
    confidence=48.0,
    regime=MarketRegime.RANGE,
)
p2.add_agent("live_signal_engine")
p2.add_reasoning(
    "live_signal_engine",
    "score=54 signal=BUY régime=RANGE confirmé=False",
    confidence_impact=0.0,
    category=ReasoningCategory.SIGNAL_QUALITY,
)
p2.transition_to(
    DecisionState.SIGNAL_GENERATED,
    "live_signal_engine",
    "Signal détecté : score=54 direction=BUY",
)

p2.add_agent("conviction_engine")
p2.add_reasoning(
    "conviction_engine",
    "Signal faible: 54/100",
    confidence_impact=0.0,
    category=ReasoningCategory.SIGNAL_QUALITY,
)
p2.add_reasoning(
    "conviction_engine",
    "Alignement MTF faible: 38/100",
    confidence_impact=-3.0,
    category=ReasoningCategory.TREND_ALIGNMENT,
)
p2.conviction = ConvictionLevel.LOW
p2.transition_to(
    DecisionState.CONTEXT_ENRICHED, "conviction_engine", "Conviction LOW score=44/100"
)

p2.add_agent("global_risk_gate")
p2.add_reasoning(
    "global_risk_gate",
    "Score 45 insuffisant (seuil=70)",
    confidence_impact=-15.0,
    category=ReasoningCategory.RISK_GOVERNANCE,
    severity=ReasoningSeverity.WARNING,
)
p2.reject("global_risk_gate", "Gate block — 1 condition échouée: signal_score (45<70)")
packets.append(p2)

# ── Packet 3 : rejeté par risk_gate (régime blacklisté) ──────────────────────
p3 = DecisionPacket(
    symbol="SOL/USDT",
    side=DecisionSide.SHORT,
    confidence=88.0,
    regime=MarketRegime.VOLATILE,
)
p3.add_agent("live_signal_engine")
p3.add_reasoning(
    "live_signal_engine",
    "score=88 signal=SELL régime=VOLATILE confirmé=True",
    confidence_impact=0.0,
    category=ReasoningCategory.SIGNAL_QUALITY,
)
p3.transition_to(
    DecisionState.SIGNAL_GENERATED,
    "live_signal_engine",
    "Signal détecté : score=88 direction=SELL",
)

p3.add_agent("conviction_engine")
p3.add_reasoning(
    "conviction_engine",
    "Signal fort: 88/100",
    confidence_impact=0.0,
    category=ReasoningCategory.SIGNAL_QUALITY,
)
p3.conviction = ConvictionLevel.MEDIUM
p3.transition_to(
    DecisionState.CONTEXT_ENRICHED,
    "conviction_engine",
    "Conviction MEDIUM score=58/100",
)

p3.add_agent("global_risk_gate")
p3.add_reasoning(
    "global_risk_gate",
    "Régime VOLATILE blacklisté",
    confidence_impact=-25.0,
    category=ReasoningCategory.RISK_GOVERNANCE,
    severity=ReasoningSeverity.CRITICAL,
)
p3.reject("global_risk_gate", "Gate block — regime_blacklisted (VOLATILE)")
packets.append(p3)

# ── Packet 4 : vetoé par kill switch ─────────────────────────────────────────
p4 = DecisionPacket(
    symbol="BTC/USDT",
    side=DecisionSide.LONG,
    confidence=91.0,
    regime=MarketRegime.TREND_BULL,
)
p4.add_agent("live_signal_engine")
p4.add_reasoning(
    "live_signal_engine",
    "score=91 signal=BUY",
    confidence_impact=0.0,
    category=ReasoningCategory.SIGNAL_QUALITY,
)
p4.transition_to(
    DecisionState.SIGNAL_GENERATED,
    "live_signal_engine",
    "Signal détecté : score=91 direction=BUY",
)
p4.veto_by("kill_switch", "Drawdown -15% détecté — halt système")
packets.append(p4)

# ── Packet 5 : rejeté par portfolio_brain (max positions) ────────────────────
p5 = DecisionPacket(
    symbol="BTC/USDT",
    side=DecisionSide.LONG,
    confidence=75.0,
    regime=MarketRegime.TREND_BULL,
)
p5.add_agent("live_signal_engine")
p5.add_reasoning(
    "live_signal_engine",
    "score=75 signal=BUY",
    confidence_impact=0.0,
    category=ReasoningCategory.SIGNAL_QUALITY,
)
p5.transition_to(
    DecisionState.SIGNAL_GENERATED,
    "live_signal_engine",
    "Signal détecté : score=75 direction=BUY",
)

p5.add_agent("conviction_engine")
p5.conviction = ConvictionLevel.MEDIUM
p5.transition_to(
    DecisionState.CONTEXT_ENRICHED,
    "conviction_engine",
    "Conviction MEDIUM score=55/100",
)

p5.add_agent("global_risk_gate")
p5.features["risk_drawdown_pct"] = 1.2
p5.transition_to(
    DecisionState.RISK_EVALUATED, "global_risk_gate", "Gate pass — 5/5 conditions OK"
)

p5.add_agent("portfolio_brain")
p5.add_reasoning(
    "portfolio_brain",
    "Max positions atteint: 5/5",
    confidence_impact=-30.0,
    category=ReasoningCategory.PORTFOLIO_RISK_BUDGET,
    severity=ReasoningSeverity.CRITICAL,
)
p5.reject("portfolio_brain", "Max positions atteint: 5/5")
packets.append(p5)

# ── Écriture ──────────────────────────────────────────────────────────────────
with open(OUT, "w", encoding="utf-8") as f:
    for p in packets:
        f.write(json.dumps(p.to_dict(), ensure_ascii=False) + "\n")

print(f"OK {len(packets)} packets ecrits dans {OUT}")
for p in packets:
    print(f"  {p.symbol} {p.side.value} -> {p.lifecycle_state.value}")
