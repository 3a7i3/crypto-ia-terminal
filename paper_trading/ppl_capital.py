"""PPL-02E-R3 — scientific-capital view over authoritative PPL state.

This module is intentionally narrower than a Financial Institute.  It preserves
the existing PAPER scientific-capital semantic at the authority handoff:

    initial_virtual_capital + realized_pnl

It does not value open positions, reconcile exchanges, or invent unknown
financial outcomes.  Any unresolved capital makes the value unavailable.
"""

from __future__ import annotations

import math
from pathlib import Path

from paper_trading.durable_event_store import DurableEventStore
from paper_trading.paper_portfolio_ledger import project


class ScientificCapitalUnavailableError(RuntimeError):
    """Authoritative PPL cannot provide a certified scientific-capital value."""


def scientific_capital_from_ppl(
    store_root: str | Path,
    paper_epoch_id: str,
) -> float:
    """Return certified PAPER scientific capital from one PPL epoch.

    There is deliberately no legacy JSONL or exchange fallback here.
    """

    if not str(store_root):
        raise ScientificCapitalUnavailableError("PPL authority store root is missing")
    if not paper_epoch_id:
        raise ScientificCapitalUnavailableError("PPL authority epoch id is missing")

    try:
        events = DurableEventStore(store_root).load_epoch(paper_epoch_id)
        state = project(events)
    except Exception as exc:
        raise ScientificCapitalUnavailableError(
            f"authoritative PPL replay unavailable for epoch={paper_epoch_id!r}: {exc}"
        ) from exc

    if state.epoch is None or state.paper_epoch_id != paper_epoch_id:
        raise ScientificCapitalUnavailableError(
            f"authoritative PPL epoch mismatch for {paper_epoch_id!r}"
        )
    if state.epoch.schema_version != 2:
        raise ScientificCapitalUnavailableError(
            "PPL authority scientific capital requires replay-complete schema v2"
        )
    if state.unresolved_capital != 0.0 or state.unresolved_positions:
        raise ScientificCapitalUnavailableError(
            "authoritative PPL contains unresolved capital; UNKNOWN != ZERO"
        )

    value = state.epoch.initial_virtual_capital + state.realized_pnl
    if not math.isfinite(value) or value < 0:
        raise ScientificCapitalUnavailableError(
            f"authoritative PPL scientific capital is invalid: {value!r}"
        )
    return float(value)


__all__ = [
    "ScientificCapitalUnavailableError",
    "scientific_capital_from_ppl",
]
