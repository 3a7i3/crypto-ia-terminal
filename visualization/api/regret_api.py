"""Regret Investigation API — read-only breakdown of RegretEngine records.

Answers "what does MISSED_WIN / GOOD_REFUSAL actually consist of?" (which
blocking layer, which regime, which score band, which time window) without
touching the decision pipeline. Pure aggregation over
databases/regret_analysis.jsonl — no writes, no recalibration (ADR-0007).
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from visualization.api.models import RegretInvestigationSnapshot

_ROOT = Path(__file__).resolve().parents[2]
_REGRET_DB = _ROOT / "databases" / "regret_analysis.jsonl"

_SCORE_BINS: tuple[tuple[float, float, str], ...] = (
    (0, 50, "<50"),
    (50, 60, "50-59"),
    (60, 70, "60-69"),
    (70, 80, "70-79"),
    (80, float("inf"), "80+"),
)


def _score_bin_label(score: float) -> str:
    for lo, hi, label in _SCORE_BINS:
        if lo <= score < hi:
            return label
    return "unknown"


def _load_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except Exception:
            continue
    return records


def load_regret_investigation(
    regret_db_path: Optional[Path] = None,
    regret_type: str = "MISSED_WIN",
) -> RegretInvestigationSnapshot:
    records = _load_records(regret_db_path or _REGRET_DB)
    subset = [r for r in records if r.get("regret_type") == regret_type]

    by_layer: Counter = Counter()
    for r in subset:
        for blocker in (r.get("refused_by") or ["unknown"]):
            by_layer[blocker] += 1

    by_regime = Counter(r.get("regime", "unknown") for r in subset)
    by_score_bin = Counter(_score_bin_label(r.get("score", 0)) for r in subset)

    ts_values = sorted(r["ts_evaluated"] for r in subset if r.get("ts_evaluated"))

    by_week: Counter = Counter()
    for ts in ts_values:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        by_week[dt.strftime("%Y-W%V")] += 1

    first_ts = datetime.fromtimestamp(ts_values[0], tz=timezone.utc) if ts_values else None
    last_ts = datetime.fromtimestamp(ts_values[-1], tz=timezone.utc) if ts_values else None

    return RegretInvestigationSnapshot(
        ts=datetime.now(timezone.utc),
        regret_type=regret_type,
        n_total=len(subset),
        by_layer=dict(by_layer.most_common()),
        by_regime=dict(by_regime.most_common()),
        by_score_bin=dict(by_score_bin),
        by_week=dict(sorted(by_week.items())),
        first_evaluated_at=first_ts,
        last_evaluated_at=last_ts,
    )
