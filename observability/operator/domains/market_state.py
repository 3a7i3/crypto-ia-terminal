"""MARKET STATE (État du marché) — mission §7.

Regime source: core/advisor_loop.py's stability-smoothed
``_adaptive_regime`` (AdvancedRegimeDetector + a consecutive-vote filter),
not the raw per-cycle detector output. Regime confidence/entropy exist
as ``RegimePacket``/``_regime_tracker`` fields
(quant_hedge_ai/agents/intelligence/market_regime_classifier.py) but are
computed and logged without ever reaching the operator-facing
SystemSnapshot today — marked NOT_CURRENTLY_AVAILABLE at the presentation
layer, per mission §7 ("do not invent confidence metrics that do not
already exist").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from observability.operator.contracts import DomainSnapshot, FreshnessStatus, ObservedValue
from observability.operator.registry import MetricDefinition, ModuleDescriptor


@dataclass(frozen=True)
class MarketStateSnapshot(DomainSnapshot):
    regime: ObservedValue = None  # str
    regime_confidence: ObservedValue = None  # float 0-1 — NOT_CURRENTLY_AVAILABLE at snapshot level today
    exchange_latency_ms: ObservedValue = None  # float
    exchange_uptime_pct: ObservedValue = None  # float
    universe_size: ObservedValue = None  # int — INCONCLUSIVE, no confirmed producer found
    instruments_with_valid_data: ObservedValue = None  # int


def compose_market_state_snapshot(
    *,
    observed_at_utc: datetime,
    regime: ObservedValue,
    regime_confidence: ObservedValue,
    exchange_latency_ms: ObservedValue,
    exchange_uptime_pct: ObservedValue,
    universe_size: ObservedValue,
    instruments_with_valid_data: ObservedValue,
    freshness: FreshnessStatus,
    status: str,
    source: str = "core.advisor_loop regime tracker + supervision.exchange_monitor",
    source_version: str = None,
    evidence: Mapping[str, object] = None,
) -> MarketStateSnapshot:
    return MarketStateSnapshot(
        domain="market_state",
        observed_at_utc=observed_at_utc,
        source=source,
        source_version=source_version,
        freshness=freshness,
        status=status,
        evidence=evidence or {},
        regime=regime,
        regime_confidence=regime_confidence,
        exchange_latency_ms=exchange_latency_ms,
        exchange_uptime_pct=exchange_uptime_pct,
        universe_size=universe_size,
        instruments_with_valid_data=instruments_with_valid_data,
    )


METRICS = (
    MetricDefinition(
        metric_id="market_state.regime",
        domain="market_state",
        operator_label_fr="Régime de marché",
        technical_name="advisor_loop._adaptive_regime (smoothed AdvancedRegimeDetector vote)",
        definition_fr="Régime de marché courant, stabilisé par un filtre de vote consécutif avant mise à jour (évite les flips à chaque cycle).",
        unit="enum",
        value_type="enum",
        freshness_source="advisor loop cycle cadence",
        expected_cadence="per advisor loop cycle",
        polarity="neutral",
        evidence_source="core/advisor_loop.py:6342-6361,6987-6988",
        presentation_priority="primary",
    ),
    MetricDefinition(
        metric_id="market_state.regime_confidence",
        domain="market_state",
        operator_label_fr="Confiance du régime",
        technical_name="RegimePacket.confidence / _regime_tracker",
        definition_fr="Confiance du détecteur de régime brut (avant lissage). Calculée et journalisée mais non exposée au SystemSnapshot opérateur aujourd'hui.",
        unit="ratio_0_1",
        value_type="score",
        freshness_source="NOT_CURRENTLY_AVAILABLE at operator snapshot layer",
        expected_cadence="per advisor loop cycle (internal only)",
        polarity="higher_is_better",
        evidence_source="quant_hedge_ai/agents/intelligence/market_regime_classifier.py:36; core/advisor_loop.py:6331-6339",
        presentation_priority="diagnostic",
        null_semantics="UNAVAILABLE — non câblé au SystemSnapshot opérateur (gap identifié, pas une hypothèse)",
    ),
    MetricDefinition(
        metric_id="market_state.exchange_latency_ms",
        domain="market_state",
        operator_label_fr="Latence exchange (marché)",
        technical_name="ExchangeMonitor.snapshot().last_latency_ms",
        definition_fr="Latence de connectivité vers l'exchange actif, telle que reflétée dans MarketSnapshot.",
        unit="ms",
        value_type="duration_ms",
        freshness_source="ExchangeMonitor background thread",
        expected_cadence="continuous",
        polarity="lower_is_better",
        evidence_source="supervision/exchange_monitor.py; core/advisor_loop.py:6989-6994",
        presentation_priority="secondary",
    ),
    MetricDefinition(
        metric_id="market_state.universe_size",
        domain="market_state",
        operator_label_fr="Taille de l'univers scanné",
        technical_name="INCONCLUSIVE — aucun compteur confirmé",
        definition_fr="Nombre d'instruments dans l'univers de scan courant.",
        unit="count",
        value_type="count",
        freshness_source="NOT_CURRENTLY_AVAILABLE",
        expected_cadence="NOT_CURRENTLY_AVAILABLE",
        polarity="not_applicable",
        evidence_source="core/perp_universe_service.py, quant_hedge_ai/agents/market/market_scanner.py — pas de champ de couverture confirmé consommé par une couche d'observabilité",
        presentation_priority="diagnostic",
        null_semantics="UNKNOWN — producteur non confirmé, à revalider avant intégration",
    ),
)

MODULES = (
    ModuleDescriptor(
        module_id="market_state.observation_pulse",
        domain="market_state",
        purpose="Collecteur de pouls marché découplé (spot+swap tickers)",
        canonical_source="observation/market_observer.py",
        status="CANONICAL_EXISTING",
        consumers=("core/topk_scheduler.py",),
        freshness_source="crypto-market-observer.timer (15 min)",
        dependencies=(),
        known_debt="Aucune — module correctement isolé (ADR-0016), zéro import moteur.",
    ),
    ModuleDescriptor(
        module_id="market_state.regime_classifier",
        domain="market_state",
        purpose="Détection et lissage du régime de marché",
        canonical_source="quant_hedge_ai/agents/intelligence/market_regime_classifier.py",
        status="PARTIAL",
        consumers=("core/advisor_loop.py", "GlobalRiskGate", "MetaStrategyEngine", "RegretEngine"),
        freshness_source="advisor loop cycle",
        dependencies=(),
        known_debt="confidence/entropy calculés mais non propagés à SystemSnapshot.market — seule la chaîne de régime brute atteint l'opérateur.",
    ),
    ModuleDescriptor(
        module_id="market_state.exchange_monitor",
        domain="market_state",
        purpose="Connectivité/latence exchange (partagé avec system_health)",
        canonical_source="supervision/exchange_monitor.py",
        status="CANONICAL_EXISTING",
        consumers=("core/advisor_loop.py",),
        freshness_source="background ping thread",
        dependencies=(),
        known_debt="Aucune",
    ),
)
