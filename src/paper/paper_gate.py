from .paper_metrics import PaperMetrics

MIN_TRADES = 50
MIN_PF = 1.2
MIN_EXPECTANCY = 0.0
MAX_DD_PCT = 15.0


def gate_passed(m: PaperMetrics) -> bool:
    return (
        m.trade_count >= MIN_TRADES
        and m.profit_factor > MIN_PF
        and m.expectancy > MIN_EXPECTANCY
        and m.max_drawdown_pct < MAX_DD_PCT
    )


def gate_status(m: PaperMetrics) -> str:
    checks = [
        (
            f"trades ≥ {MIN_TRADES}",
            m.trade_count >= MIN_TRADES,
            f"{m.trade_count}/{MIN_TRADES}",
        ),
        (f"PF > {MIN_PF}", m.profit_factor > MIN_PF, f"{m.profit_factor:.3f}"),
        ("expectancy > 0", m.expectancy > MIN_EXPECTANCY, f"{m.expectancy:+.2f}"),
        (
            f"maxDD < {MAX_DD_PCT}%",
            m.max_drawdown_pct < MAX_DD_PCT,
            f"{m.max_drawdown_pct:.1f}%",
        ),
    ]
    return "\n".join(
        f"{'✓' if ok else '✗'} {label}: {val}" for label, ok, val in checks
    )
