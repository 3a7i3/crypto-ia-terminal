"""
Tests CFG-P2-01 — config/settings.py

Invariants:
  CFG-01  Defaults corrects sans env ni JSON
  CFG-02  Env vars surchargent les defaults
  CFG-03  JSON override surcharge env + defaults
  CFG-04  JSON manquant → pas de crash, defaults conservés
  CFG-05  JSON corrompu → pas de crash, defaults conservés
  CFG-06  exec_max_order_usd <= 0 → ValidationError
  CFG-07  TelegramSettings.enabled False si token vide
  CFG-08  TelegramSettings.enabled True si token+chat présents
  CFG-09  get_settings() retourne le même objet (singleton)
  CFG-10  Settings avec _runtime_override_path=None ignore le JSON
  CFG-11  JSON override EXEC_MAX_ORDER_USD appliqué sur execution.exec_max_order_usd
  CFG-12  JSON override partiel n'affecte que les clés présentes
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from config.settings import (
    ExchangeSettings,
    ExecutionSettings,
    FeatureFlags,
    MonitoringSettings,
    PortfolioSettings,
    RiskSettings,
    Settings,
    TelegramSettings,
    get_settings,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _clean_env(monkeypatch, *keys: str) -> None:
    """Ensure the given env keys are unset for the duration of the test."""
    for k in keys:
        monkeypatch.delenv(k, raising=False)


# ── CFG-01 : defaults corrects ─────────────────────────────────────────────────


def test_exchange_defaults(monkeypatch):
    _clean_env(monkeypatch, "EXCHANGE_ID", "EXCHANGE_TESTNET", "EXCHANGE_HEARTBEAT_S")
    s = ExchangeSettings(_env_file=None)
    assert s.exchange_id == "binance"
    assert s.exchange_testnet is False
    assert s.exchange_heartbeat_s == 15


def test_execution_defaults(monkeypatch):
    _clean_env(
        monkeypatch,
        "EXEC_MAX_ORDER_USD",
        "EXEC_MAX_DD",
        "EXEC_MAX_LOSS",
        "EXEC_MAX_CONSEC_LOSSES",
        "EXEC_DEDUP_WINDOW",
        "FORCE_TEST_EXECUTION",
    )
    s = ExecutionSettings(_env_file=None)
    assert s.exec_max_order_usd == 50.0
    assert s.exec_max_dd == 0.05
    assert s.exec_max_loss == 0.03
    assert s.exec_max_consec_losses == 3
    assert s.exec_dedup_window == 30.0
    assert s.force_test_execution is False


def test_risk_defaults(monkeypatch):
    _clean_env(monkeypatch, "SIGNAL_MIN_SCORE", "EO_DD_VETO", "EO_DD_RECOVERY")
    s = RiskSettings(_env_file=None)
    assert s.signal_min_score == 70.0
    assert s.gate_min_score_override == 0.0
    assert s.eo_dd_veto == 0.10
    assert s.eo_dd_recovery == 0.04


def test_portfolio_defaults(monkeypatch):
    _clean_env(monkeypatch, "V9_INITIAL_CAPITAL", "V9_KELLY_SAFETY", "V9_MAX_DRAWDOWN")
    s = PortfolioSettings(_env_file=None)
    assert s.v9_initial_capital == 1000.0
    assert s.v9_kelly_safety == 0.25
    assert s.v9_max_drawdown == 0.05


# ── CFG-02 : env vars surchargent les defaults ─────────────────────────────────


def test_exchange_env_override(monkeypatch):
    monkeypatch.setenv("EXCHANGE_ID", "bybit")
    monkeypatch.setenv("EXCHANGE_TESTNET", "true")
    s = ExchangeSettings(_env_file=None)
    assert s.exchange_id == "bybit"
    assert s.exchange_testnet is True


def test_execution_env_override(monkeypatch):
    monkeypatch.setenv("EXEC_MAX_ORDER_USD", "75")
    monkeypatch.setenv("EXEC_MAX_DD", "0.08")
    s = ExecutionSettings(_env_file=None)
    assert s.exec_max_order_usd == 75.0
    assert s.exec_max_dd == 0.08


def test_risk_env_override(monkeypatch):
    monkeypatch.setenv("SIGNAL_MIN_SCORE", "65")
    monkeypatch.setenv("EO_DD_VETO", "0.12")
    s = RiskSettings(_env_file=None)
    assert s.signal_min_score == 65.0
    assert s.eo_dd_veto == 0.12


def test_feature_flags_env_override(monkeypatch):
    monkeypatch.setenv("V9_ADVISOR_ONLY", "false")
    monkeypatch.setenv("MARKET_SCANNER_SYNTHETIC", "true")
    s = FeatureFlags(_env_file=None)
    assert s.v9_advisor_only is False
    assert s.market_scanner_synthetic is True


# ── CFG-03/04/05 : JSON overrides ─────────────────────────────────────────────


def test_json_override_applied(tmp_path, monkeypatch):
    override_file = tmp_path / "runtime_config.json"
    override_file.write_text(
        json.dumps({"EXEC_MAX_ORDER_USD": 99.0, "SIGNAL_MIN_SCORE": 65.0}),
        encoding="utf-8",
    )
    _clean_env(monkeypatch, "EXEC_MAX_ORDER_USD", "SIGNAL_MIN_SCORE")
    s = Settings(_runtime_override_path=override_file)
    assert s.execution.exec_max_order_usd == 99.0
    assert s.risk.signal_min_score == 65.0


def test_json_missing_no_crash(tmp_path, monkeypatch):
    _clean_env(monkeypatch, "EXEC_MAX_ORDER_USD", "SIGNAL_MIN_SCORE")
    s = Settings(_runtime_override_path=tmp_path / "nonexistent.json")
    assert s.execution.exec_max_order_usd == 50.0
    assert s.risk.signal_min_score == 70.0


def test_json_corrupt_no_crash(tmp_path, monkeypatch):
    override_file = tmp_path / "bad.json"
    override_file.write_text("{ not valid json", encoding="utf-8")
    _clean_env(monkeypatch, "EXEC_MAX_ORDER_USD")
    s = Settings(_runtime_override_path=override_file)
    assert s.execution.exec_max_order_usd == 50.0


def test_settings_none_override_path(monkeypatch):
    _clean_env(monkeypatch, "EXEC_MAX_ORDER_USD")
    s = Settings(_runtime_override_path=None)
    assert s.execution.exec_max_order_usd == 50.0


def test_json_partial_override_no_side_effect(tmp_path, monkeypatch):
    override_file = tmp_path / "partial.json"
    override_file.write_text(json.dumps({"EO_DD_VETO": 0.15}), encoding="utf-8")
    _clean_env(monkeypatch, "EO_DD_VETO", "EO_DD_RECOVERY", "SIGNAL_MIN_SCORE")
    s = Settings(_runtime_override_path=override_file)
    assert s.risk.eo_dd_veto == 0.15
    assert s.risk.eo_dd_recovery == 0.04  # untouched
    assert s.risk.signal_min_score == 70.0  # untouched


# ── CFG-06 : validation ────────────────────────────────────────────────────────


def test_exec_max_order_usd_zero_raises(monkeypatch):
    monkeypatch.setenv("EXEC_MAX_ORDER_USD", "0")
    with pytest.raises(ValidationError):
        ExecutionSettings(_env_file=None)


def test_exec_max_order_usd_negative_raises(monkeypatch):
    monkeypatch.setenv("EXEC_MAX_ORDER_USD", "-10")
    with pytest.raises(ValidationError):
        ExecutionSettings(_env_file=None)


# ── CFG-07/08 : TelegramSettings.enabled ──────────────────────────────────────


def test_telegram_disabled_by_default(monkeypatch):
    _clean_env(monkeypatch, "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
    s = TelegramSettings(_env_file=None)
    assert s.enabled is False


def test_telegram_enabled_when_both_set(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1234:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654")
    s = TelegramSettings(_env_file=None)
    assert s.enabled is True


def test_telegram_disabled_token_only(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1234:abc")
    _clean_env(monkeypatch, "TELEGRAM_CHAT_ID")
    s = TelegramSettings(_env_file=None)
    assert s.enabled is False


# ── CFG-09 : singleton ─────────────────────────────────────────────────────────


def test_get_settings_singleton():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


# ── CFG-10/11/12 couvertes par les tests JSON ci-dessus ───────────────────────


def test_settings_has_all_subsettings(monkeypatch):
    s = Settings(_runtime_override_path=None)
    assert hasattr(s, "exchange")
    assert hasattr(s, "execution")
    assert hasattr(s, "risk")
    assert hasattr(s, "telegram")
    assert hasattr(s, "portfolio")
    assert hasattr(s, "monitoring")
    assert hasattr(s, "flags")


def test_monitoring_default_log_level(monkeypatch):
    _clean_env(monkeypatch, "V9_LOG_LEVEL")
    s = MonitoringSettings(_env_file=None)
    assert s.v9_log_level == "INFO"
