"""Burn-in API — assembles BurnInSnapshot from burnin_v3.json + RegretEngine.

Exposes progress against the statistician thresholds (CLAUDE.md — Règle du
statisticien) without computing any new derived score. CRI stays unset until
tools/cri_calculator.py exists (docs/blueprint_v2.md gate S3 — not yet built).

Read-only: RegretEngine is instantiated only to call .stats() on records
already persisted to disk (ADR-0007 — passivité).
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from visualization.api.models import BurnInSnapshot

_ROOT = Path(__file__).resolve().parents[2]
_BURNIN_V3 = _ROOT / "cache" / "burn_in_reports" / "burnin_v3.json"
_REGRET_DB = _ROOT / "databases" / "regret_analysis.jsonl"

# Seuils constitutionnels — CLAUDE.md § Règle du statisticien
TRADES_MIN = 500
WINS_MIN = 150
LOSSES_MIN = 150
MISSED_WIN_MIN = 100
GOOD_REFUSAL_MIN = 100
PER_REGIME_MIN = 50
PER_LAYER_MIN = 30
CRI_MIN = 90


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _finite(value: float, cap: float = 999.0) -> float:
    """Clamp non-finite floats (inf/-inf/nan) to a JSON-serialisable value.

    profit_factor = gross_profit / gross_loss is +inf with zero losses —
    a real, expected state at N<10 trades, not a data error. JSON has no
    Infinity literal; FastAPI's response encoder rejects it outright.
    """
    if value is None or math.isnan(value):
        return 0.0
    if math.isinf(value):
        return cap if value > 0 else -cap
    return value


def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def _regret_stats(regret_db_path: Path) -> dict:
    if not regret_db_path.exists():
        return {"missed_wins": 0, "good_refusals": 0}
    try:
        from quant_hedge_ai.agents.intelligence.regret_engine import RegretEngine

        stats = RegretEngine(db_path=str(regret_db_path)).stats()
        return {
            "missed_wins": stats.get("missed_wins", 0),
            "good_refusals": stats.get("good_refusals", 0),
        }
    except Exception:
        return {"missed_wins": 0, "good_refusals": 0}


def load_burnin_snapshot(
    burnin_path: Optional[Path] = None,
    regret_db_path: Optional[Path] = None,
) -> BurnInSnapshot:
    """Load and compute BurnInSnapshot from the two canonical sources."""
    burnin = _load_json(burnin_path or _BURNIN_V3)
    regret = _regret_stats(regret_db_path or _REGRET_DB)

    trades = burnin.get("trades", {})
    auto_calib = os.getenv("FEATURE_AUTO_CALIBRATION", "false").strip().lower()
    calibration_locked = auto_calib != "true"

    return BurnInSnapshot(
        ts=datetime.now(timezone.utc),
        generated_at=_parse_dt(burnin.get("generated_at")),
        trades_count=trades.get("count", 0),
        trades_min=TRADES_MIN,
        wins=trades.get("wins", 0),
        wins_min=WINS_MIN,
        losses=trades.get("losses", 0),
        losses_min=LOSSES_MIN,
        missed_win_count=regret["missed_wins"],
        missed_win_min=MISSED_WIN_MIN,
        good_refusal_count=regret["good_refusals"],
        good_refusal_min=GOOD_REFUSAL_MIN,
        per_regime_min=PER_REGIME_MIN,
        per_layer_min=PER_LAYER_MIN,
        win_rate_pct=_finite(trades.get("win_rate_pct", 0.0)),
        profit_factor=_finite(trades.get("profit_factor", 0.0)),
        expectancy_pct=_finite(trades.get("expectancy_pct", 0.0)),
        coverage_pct=_finite(burnin.get("coverage_pct", 0.0)),
        cri=None,
        cri_min=CRI_MIN,
        calibration_locked=calibration_locked,
        go_no_go=burnin.get("go_no_go", "UNKNOWN"),
        blockers=burnin.get("blockers", []),
        warnings=burnin.get("warnings", []),
    )
