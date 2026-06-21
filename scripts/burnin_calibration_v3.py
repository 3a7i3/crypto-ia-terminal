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

# ── Paths ─────────────────────────────────────────────────────────────────────

_DEFAULT_GATE_CSV = Path("databases/gate_rejections.csv")
_DEFAULT_TRADES_JSONL = Path(
    os.getenv("PAPER_TRADE_LOG", "databases/paper_trades.jsonl")
)
_DEFAULT_KS_STATE = Path("cache/startup/killswitch_state.json")
_DEFAULT_OUTPUT = Path("cache/burn_in_reports/burnin_v3.json")

# Real trades have BTC price >> 1000. Test fixtures use price 101-102.
_REAL_TRADE_PRICE_FLOOR = 500.0


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


# ── Loaders ───────────────────────────────────────────────────────────────────


def _load_gate_funnel(path: Path) -> GateFunnel:
    if not path.exists():
        return GateFunnel()

    rows = []
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            rows = list(csv.DictReader(fh))
    except Exception:
        return GateFunnel()

    if not rows:
        return GateFunnel()

    allowed = [r for r in rows if r.get("allowed") == "True"]
    rejected = [r for r in rows if r.get("allowed") == "False"]

    timestamps = []
    for r in rows:
        try:
            timestamps.append(float(r["ts"]))
        except (KeyError, ValueError):
            pass

    window_h = (
        (max(timestamps) - min(timestamps)) / 3600 if len(timestamps) >= 2 else 0.0
    )

    scores = []
    for r in rows:
        try:
            scores.append(int(r["score"]))
        except (KeyError, ValueError):
            pass

    score_bins: dict[str, int] = {
        "<50": 0,
        "50-59": 0,
        "60-69": 0,
        "70-79": 0,
        "80+": 0,
    }
    for s in scores:
        if s < 50:
            score_bins["<50"] += 1
        elif s < 60:
            score_bins["50-59"] += 1
        elif s < 70:
            score_bins["60-69"] += 1
        elif s < 80:
            score_bins["70-79"] += 1
        else:
            score_bins["80+"] += 1

    from collections import Counter

    regimes = Counter(r.get("regime", "?") for r in rows)
    top_regimes = dict(regimes.most_common(5))

    rejection_reasons: Counter = Counter()
    for r in rejected:
        raw = r.get("failed", "")
        try:
            items = json.loads(raw)
            if isinstance(items, list):
                for item in items:
                    rejection_reasons[str(item).split(" ")[0]] += 1
        except Exception:
            rejection_reasons[raw[:40]] += 1

    now = time.time()
    last_24h = sum(1 for r in rows if _safe_float(r.get("ts", 0)) > now - 86400)

    return GateFunnel(
        total=len(rows),
        allowed=len(allowed),
        rejected=len(rejected),
        window_h=round(window_h, 1),
        score_avg=round(sum(scores) / len(scores), 1) if scores else 0.0,
        score_min=min(scores) if scores else 0,
        score_max=max(scores) if scores else 0,
        score_bins=score_bins,
        top_regimes=top_regimes,
        top_rejection_reasons=dict(rejection_reasons.most_common(5)),
        last_24h=last_24h,
        signals_per_hour=round(len(rows) / window_h, 1) if window_h > 0 else 0.0,
        allowed_per_hour=round(len(allowed) / window_h, 1) if window_h > 0 else 0.0,
    )


def _load_real_trades(path: Path) -> list[dict]:
    """Load closed trades from paper_trades.jsonl, filtering out test fixtures and restore artifacts.

    Two categories excluded:
      1. Test fixtures: price < 500 AND score == 0 (synthetic data, old unit tests).
      2. Restore artifacts: duration_s == 0.0 AND score == 0 AND regime == "unknown"
         — MexcSimulator._restore_positions() bug: open positions were re-closed
         instantly on restart before the fix (session 2026-06-07). These have
         real BTC prices but no pipeline context and zero hold time.
    """
    if not path.exists():
        return []

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []

    closes = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("event") != "CLOSE":
            continue

        price = _safe_float(record.get("price", 0) or record.get("exit_price", 0))
        score = _safe_float(record.get("score", 0))
        regime = record.get("regime", "unknown")
        duration = _safe_float(record.get("duration_s", -1))

        # Test fixtures: synthetic price, no pipeline score
        if price < _REAL_TRADE_PRICE_FLOOR and score == 0:
            continue

        # Restore artifacts: instant close, no pipeline context
        if duration == 0.0 and score == 0 and regime == "unknown":
            continue

        closes.append(record)

    return closes


