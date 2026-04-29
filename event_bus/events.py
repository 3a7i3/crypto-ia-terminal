"""
Tous les types d'événements du système crypto_ai_terminal.

Hiérarchie:
  BaseEvent
  ├── SecurityEvents     (Pieuvre, sécurité statique)
  ├── MarketEvents       (scanner, régimes, prix)
  ├── TradingEvents      (ordres, positions, drawdown)
  ├── ApiEvents          (clés, connectivité exchange)
  ├── SystemEvents       (startup, shutdown, crash, santé)
  ├── EvolutionEvents    (cycles AI, mémoire stratégique)
  └── DemoEvents         (paper trading, FakeMoney — Phase 2)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


def _uid() -> str:
    return str(uuid.uuid4())[:8]


# ── Base ──────────────────────────────────────────────────────────────────────


@dataclass
class BaseEvent:
    """Classe mère de tous les événements."""

    event_id: str = field(default_factory=_uid)
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = "system"

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": type(self).__name__,
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            **{
                k: v
                for k, v in self.__dict__.items()
                if k not in ("event_id", "timestamp", "source")
            },
        }


# ── Security Events ───────────────────────────────────────────────────────────


@dataclass
class SecurityAlertEvent(BaseEvent):
    """Un tentacule de la Pieuvre a détecté une vulnérabilité."""

    severity: str = "low"  # low | medium | high | critical
    rule: str = ""
    file: str = ""
    line: int = 0
    message: str = ""
    tentacle: str = ""
    source: str = "pieuvre.securite"


@dataclass
class IncidentStartedEvent(BaseEvent):
    """La Pieuvre est passée en état ALERTE."""

    incident_id: str = ""
    severity: str = "low"
    module: str = ""
    message: str = ""
    source: str = "pieuvre.brain"


@dataclass
class IncidentResolvedEvent(BaseEvent):
    """La Pieuvre a résolu un incident et gagné de la force."""

    incident_id: str = ""
    severity: str = "low"
    strength_gained: float = 0.0
    recovery_seconds: float = 0.0
    new_force: float = 1.0
    immunity_patterns: list[str] = field(default_factory=list)
    source: str = "pieuvre.brain"


@dataclass
class PieuvreRegrowthEvent(BaseEvent):
    """La Pieuvre a terminé sa croissance post-incident."""

    generation: int = 0
    total_force: float = 1.0
    total_immunities: int = 0
    source: str = "pieuvre.brain"


# ── Market Events ─────────────────────────────────────────────────────────────


@dataclass
class TrendChangeEvent(BaseEvent):
    """Un régime de marché a changé."""

    symbol: str = ""
    old_regime: str = ""
    new_regime: str = ""  # bull_trend | bear_trend | ranging | volatile
    confidence: float = 0.0
    timeframe: str = "1h"
    source: str = "regime_detector"


@dataclass
class MarketScanCompleteEvent(BaseEvent):
    """Un cycle de scan de marché est terminé."""

    symbols_scanned: int = 0
    opportunities_found: int = 0
    top_symbol: str = ""
    top_score: float = 0.0
    exchange: str = ""
    source: str = "market_scanner"


@dataclass
class PriceAlertEvent(BaseEvent):
    """Un symbole a franchi un niveau de prix critique."""

    symbol: str = ""
    price: float = 0.0
    threshold: float = 0.0
    direction: str = "above"  # above | below
    change_pct: float = 0.0
    source: str = "price_monitor"


@dataclass
class BuySellPressureEvent(BaseEvent):
    """Pression achat/vente significative détectée."""

    symbol: str = ""
    buy_pressure_pct: float = 50.0  # 0-100
    sell_pressure_pct: float = 50.0
    net_flow_usd: float = 0.0
    dominant: str = "neutral"  # buy | sell | neutral
    timeframe: str = "1h"
    source: str = "orderflow_agent"


# ── Trading Events ────────────────────────────────────────────────────────────


@dataclass
class OrderFilledEvent(BaseEvent):
    """Un ordre a été exécuté (live ou paper)."""

    order_id: str = ""
    symbol: str = ""
    side: str = ""  # buy | sell
    size: float = 0.0
    price: float = 0.0
    value_usd: float = 0.0
    mode: str = "paper"  # paper | live | demo
    exchange: str = ""
    source: str = "execution_engine"


@dataclass
class OrderRejectedEvent(BaseEvent):
    """Un ordre a été rejeté."""

    symbol: str = ""
    side: str = ""
    size: float = 0.0
    reason: str = ""
    mode: str = "paper"
    source: str = "execution_engine"


@dataclass
class PositionOpenedEvent(BaseEvent):
    """Une nouvelle position a été ouverte."""

    symbol: str = ""
    side: str = ""
    size: float = 0.0
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    source: str = "execution_engine"


@dataclass
class PositionClosedEvent(BaseEvent):
    """Une position a été fermée."""

    symbol: str = ""
    side: str = ""
    pnl_usd: float = 0.0
    pnl_pct: float = 0.0
    duration_seconds: float = 0.0
    exit_reason: str = ""  # tp | sl | signal | manual
    source: str = "execution_engine"


@dataclass
class DrawdownAlertEvent(BaseEvent):
    """Drawdown dangereux détecté."""

    current_drawdown_pct: float = 0.0
    max_allowed_pct: float = 0.0
    symbol: str = ""
    action_taken: str = ""  # halt | reduce | warn
    source: str = "drawdown_guard"


@dataclass
class SessionHaltEvent(BaseEvent):
    """La session de trading a été suspendue."""

    reason: str = ""
    halt_duration_seconds: float = 0.0
    source: str = "session_guard"


# ── API / Exchange Events ─────────────────────────────────────────────────────


@dataclass
class ApiKeyUpdatedEvent(BaseEvent):
    """Une clé API a été ajoutée ou modifiée."""

    exchange: str = ""
    testnet: bool = False
    source: str = "api_keystore"


@dataclass
class ApiKeyValidatedEvent(BaseEvent):
    """Test de connectivité d'une clé API."""

    exchange: str = ""
    ok: bool = True
    latency_ms: float = 0.0
    error: str = ""
    source: str = "api_keystore"


