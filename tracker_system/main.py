from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tracker_system.analytics.metrics import compute_all_metrics
from tracker_system.backtesting.auto_backtester import run_backtest
from tracker_system.config.settings import (
    AUTO_UPDATE_LOG_FILE,
    DASHBOARD_FILE,
    OPEN_POSITIONS_FILE,
    OPTIMIZER_FILE,
    TRADES_LOG_FILE,
    bootstrap_tracker_layout,
    get_tracker_status,
)
from tracker_system.core.trade_tracker import sync_entries_from_log, update_positions
from tracker_system.dashboard.builder import build_dashboard
from tracker_system.scheduler.auto_update import run_auto_update


def run_cycle(
    current_prices: dict[str, float] | None = None,
    run_optimizer: bool = False,
    log_file: Path = TRADES_LOG_FILE,
    state_file: Path = OPEN_POSITIONS_FILE,
    optimizer_file: Path = OPTIMIZER_FILE,
    dashboard_file: Path = DASHBOARD_FILE,
    vault_dir: Path | None = None,
    optimizer_min_trades: int = 20,
) -> dict[str, Any]:
    imported_entries = sync_entries_from_log(log_file=log_file, state_file=state_file)
    closed_positions = (
        update_positions(current_prices or {}, state_file=state_file, log_file=log_file)
        if current_prices
        else []
    )
    optimizer = (
        run_backtest(min_trades=optimizer_min_trades, log_file=log_file, out_file=optimizer_file)
        if run_optimizer
        else {}
    )
    metrics = compute_all_metrics(log_file)
    dashboard_path = build_dashboard(
        log_file=log_file,
        optimizer_file=optimizer_file,
        output_file=dashboard_file,
        vault_dir=vault_dir,
    )
    return {
        "imported_entries": imported_entries,
        "closed_positions": closed_positions,
        "metrics": metrics,
        "optimizer": optimizer,
        "dashboard": str(dashboard_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="tracker_system main entrypoint")
    parser.add_argument("--prices", default="{}", help="JSON object of current prices")
    parser.add_argument("--optimizer", action="store_true", help="Run backtester before building dashboard")
    parser.add_argument("--scheduler", action="store_true", help="Run periodic tracker refresh loop")
    parser.add_argument("--interval-seconds", type=float, default=1800.0, help="Delay between scheduler iterations")
    parser.add_argument("--max-iterations", type=int, default=None, help="Stop scheduler after N iterations")
    parser.add_argument("--no-optimizer", action="store_true", help="Scheduler mode: skip optimizer refresh")
    parser.add_argument("--scheduler-log-file", default=str(AUTO_UPDATE_LOG_FILE), help="Scheduler log file path")
    parser.add_argument("--bootstrap", action="store_true", help="Ensure tracker runtime layout exists")
    parser.add_argument("--status", action="store_true", help="Print tracker structure and runtime status")
    args = parser.parse_args()

    if args.bootstrap:
        print(json.dumps(bootstrap_tracker_layout(), indent=2, default=str))
        return

    if args.status:
        print(json.dumps(get_tracker_status(), indent=2, default=str))
        return

    if args.scheduler:
        results = run_auto_update(
            interval_seconds=args.interval_seconds,
            run_optimizer=not args.no_optimizer,
            max_iterations=args.max_iterations,
            log_file=Path(args.scheduler_log_file),
        )
        print(json.dumps(results[-1] if results else {}, indent=2, default=str))
        return

    current_prices = json.loads(args.prices)
    result = run_cycle(current_prices=current_prices, run_optimizer=args.optimizer)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()