def _compute_trade_stats(trades: list[dict]) -> TradeStats:
    if not trades:
        return TradeStats()

    pnl_pcts = [_safe_float(t.get("pnl_pct", 0)) for t in trades]
    pnl_usds = [_safe_float(t.get("pnl_usd", 0)) for t in trades]
    durations = [_safe_float(t.get("duration_s", 0)) for t in trades]

    wins = [p for p in pnl_pcts if p > 0]
    losses = [p for p in pnl_pcts if p <= 0]

    total_gain = sum(p for p in pnl_usds if p > 0)
    total_loss = abs(sum(p for p in pnl_usds if p < 0))
    pf = round(total_gain / total_loss, 2) if total_loss > 0 else float("inf")

    # Equity curve for max drawdown — additive USD (not compounded %)
    # Using pnl_usd avoids distortion from impossible pnl_pct values (>100%).
    capital = 1000.0
    equity = [capital]
    for p_usd in pnl_usds:
        equity.append(equity[-1] + p_usd)
    peak = equity[0]
    max_dd = 0.0
    for e in equity:
        if e > peak:
            peak = e
        dd = (peak - e) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    # Sharpe (daily, approximated from pnl_pct)
    sharpe = 0.0
    if len(pnl_pcts) >= 2:
        mean_r = sum(pnl_pcts) / len(pnl_pcts)
        variance = sum((r - mean_r) ** 2 for r in pnl_pcts) / len(pnl_pcts)
        std_r = math.sqrt(variance) if variance > 0 else 0
        sharpe = round(mean_r / std_r * math.sqrt(252), 2) if std_r > 0 else 0.0

    return TradeStats(
        count=len(trades),
        wins=len(wins),
        losses=len(losses),
        win_rate_pct=round(100.0 * len(wins) / len(pnl_pcts), 1),
        profit_factor=pf,
        expectancy_pct=(
            round(sum(pnl_pcts) / len(pnl_pcts) * 100, 4) if pnl_pcts else 0.0
        ),
        max_drawdown_pct=round(max_dd * 100, 2),
        sharpe=sharpe,
        avg_duration_h=(
            round(sum(durations) / len(durations) / 3600, 2) if durations else 0.0
        ),
        avg_pnl_usd=round(sum(pnl_usds) / len(pnl_usds), 4) if pnl_usds else 0.0,
        total_pnl_usd=round(sum(pnl_usds), 2),
    )


def _load_system_state(ks_path: Path) -> SystemState:
    from dotenv import load_dotenv

    load_dotenv()

    ks_halted = False
    ks_safe = False
    if ks_path.exists():
        try:
            d = json.loads(ks_path.read_text(encoding="utf-8"))
            ks_halted = bool(d.get("halted", False))
            ks_safe = bool(d.get("safe_mode", False))
        except Exception:
            pass

    warmup_state = "UNKNOWN"
    ws_path = Path("cache/startup/warmup_state.json")
    if ws_path.exists():
        try:
            w = json.loads(ws_path.read_text(encoding="utf-8"))
            warmup_state = w.get("state", "UNKNOWN")
        except Exception:
            pass

    return SystemState(
        killswitch_halted=ks_halted,
        killswitch_safe_mode=ks_safe,
        v9_advisor_only=os.getenv("V9_ADVISOR_ONLY", "true").lower()
        in {"true", "1", "yes"},
        paper_trading_enabled=os.getenv("PAPER_TRADING_ENABLED", "false").lower()
        in {"true", "1", "yes"},
        exec_bootstrap=os.getenv("ADVISOR_LIVE_EXECUTION_BOOTSTRAP", "false").lower()
        in {"true", "1", "yes"},
        warmup_state=warmup_state,
    )


# ── Pre-flight check ─────────────────────────────────────────────────────────


def _preflight_check(ks_path: Path = _DEFAULT_KS_STATE) -> tuple[bool, list[str]]:
    """
    Verify prerequisites before starting a burn-in run.

    Fails fast so a misconfigured environment is caught before any data is loaded.
    Returns (all_ok, list_of_failed_checks).
    """
    from dotenv import load_dotenv

    load_dotenv()

    failed: list[str] = []

    pt = os.getenv("PAPER_TRADING_ENABLED", "false").lower() in {"true", "1", "yes"}
    bootstrap = os.getenv("ADVISOR_LIVE_EXECUTION_BOOTSTRAP", "false").lower() in {
        "true",
        "1",
        "yes",
    }
    if not pt and not bootstrap:
        failed.append("Paper trading disabled — set PAPER_TRADING_ENABLED=true in .env")

    if ks_path.exists():
        try:
            d = json.loads(ks_path.read_text(encoding="utf-8"))
            if d.get("halted"):
                failed.append("KillSwitch HALTED — reset before running burn-in")
        except Exception:
            pass

    if not Path("databases").exists():
        failed.append("databases/ directory missing")

    return len(failed) == 0, failed


