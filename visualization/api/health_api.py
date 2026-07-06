"""Health API — assembles HealthSnapshot from system_state.json + live_snapshot.json + burnin_v3.json."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from visualization.api.models import HealthSnapshot

_ROOT = Path(__file__).resolve().parents[2]
_SYSTEM_STATE = _ROOT / "databases" / "system_state.json"
_LIVE_SNAPSHOT = _ROOT / "databases" / "live_snapshot.json"
_BURNIN = _ROOT / "cache" / "burn_in_reports" / "burnin_v3.json"

# Milestones for knowledge/evidence scoring
_N_KNOWLEDGE_MILESTONE = 50    # First meaningful statistical gate
_N_EVIDENCE_MILESTONE = 100    # Full evidence baseline


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _observer_score(system: dict) -> tuple[float, Optional[datetime], Optional[float]]:
    """Heartbeat recency + exchange sync → 0-100."""
    raw_hb = system.get("last_heartbeat_at")
    dt_hb = _parse_dt(raw_hb)
    age_s: Optional[float] = None

    if dt_hb:
        now = datetime.now(timezone.utc)
        age_s = (now - dt_hb).total_seconds()
        # 0-5 min → 100%, 5-60 min → 80%, 1-24h → 50%, >24h → 10%
        if age_s < 300:
            score = 100.0
        elif age_s < 3600:
            score = 80.0
        elif age_s < 86400:
            score = 50.0
        else:
            score = 10.0
    else:
        score = 0.0

    if system.get("stall_alert_active"):
        score = min(score, 40.0)
    if not system.get("exchange_sync_ok", True):
        score = min(score, 60.0)

    return score, dt_hb, age_s


def _dataset_score(live: dict) -> float:
    """Universe coverage + actionable ratio → 0-100."""
    n_sym = live.get("n_symbols", 0)
    n_act = live.get("n_actionable", 0)

    if n_sym == 0:
        return 0.0

    # Expect 20+ symbols for full score
    coverage = min(n_sym / 20.0, 1.0) * 60.0
    actionable = (n_act / n_sym) * 40.0 if n_sym > 0 else 0.0
    return round(coverage + actionable, 1)


def _knowledge_score(burnin: dict) -> float:
    """Burn-in progress toward N=50 milestone → 0-100."""
    n = burnin.get("trades", {}).get("count", 0)
    return round(min(n / _N_KNOWLEDGE_MILESTONE, 1.0) * 100.0, 1)


def _evidence_score(burnin: dict) -> float:
    """Cumulative evidence quality (N/100 * quality multiplier) → 0-100."""
    trades = burnin.get("trades", {})
    n = trades.get("count", 0)
    wr = trades.get("win_rate_pct", 0.0)
    pf = trades.get("profit_factor", 0.0)

    base = min(n / _N_EVIDENCE_MILESTONE, 1.0) * 60.0

    # Quality multiplier: good WR and PF add up to 40 points
    wr_bonus = min(max(wr - 50.0, 0.0) / 50.0, 1.0) * 20.0  # 0 pts at 50%, 20 at 100%
    pf_bonus = min(max(pf - 1.0, 0.0) / 2.0, 1.0) * 20.0    # 0 pts at PF=1, 20 at PF=3+

    return round(base + wr_bonus + pf_bonus, 1)


def _capital_score(live: dict) -> tuple[float, float]:
    """Current capital vs initial 1000 → 0-100, plus raw USD."""
    capital = live.get("capital", 1000.0)
    initial = 1000.0
    ratio = capital / initial
    # 100% if above initial, scales down with drawdown
    score = min(ratio, 1.0) * 100.0
    return round(score, 1), round(capital, 2)


def _top_root_cause(live: dict) -> tuple[Optional[str], Optional[float]]:
    breakdown: dict = live.get("refusal_breakdown", {})
    if not breakdown:
        return None, None
    total = sum(breakdown.values())
    if total == 0:
        return None, None
    top = max(breakdown, key=breakdown.get)
    pct = round(breakdown[top] / total * 100, 1)
    return top, pct


def load_health_snapshot() -> HealthSnapshot:
    """Load and compute HealthSnapshot from the three canonical sources."""
    system = _load_json(_SYSTEM_STATE)
    live = _load_json(_LIVE_SNAPSHOT)
    burnin = _load_json(_BURNIN)

    observer_pct, dt_hb, age_s = _observer_score(system)
    dataset_pct = _dataset_score(live)
    knowledge_pct = _knowledge_score(burnin)
    evidence_pct = _evidence_score(burnin)
    capital_pct, capital_usd = _capital_score(live)

    # Scientific drift: no formal tracker yet — placeholder from observation
    drift_pct = 18.0

    trades = burnin.get("trades", {})
    top_cause, top_cause_pct = _top_root_cause(live)

    return HealthSnapshot(
        ts=datetime.now(timezone.utc),
        observer_pct=observer_pct,
        dataset_pct=dataset_pct,
        knowledge_pct=knowledge_pct,
        evidence_pct=evidence_pct,
        capital_pct=capital_pct,
        drift_pct=drift_pct,
        system_state=system.get("state", "UNKNOWN"),
        trading_enabled=system.get("trading_enabled", False),
        capital_usd=capital_usd,
        n_trades=trades.get("count", 0),
        win_rate_pct=trades.get("win_rate_pct", 0.0),
        profit_factor=trades.get("profit_factor", 0.0),
        last_heartbeat_at=dt_hb,
        heartbeat_age_seconds=age_s,
        top_root_cause=top_cause,
        top_root_cause_pct=top_cause_pct,
    )
