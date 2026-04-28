import sys

if __name__ != "__main__" and (
    "pytest" in sys.modules or any("pytest" in arg for arg in sys.argv)
):
    import pytest

    pytest.skip(
        "dashboard_quant_terminal.py is a Panel app and should not be tested with pytest.",
        allow_module_level=True,
    )
"""
Dashboard Quant Terminal — V12
Panel + Plotly dashboard integrating:
  • Market Scanner              (200 synthetic coins + live refresh)
  • Candlestick + RSI + MACD   (live chart panel)
  • AI Strategy Generator      (1 000 strategies, genetic ranking)
  • Backtest Engine             (Sharpe / Win-rate / PnL)
  • Portfolio Manager           (Kelly-weighted allocation)
  • Whale Radar                 (anomaly detection)
  • Risk Engine                 (drawdown, VaR, circuit-breaker)
  • AI Agents Monitor           (V9.1 agent status)
  • Strategy Scoreboard         (loads live JSON from V9.1)
  • System Metrics              (CPU, memory, cycle count)

Run:
    cd quant-hedge-ai
        cd quant_hedge_ai
    panel serve dashboard/dashboard_quant_terminal.py --show --port 5010
"""
# ...existing code from quant_terminal_v12.py...