# ── Go/No-Go assessment ───────────────────────────────────────────────────────


def _assess(report: BurnInV3Report) -> tuple[str, list[str], list[str]]:
    blockers = []
    warnings = []
    s = report.system
    g = report.gate
    t = report.trades

    if s.killswitch_halted:
        blockers.append("KillSwitch HALTED -- execution bloquee")

    if not s.paper_trading_enabled and not s.exec_bootstrap:
        blockers.append(
            "PAPER_TRADING_ENABLED non defini et ADVISOR_LIVE_EXECUTION_BOOTSTRAP=false "
            "-- aucun ordre n'atteint le simulateur. "
            "Fix: ajouter PAPER_TRADING_ENABLED=true dans .env"
        )

    if t.count == 0:
        blockers.append(
            f"0 trade reel ferme (objectif: {report.target_trades}). "
            "Burn-in non demarre."
        )
    elif t.count < 30:
        blockers.append(
            f"{t.count} trades reels < 30 minimum statistique (objectif: {report.target_trades})"
        )

    if g.total == 0:
        blockers.append(
            "Aucune donnee gate_rejections.csv -- pipeline Decision->Gate inactif"
        )
    elif g.pass_rate_pct < 10:
        warnings.append(
            f"Gate pass rate tres bas ({g.pass_rate_pct}%) -- score moyen faible"
        )

    if t.count >= 30:
        if t.max_drawdown_pct > 25:
            blockers.append(f"Max drawdown {t.max_drawdown_pct}% > 25% seuil P13")
        if t.win_rate_pct < 30:
            warnings.append(f"Win rate bas ({t.win_rate_pct}%)")
        if t.profit_factor < 1.0 and t.profit_factor > 0:
            warnings.append(f"Profit factor < 1.0 ({t.profit_factor})")

    if s.warmup_state not in {"OK", "READY", "COMPLETE", "UNKNOWN", "FAILED"}:
        warnings.append(f"Warmup state: {s.warmup_state}")
    elif s.warmup_state == "FAILED":
        # warmup_state.json is written by ColdStartManager (runtime/advisor_main.py).
        # The active process (advisor_loop.py) never reads it — FAILED is cosmetic.
        warnings.append(
            "Warmup state FAILED (stale P10-B artifact — advisor_loop.py non affecte)"
        )

    if blockers:
        verdict = "NO_GO"
    elif warnings:
        verdict = "DEGRADED"
    else:
        verdict = "GO" if t.count >= report.target_trades else "IN_PROGRESS"

    return verdict, blockers, warnings


# ── Report builder ────────────────────────────────────────────────────────────


def build_report(
    gate_path: Path = _DEFAULT_GATE_CSV,
    trades_path: Path = _DEFAULT_TRADES_JSONL,
    ks_path: Path = _DEFAULT_KS_STATE,
    target_trades: int = 100,
) -> BurnInV3Report:
    gate = _load_gate_funnel(gate_path)
    real_trades = _load_real_trades(trades_path)
    trade_stats = _compute_trade_stats(real_trades)
    system = _load_system_state(ks_path)

    window_h = gate.window_h

    report = BurnInV3Report(
        generated_at=_iso_now(),
        burn_in_window_h=window_h,
        gate=gate,
        trades=trade_stats,
        system=system,
        target_trades=target_trades,
        coverage_pct=round(100.0 * trade_stats.count / target_trades, 1),
    )

    verdict, blockers, warnings = _assess(report)
    report.go_no_go = verdict
    report.blockers = blockers
    report.warnings = warnings

    return report


# ── Console output ────────────────────────────────────────────────────────────

_W = 58


