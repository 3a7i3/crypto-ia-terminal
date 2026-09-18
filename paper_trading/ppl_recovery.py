"""PPL-02E-R2 — deterministic restart planning for authoritative PAPER.

This module performs no I/O and emits no lifecycle event.  It classifies the
already-replayed PPL open positions so a runtime coordinator can decide which
operational projections may be restored and which positions require an
explicit POSITION_UNRESOLVED event.

Historical/SHADOW schema-v1 OPEN positions are intentionally not restart-
eligible: their TP/SL/timeout terms were never durable evidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from paper_trading.paper_portfolio_ledger import PaperPortfolioState


class ReplayIncompletePositionError(RuntimeError):
    """An open position lacks durable facts required for authoritative restart."""


class RestartDisposition(str, Enum):
    RESTORE_MONITORING = "RESTORE_MONITORING"
    RESTORE_TIMEOUT_DUE = "RESTORE_TIMEOUT_DUE"
    UNRESOLVED_REQUIRED = "UNRESOLVED_REQUIRED"


@dataclass(frozen=True)
class RestartPositionPlan:
    trade_id: str
    disposition: RestartDisposition


@dataclass(frozen=True)
class RestartRecoveryPlan:
    paper_epoch_id: str
    positions: tuple[RestartPositionPlan, ...]


def plan_restart_recovery(
    state: PaperPortfolioState, *, now: float
) -> RestartRecoveryPlan:
    """Classify every open position from durable PPL facts only.

    - before timeout_at: restore ordinary monitoring;
    - at/after timeout_at but still inside the recovery window: restore the
      exact position, then let the certified lifecycle policy resolve timeout;
    - after recovery_eligible_until: a new explicit UNRESOLVED resolution is
      required.  No price or PnL is fabricated here.
    """

    if not isinstance(now, (int, float)) or isinstance(now, bool):
        raise ValueError("now must be a real number")
    now_value = float(now)
    if not math.isfinite(now_value):
        raise ValueError("now must be finite")
    if not state.paper_epoch_id or state.epoch is None:
        raise ReplayIncompletePositionError("cannot plan restart without an epoch")

    plans: list[RestartPositionPlan] = []
    for trade_id in sorted(state.open_positions):
        position = state.open_positions[trade_id]
        if not position.replay_complete or state.epoch.schema_version != 2:
            raise ReplayIncompletePositionError(
                f"trade_id={trade_id!r} is not replay-complete; "
                "historical/SHADOW OPEN terms must not be inferred"
            )

        assert position.timeout_at is not None
        assert position.recovery_eligible_until is not None
        if now_value > position.recovery_eligible_until:
            disposition = RestartDisposition.UNRESOLVED_REQUIRED
        elif now_value >= position.timeout_at:
            disposition = RestartDisposition.RESTORE_TIMEOUT_DUE
        else:
            disposition = RestartDisposition.RESTORE_MONITORING

        plans.append(
            RestartPositionPlan(
                trade_id=trade_id,
                disposition=disposition,
            )
        )

    return RestartRecoveryPlan(
        paper_epoch_id=state.paper_epoch_id,
        positions=tuple(plans),
    )


__all__ = [
    "ReplayIncompletePositionError",
    "RestartDisposition",
    "RestartPositionPlan",
    "RestartRecoveryPlan",
    "plan_restart_recovery",
]
