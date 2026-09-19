"""PPL scientific-capital and experiment-baseline views.

Under PPL authority, both current scientific capital and the immutable
drawdown/ROI baseline come exclusively from one replay-complete durable epoch.
There is no legacy JSONL or exchange fallback.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from paper_trading.durable_event_store import DurableEventStore
from paper_trading.paper_portfolio_ledger import PaperPortfolioState, project


class ScientificCapitalUnavailableError(RuntimeError):
    """Authoritative PPL cannot provide a certified scientific-capital value."""


@dataclass(frozen=True)
class ScientificEpochBaseline:
    paper_epoch_id: str
    created_at: float
    initial_virtual_capital: float


def _validated_ppl_state(
    store_root: str | Path,
    paper_epoch_id: str,
) -> PaperPortfolioState:
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
    return state


def scientific_epoch_baseline_from_ppl(
    store_root: str | Path,
    paper_epoch_id: str,
) -> ScientificEpochBaseline:
    """Return immutable experiment identity and initial virtual capital."""

    state = _validated_ppl_state(store_root, paper_epoch_id)
    assert state.epoch is not None
    return ScientificEpochBaseline(
        paper_epoch_id=paper_epoch_id,
        created_at=float(state.epoch.created_at),
        initial_virtual_capital=float(state.epoch.initial_virtual_capital),
    )


def scientific_capital_from_ppl(
    store_root: str | Path,
    paper_epoch_id: str,
) -> float:
    """Return current certified PAPER scientific capital from one PPL epoch."""

    state = _validated_ppl_state(store_root, paper_epoch_id)
    assert state.epoch is not None
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
    "ScientificEpochBaseline",
    "scientific_capital_from_ppl",
    "scientific_epoch_baseline_from_ppl",
]