@dataclass
class ApiKeyErrorEvent(BaseEvent):
    """Erreur critique sur une clé API (révoquée, expirée, invalide)."""

    exchange: str = ""
    error: str = ""
    source: str = "api_keystore"


@dataclass
class ExchangeConnectedEvent(BaseEvent):
    """Connexion à un exchange établie."""

    exchange: str = ""
    mode: str = "paper"
    source: str = "api_keystore"


# ── System Events ─────────────────────────────────────────────────────────────


@dataclass
class SystemStartupEvent(BaseEvent):
    """Le système a démarré."""

    mode: str = "paper"
    exchanges: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    version: str = ""
    source: str = "main"


@dataclass
class SystemShutdownEvent(BaseEvent):
    """Le système s'est arrêté."""

    reason: str = "user_stop"
    uptime_seconds: float = 0.0
    total_cycles: int = 0
    source: str = "main"


@dataclass
class CrashEvent(BaseEvent):
    """Exception non gérée dans un cycle."""

    context: str = ""
    error: str = ""
    error_type: str = ""
    traceback_snippet: str = ""
    source: str = "ops_watchdog"


@dataclass
class SystemHealthEvent(BaseEvent):
    """Snapshot de santé système périodique."""

    cpu_pct: float = 0.0
    ram_pct: float = 0.0
    disk_pct: float = 0.0
    status: str = "ok"  # ok | degraded | critical
    source: str = "surveillance"


@dataclass
class WsStaleEvent(BaseEvent):
    """Les données WebSocket sont périmées."""

    symbol: str = ""
    stale_seconds: float = 0.0
    source: str = "ops_watchdog"


# ── Evolution Events ──────────────────────────────────────────────────────────


@dataclass
class EvolutionCycleEvent(BaseEvent):
    """Un cycle d'évolution de stratégie est terminé."""

    cycle: int = 0
    generation: int = 0
    regime: str = ""
    candidates_tested: int = 0
    best_sharpe: float = 0.0
    avg_sharpe: float = 0.0
    saved_to_memory: int = 0
    source: str = "evolution_engine"


@dataclass
class NewBestStrategyEvent(BaseEvent):
    """Une nouvelle meilleure stratégie a été trouvée."""

    regime: str = ""
    sharpe: float = 0.0
    drawdown: float = 0.0
    strategy_name: str = ""
    source: str = "evolution_engine"


# ── Demo Events (Phase 2 — FakeMoney) ────────────────────────────────────────


@dataclass
class DemoDepositEvent(BaseEvent):
    """L'utilisateur a déposé des FakeMoney."""

    amount: float = 0.0
    currency: str = "USDT"
    new_balance: float = 0.0
    source: str = "demo_engine"


@dataclass
class DemoTradeExecutedEvent(BaseEvent):
    """La machine a exécuté un trade en mode Demo."""

    symbol: str = ""
    side: str = ""
    amount_usd: float = 0.0
    price: float = 0.0
    explanation: str = ""  # narration pas-à-pas
    fake_pnl_usd: float = 0.0
    source: str = "demo_engine"


@dataclass
class DemoSectorAnalysisEvent(BaseEvent):
    """Analyse sectorielle complète générée pour le panel Demo."""

    exchange: str = ""
    sector: str = ""
    top_buy_symbols: list[str] = field(default_factory=list)
    top_sell_symbols: list[str] = field(default_factory=list)
    source: str = "sector_ranker"
