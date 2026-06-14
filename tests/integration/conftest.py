"""Fixtures partagées — tests d'intégration Chantier C."""

from __future__ import annotations

import os

import pytest

from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine
from quant_hedge_ai.agents.market.market_scanner import MarketScanner
from quant_hedge_ai.agents.quant.backtest_lab import BacktestLab
from quant_hedge_ai.agents.quant.walk_forward import WalkForwardValidator

# ── Constantes ────────────────────────────────────────────────────────────────

SYMBOLS = ["BTCUSDT", "ETHUSDT"]

STRATEGY_EMA = {"entry_indicator": "EMA", "period": 14, "threshold": 1.0}
STRATEGY_RSI = {"entry_indicator": "RSI", "period": 14, "threshold": 1.0}
STRATEGIES = [STRATEGY_EMA, STRATEGY_RSI]

HAS_TESTNET_KEYS = bool(
    os.getenv("MEXC_API_KEY")
    and os.getenv("MEXC_API_SECRET")
    and os.getenv("EXCHANGE_TESTNET", "false").lower() == "true"
)

SKIP_TESTNET = pytest.mark.skipif(
    not HAS_TESTNET_KEYS,
    reason="Requiert MEXC_API_KEY + MEXC_API_SECRET + EXCHANGE_TESTNET=true",
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def scanner_synthetic(monkeypatch):
    """MarketScanner forcé en mode synthétique (aucune requête réseau)."""
    monkeypatch.setenv("MARKET_SCANNER_SYNTHETIC", "true")
    return MarketScanner(symbols=SYMBOLS, timeframe="1h", limit=150)


@pytest.fixture
def scanner_testnet():
    """MarketScanner branché sur testnet.binance.vision (nécessite clés API)."""
    return MarketScanner(symbols=SYMBOLS, timeframe="1h", limit=100)


@pytest.fixture
def engine_paper(tmp_path, monkeypatch):
    """ExecutionEngine en mode paper avec SQLite temporaire."""
    monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trades.sqlite"))
    monkeypatch.setenv("EXEC_MAX_ORDER_USD", "5000")
    engine = ExecutionEngine(live=False)
    engine.start_session(equity=10_000.0)
    return engine


@pytest.fixture
def engine_testnet(tmp_path, monkeypatch):
    """ExecutionEngine live sur testnet Binance (nécessite clés API)."""
    monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trades_testnet.sqlite"))
    monkeypatch.setenv("EXCHANGE_TESTNET", "true")
    engine = ExecutionEngine.from_env()
    engine.start_session(equity=10_000.0)
    return engine


@pytest.fixture
def lab():
    return BacktestLab()


@pytest.fixture
def validator():
    return WalkForwardValidator(train_ratio=0.7, decay_threshold=0.5, min_trades_oos=3)
