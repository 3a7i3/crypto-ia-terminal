"""Source-only, one-way admission fence for the explicitly named burn-in.

No environment lookup, runtime default path, clock or import-time I/O.
Installing this candidate is itself an admission change requiring a runtime gate.
The receipt is evidence of a governed boundary, never permission to reopen.
"""

from __future__ import annotations

import re
from datetime import datetime

BURN_IN_EPOCH_ID = "BURN-IN-EPOCH-01-20260926T064144Z"


class PPLAdmissionClosedError(RuntimeError):
    """A new OPEN is denied; this does not degrade existing lifecycle truth."""


def require_open_admission(paper_epoch_id: str) -> None:
    # Absence, corruption, deletion or rollback of a receipt cannot reopen
    # this population. Exact persisted retries are handled before this fence.
    if paper_epoch_id == BURN_IN_EPOCH_ID:
        raise PPLAdmissionClosedError("BURN_IN_OPEN_ADMISSION_CLOSED")


def validate_drain_decision(*, decision_url: str, operator: str, decided_at: str) -> None:
    if not isinstance(decision_url, str) or not re.fullmatch(
        r"https://github\.com/3a7i3/crypto-ia-terminal/(issues|pull)/[1-9][0-9]*"
        r"(?:#issuecomment-[0-9]+)?", decision_url
    ):
        raise ValueError("drain decision must reference this repository on GitHub")
    if not isinstance(operator, str) or not operator.strip():
        raise ValueError("operator identity is required")
    if not isinstance(decided_at, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z",
        decided_at,
    ):
        raise ValueError("decided_at must be an explicit UTC timestamp ending in Z")
    datetime.fromisoformat(decided_at[:-1] + "+00:00")
