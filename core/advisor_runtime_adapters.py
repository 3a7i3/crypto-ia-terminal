from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class AdvisorRuntime:
    MarketScanner: Any
    MultiTimeframeScanner: Any
    LiveSignalEngine: Any
    GlobalRiskGate: Any
    AIAdvisor: Any
    ShadowExecutionEngine: Any
    PerformanceWatchdog: Any
    StrategyMemoryStore: Any
    TelegramKillSwitch: Any
    ExchangeMonitor: Any
    SelfHealingBot: Any
    ExecutionEngine: Any
    PositionManager: Any
    Position: Any
    tracker_finalize_position: Callable[..., Any]
    tracker_open_position: Callable[..., Any]
    tracker_run_cycle: Callable[..., Any]
    MetaStrategyEngine: Any
    StrategyRanker: Any
    SelfAwarenessEngine: Any
    DangerLevel: Any
    NoTradeIntelligence: Any
    ConvictionEngine: Any
    DecisionQualityEngine: Any
    PortfolioBrain: Any
    CapitalAllocationEngine: Any
    MistakeMemory: Any
    ExecutiveOverride: Any
    BlackBox: Any
    RegretEngine: Any
    ChiefOfficer: Any
    ThreatRadar: Any
    MetaLearner: Any
    FeatureEngineer: Any
    AdvancedRegimeDetector: Any
    ConfidenceExplainer: Any
    AdaptiveThresholdEngine: Any = field(default=None)
    RegimeTransitionSmoother: Any = field(default=None)
    RegimeStateTracker: Any = field(default=None)


def load_advisor_runtime() -> AdvisorRuntime:
    from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine
    from quant_hedge_ai.agents.execution.live_signal_engine import LiveSignalEngine
    from quant_hedge_ai.agents.execution.position_manager import (
        Position,
        PositionManager,
    )
    from quant_hedge_ai.agents.execution.shadow_engine import ShadowExecutionEngine
    from quant_hedge_ai.agents.intelligence.adaptive_threshold_engine import (
        AdaptiveThresholdEngine,
    )
    from quant_hedge_ai.agents.intelligence.ai_advisor import AIAdvisor
    from quant_hedge_ai.agents.intelligence.black_box import BlackBox
    from quant_hedge_ai.agents.intelligence.chief_officer import ChiefOfficer
    from quant_hedge_ai.agents.intelligence.confidence_explainer import (
        ConfidenceExplainer,
    )
    from quant_hedge_ai.agents.intelligence.conviction_engine import ConvictionEngine
    from quant_hedge_ai.agents.intelligence.decision_quality_engine import (
        DecisionQualityEngine,
    )
    from quant_hedge_ai.agents.intelligence.feature_engineer import FeatureEngineer
    from quant_hedge_ai.agents.intelligence.market_regime_classifier import (
        RegimeStateTracker,
    )
    from quant_hedge_ai.agents.intelligence.meta_strategy_engine import (
        MetaStrategyEngine,
    )
    from quant_hedge_ai.agents.intelligence.mistake_memory import MistakeMemory
    from quant_hedge_ai.agents.intelligence.no_trade_layer import NoTradeIntelligence
    from quant_hedge_ai.agents.intelligence.regime_detector import (
        AdvancedRegimeDetector,
    )
    from quant_hedge_ai.agents.intelligence.regime_transition_smoother import (
        RegimeTransitionSmoother,
    )
    from quant_hedge_ai.agents.intelligence.regret_engine import RegretEngine
    from quant_hedge_ai.agents.intelligence.self_awareness_engine import (
        DangerLevel,
        SelfAwarenessEngine,
    )
    from quant_hedge_ai.agents.intelligence.threat_radar import ThreatRadar
    from quant_hedge_ai.agents.market.market_scanner import MarketScanner
    from quant_hedge_ai.agents.market.multi_timeframe_scanner import (
        MultiTimeframeScanner,
    )
    from quant_hedge_ai.agents.risk.capital_allocation_engine import (
        CapitalAllocationEngine,
    )
    from quant_hedge_ai.agents.risk.executive_override import ExecutiveOverride
    from quant_hedge_ai.agents.risk.global_risk_gate import GlobalRiskGate
    from quant_hedge_ai.agents.risk.portfolio_brain import PortfolioBrain
    from quant_hedge_ai.ai_evolution.strategy_memory import StrategyMemoryStore
    from quant_hedge_ai.ai_evolution.strategy_ranker import StrategyRanker
    from supervision.exchange_monitor import ExchangeMonitor
    from supervision.killswitch_hardened import KillSwitchHardened as TelegramKillSwitch
    from supervision.performance_watchdog import PerformanceWatchdog
    from supervision.self_healing_bot import SelfHealingBot
    from tracker_system.core.trade_tracker import (
        finalize_position as tracker_finalize_position,
    )
    from tracker_system.core.trade_tracker import open_position as tracker_open_position
    from tracker_system.main import run_cycle as tracker_run_cycle
    from tracker_system.meta_learner import MetaLearner

    return AdvisorRuntime(
        MarketScanner=MarketScanner,
        MultiTimeframeScanner=MultiTimeframeScanner,
        LiveSignalEngine=LiveSignalEngine,
        GlobalRiskGate=GlobalRiskGate,
        AIAdvisor=AIAdvisor,
        ShadowExecutionEngine=ShadowExecutionEngine,
        PerformanceWatchdog=PerformanceWatchdog,
        StrategyMemoryStore=StrategyMemoryStore,
        TelegramKillSwitch=TelegramKillSwitch,
        ExchangeMonitor=ExchangeMonitor,
        SelfHealingBot=SelfHealingBot,
        ExecutionEngine=ExecutionEngine,
        PositionManager=PositionManager,
        Position=Position,
        tracker_finalize_position=tracker_finalize_position,
        tracker_open_position=tracker_open_position,
        tracker_run_cycle=tracker_run_cycle,
        MetaStrategyEngine=MetaStrategyEngine,
        StrategyRanker=StrategyRanker,
        SelfAwarenessEngine=SelfAwarenessEngine,
        DangerLevel=DangerLevel,
        NoTradeIntelligence=NoTradeIntelligence,
        ConvictionEngine=ConvictionEngine,
        DecisionQualityEngine=DecisionQualityEngine,
        PortfolioBrain=PortfolioBrain,
        CapitalAllocationEngine=CapitalAllocationEngine,
        MistakeMemory=MistakeMemory,
        ExecutiveOverride=ExecutiveOverride,
        BlackBox=BlackBox,
        RegretEngine=RegretEngine,
        ChiefOfficer=ChiefOfficer,
        ThreatRadar=ThreatRadar,
        MetaLearner=MetaLearner,
        FeatureEngineer=FeatureEngineer,
        AdvancedRegimeDetector=AdvancedRegimeDetector,
        ConfidenceExplainer=ConfidenceExplainer,
        AdaptiveThresholdEngine=AdaptiveThresholdEngine,
        RegimeTransitionSmoother=RegimeTransitionSmoother,
        RegimeStateTracker=RegimeStateTracker,
    )
