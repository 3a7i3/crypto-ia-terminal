from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from tracker_system.config.settings import TRADES_LOG_FILE
from tracker_system.storage.loader import load_jsonl

logger = logging.getLogger(__name__)

REQUIRED_ENTRY_FIELDS: tuple[str, ...] = (
    "type",
    "symbol",
    "side",
    "entry_price",
    "size",
)

REQUIRED_EXIT_FIELDS: tuple[str, ...] = (
    "type",
    "symbol",
    "side",
    "entry_price",
    "exit_price",
    "pnl_usd",
    "pnl_pct",
    "duration_min",
)


class SchemaValidationError(ValueError):
    pass


def validate_event(event: dict[str, Any]) -> list[str]:
    """Retourne la liste des champs manquants pour l'event donné."""
    event_type = event.get("type", "")
    if event_type == "entry":
        required = REQUIRED_ENTRY_FIELDS
    elif event_type == "exit":
        required = REQUIRED_EXIT_FIELDS
    else:
        return []
    return [f for f in required if f not in event or event[f] is None]


def validate_log_file(
    log_file: Path = TRADES_LOG_FILE,
    strict: bool = False,
) -> dict[str, Any]:
    """
    Valide tous les events du fichier JSONL.

    Args:
        log_file: Chemin vers le fichier trades.jsonl
        strict: Si True, lève SchemaValidationError au premier event invalide.
                Si False, logge les erreurs et continue.

    Returns:
        {
            "total": int,
            "valid": int,
            "invalid": int,
            "errors": [{"line": int, "id": str, "missing": [str]}]
        }
    """
    events = load_jsonl(log_file)
    errors: list[dict[str, Any]] = []

    for idx, event in enumerate(events, start=1):
        missing = validate_event(event)
        if not missing:
            continue

        error = {
            "line": idx,
            "id": event.get("id", "unknown"),
            "type": event.get("type", "unknown"),
            "symbol": event.get("symbol", "unknown"),
            "missing": missing,
        }
        errors.append(error)

        msg = (
            f"[boot_validator] Event invalide ligne {idx} "
            f"(id={error['id']}, type={error['type']}, symbol={error['symbol']}) "
            f"— champs manquants: {missing}"
        )

        if strict:
            raise SchemaValidationError(msg)

        logger.warning(msg)

    result = {
        "total": len(events),
        "valid": len(events) - len(errors),
        "invalid": len(errors),
        "errors": errors,
    }

    if errors:
        logger.warning(
            "[boot_validator] %d/%d events invalides dans %s",
            len(errors),
            len(events),
            log_file,
        )
    else:
        logger.info(
            "[boot_validator] Schéma OK — %d events validés dans %s",
            len(events),
            log_file,
        )

    return result


def boot_validate(log_file: Path = TRADES_LOG_FILE) -> dict[str, Any]:
    """Point d'entrée appelé au démarrage du système."""
    result = validate_log_file(log_file, strict=False)
    if result["invalid"] > 0:
        print(
            f"[BOOT] WARN {result['invalid']} events invalides detectes "
            f"({result['valid']}/{result['total']} OK) -- voir logs pour detail."
        )
    else:
        print(f"[BOOT] OK schema JSONL -- {result['total']} events valides.")
    return result
