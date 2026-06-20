"""
config/parameter_audit.py — Audit trail append-only des changements de paramètres live.

Deux responsabilités distinctes :
  databases/runtime_parameter_audit.jsonl  — historique immuable
  databases/runtime_config.json           — état courant (_config_version)

change_id format: CFG-YYYYMMDD-NNNN  (séquentiel par jour UTC)

Usage :
    from config.parameter_audit import record_parameter_change, current_config_version

    change_id = record_parameter_change(
        parameter="SIGNAL_MIN_SCORE",
        old_value=60,
        new_value=66,
        source="telegram",
        command="/set SIGNAL_MIN_SCORE 66",
        operator="123456789",
    )
    # → "CFG-20260619-0001"

    version = current_config_version()
    # → "CFG-20260619-0001"
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_DEFAULT_AUDIT_PATH = Path(
    os.getenv("PARAM_AUDIT_LOG", "databases/runtime_parameter_audit.jsonl")
)
_DEFAULT_RUNTIME_CONFIG = Path("databases/runtime_config.json")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _next_change_id(audit_path: Path) -> str:
    """Generate next sequential change_id for today UTC."""
    today = _today_str()
    prefix = f"CFG-{today}-"
    count = 0
    if audit_path.exists():
        try:
            with audit_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        if json.loads(line).get("change_id", "").startswith(prefix):
                            count += 1
                    except json.JSONDecodeError:
                        pass
        except OSError:
            pass
    return f"{prefix}{count + 1:04d}"


def record_parameter_change(
    parameter: str,
    old_value: object,
    new_value: object,
    source: str = "telegram",
    command: str = "",
    operator: str = "",
    reason: str = "manual override",
    audit_path: Path = _DEFAULT_AUDIT_PATH,
    runtime_config_path: Path = _DEFAULT_RUNTIME_CONFIG,
) -> str:
    """
    Append one audit entry to runtime_parameter_audit.jsonl.
    Update _config_version in runtime_config.json.
    Return the change_id for trade correlation.
    """
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    change_id = _next_change_id(audit_path)

    entry = {
        "change_id": change_id,
        "timestamp": _utcnow_iso(),
        "parameter": parameter,
        "old": old_value,
        "new": new_value,
        "source": source,
        "command": command or f"set {parameter}={new_value}",
        "operator": operator,
        "confirmed": True,
        "reason": reason,
    }

    with audit_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    _bump_config_version(change_id, runtime_config_path)
    return change_id


def _bump_config_version(change_id: str, path: Path) -> None:
    """Write _config_version into runtime_config.json (current-state marker)."""
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    data["_config_version"] = change_id
    try:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass


def current_config_version(
    runtime_config_path: Optional[Path] = None,
) -> str:
    """Return the active config version — embedded in trade records for correlation."""
    path = (
        runtime_config_path
        if runtime_config_path is not None
        else _DEFAULT_RUNTIME_CONFIG
    )
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("_config_version", "CFG-INITIAL")
        except (json.JSONDecodeError, OSError):
            pass
    return "CFG-INITIAL"
