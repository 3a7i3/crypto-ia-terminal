"""SystemSnapshot source adapter for visualization/API layers.

Single read path for UI consumers:
  databases/live_snapshot.json -> system_snapshot
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parents[2]
_LIVE_SNAPSHOT = _ROOT / "databases" / "live_snapshot.json"


def _read_live_snapshot() -> dict[str, Any]:
    if not _LIVE_SNAPSHOT.exists():
        return {}
    try:
        return json.loads(_LIVE_SNAPSHOT.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_system_snapshot_dict() -> dict[str, Any]:
    live = _read_live_snapshot()
    snap = live.get("system_snapshot")
    return snap if isinstance(snap, dict) else {}


def load_system_snapshot_meta() -> dict[str, Any]:
    snap = load_system_snapshot_dict()
    meta = snap.get("meta", {})
    if not isinstance(meta, dict):
        return {}
    return meta


def parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None
