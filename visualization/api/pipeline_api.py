"""Pipeline API — loads PipelineSnapshot from live_snapshot.json."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from visualization.api.models import PipelineSnapshot

_ROOT = Path(__file__).resolve().parents[2]
_LIVE_SNAPSHOT = _ROOT / "databases" / "live_snapshot.json"


def load_pipeline_snapshot() -> PipelineSnapshot:
    if not _LIVE_SNAPSHOT.exists():
        return PipelineSnapshot(
            ts=datetime.now(timezone.utc),
            n_signals=0, n_traded=0, n_refused=0,
            refusal_breakdown={}, regime_distribution={},
            capital_usd=1000.0, cycle=0,
        )

    raw = json.loads(_LIVE_SNAPSHOT.read_text(encoding="utf-8"))

    return PipelineSnapshot(
        ts=datetime.now(timezone.utc),
        n_signals=raw.get("n_symbols", 0),
        n_traded=raw.get("n_traded", 0),
        n_refused=raw.get("n_refused", 0),
        refusal_breakdown=raw.get("refusal_breakdown", {}),
        regime_distribution=raw.get("regime_distribution", {}),
        capital_usd=raw.get("capital", 1000.0),
        cycle=raw.get("cycle", 0),
    )
