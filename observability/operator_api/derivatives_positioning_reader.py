"""GET-only reader of the derivatives positioning store (Plateformes & levier, lot 2).

Opens the SQLite store READ-ONLY (``mode=ro``, never migrates, never writes) and
projects a bounded snapshot for an explicit roster. Unset configuration =>
NOT_CONFIGURED; a storage or roster failure is a typed error, never an empty market.

    OPERATOR_DERIVATIVES_POSITIONING_DIR     existing store directory
    OPERATOR_DERIVATIVES_POSITIONING_ROSTER  roster JSON (legs, cadences, evidence kind)
    OPERATOR_DERIVATIVES_POSITIONING_POLICY  optional policy JSON
"""

from dataclasses import dataclass
import json
import math
import os
import time

from observability.derivatives_positioning.models_roster import RosterError
from observability.derivatives_positioning.policy import PositioningPolicy
from observability.derivatives_positioning.projection import load_roster, project
from observability.derivatives_positioning.store import PositioningStore, StorageError


@dataclass(frozen=True)
class PositioningReadResult:
    ok: bool
    snapshot: dict | None = None
    error_code: str | None = None


class DerivativesPositioningReader:
    def __init__(self, data_dir=None, roster=None, policy=None, *, now_fn=time.time):
        env = os.getenv
        self.data_dir = env("OPERATOR_DERIVATIVES_POSITIONING_DIR") if data_dir is None else data_dir
        self.roster = env("OPERATOR_DERIVATIVES_POSITIONING_ROSTER") if roster is None else roster
        self.policy = env("OPERATOR_DERIVATIVES_POSITIONING_POLICY") if policy is None else policy
        self.now_fn = now_fn

    def read(self):
        def failure(code):
            return PositioningReadResult(False, error_code="DERIVATIVES_POSITIONING_" + code)

        if not self.data_dir or not self.roster:
            return failure("NOT_CONFIGURED")
        try:
            roster = load_roster(self.roster)
            policy = PositioningPolicy.from_file(self.policy) if self.policy else PositioningPolicy()
        except (OSError, ValueError, RosterError):
            return failure("INVALID_CONFIGURATION")
        try:
            now = float(self.now_fn())
            if not math.isfinite(now):
                return failure("INVALID_READER_CLOCK")
        except (TypeError, ValueError):
            return failure("INVALID_READER_CLOCK")
        try:
            with PositioningStore(self.data_dir, policy=policy, read_only=True) as store:
                snapshot = project(store, roster, as_of_ms=int(now * 1000))
        except StorageError as exc:
            return failure(exc.code)
        json.dumps(snapshot)  # must be plain JSON
        return PositioningReadResult(True, snapshot)
