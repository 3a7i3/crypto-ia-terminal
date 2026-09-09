"""observability/mode_provenance.py — canonical mode-provenance resolver.

Extracted, pure equivalent of `core/advisor_loop.py::_balance_provenance_from_mode()`
(§7 MODE_PROVENANCE_CONTRACT, BLOCKER E) — identical semantics, reused by
both the advisor loop (which keeps its own thin wrapper for backward
compatibility with existing call sites) and the O-02W-C operator snapshot
builder, so the vocabulary/override/fail-closed behavior is defined in
exactly one place.

Vocabulary: PAPER / REAL_API / TESTNET_API / UNKNOWN.
`PAPER_TRADING_ENABLED` (truthy) always overrides `exec_mode` to PAPER.
An unrecognized `exec_mode` fails closed to UNKNOWN — never REAL_API.
"""

from __future__ import annotations

import os
from typing import Optional

_PAPER_TRADING_TRUTHY = {"1", "true", "yes", "on"}

_MODE_MAP = {"paper": "PAPER", "live": "REAL_API", "testnet": "TESTNET_API"}


def resolve_mode_provenance(
    exec_mode: Optional[str],
    paper_trading_enabled: Optional[bool] = None,
) -> str:
    """Resolve the presentation-provenance label for a raw internal mode.

    `paper_trading_enabled`: if None, re-reads `PAPER_TRADING_ENABLED`
    directly from the environment (default "true"), matching
    `_balance_provenance_from_mode()`'s own behavior exactly — never
    trusting a possibly-diverged locally-cached variable. Pass an explicit
    bool (as tests do) to avoid environment coupling.
    """

    if paper_trading_enabled is None:
        paper_trading_enabled = (
            os.getenv("PAPER_TRADING_ENABLED", "true").lower() in _PAPER_TRADING_TRUTHY
        )
    if paper_trading_enabled:
        return "PAPER"
    return _MODE_MAP.get(exec_mode, "UNKNOWN")


__all__ = ["resolve_mode_provenance"]
