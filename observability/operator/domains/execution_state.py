"""EXECUTION STATE (État d'exécution) — mission §11. Observation only —
no execution logic is touched by this module.

TradeLogger (SQLite) is the actual "orders attempted/accepted/rejected"
audit log; ExecutionLatencyMonitor covers fill latency/timeout/WS-desync.
No component in the repository joins these into a single canonical
execution-health snapshot today (a genuine gap, not fabricated here).
PAPER_TRADING_ENABLED / LIVE_TRADING_CONFIRMED are read via scattered
os.getenv() calls (execution_engine.py, advisor_loop.py,
scripts/prelive_gate.py) rather than centralized in
config/feature_flags.py — documented as-is, not changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from observability.operator.contracts import DomainSnapshot, FreshnessStatus, ObservedValue
from observability.operator.registry import MetricDefinition, ModuleDescriptor


@dataclass(frozen=True)
class ExecutionStateSnapshot(DomainSnapshot):
    mode: ObservedValue = None  # str: paper|live|live_failed|rejected
    paper_trading_enabled: ObservedValue = None  # bool
    live_trading_confirmed: ObservedValue = None  # bool
    orders_attempted: ObservedValue = None  # int
    orders_accepted: ObservedValue = None  # int
    orders_rejected: ObservedValue = None  # int
    last_execution_utc: ObservedValue = None  # datetime


def compose_execution_state_snapshot(
    *,
    observed_at_utc: datetime,
    mode: ObservedValue,
    paper_trading_enabled: ObservedValue,
    live_trading_confirmed: ObservedValue,
    orders_attempted: ObservedValue,
    orders_accepted: ObservedValue,
    orders_rejected: ObservedValue,
    last_execution_utc: ObservedValue,
    freshness: FreshnessStatus,
    status: str,
    source: str = "quant_hedge_ai.agents.execution.execution_engine.ExecutionEngine + TradeLogger",
    source_version: str = None,
    evidence: Mapping[str, object] = None,
) -> ExecutionStateSnapshot:
    return ExecutionStateSnapshot(
        domain="execution_state",
        observed_at_utc=observed_at_utc,
        source=source,
        source_version=source_version,
        freshness=freshness,
        status=status,
        evidence=evidence or {},
        mode=mode,
        paper_trading_enabled=paper_trading_enabled,
        live_trading_confirmed=live_trading_confirmed,
        orders_attempted=orders_attempted,
        orders_accepted=orders_accepted,
        orders_rejected=orders_rejected,
        last_execution_utc=last_execution_utc,
    )


METRICS = (
    MetricDefinition(
        metric_id="execution_state.mode",
        domain="execution_state",
        operator_label_fr="Mode d'exécution",
        technical_name="ExecutionEngine.create_order() return.mode",
        definition_fr="Mode effectif du dernier ordre traité: paper, live, live_failed ou rejected.",
        unit="enum",
        value_type="enum",
        freshness_source="per order attempt",
        expected_cadence="on order attempt",
        polarity="not_applicable",
        evidence_source="quant_hedge_ai/agents/execution/execution_engine.py:265-332",
        presentation_priority="primary",
    ),
    MetricDefinition(
        metric_id="execution_state.live_trading_confirmed",
        domain="execution_state",
        operator_label_fr="Confirmation trading réel (SEC-01)",
        technical_name="os.getenv('LIVE_TRADING_CONFIRMED')",
        definition_fr="Double-opt-in défense-en-profondeur: doit être true ET une clé API doit être présente avant que le chemin d'exécution réelle soit atteignable.",
        unit="boolean",
        value_type="boolean",
        freshness_source="process env at read time",
        expected_cadence="static per process lifetime",
        polarity="not_applicable",
        evidence_source="quant_hedge_ai/agents/execution/execution_engine.py:185-200",
        presentation_priority="primary",
        critical_semantics="true hors fenêtre de stabilisation autorisée doit être signalé à l'opérateur",
    ),
    MetricDefinition(
        metric_id="execution_state.orders_rejected",
        domain="execution_state",
        operator_label_fr="Ordres rejetés (pré-exchange)",
        technical_name="TradeLogger.log_rejected() count",
        definition_fr="Nombre d'ordres rejetés avant tout envoi à l'exchange (SessionGuard, déduplication, limites).",
        unit="count",
        value_type="count",
        freshness_source="TradeLogger SQLite table",
        expected_cadence="per order attempt",
        polarity="lower_is_better",
        evidence_source="quant_hedge_ai/agents/execution/trade_logger.py:48-125",
        presentation_priority="secondary",
        null_semantics="ZERO si aucun rejet enregistré; UNAVAILABLE si la table SQLite est injoignable",
    ),
)

MODULES = (
    ModuleDescriptor(
        module_id="execution_state.execution_engine",
        domain="execution_state",
        purpose="Point d'entrée gate/télémétrie pour toute tentative d'ordre",
        canonical_source="quant_hedge_ai/agents/execution/execution_engine.py",
        status="CANONICAL_EXISTING",
        consumers=("core/advisor_loop.py",),
        freshness_source="per order attempt",
        dependencies=("infra.wallet_sync",),
        known_debt="PAPER_TRADING_ENABLED/LIVE_TRADING_CONFIRMED lus via os.getenv() dispersés plutôt que centralisés dans config/feature_flags.py (fichier protégé, hors périmètre O-01).",
    ),
    ModuleDescriptor(
        module_id="execution_state.trade_logger",
        domain="execution_state",
        purpose="Journal SQLite de chaque tentative d'ordre (acceptée ou rejetée)",
        canonical_source="quant_hedge_ai/agents/execution/trade_logger.py",
        status="CANONICAL_EXISTING",
        consumers=("execution_engine.create_order()",),
        freshness_source="write per order attempt",
        dependencies=(),
        known_debt="Aucune",
    ),
    ModuleDescriptor(
        module_id="execution_state.latency_monitor",
        domain="execution_state",
        purpose="Latence de remplissage, timeouts, désynchronisation WS",
        canonical_source="quant_hedge_ai/agents/execution/latency_monitor.py",
        status="PARTIAL",
        consumers=(),
        freshness_source="per fill/reject/timeout event",
        dependencies=(),
        known_debt="Câblage vers les points d'appel live non entièrement confirmé dans cette passe forensique — à vérifier avant intégration.",
    ),
    ModuleDescriptor(
        module_id="execution_state.execution_simulator",
        domain="execution_state",
        purpose="Piste d'audit de remplissage structurée pour la couche de simulation (slippage, spread, latence, frais)",
        canonical_source="execution_simulator/models.py + execution_simulator/simulator.py",
        status="CANONICAL_EXISTING",
        consumers=("paper_trading/engine.py::BurninSimulationEngine (offline P5 uniquement)", "execution_simulator/fill_error_metric.py"),
        freshness_source="per simulated fill",
        dependencies=(),
        known_debt="Scopé au burn-in offline, pas à l'exécution live.",
    ),
    ModuleDescriptor(
        module_id="execution_state.paper_trading_engine_duplicate",
        domain="execution_state",
        purpose="Second moteur de paper trading, point d'entrée différent",
        canonical_source="quant_hedge_ai/agents/execution/paper_trading_engine.py",
        status="DUPLICATED",
        consumers=("quant_hedge_ai/main_system.py", "quant_hedge_ai/main_v91.py"),
        freshness_source="n/a",
        dependencies=(),
        known_debt="Parallèle à MexcSimulator (le moteur réellement utilisé par advisor_loop.py) via un entrypoint différent (main_system.py/main_v91.py) — nécessite une décision d'autorité hors périmètre O-01.",
    ),
    ModuleDescriptor(
        module_id="execution_state.unified_execution_health_gap",
        domain="execution_state",
        purpose="Vue agrégée 'ordres tentés/acceptés/rejetés sur N derniers cycles'",
        canonical_source="FUTURE_PROVIDER — aucun composant ne joint TradeLogger + ExecutionLatencyMonitor aujourd'hui",
        status="FUTURE_PROVIDER",
        consumers=(),
        freshness_source="n/a",
        dependencies=("execution_state.trade_logger", "execution_state.latency_monitor"),
        known_debt="Écart identifié par la passe forensique — pas de snapshot unique honnête équivalent à paper_trading/portfolio_status.py côté portefeuille.",
    ),
)
