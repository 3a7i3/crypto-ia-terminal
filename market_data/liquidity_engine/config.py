from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class LiquidityEngineConfig:
    binance_enabled: bool = True
    mexc_enabled: bool = True
    symbols: list[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])

    queue_max_size: int = 5000
    log_level: str = "INFO"

    aggregation_windows: list[int] = field(default_factory=lambda: [1, 5, 10, 30, 60])
    price_bucket_size: float = 5.0
    pocket_time_window_s: int = 30
    min_cluster_notional: float = 25_000.0
    min_cluster_events: int = 3

    large_trade_threshold_usd: float = 10_000.0
    whale_trade_threshold_usd: float = 100_000.0
    threshold_by_exchange_symbol: dict[str, dict[str, dict[str, float]]] = field(
        default_factory=dict
    )
    dynamic_percentile: float | None = None
    dynamic_min_samples: int = 200

    ws_timeout_s: float = 20.0
    base_backoff_s: float = 1.0
    max_backoff_s: float = 30.0

    @classmethod
    def from_env(cls) -> "LiquidityEngineConfig":
        def _bool(name: str, default: bool) -> bool:
            raw = os.getenv(name)
            if raw is None:
                return default
            return raw.lower() in {"1", "true", "yes", "on"}

        symbols = os.getenv("LIQ_SYMBOLS", "BTCUSDT,ETHUSDT")
        windows = os.getenv("LIQ_AGG_WINDOWS", "1,5,10,30,60")
        return cls(
            binance_enabled=_bool("LIQ_BINANCE_ENABLED", True),
            mexc_enabled=_bool("LIQ_MEXC_ENABLED", True),
            symbols=[s.strip().upper() for s in symbols.split(",") if s.strip()],
            queue_max_size=int(os.getenv("LIQ_QUEUE_MAX_SIZE", "5000")),
            log_level=os.getenv("LIQ_LOG_LEVEL", "INFO"),
            aggregation_windows=[
                int(x.strip()) for x in windows.split(",") if x.strip()
            ],
            price_bucket_size=float(os.getenv("LIQ_PRICE_BUCKET_SIZE", "5.0")),
            pocket_time_window_s=int(os.getenv("LIQ_TIME_WINDOW_S", "30")),
            min_cluster_notional=float(
                os.getenv("LIQ_MIN_CLUSTER_NOTIONAL", "25000")
            ),
            min_cluster_events=int(os.getenv("LIQ_MIN_CLUSTER_EVENTS", "3")),
            large_trade_threshold_usd=float(
                os.getenv("LIQ_LARGE_TRADE_THRESHOLD_USD", "10000")
            ),
            whale_trade_threshold_usd=float(
                os.getenv("LIQ_WHALE_TRADE_THRESHOLD_USD", "100000")
            ),
            dynamic_percentile=(
                float(os.getenv("LIQ_DYNAMIC_PERCENTILE"))
                if os.getenv("LIQ_DYNAMIC_PERCENTILE")
                else None
            ),
            dynamic_min_samples=int(os.getenv("LIQ_DYNAMIC_MIN_SAMPLES", "200")),
            ws_timeout_s=float(os.getenv("LIQ_WS_TIMEOUT_S", "20")),
            base_backoff_s=float(os.getenv("LIQ_BASE_BACKOFF_S", "1")),
            max_backoff_s=float(os.getenv("LIQ_MAX_BACKOFF_S", "30")),
        )
