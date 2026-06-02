"""
dashboard/alert_dashboard.py — Lecteur du fichier d'audit d'alertes.

Normalise les deux formats présents dans alerts_audit.jsonl :
  - Format plat  : {"type":..., "severity":..., "module":..., "timestamp":...}
  - Format niché : {"alert": {"type":..., ...}, "timestamp":..., ...}

Toutes les entrées retournées par load_audit() ont toujours une clé "alert".
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

AUDIT_FILE: pathlib.Path = pathlib.Path("alerts_audit.jsonl")

_ALERT_FIELDS = {"type", "severity", "module", "message", "context"}


def load_audit() -> list[dict[str, Any]]:
    """
    Lit AUDIT_FILE et retourne une liste de dicts normalisés.

    Chaque entrée a au minimum :
      - "alert"     : dict avec type / severity / module / message
      - "timestamp" : str ISO
    """
    path = pathlib.Path(AUDIT_FILE)
    if not path.exists():
        return []

    entries: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj: dict[str, Any] = json.loads(line)
                if "alert" not in obj:
                    alert: dict[str, Any] = {
                        k: obj[k] for k in _ALERT_FIELDS if k in obj
                    }
                    obj = {"alert": alert, "timestamp": obj.get("timestamp", "")}
                entries.append(obj)
            except (json.JSONDecodeError, KeyError):
                continue

    return entries
