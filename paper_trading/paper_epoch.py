"""paper_trading/paper_epoch.py — PaperEpoch: scientific financial experiment boundary.

PPL-02A (hardened in PPL-02A-R1). Pure domain model, no I/O, no wiring into
any runtime path.

A `paper_epoch_id` identifies one bounded PAPER financial experiment over the
future PaperPortfolioLedger. It is NOT any of the other identifiers already
present in this codebase:

- `exposure_epoch_id` (observability/runtime_provenance_snapshot.py) is
  process/observability provenance — which runtime process instance produced
  an exposure snapshot. Unrelated concept, never aliased here.
- `cycle_id` is one advisor-loop iteration.
- `trace_id` / `decision_id` are per-cycle / per-decision causal identifiers.

Per PPL-01R's PAPER_EPOCH_ID_CONTRACT: a PaperEpoch is created only by
explicit, deliberate caller intent — `create_paper_epoch()` requires every
identity-relevant field, has no restart/deploy-triggered default, and this
module contains no code path that could be invoked automatically. RESTART !=
RESET, DEPLOY != RESET, PULL != RESET: none of those events may construct a
PaperEpoch.

PAPER EPOCH AUTHORITY CONTRACT (PPL-02A-R1, MASTER finding R1-C/R1-K):
`EPOCH_CREATED` (see ledger_events.py) is the future DURABLE birth fact for a
PaperEpoch. `PaperEpoch` itself is a pure domain VALUE OBJECT representing
that fact — it is never an independent persisted financial authority. A
caller builds a `PaperEpoch` via `create_paper_epoch()`, then builds the
`EPOCH_CREATED` event from it (`ledger_events.make_epoch_created_event`,
carrying every PaperEpoch field in its payload); `paper_portfolio_ledger.
project()` reconstructs the complete `PaperEpoch` (as `PaperPortfolioState.
epoch`) purely by replaying that one event — no external file or side
channel is required to recover the epoch's birth metadata.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import Enum


class PaperEpochStatus(str, Enum):
    """Lifecycle status of a PaperEpoch."""

    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    SUPERSEDED = "SUPERSEDED"


_TERMINAL_STATUSES = (PaperEpochStatus.CLOSED, PaperEpochStatus.SUPERSEDED)


class PaperEpochError(Exception):
    """Base class for PaperEpoch domain errors."""


class InvalidPaperEpochTransition(PaperEpochError):
    """Raised when a status transition is not permitted."""


def _require_finite(name: str, value: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be a real number, got {value!r}")
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return float(value)


@dataclass(frozen=True)
class PaperEpoch:
    """A bounded PAPER financial experiment.

    Immutable except for its terminal `status` transition (`close()` /
    `supersede()`, which return a new instance — the object itself is never
    mutated in place).
    """

    paper_epoch_id: str
    created_at: float
    initial_virtual_capital: float
    status: PaperEpochStatus
    code_sha: str
    config_snapshot_hash: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.paper_epoch_id:
            raise ValueError("paper_epoch_id must be non-empty")
        created_at = _require_finite("created_at", self.created_at)
        capital = _require_finite("initial_virtual_capital", self.initial_virtual_capital)
        if capital <= 0:
            raise ValueError("initial_virtual_capital must be > 0")
        if not self.code_sha:
            raise ValueError("code_sha must be non-empty")
        if not self.config_snapshot_hash:
            raise ValueError("config_snapshot_hash must be non-empty")
        if not isinstance(self.schema_version, int) or self.schema_version < 1:
            raise ValueError("schema_version must be an integer >= 1")
        # Normalize float coercion (e.g. created_at=1000 -> 1000.0) without
        # mutating a frozen instance outside __post_init__'s object.__setattr__.
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "initial_virtual_capital", capital)

    def close(self) -> "PaperEpoch":
        """Terminal transition ACTIVE -> CLOSED. Returns a new instance."""
        return self._transition_to(PaperEpochStatus.CLOSED)

    def supersede(self) -> "PaperEpoch":
        """Terminal transition ACTIVE -> SUPERSEDED. Returns a new instance."""
        return self._transition_to(PaperEpochStatus.SUPERSEDED)

    def _transition_to(self, new_status: PaperEpochStatus) -> "PaperEpoch":
        if self.status in _TERMINAL_STATUSES:
            raise InvalidPaperEpochTransition(
                f"epoch {self.paper_epoch_id} is already terminal "
                f"({self.status.value}); cannot transition to {new_status.value}"
            )
        return replace(self, status=new_status)

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL_STATUSES


def create_paper_epoch(
    *,
    paper_epoch_id: str,
    created_at: float,
    initial_virtual_capital: float,
    code_sha: str,
    config_snapshot_hash: str,
    schema_version: int = 1,
) -> PaperEpoch:
    """Explicit constructor — every identity-relevant field is required.

    There is no default-constructing form and no zero-argument factory: a
    caller must supply `paper_epoch_id`, `created_at`, and
    `initial_virtual_capital` deliberately. This function must never be
    invoked from restart, deploy, or pull code paths (PPL-01R invariant:
    RESTART != RESET, DEPLOY != RESET, PULL != RESET).
    """
    return PaperEpoch(
        paper_epoch_id=paper_epoch_id,
        created_at=created_at,
        initial_virtual_capital=initial_virtual_capital,
        status=PaperEpochStatus.ACTIVE,
        code_sha=code_sha,
        config_snapshot_hash=config_snapshot_hash,
        schema_version=schema_version,
    )
