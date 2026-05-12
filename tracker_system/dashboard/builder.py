from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from tracker_system.analytics.metrics import compute_all_metrics
from tracker_system.config.settings import (
    DASHBOARD_FILE,
    OBSIDIAN_VAULT_PATH,
    OPTIMIZER_FILE,
    TRADES_LOG_FILE,
)
from tracker_system.storage.loader import load_json, load_jsonl


def _format_pct(value: float | int) -> str:
    return f"{float(value) * 100:.2f}%"


def _build_optimizer_section(optimizer: dict) -> str:
    if not optimizer:
        return "- no optimizer data"

    lines: list[str] = []
    for regime, params in sorted(optimizer.items()):
        if regime.startswith("_"):
            continue
        lines.append(f"### {regime}")
        lines.append(f"- TP: {params.get('tp', 0)}")
        lines.append(f"- SL: {params.get('sl', 0)}")
        lines.append(f"- Trailing: {params.get('trailing', 0)}")
        lines.append(f"- Score: {params.get('score', 0):.6f}")
        lines.append(f"- Winrate: {_format_pct(params.get('winrate', 0))}")
    return "\n".join(lines) if lines else "- no optimizer data"


def _build_regime_section(regimes: list[dict]) -> str:
    if not regimes:
        return "- no regime data"
    return "\n".join(
        f"- {regime['regime']}: {regime['trades']} trades | winrate={_format_pct(regime['winrate'])} | avg pnl={_format_pct(regime['avg_pnl_pct'])}"
        for regime in regimes
    )


def _compute_drawdown(curve: list[float]) -> tuple[float, float, float]:
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


def _build_equity_curve(log_file: Path, max_points: int = 30) -> str:
    exits = [event for event in load_jsonl(log_file) if event.get("type") == "exit"]
    if not exits:
        return "- no realized equity data"

    curve: list[float] = []
    running_total = 0.0
    for event in exits[-max_points:]:
        running_total += float(event.get("pnl_usd", 0.0))
        curve.append(round(running_total, 4))

    if not curve:
        return "- no realized equity data"

    current_drawdown, max_drawdown, max_drawdown_pct = _compute_drawdown(curve)

    x_axis = ", ".join(str(index) for index in range(1, len(curve) + 1))
    y_axis = ", ".join(f"{value:.4f}" for value in curve)
    y_min = min(0.0, min(curve))
    y_max = max(0.0, max(curve))
    if y_min == y_max:
        y_max = y_min + 1.0

    return f"""- Last equity: {curve[-1]:.2f}
- Peak equity: {max(curve):.2f}
- Current drawdown: {current_drawdown:.2f}
- Max drawdown: {max_drawdown:.2f} ({_format_pct(max_drawdown_pct)})
- Points: {len(curve)}

```mermaid
xychart-beta
    title \"Realized Equity Curve\"
    x-axis [{{x_axis}}]
    y-axis \"PnL USD\" {y_min:.2f} --> {y_max:.2f}
    line [{{y_axis}}]
```
""".replace("{x_axis}", x_axis).replace("{y_axis}", y_axis)


def build_dashboard(
    log_file: Path = TRADES_LOG_FILE,
    optimizer_file: Path = OPTIMIZER_FILE,
    output_file: Path = DASHBOARD_FILE,
    vault_dir: Path | None = None,
) -> Path:
    metrics = compute_all_metrics(log_file)
    optimizer = load_json(optimizer_file, {})

    # Priority: explicit vault_dir > OBSIDIAN_VAULT_PATH env var > legacy output_file
    if vault_dir is not None:
        target = vault_dir / "06_Dashboard" / "dashboard.md"
    elif OBSIDIAN_VAULT_PATH is not None:
        target = OBSIDIAN_VAULT_PATH / "06_Dashboard" / "dashboard.md"
    else:
        target = output_file

    content = f"""# Dashboard Intelligence

_Last update: {datetime.now(timezone.utc).isoformat()}_

## Performance
- Trades: {metrics.get('trades', 0)}
- Total PnL: {metrics.get('pnl_total', 0):.2f}
- Winrate: {_format_pct(metrics.get('winrate', 0))}
- Expectancy: {metrics.get('expectancy', 0):.4f}

## Trade Quality
- Avg MFE: {_format_pct(metrics.get('avg_mfe', 0))}
- Avg MAE: {_format_pct(metrics.get('avg_mae', 0))}
- Efficiency: {_format_pct(metrics.get('efficiency', 0))}

## Equity Curve
{_build_equity_curve(log_file)}

## Regime State
{_build_regime_section(metrics.get('regimes', []))}

## Optimizer State
{_build_optimizer_section(optimizer)}
"""

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


if __name__ == "__main__":
    print(build_dashboard())
