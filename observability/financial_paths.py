"""Neutral FIN-02 artifact path contract.

This module is intentionally side-effect free.  Producer and read-only API
import the same resolver so the FIN-02 observational artifact cannot silently
split into two filesystem authorities.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

FINANCIAL_RECONCILIATION_SNAPSHOT_PATH_ENV = (
    "FINANCIAL_RECONCILIATION_SNAPSHOT_PATH"
)
CANONICAL_FINANCIAL_RECONCILIATION_PATH = Path(
    "databases/financial_reconciliation_snapshot.json"
)


def resolve_financial_reconciliation_path(
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the single governed FIN-02 producer/reader artifact path."""

    source = os.environ if environ is None else environ
    return Path(
        source.get(
            FINANCIAL_RECONCILIATION_SNAPSHOT_PATH_ENV,
            str(CANONICAL_FINANCIAL_RECONCILIATION_PATH),
        )
    )


# Backward-compatible effective default: preserves the pre-R4 behavior where
# FINANCIAL_RECONCILIATION_SNAPSHOT_PATH is resolved once at process import.
DEFAULT_FINANCIAL_RECONCILIATION_PATH = (
    resolve_financial_reconciliation_path()
)


__all__ = [
    "CANONICAL_FINANCIAL_RECONCILIATION_PATH",
    "DEFAULT_FINANCIAL_RECONCILIATION_PATH",
    "FINANCIAL_RECONCILIATION_SNAPSHOT_PATH_ENV",
    "resolve_financial_reconciliation_path",
]
