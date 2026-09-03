"""PORTFOLIO STATE (État du portefeuille) — mission §10.

Constitutional separation: REAL ACCOUNT API OBSERVATION
(observability/real_accounts.py, read-only multi-exchange balances) is
never arithmetically combined with PAPER/SIMULATED MACHINE CAPITAL
(infra/wallet_sync.py, WALLET_PAPER_CAPITAL-based). This is a designed
guardrail already enforced in the codebase
(observability/real_accounts.py:6-7,201-202: "jamais utilisé pour le
sizing... la base de sizing reste WALLET_PAPER_CAPITAL") — this contract
preserves that separation as two distinct, independently-labeled fields
that must never be summed by a presentation adapter.

Forensic finding to carry forward: two competing open-position stores
exist (MexcSimulator, populated with real prices, vs pos_manager fed to
PortfolioBrain.portfolio_health(), frequently empty) — exposure/free-cash
fields sourced from PortfolioBrain inherit that divergence risk until
reconciled outside O-01's scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from observability.operator.contracts import DomainSnapshot, FreshnessStatus, ObservedValue
from observability.operator.registry import MetricDefinition, ModuleDescriptor


@dataclass(frozen=True)
class PortfolioStateSnapshot(DomainSnapshot):
    paper_equity_usd: ObservedValue = None  # float — WALLET_PAPER_CAPITAL-based, infra/wallet_sync.py
    paper_open_positions_count: ObservedValue = None  # int
    paper_unrealized_pnl_usd: ObservedValue = None  # float
    paper_realized_pnl_usd: ObservedValue = None  # float
    real_account_equity_usd: ObservedValue = None  # float — observability/real_accounts.py, read-only
    real_account_free_usd: ObservedValue = None  # float
    real_account_stale: ObservedValue = None  # bool


def compose_portfolio_state_snapshot(
    *,
    observed_at_utc: datetime,
    paper_equity_usd: ObservedValue,
    paper_open_positions_count: ObservedValue,
    paper_unrealized_pnl_usd: ObservedValue,
    paper_realized_pnl_usd: ObservedValue,
    real_account_equity_usd: ObservedValue,
    real_account_free_usd: ObservedValue,
    real_account_stale: ObservedValue,
    freshness: FreshnessStatus,
    status: str,
    source: str = "infra.wallet_sync.WalletSync + observability.real_accounts.RealAccountsObserver",
    source_version: str = None,
    evidence: Mapping[str, object] = None,
) -> PortfolioStateSnapshot:
    return PortfolioStateSnapshot(
        domain="portfolio_state",
        observed_at_utc=observed_at_utc,
        source=source,
        source_version=source_version,
        freshness=freshness,
        status=status,
        evidence=evidence or {},
        paper_equity_usd=paper_equity_usd,
        paper_open_positions_count=paper_open_positions_count,
        paper_unrealized_pnl_usd=paper_unrealized_pnl_usd,
        paper_realized_pnl_usd=paper_realized_pnl_usd,
        real_account_equity_usd=real_account_equity_usd,
        real_account_free_usd=real_account_free_usd,
        real_account_stale=real_account_stale,
    )


METRICS = (
    MetricDefinition(
        metric_id="portfolio_state.paper_equity_usd",
        domain="portfolio_state",
        operator_label_fr="Capital paper (simulé)",
        technical_name="infra.wallet_sync.WalletSync.get_balance() [paper mode]",
        definition_fr="Équité simulée, basée sur WALLET_PAPER_CAPITAL + PnL cumulé du ledger paper_trades.jsonl. Ne représente aucun fonds réel.",
        unit="usd",
        value_type="currency_usd",
        freshness_source="infra/wallet_sync.py ledger read",
        expected_cadence="per advisor loop cycle",
        polarity="not_applicable",
        evidence_source="infra/wallet_sync.py:48-70",
        presentation_priority="primary",
    ),
    MetricDefinition(
        metric_id="portfolio_state.real_account_equity_usd",
        domain="portfolio_state",
        operator_label_fr="Équité compte réel (API, lecture seule)",
        technical_name="observability.real_accounts.RealAccountsObserver.aggregate()",
        definition_fr="Équité agrégée lue en lecture seule depuis les comptes exchange réels (multi-exchange via ccxt). Jamais utilisée pour le sizing et jamais combinée arithmétiquement au capital paper.",
        unit="usd",
        value_type="currency_usd",
        freshness_source="RealAccountsObserver poll cadence",
        expected_cadence="per notify cycle",
        polarity="not_applicable",
        evidence_source="observability/real_accounts.py:39-271; core/advisor_loop.py:393-401,7102-7106",
        presentation_priority="primary",
        null_semantics="NOT_APPLICABLE si aucun compte réel n'est configuré pour cette fenêtre de stabilisation",
    ),
    MetricDefinition(
        metric_id="portfolio_state.paper_open_positions_count",
        domain="portfolio_state",
        operator_label_fr="Positions paper ouvertes",
        technical_name="paper_trading.mexc_simulator.MexcSimulator._positions (via paper_portfolio_view)",
        definition_fr="Nombre de positions simulées actuellement ouvertes, prix réels de marché.",
        unit="count",
        value_type="count",
        freshness_source="MexcSimulator in-memory state",
        expected_cadence="per advisor loop cycle",
        polarity="not_applicable",
        evidence_source="paper_trading/mexc_simulator.py; paper_trading/paper_portfolio_view.py:46-108",
        presentation_priority="primary",
        null_semantics="ZERO si le simulateur est actif sans position; UNAVAILABLE si le simulateur n'est pas instancié",
    ),
)

MODULES = (
    ModuleDescriptor(
        module_id="portfolio_state.wallet_sync",
        domain="portfolio_state",
        purpose="Source unique de capital/équité paper (remplace 4 constantes historiquement divergentes)",
        canonical_source="infra/wallet_sync.py",
        status="CANONICAL_EXISTING",
        consumers=("quant_hedge_ai/agents/execution/execution_engine.py::fetch_available_capital()",),
        freshness_source="ledger read at call time",
        dependencies=("databases/paper_trades.jsonl",),
        known_debt="Aucune pour le capital lui-même.",
    ),
    ModuleDescriptor(
        module_id="portfolio_state.mexc_simulator",
        domain="portfolio_state",
        purpose="Livre de positions paper réel (prix de marché réels, remplissages simulés)",
        canonical_source="paper_trading/mexc_simulator.py",
        status="CANONICAL_EXISTING",
        consumers=("paper_trading/paper_portfolio_view.py", "PortfolioBrain via l'adaptateur"),
        freshness_source="in-process, per cycle",
        dependencies=(),
        known_debt="Coexiste avec un second store de positions (pos_manager) alimentant PortfolioBrain.portfolio_health() de façon divergente — voir portfolio_state.portfolio_brain_duplicated ci-dessous.",
    ),
    ModuleDescriptor(
        module_id="portfolio_state.portfolio_status_builder",
        domain="portfolio_state",
        purpose="Vue portefeuille honnête, construite uniquement à partir de paper_portfolio_view",
        canonical_source="paper_trading/portfolio_status.py::build_portfolio_status()",
        status="CANONICAL_EXISTING",
        consumers=(),
        freshness_source="paper_portfolio_view snapshot",
        dependencies=("paper_trading.paper_portfolio_view",),
        known_debt="Aucune — conçu spécifiquement pour éviter la mésattribution constatée dans meta_engine.current_personality().",
    ),
    ModuleDescriptor(
        module_id="portfolio_state.portfolio_brain_duplicated",
        domain="portfolio_state",
        purpose="Calcul d'exposition/free-capital à partir d'un second store de positions",
        canonical_source="quant_hedge_ai/agents/risk/portfolio_brain.py::portfolio_health()",
        status="DUPLICATED",
        consumers=("core/advisor_loop.py:6785-6787", "system/integrity_snapshot.py"),
        freshness_source="pos_manager.get_open() snapshot",
        dependencies=(),
        known_debt="pos_manager diverge de MexcSimulator (souvent vide alors que des positions réelles-paper existent) — free_capital/exposure_pct hérités de ce calcul sont potentiellement incorrects tant que non réconciliés.",
    ),
    ModuleDescriptor(
        module_id="portfolio_state.real_accounts_observer",
        domain="portfolio_state",
        purpose="Observation lecture-seule des comptes exchange réels, isolée du sizing",
        canonical_source="observability/real_accounts.py",
        status="CANONICAL_EXISTING",
        consumers=("core/advisor_loop.py (bloc texte séparé, jamais sommé)",),
        freshness_source="poll per notify cycle",
        dependencies=(),
        known_debt="Aucune — garde-fou de séparation à préserver explicitement dans toute nouvelle présentation.",
    ),
    ModuleDescriptor(
        module_id="portfolio_state.portfolio_api_static",
        domain="portfolio_state",
        purpose="Endpoint REST retournant un snapshot portefeuille",
        canonical_source="visualization/api/portfolio_api.py::load_portfolio_snapshot()",
        status="PRESENTATION_ONLY",
        consumers=("dashboard REST consumer (non confirmé)",),
        freshness_source="n/a",
        dependencies=(),
        known_debt="8 des 10 champs retournés sont codés en dur à 0.0; total_pnl_usd substitue silencieusement le PnL ouvert au PnL total. Ne pas traiter comme source canonique tant que non corrigé.",
    ),
    ModuleDescriptor(
        module_id="portfolio_state.virtual_portfolio_legacy",
        domain="portfolio_state",
        purpose="Ancien livre de positions simulées",
        canonical_source="paper_trading/virtual_portfolio.py",
        status="LEGACY",
        consumers=("tests only",),
        freshness_source="n/a",
        dependencies=(),
        known_debt="Zéro point d'appel en production — superseded par MexcSimulator, jamais supprimé.",
    ),
)
