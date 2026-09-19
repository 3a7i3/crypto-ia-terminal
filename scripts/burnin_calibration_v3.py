"""
scripts/burnin_calibration_v3.py — BURNIN_CALIBRATION_V3

Post-P1 pipeline validation. Measures the complete funnel:

    Decision Layer → RiskGate → KillSwitch → Execution → Reporting

Data sources (read-only):
  - databases/gate_rejections.csv         — gate funnel decisions
  - databases/paper_trades.jsonl          — closed paper trades (real only)
  - cache/startup/killswitch_state.json   — killswitch status
  - os.environ (via .env)                 — execution flags

Output: structured JSON report + console KPI table.

Usage:
    python scripts/burnin_calibration_v3.py
    python scripts/burnin_calibration_v3.py --output cache/burn_in_reports/v3.json
    python scripts/burnin_calibration_v3.py --quiet   # JSON only, no table
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.cri_calculator import (  # noqa: E402
    default_trades_path,
    load_clean_trades,
    trades_provenance,
)

# ── Paths ─────────────────────────────────────────────────────────────────────

_DEFAULT_GATE_CSV = Path("databases/gate_rejections.csv")
_DEFAULT_KS_STATE = Path("cache/startup/killswitch_state.json")
_DEFAULT_OUTPUT = Path("cache/burn_in_reports/burnin_v3.json")


def _initial_capital() -> float:
    """Base de capital pour le drawdown — même source que prelive_gate.

    En PPL_AUTHORITY, une baseline indisponible est une erreur scientifique
    bloquante. Aucun fallback numérique ne peut fabriquer un capital initial.
    """
    from infra.wallet_sync import get_wallet_sync

    return float(get_wallet_sync().initial_capital())


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class GateFunnel:
    total: int = 0
    allowed: int = 0
    rejected: int = 0
    window_h: float = 0.0
    score_avg: float = 0.0
    score_min: int = 0
    score_max: int = 0
    score_bins: dict = field(default_factory=dict)
    top_regimes: dict = field(default_factory=dict)
    top_rejection_reasons: dict = field(default_factory=dict)
    last_24h: int = 0
    signals_per_hour: float = 0.0
    allowed_per_hour: float = 0.0

    @property
    def pass_rate_pct(self) -> float:
        return round(100.0 * self.allowed / self.total, 1) if self.total else 0.0


@dataclass
class TradeStats:
    count: int = 0
    wins: int = 0
    losses: int = 0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    expectancy_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe: float = 0.0
    avg_duration_h: float = 0.0
    avg_pnl_usd: float = 0.0
    total_pnl_usd: float = 0.0


@dataclass
class SystemState:
    killswitch_halted: bool = False
    killswitch_safe_mode: bool = False
    v9_advisor_only: bool = True
    paper_trading_enabled: bool = False
    exec_bootstrap: bool = False
    warmup_state: str = "UNKNOWN"


@dataclass
class BurnInV3Report:
    generated_at: str = ""
    burn_in_window_h: float = 0.0
    gate: GateFunnel = field(default_factory=GateFunnel)
    trades: TradeStats = field(default_factory=TradeStats)
    system: SystemState = field(default_factory=SystemState)
    go_no_go: str = "NO_GO"
    blockers: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    target_trades: int = 100
    coverage_pct: float = 0.0