from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tracker_system.config.settings import (
    MIN_PROFIT_FACTOR,
    NO_TRADE_REGIMES,
    REFERENCE_CAPITAL,
    TRACKER_ROOT,
)
from tracker_system.sessions.schemas.session_schema import ALLOWED_MODES, SYSTEM_VERSION

SESSIONS_ROOT = TRACKER_ROOT / "sessions"


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=TRACKER_ROOT,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session_dir(session_id: str) -> Path:
    return SESSIONS_ROOT / session_id


class SessionManager:
    """Lifecycle d'une session : création, enregistrement trades, clôture."""

    def __init__(
        self, market: str = "BTCUSDT", timeframe: str = "1m", mode: str = "paper"
    ) -> None:
        if mode not in ALLOWED_MODES:
            raise ValueError(f"mode invalide : {mode}. Attendu : {ALLOWED_MODES}")

        ts = datetime.now(timezone.utc).strftime("%Y_%m_%d_%H_%M")
        self.session_id = f"session_{ts}"
        self.market = market
        self.timeframe = timeframe
        self.mode = mode
        self.start_time = _now_iso()
        self.end_time: str | None = None
        self.total_cycles: int = 0
        self._trades: list[dict] = []

        self.session_dir = _session_dir(self.session_id)
        self.session_dir.mkdir(parents=True, exist_ok=True)

        self._save_config_snapshot()
        self._save_metadata()

    def _save_config_snapshot(self) -> None:
        snapshot = {
            "REFERENCE_CAPITAL": REFERENCE_CAPITAL,
            "MIN_PROFIT_FACTOR": MIN_PROFIT_FACTOR,
            "NO_TRADE_REGIMES": list(NO_TRADE_REGIMES),
            "SYSTEM_VERSION": SYSTEM_VERSION,
        }
        _write_json(self.session_dir / "config_snapshot.json", snapshot)

    def _save_metadata(self) -> None:
        meta: dict[str, Any] = {
            "session_id": self.session_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_minutes": None,
            "git_commit": _git_commit(),
            "mode": self.mode,
            "market": self.market,
            "timeframe": self.timeframe,
            "total_cycles": self.total_cycles,
            "system_version": SYSTEM_VERSION,
        }
        _write_json(self.session_dir / "session_metadata.json", meta)

    def log_trade(self, trade: dict) -> None:
        """Ajoute un trade au JSONL de session."""
        self._trades.append(trade)
        trades_file = self.session_dir / "trades.jsonl"
        with trades_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(trade, default=str) + "\n")

    def tick(self) -> None:
        self.total_cycles += 1

    def close(self) -> Path:
        """Clôture la session. Retourne le répertoire de session."""
        self.end_time = _now_iso()
        start_dt = datetime.fromisoformat(self.start_time)
        end_dt = datetime.fromisoformat(self.end_time)
        duration_min = (end_dt - start_dt).total_seconds() / 60.0

        meta: dict[str, Any] = {
            "session_id": self.session_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_minutes": round(duration_min, 2),
            "git_commit": _git_commit(),
            "mode": self.mode,
            "market": self.market,
            "timeframe": self.timeframe,
            "total_cycles": self.total_cycles,
            "system_version": SYSTEM_VERSION,
        }
        _write_json(self.session_dir / "session_metadata.json", meta)
        return self.session_dir

    def get_trades(self) -> list[dict]:
        return list(self._trades)

    @property
    def path(self) -> Path:
        return self.session_dir


def load_session_trades(session_dir: Path) -> list[dict]:
    trades_file = session_dir / "trades.jsonl"
    if not trades_file.exists():
        return []
    trades = []
    for line in trades_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                trades.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return trades


def list_sessions() -> list[str]:
    """Retourne les session IDs triés du plus récent au plus ancien."""
    if not SESSIONS_ROOT.exists():
        return []
    return sorted(
        [
            d.name
            for d in SESSIONS_ROOT.iterdir()
            if d.is_dir() and d.name.startswith("session_")
        ],
        reverse=True,
    )


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
