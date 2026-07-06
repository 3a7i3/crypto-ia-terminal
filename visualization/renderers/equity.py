"""EquityRenderer — SVL canonical chart for PortfolioSnapshot.

SVL v1.0 § 6.8 — Capital Equity — Equity Curve
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from visualization.api.models import PortfolioSnapshot
from visualization.renderers.base import (
    BaseRenderer, SVL_BG, SVL_TEXT, SVL_TEXT_DIM, SVL_GRID,
    SVL_COLORS, pct_to_color, SVL_DPI, SVL_W, SVL_H,
)


class EquityRenderer(BaseRenderer):

    def render(self, obj: object) -> bytes:
        assert isinstance(obj, PortfolioSnapshot)
        p = obj

        fig = plt.figure(figsize=(SVL_W / SVL_DPI, SVL_H / SVL_DPI), dpi=SVL_DPI, facecolor=SVL_BG)

        if p.trade_history:
            ax_eq = fig.add_subplot(211, facecolor=SVL_BG)
            ax_stats = fig.add_subplot(212, facecolor=SVL_BG)
            self._draw_equity_curve(ax_eq, p)
            self._draw_stats_bar(ax_stats, p)
        else:
            ax = fig.add_subplot(111, facecolor=SVL_BG)
            self._draw_no_data(ax, p)

        fig.suptitle(
            f"SDOS PORTFOLIO — {p.ts.strftime('%Y-%m-%d %H:%M')} UTC",
            color=SVL_TEXT, fontsize=12, fontweight="bold",
            fontfamily="monospace", y=0.98,
        )
        fig.tight_layout(rect=[0, 0, 1, 0.96])
        return self._to_png(fig)

    def _draw_equity_curve(self, ax, p: PortfolioSnapshot):
        ax.set_facecolor(SVL_BG)

        # Build cumulative PnL from trade history
        pnls = [t.get("pnl_usd", 0.0) for t in p.trade_history if t.get("pnl_usd") is not None]
        if not pnls:
            ax.text(0.5, 0.5, "No closed trades", ha="center", va="center",
                    color=SVL_TEXT_DIM, fontfamily="monospace", transform=ax.transAxes)
            return

        cum = np.cumsum([0.0] + pnls)
        xs = range(len(cum))

        color = SVL_COLORS["STRONG"] if cum[-1] >= 0 else SVL_COLORS["CONTRADICTED"]
        ax.plot(xs, cum, color=color, linewidth=2)
        ax.fill_between(xs, cum, 0, alpha=0.15, color=color)
        ax.axhline(0, color=SVL_GRID, linewidth=0.8, linestyle="--")

        ax.set_xlabel("Trades", color=SVL_TEXT_DIM, fontsize=8, fontfamily="monospace")
        ax.set_ylabel("Cumulative PnL ($)", color=SVL_TEXT_DIM, fontsize=8, fontfamily="monospace")
        ax.tick_params(colors=SVL_TEXT_DIM, labelsize=7)
        for spine in ax.spines.values():
            spine.set_color(SVL_GRID)
        ax.grid(color=SVL_GRID, linewidth=0.4, alpha=0.5)

        ax.text(
            0.99, 0.05,
            f"Total PnL: ${cum[-1]:+.2f}",
            ha="right", va="bottom", color=color,
            fontsize=9, fontweight="bold", fontfamily="monospace",
            transform=ax.transAxes,
        )

    def _draw_stats_bar(self, ax, p: PortfolioSnapshot):
        ax.axis("off")
        wr_color = pct_to_color(p.win_rate_pct)
        pf_color = pct_to_color(min(p.profit_factor / 3.0 * 100, 100))

        stats = [
            ("N Trades",       f"{p.n_trades}",                    SVL_TEXT),
            ("Win Rate",       f"{p.win_rate_pct:.1f}%",           wr_color),
            ("Profit Factor",  f"{p.profit_factor:.2f}",           pf_color),
            ("Expectancy",     f"{p.expectancy_pct:+.3f}%",        SVL_TEXT),
            ("Max Drawdown",   f"{p.max_drawdown_pct:.2f}%",       SVL_COLORS["DRIFT"]),
            ("Sharpe",         f"{p.sharpe:.2f}",                  SVL_TEXT),
            ("Avg Duration",   f"{p.avg_duration_h:.1f}h",         SVL_TEXT_DIM),
            ("Capital",        f"${p.capital_usd:,.2f}",           SVL_TEXT),
        ]

        cols = 4
        for i, (label, val, color) in enumerate(stats):
            col = i % cols
            row = i // cols
            x = 0.12 + col * 0.24
            y = 0.75 - row * 0.35
            ax.text(x, y, label, ha="center", va="top",
                    color=SVL_TEXT_DIM, fontsize=7.5, fontfamily="monospace",
                    transform=ax.transAxes)
            ax.text(x, y - 0.15, val, ha="center", va="top",
                    color=color, fontsize=11, fontweight="bold",
                    fontfamily="monospace", transform=ax.transAxes)

    def _draw_no_data(self, ax, p: PortfolioSnapshot):
        ax.axis("off")
        ax.text(0.5, 0.6, f"N = {p.n_trades} trades", ha="center", va="center",
                color=SVL_TEXT, fontsize=14, fontfamily="monospace",
                transform=ax.transAxes)
        ax.text(0.5, 0.45, f"WR {p.win_rate_pct:.1f}%  |  PF {p.profit_factor:.2f}  |  PnL ${p.total_pnl_usd:+.2f}",
                ha="center", va="center", color=pct_to_color(p.win_rate_pct),
                fontsize=11, fontfamily="monospace", transform=ax.transAxes)
        ax.text(0.5, 0.30, "Accumulating trade history…",
                ha="center", va="center", color=SVL_TEXT_DIM,
                fontsize=9, fontfamily="monospace", transform=ax.transAxes)