def print_report(report: BurnInV3Report) -> None:
    g = report.gate
    t = report.trades
    s = report.system

    _hr = "-" * _W
    _eq = "=" * _W

    def _kpi(label: str, value: str, note: str = "") -> str:
        note_str = f"  ({note})" if note else ""
        return f"  {label:<30} {value:>10}{note_str}"

    verdict_tag = {
        "GO": "[GO]",
        "NO_GO": "[NO_GO]",
        "DEGRADED": "[DEGRADED]",
        "IN_PROGRESS": "[IN_PROGRESS]",
    }.get(report.go_no_go, "[?]")

    print()
    print(_eq)
    print(f"  BURNIN_CALIBRATION_V3  --  {report.generated_at}")
    print(_eq)

    print(f"\n  Verdict: {verdict_tag}")

    if report.blockers:
        print("\n  BLOCKERS:")
        for b in report.blockers:
            print(f"    - {b}")

    if report.warnings:
        print("\n  WARNINGS:")
        for w in report.warnings:
            print(f"    ~ {w}")

    print(f"\n  {_hr}")
    print(f"  GATE FUNNEL  ({g.window_h}h de donnees)")
    print(f"  {_hr}")
    print(_kpi("Signaux evalues", str(g.total)))
    print(
        _kpi(
            "Passent la gate",
            f"{g.allowed} ({g.pass_rate_pct}%)",
            f"{g.allowed_per_hour}/h",
        )
    )
    print(_kpi("Rejetes", str(g.rejected)))
    print(_kpi("Score moyen", str(g.score_avg), f"[{g.score_min}-{g.score_max}]"))
    print(_kpi("Dernieres 24h", str(g.last_24h)))
    print(f"  Score bins: {g.score_bins}")
    print(f"  Top regimes: {g.top_regimes}")

    print(f"\n  {_hr}")
    print(
        f"  EXECUTION PAPER TRADES  ({t.count}/{report.target_trades} -- {report.coverage_pct}%)"
    )
    print(f"  {_hr}")
    if t.count == 0:
        print("  Aucun trade reel ferme.")
    else:
        print(_kpi("Trades fermes", str(t.count)))
        print(_kpi("Win Rate", f"{t.win_rate_pct}%"))
        print(_kpi("Profit Factor", str(t.profit_factor)))
        print(_kpi("Expectancy", f"{t.expectancy_pct:.4f}%"))
        print(_kpi("Max Drawdown", f"{t.max_drawdown_pct}%"))
        print(_kpi("Sharpe", str(t.sharpe)))
        print(_kpi("PnL total", f"${t.total_pnl_usd:.2f}"))
        print(_kpi("Duree moyenne", f"{t.avg_duration_h:.2f}h"))

    print(f"\n  {_hr}")
    print(f"  ETAT SYSTEME")
    print(f"  {_hr}")
    print(_kpi("KillSwitch", "HALTED" if s.killswitch_halted else "OK"))
    print(_kpi("V9_ADVISOR_ONLY", str(s.v9_advisor_only)))
    print(_kpi("PAPER_TRADING_ENABLED", str(s.paper_trading_enabled)))
    print(_kpi("EXEC_BOOTSTRAP", str(s.exec_bootstrap)))
    print(_kpi("Warmup state", s.warmup_state))

    print(f"\n  {_eq}\n")


# ── Utilities ─────────────────────────────────────────────────────────────────


def _safe_float(val: object) -> float:
    try:
        return float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _iso_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── CLI entry point ───────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="BURNIN_CALIBRATION_V3 report")
    parser.add_argument(
        "--output", type=Path, default=None, help="Save JSON report here"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="JSON output only, no table"
    )
    parser.add_argument("--gate-csv", type=Path, default=_DEFAULT_GATE_CSV)
    parser.add_argument("--trades-jsonl", type=Path, default=_DEFAULT_TRADES_JSONL)
    parser.add_argument("--ks-state", type=Path, default=_DEFAULT_KS_STATE)
    parser.add_argument("--target-trades", type=int, default=100)
    args = parser.parse_args()

    ok, preflight_failures = _preflight_check(ks_path=args.ks_state)
    if not ok:
        print()
        print("BURN-IN ABORTED")
        print()
        print("  Reason:")
        for item in preflight_failures:
            print(f"    - {item}")
        print()
        return 1

    report = build_report(
        gate_path=args.gate_csv,
        trades_path=args.trades_jsonl,
        ks_path=args.ks_state,
        target_trades=args.target_trades,
    )

    if not args.quiet:
        print_report(report)

    output_path = args.output or _DEFAULT_OUTPUT
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    if not args.quiet:
        print(f"  Report saved -> {output_path}")

    return 0 if report.go_no_go in {"GO", "IN_PROGRESS"} else 1


if __name__ == "__main__":
    sys.exit(main())
