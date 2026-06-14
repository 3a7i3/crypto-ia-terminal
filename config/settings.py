"""
config/settings.py — Single source of truth for runtime configuration (CFG-P2-01).

Priority (high → low):
  1. databases/runtime_config.json  — runtime overrides (hot-patchable without restart)
  2. Environment variables (+ .env)
  3. Field defaults defined here

Usage:
    from config.settings import get_settings
    cfg = get_settings()
    cfg.execution.exec_max_order_usd   # float
    cfg.telegram.enabled               # bool (property)

Sub-settings instantiated independently so they can be injected into components
without carrying the full Settings graph.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_log = logging.getLogger(__name__)

_ENV_FILE = ".env"
_DEFAULT_RUNTIME_OVERRIDE_PATH = Path("databases/runtime_config.json")

# Maps each JSON override key to (sub-settings attribute name, field name).
# These are the keys present in databases/runtime_config.json.
_JSON_OVERRIDE_MAP: dict[str, tuple[str, str]] = {
    "GATE_MIN_SCORE_OVERRIDE": ("risk", "gate_min_score_override"),
    "FORCE_TEST_EXECUTION": ("execution", "force_test_execution"),
    "EXEC_MAX_ORDER_USD": ("execution", "exec_max_order_usd"),
    "SIGNAL_MIN_SCORE": ("risk", "signal_min_score"),
    "EO_DD_VETO": ("risk", "eo_dd_veto"),
    "EO_DD_RECOVERY": ("risk", "eo_dd_recovery"),
    "EXCHANGE_HEARTBEAT_S": ("exchange", "exchange_heartbeat_s"),
}


class ExchangeSettings(BaseSettings):
    """Exchange connectivity — env vars: EXCHANGE_ID, EXCHANGE_TESTNET, EXCHANGE_HEARTBEAT_S."""

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    exchange_id: str = "mexc"
    exchange_testnet: bool = False
    exchange_heartbeat_s: int = 15


class ExecutionSettings(BaseSettings):
    """Order execution limits — env vars: EXEC_MAX_ORDER_USD, EXEC_MAX_DD, etc.

    exec_max_order_usd canonical default = 50 USD (safe for small accounts).
    Resolves conflicting defaults: execution_engine had 10 000, advisor_loop had 50.
    """

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    exec_max_order_usd: float = 50.0
    exec_max_dd: float = 0.05
    exec_max_loss: float = 0.03
    exec_max_consec_losses: int = 3
    exec_dedup_window: float = 30.0
    exec_trade_log: str = "databases/trade_log.sqlite"
    exec_futures_min_order_usd: float = 55.0
    exec_futures_max_order_usd: float = 100.0
    force_test_execution: bool = False

    @field_validator("exec_max_order_usd")
    @classmethod
    def positive_max_order(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("exec_max_order_usd must be > 0")
        return v


class RiskSettings(BaseSettings):
    """Gate and drawdown thresholds — env vars: SIGNAL_MIN_SCORE, EO_DD_*, GATE_*."""

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    signal_min_score: float = 70.0
    gate_min_score_override: float = 0.0
    gate_require_confirmed: bool = True
    gate_log_csv: str = "databases/gate_rejections.csv"
    eo_dd_reduce: float = 0.03
    eo_dd_careful: float = 0.05
    eo_dd_minimal: float = 0.07
    eo_dd_veto: float = 0.10
    eo_dd_recovery: float = 0.04


class TelegramSettings(BaseSettings):
    """Telegram notification settings — env vars: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID."""

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_behavior_chat_id: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


class PortfolioSettings(BaseSettings):
    """Capital allocation parameters — env vars: V9_INITIAL_CAPITAL, V9_KELLY_SAFETY, etc."""

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    v9_initial_capital: float = 1000.0
    v9_kelly_safety: float = 0.25
    v9_max_position_weight: float = 0.10
    v9_max_drawdown: float = 0.05
    v9_min_sharpe: float = 2.0


class MonitoringSettings(BaseSettings):
    """Logging and observability — env var: V9_LOG_LEVEL."""

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    v9_log_level: str = "INFO"


class FeatureFlags(BaseSettings):
    """Runtime feature switches — env vars: V9_ADVISOR_ONLY, MARKET_SCANNER_SYNTHETIC, etc."""

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    v9_advisor_only: bool = True
    market_scanner_synthetic: bool = False
    paper_trading_enabled: bool = False
    advisor_live_execution_bootstrap: bool = False


class Settings:
    """
    Root settings — composes all sub-settings, then applies JSON overrides.

    Instantiate directly in tests; use get_settings() for the process singleton.

    Args:
        _runtime_override_path: Path to runtime_config.json (override in tests via tmp_path).
    """

    def __init__(
        self,
        _runtime_override_path: Path | None = _DEFAULT_RUNTIME_OVERRIDE_PATH,
    ) -> None:
        self.exchange = ExchangeSettings()
        self.execution = ExecutionSettings()
        self.risk = RiskSettings()
        self.telegram = TelegramSettings()
        self.portfolio = PortfolioSettings()
        self.monitoring = MonitoringSettings()
        self.flags = FeatureFlags()
        self._apply_json_overrides(_runtime_override_path)

    def _apply_json_overrides(self, path: Path | None) -> None:
        if path is None or not path.exists():
            return
        try:
            overrides: dict = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            _log.warning("[Settings] runtime_config.json unreadable — skipped: %s", exc)
            return

        by_sub: dict[str, dict[str, object]] = {}
        for json_key, (sub, field) in _JSON_OVERRIDE_MAP.items():
            if json_key in overrides:
                by_sub.setdefault(sub, {})[field] = overrides[json_key]

        for sub_name, updates in by_sub.items():
            current: BaseSettings = getattr(self, sub_name)
            setattr(self, sub_name, current.model_copy(update=updates))
            _log.debug(
                "[Settings] json-override %s → %s", sub_name, list(updates.keys())
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process singleton — constructed once at first call, cached for the process lifetime."""
    return Settings()
