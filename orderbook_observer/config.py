"""
config.py — Configuration du module orderbook_observer via variables d'environnement.

Feature flag principal : ORDERBOOK_OBSERVER_ENABLED (defaut false).
"""

from __future__ import annotations

import os


def is_enabled() -> bool:
    """Retourne True si l'observer est active par l'operateur."""
    return os.getenv("ORDERBOOK_OBSERVER_ENABLED", "false").lower() in ("true", "1", "yes")


def get_config() -> dict:
    """Configuration complete depuis l'environnement."""
    return {
        "enabled": is_enabled(),
        "exchange": os.getenv("ORDERBOOK_EXCHANGE", "mexc"),
        "snapshot_interval_s": int(os.getenv("ORDERBOOK_SNAPSHOT_INTERVAL_S", "60")),
        "retention_days": int(os.getenv("ORDERBOOK_RETENTION_DAYS", "7")),
        "db_path": os.getenv("ORDERBOOK_DB_PATH", "databases/orderbook_flow.sqlite"),
        "depth": int(os.getenv("ORDERBOOK_DEPTH", "20")),
        "wall_threshold_multiplier": float(os.getenv("ORDERBOOK_WALL_THRESHOLD", "5.0")),
        "purge_interval_s": int(os.getenv("ORDERBOOK_PURGE_INTERVAL_S", "3600")),
    }
