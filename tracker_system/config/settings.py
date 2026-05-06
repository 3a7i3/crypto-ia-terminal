from __future__ import annotations

import os
from pathlib import Path
from typing import Any

TRACKER_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = TRACKER_ROOT / "logs"
TRADES_LOG_FILE = LOGS_DIR / "trades.jsonl"
OPEN_POSITIONS_FILE = LOGS_DIR / "open_positions.json"
OPTIMIZER_FILE = LOGS_DIR / "optimizer.json"
AUTO_UPDATE_LOG_FILE = LOGS_DIR / "auto_update.log"
DASHBOARD_FILE = TRACKER_ROOT / "dashboard" / "dashboard.md"

TRACKER_STRUCTURE: dict[str, dict[str, Any]] = {
    "core": {
        "role": "trade lifecycle, open positions, pnl",
        "files": [
            "core/trade_logger.py",
            "core/trade_tracker.py",
            "core/position_manager.py",
        ],
    },
    "engine": {
        "role": "modular exit logic",
        "files": [
            "engine/exit_engine.py",
            "engine/rules/tp_sl.py",
            "engine/rules/trailing.py",
            "engine/rules/breakeven.py",
        ],
    },
    "analytics": {
        "role": "metrics, mfe/mae, regime analysis",
        "files": [
            "analytics/metrics.py",
            "analytics/mfe_mae.py",
            "analytics/regime_analysis.py",
        ],
    },
    "backtesting": {
        "role": "simulation and optimizer loop",
        "files": [
            "backtesting/auto_backtester.py",
            "backtesting/simulator.py",
        ],
    },
    "storage": {
        "role": "json/jsonl persistence",
        "files": [
            "storage/loader.py",
            "storage/saver.py",
        ],
    },
    "dashboard": {
        "role": "markdown dashboard generation",
        "files": [
            "dashboard/builder.py",
            "dashboard/dashboard.md",
        ],
    },
    "scheduler": {
        "role": "periodic optimizer and dashboard refresh",
        "files": [
            "scheduler/auto_update.py",
        ],
    },
    "config": {
        "role": "settings and dynamic exit config",
        "files": [
            "config/settings.py",
            "config/exit_config.py",
        ],
    },
    "runtime": {
        "role": "live state files",
        "files": [
            "logs/trades.jsonl",
            "logs/open_positions.json",
            "logs/optimizer.json",
            "logs/auto_update.log",
            "main.py",
        ],
    },
}

PRICE_PATH_LIMIT = 200
DEFAULT_MAX_POSITION_DURATION_MIN = 240.0

# Set OBSIDIAN_VAULT_PATH env var to route dashboard writes into the real vault.
# Unset (or empty string) = local fallback (DASHBOARD_FILE). Fully reversible.
_vault_env = os.environ.get("OBSIDIAN_VAULT_PATH", "").strip()
OBSIDIAN_VAULT_PATH: Path | None = Path(_vault_env) if _vault_env else None


def _touch_if_missing(path: Path, default_content: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(default_content, encoding="utf-8")


def ensure_tracker_layout() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    DASHBOARD_FILE.parent.mkdir(parents=True, exist_ok=True)
    _touch_if_missing(OPEN_POSITIONS_FILE, "[]\n")
    _touch_if_missing(OPTIMIZER_FILE, "{}\n")
    _touch_if_missing(TRADES_LOG_FILE, "")
    _touch_if_missing(AUTO_UPDATE_LOG_FILE, "")
    _touch_if_missing(
        DASHBOARD_FILE,
        "# Dashboard Intelligence\n\n_Tracker bootstrap initialized._\n",
    )


def bootstrap_tracker_layout() -> dict[str, Any]:
    ensure_tracker_layout()
    return get_tracker_status()


def get_tracker_status() -> dict[str, Any]:
    ensure_tracker_layout()
    sections: dict[str, dict[str, Any]] = {}
    for name, payload in TRACKER_STRUCTURE.items():
        section_files: list[dict[str, Any]] = []
        for relative_path in payload["files"]:
            path = TRACKER_ROOT / relative_path
            section_files.append(
                {
                    "path": relative_path,
                    "exists": path.exists(),
                }
            )
        sections[name] = {
            "role": payload["role"],
            "files": section_files,
        }

    runtime = {
        "tracker_root": str(TRACKER_ROOT),
        "logs_dir": str(LOGS_DIR),
        "dashboard_file": str(DASHBOARD_FILE),
        "obsidian_vault_path": str(OBSIDIAN_VAULT_PATH) if OBSIDIAN_VAULT_PATH else None,
    }
    return {
        "runtime": runtime,
        "sections": sections,
    }


ensure_tracker_layout()