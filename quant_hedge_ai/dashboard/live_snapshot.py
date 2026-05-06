"""
live_snapshot.py — Écriture atomique du snapshot live par cycle.

Utilisé par advisor_loop.py pour exposer l'état complet du bot
à tout dashboard externe sans toucher aux logs.

Usage :
    from quant_hedge_ai.dashboard.live_snapshot import write_snapshot
    write_snapshot(Path("databases/live_snapshot.json"), data)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_SNAPSHOT_PATH = Path("databases/live_snapshot.json")


def write_snapshot(data: dict[str, Any], path: Path = _SNAPSHOT_PATH) -> None:
    """
    Écrit data en JSON de façon atomique (write tmp → rename).
    Garanti que le lecteur ne voit jamais un fichier à moitié écrit.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, indent=2, default=_json_safe),
            encoding="utf-8",
        )
        tmp.replace(path)
    except Exception as exc:
        log.warning("[LiveSnapshot] Écriture échouée: %s", exc)


def read_snapshot(path: Path = _SNAPSHOT_PATH) -> dict[str, Any] | None:
    """Lit le dernier snapshot. Retourne None si absent ou corrompu."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _json_safe(obj: Any) -> Any:
    """Sérialise les types non-JSON (enum, dataclass, etc.)."""
    if hasattr(obj, "value"):
        return obj.value
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)
