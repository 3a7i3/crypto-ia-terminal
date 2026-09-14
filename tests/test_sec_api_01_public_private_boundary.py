"""SEC-API-01 — PUBLIC DATA / PRIVATE KEY SEPARATION.

Source-level least-privilege tests. They never read real secret values and
perform no network calls.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXCHANGE_SECRET_NAMES = {
    "MEXC_API_KEY",
    "MEXC_API_SECRET",
    "MEXC_SECRET_KEY",
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
    "BINANCE_LIVE_API_KEY",
    "BINANCE_LIVE_API_SECRET",
    "BINANCE_FUTURES_DEMO_KEY",
    "BINANCE_FUTURES_DEMO_SECRET",
    "BINANCE_SECRET",
    "KRAKEN_API_KEY",
    "KRAKEN_API_SECRET",
    "GATEIO_API_KEY",
    "GATEIO_API_SECRET",
    "BYBIT_API_KEY",
    "BYBIT_API_SECRET",
    "OKX_API_KEY",
    "OKX_API_SECRET",
    "OKX_PASSWORD",
    "LIVE_READER_API_KEY",
    "LIVE_READER_API_SECRET",
}

ZERO_KEY_UNITS = (
    "crypto-lmi-observatory.service",
    "crypto-market-observer.service",
    "crypto-market-radar.service",
    "crypto-market-horizons.service",
)

DEDICATED_SECRET_UNITS = {
    "crypto-quant-observer.service": "/etc/crypto-ai/secrets/quant-observer.env",
    "crypto-radar-bot.service": "/etc/crypto-ai/secrets/radar-bot.env",
    "crypto-dashboard.service": "/etc/crypto-ai/secrets/dashboard.env",
    "paper-arena.service": "/etc/crypto-ai/secrets/paper-arena.env",
    "crypto-watchdog.service": "/etc/crypto-ai/secrets/watchdog.env",
}


def _unit(name: str) -> str:
    return (ROOT / "scripts" / "systemd" / name).read_text(encoding="utf-8")


def _load_stream_bus(monkeypatch):
    fake_ccxt = types.ModuleType("ccxt")
    fake_pro = types.ModuleType("ccxt.pro")
    fake_pro.Exchange = object
    fake_ccxt.pro = fake_pro
    monkeypatch.setitem(sys.modules, "ccxt", fake_ccxt)
    monkeypatch.setitem(sys.modules, "ccxt.pro", fake_pro)

    path = ROOT / "infra" / "stream_bus.py"
    spec = importlib.util.spec_from_file_location("sec_api_01_stream_bus", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_stream_bus_ignores_environment_exchange_credentials(monkeypatch):
    monkeypatch.setenv("MEXC_API_KEY", "synthetic-test-value")
    monkeypatch.setenv("MEXC_API_SECRET", "synthetic-test-value")
    module = _load_stream_bus(monkeypatch)

    bus = module.StreamBus(symbols=["BTC/USDT"], exchange_id="mexc")

    assert bus.exchange_config == {"enableRateLimit": True}
    assert "apiKey" not in bus.exchange_config
    assert "secret" not in bus.exchange_config


def test_stream_bus_strips_explicit_private_ccxt_fields(monkeypatch):
    module = _load_stream_bus(monkeypatch)

    bus = module.StreamBus(
        symbols=["BTC/USDT"],
        exchange_id="binance",
        exchange_config={
            "enableRateLimit": True,
            "apiKey": "synthetic-test-value",
            "secret": "synthetic-test-value",
            "password": "synthetic-test-value",
            "options": {"defaultType": "future"},
        },
    )

    assert bus.exchange_config == {
        "enableRateLimit": True,
        "options": {"defaultType": "future"},
    }


def test_historical_fetcher_builds_public_ccxt_client(monkeypatch):
    captured: dict = {}

    class FakeExchange:
        rateLimit = 100

    fake_ccxt = types.ModuleType("ccxt")

    def mexc(config):
        captured.update(config)
        return FakeExchange()

    fake_ccxt.mexc = mexc
    monkeypatch.setitem(sys.modules, "ccxt", fake_ccxt)
    monkeypatch.setenv("MEXC_API_KEY", "synthetic-test-value")
    monkeypatch.setenv("MEXC_API_SECRET", "synthetic-test-value")

    from quant_hedge_ai.agents.market.historical_fetcher import HistoricalDataFetcher

    fetcher = HistoricalDataFetcher(exchange_id="mexc")
    assert fetcher._get_exchange() is not None
    assert captured == {"enableRateLimit": True}


def test_zero_key_public_units_do_not_load_global_secret_store():
    for name in ZERO_KEY_UNITS:
        text = _unit(name)
        assert ".env.secrets" not in text, name


def test_dedicated_secret_units_use_only_their_fragment():
    for name, fragment in DEDICATED_SECRET_UNITS.items():
        text = _unit(name)
        env_lines = [
            line for line in text.splitlines() if line.startswith("EnvironmentFile=")
        ]
        assert "EnvironmentFile=-/home/mathieu/crypto_ai_terminal/.env.secrets" not in env_lines, name
        assert "EnvironmentFile=/home/mathieu/crypto_ai_terminal/.env.secrets" not in env_lines, name
        assert f"EnvironmentFile={fragment}" in env_lines, name
        assert f"EnvironmentFile=-{fragment}" not in env_lines, name


def test_service_identity_fragments_are_domain_specific():
    fragments = set(DEDICATED_SECRET_UNITS.values())
    for name, own_fragment in DEDICATED_SECRET_UNITS.items():
        text = _unit(name)
        for foreign_fragment in fragments - {own_fragment}:
            assert foreign_fragment not in text, (name, foreign_fragment)

