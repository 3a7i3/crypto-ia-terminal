"""PPL-02E-R3 — authoritative PPL startup/readiness validation.

This gate replaces legacy JSONL lifecycle correctness checks once PPL is the
selected PAPER authority.  It is read-only and performs no remediation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from paper_trading.durable_event_store import DurableEventStore
from paper_trading.paper_portfolio_ledger import project


@dataclass(frozen=True)
class PPLAuthorityDatasetReport:
    ready_for_mutation: bool
    paper_epoch_id: str
    reason: str
    open_positions: int
    unresolved_positions: int


def validate_ppl_authority_dataset(
    store_root: str | Path,
    paper_epoch_id: str,
) -> PPLAuthorityDatasetReport:
    """Validate durable epoch integrity and replay completeness, read-only."""

    if not str(store_root):
        return PPLAuthorityDatasetReport(
            False, paper_epoch_id, "STORE_ROOT_MISSING", 0, 0
        )
    if not paper_epoch_id:
        return PPLAuthorityDatasetReport(
            False, "", "PAPER_EPOCH_ID_MISSING", 0, 0
        )

    try:
        events = DurableEventStore(store_root).load_epoch(paper_epoch_id)
        state = project(events)
    except Exception as exc:
        return PPLAuthorityDatasetReport(
            False,
            paper_epoch_id,
            f"REPLAY_FAILED:{type(exc).__name__}",
            0,
            0,
        )

    if state.epoch is None or state.paper_epoch_id != paper_epoch_id:
        return PPLAuthorityDatasetReport(
            False, paper_epoch_id, "EPOCH_MISMATCH", 0, 0
        )
    if state.epoch.schema_version != 2:
        return PPLAuthorityDatasetReport(
            False,
            paper_epoch_id,
            "SCHEMA_NOT_REPLAY_COMPLETE",
            len(state.open_positions),
            len(state.unresolved_positions),
        )

    incomplete = [
        trade_id
        for trade_id, position in state.open_positions.items()
        if not position.replay_complete
    ]
    if incomplete:
        return PPLAuthorityDatasetReport(
            False,
            paper_epoch_id,
            "OPEN_POSITION_NOT_REPLAY_COMPLETE",
            len(state.open_positions),
            len(state.unresolved_positions),
        )

    if state.unresolved_positions or state.unresolved_capital != 0.0:
        return PPLAuthorityDatasetReport(
            False,
            paper_epoch_id,
            "UNRESOLVED_CAPITAL",
            len(state.open_positions),
            len(state.unresolved_positions),
        )

    return PPLAuthorityDatasetReport(
        True,
        paper_epoch_id,
        "READY",
        len(state.open_positions),
        0,
    )


__all__ = [
    "PPLAuthorityDatasetReport",
    "validate_ppl_authority_dataset",
]
