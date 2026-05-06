from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tracker_system.config.settings import AUTO_UPDATE_LOG_FILE
from tracker_system.storage.loader import load_jsonl


CycleRunner = Callable[..., dict[str, Any]]
SleepFn = Callable[[float], None]


def _write_log(log_file: Path, message: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")


def _compute_drawdown_from_trade_log(log_file: Path, max_points: int = 200) -> tuple[float, float, float]:
    exits = [event for event in load_jsonl(log_file) if event.get("type") == "exit"]
    if not exits:
        return 0.0, 0.0, 0.0

    curve: list[float] = []
    running_total = 0.0
    for event in exits[-max_points:]:
        running_total += float(event.get("pnl_usd", 0.0))
        curve.append(running_total)

    if not curve:
        return 0.0, 0.0, 0.0

    peak = curve[0]
    current_drawdown = 0.0
    max_drawdown = 0.0
    max_drawdown_pct = 0.0
    for value in curve:
        peak = max(peak, value)
        drawdown = peak - value
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            max_drawdown_pct = (drawdown / peak) if peak > 0 else 0.0
        current_drawdown = drawdown
    return current_drawdown, max_drawdown, max_drawdown_pct


def run_auto_update(
    interval_seconds: float = 1800.0,
    run_optimizer: bool = True,
    max_iterations: int | None = None,
    cycle_runner: CycleRunner | None = None,
    sleep_fn: SleepFn = time.sleep,
    cycle_kwargs: dict[str, Any] | None = None,
    log_file: Path = AUTO_UPDATE_LOG_FILE,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    iteration = 0
    cycle_kwargs = dict(cycle_kwargs or {})

    if cycle_runner is None:
        from tracker_system.main import run_cycle

        cycle_runner = run_cycle

    _write_log(
        log_file,
        f"auto-update started interval_seconds={interval_seconds} run_optimizer={run_optimizer} max_iterations={max_iterations}",
    )

    while max_iterations is None or iteration < max_iterations:
        result = cycle_runner(run_optimizer=run_optimizer, **cycle_kwargs)
        results.append(result)
        iteration += 1

        metrics = result.get("metrics") or {}
        trades = int(metrics.get("trades", 0))
        pnl_total = float(metrics.get("pnl_total", 0.0))
        trade_log = Path(cycle_kwargs.get("log_file")) if cycle_kwargs.get("log_file") else None
        if trade_log is None:
            from tracker_system.config.settings import TRADES_LOG_FILE

            trade_log = TRADES_LOG_FILE
        current_dd, max_dd, max_dd_pct = _compute_drawdown_from_trade_log(trade_log)

        _write_log(
            log_file,
            "cycle_complete iteration={iteration} run_optimizer={run_optimizer} dashboard={dashboard} optimizer_keys={optimizer_keys} trades={trades} pnl_total={pnl_total:.6f} current_drawdown={current_dd:.6f} max_drawdown={max_dd:.6f} max_drawdown_pct={max_dd_pct:.6f}".format(
                iteration=iteration,
                run_optimizer=run_optimizer,
                dashboard=result.get("dashboard"),
                optimizer_keys=sorted((result.get("optimizer") or {}).keys()),
                trades=trades,
                pnl_total=pnl_total,
                current_dd=current_dd,
                max_dd=max_dd,
                max_dd_pct=max_dd_pct,
            ),
        )
        if max_iterations is not None and iteration >= max_iterations:
            break
        sleep_fn(interval_seconds)

    _write_log(log_file, f"auto-update stopped iterations={iteration}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="tracker_system periodic auto refresh")
    parser.add_argument("--interval-seconds", type=float, default=1800.0, help="Delay between refresh cycles")
    parser.add_argument("--max-iterations", type=int, default=None, help="Stop after N cycles")
    parser.add_argument("--no-optimizer", action="store_true", help="Refresh dashboard/metrics without re-running optimizer")
    parser.add_argument("--log-file", default=str(AUTO_UPDATE_LOG_FILE), help="Dedicated scheduler log file path")
    args = parser.parse_args()

    results = run_auto_update(
        interval_seconds=args.interval_seconds,
        run_optimizer=not args.no_optimizer,
        max_iterations=args.max_iterations,
        log_file=Path(args.log_file),
    )
    print(json.dumps(results[-1] if results else {}, indent=2, default=str))


if __name__ == "__main__":
    main()