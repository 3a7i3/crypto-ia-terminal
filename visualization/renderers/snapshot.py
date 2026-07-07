"""SnapshotRenderer — 4-panel SDOS Snapshot (SVL § 6.12 + SOI V3).

This is the /snapshot command output: the "home page" of the SDOS.
One image, 2 seconds to understand if the system is alive and healthy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt

from visualization.api.models import HealthSnapshot, PipelineSnapshot, PortfolioSnapshot
from visualization.renderers.base import (
    SVL_BG,
    SVL_COLORS,
    SVL_DPI,
    SVL_GRID,
    SVL_TEXT,
    SVL_TEXT_DIM,
    BaseRenderer,
    bar_text,
    pct_to_color,
    pct_to_icon,
)


@dataclass
class SnapshotBundle:
    """Container passed to SnapshotRenderer — not a standalone scientific type."""

    health: HealthSnapshot
    pipeline: PipelineSnapshot
    portfolio: PortfolioSnapshot


class SnapshotRenderer(BaseRenderer):
    """4-panel snapshot: health radar + pipeline + portfolio + text summary."""

    def render(self, obj: object) -> bytes:
        assert isinstance(obj, SnapshotBundle)
        b = obj

        fig = plt.figure(figsize=(14, 9), dpi=SVL_DPI, facecolor=SVL_BG)
        gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.35, wspace=0.25)

        ax_radar = fig.add_subplot(gs[0, 0], polar=True, facecolor=SVL_BG)
        ax_text = fig.add_subplot(gs[0, 1], facecolor=SVL_BG)
        ax_pipe = fig.add_subplot(gs[1, 0], facecolor=SVL_BG)
        ax_pf = fig.add_subplot(gs[1, 1], facecolor=SVL_BG)

        self._draw_mini_radar(ax_radar, b.health)
        self._draw_health_text(ax_text, b.health)
        self._draw_mini_pipeline(ax_pipe, b.pipeline)
        self._draw_portfolio_kpis(ax_pf, b.portfolio)

        state_icon = "[OK]" if b.health.system_state == "NORMAL" else "[!!]"
        fig.suptitle(
            f"{state_icon} SDOS SNAPSHOT — "
            f"{b.health.ts.strftime('%Y-%m-%d %H:%M')} UTC",
            color=SVL_TEXT,
            fontsize=13,
            fontweight="bold",
            fontfamily="monospace",
        )
        return self._to_png(fig)

    # ── Mini Radar (top-left) ────────────────────────────────────────────────

    def _draw_mini_radar(self, ax, h: HealthSnapshot):
        axes_labels = [
            "Observer",
            "Dataset",
            "Knowledge",
            "Evidence",
            "Capital",
            "~Drift",
        ]
        values = [
            h.observer_pct,
            h.dataset_pct,
            h.knowledge_pct,
            h.evidence_pct,
            h.capital_pct,
            100.0 - h.drift_pct,
        ]

        N = len(axes_labels)
        angles = [n / float(N) * 2 * math.pi for n in range(N)]
        angles_c = angles + [angles[0]]
        values_c = values + [values[0]]

        avg = sum(values) / len(values)
        color = pct_to_color(avg)

        for lv in [25, 50, 75, 100]:
            ax.plot(
                angles_c, [lv] * (N + 1), color=SVL_GRID, linewidth=0.4, linestyle="--"
            )
        for a in angles:
            ax.plot([a, a], [0, 100], color=SVL_GRID, linewidth=0.4)

        ax.plot(angles_c, values_c, color=color, linewidth=2)
        ax.fill(angles_c, values_c, alpha=0.2, color=color)
        for a, v in zip(angles, values):
            ax.scatter([a], [v], color=pct_to_color(v), s=25, zorder=5)

        ax.set_xticks(angles)
        ax.set_xticklabels(
            axes_labels, fontsize=7, fontfamily="monospace", color=SVL_TEXT
        )
        ax.set_ylim(0, 100)
        ax.set_yticks([])
        ax.spines["polar"].set_visible(False)
        ax.set_facecolor(SVL_BG)
        ax.set_title(
            "System Health", color=SVL_TEXT, fontsize=9, fontfamily="monospace", pad=8
        )

    # ── Health text (top-right) ──────────────────────────────────────────────

    def _draw_health_text(self, ax, h: HealthSnapshot):
        ax.axis("off")
        rows = [
            ("Observer", h.observer_pct),
            ("Dataset", h.dataset_pct),
            ("Knowledge", h.knowledge_pct),
            ("Evidence", h.evidence_pct),
            ("Capital", h.capital_pct),
            ("Drift", 100.0 - h.drift_pct),
        ]
        y = 0.92
        ax.text(
            0.02,
            1.0,
            "Health Details",
            color=SVL_TEXT_DIM,
            fontsize=9,
            fontfamily="monospace",
            transform=ax.transAxes,
            va="top",
        )
        y = 0.86

        for label, pct in rows:
            bar = bar_text(pct, 12)
            color = pct_to_color(pct)
            icon = pct_to_icon(pct)
            real_val = h.drift_pct if label == "Drift" else pct
            ax.text(
                0.02,
                y,
                f"{label:<10} {bar}  {real_val:.0f}%  {icon}",
                color=color,
                fontsize=8,
                fontfamily="monospace",
                transform=ax.transAxes,
                va="top",
            )
            y -= 0.11

        y -= 0.04
        state_color = (
            SVL_COLORS["STRONG"]
            if h.system_state == "NORMAL"
            else SVL_COLORS["CONTRADICTED"]
        )
        state_lbl = "[OK]" if h.system_state == "NORMAL" else "[!!]"
        ax.text(
            0.02,
            y,
            f"State: {state_lbl} {h.system_state}",
            color=state_color,
            fontsize=9,
            fontweight="bold",
            fontfamily="monospace",
            transform=ax.transAxes,
            va="top",
        )
        y -= 0.11
        trade_color = pct_to_color(h.win_rate_pct)
        ax.text(
            0.02,
            y,
            f"N={h.n_trades}  WR={h.win_rate_pct:.0f}%  PF={h.profit_factor:.2f}",
            color=trade_color,
            fontsize=8,
            fontfamily="monospace",
            transform=ax.transAxes,
            va="top",
        )

    # ── Mini Pipeline (bottom-left) ──────────────────────────────────────────

    def _draw_mini_pipeline(self, ax, p: PipelineSnapshot):
        ax.axis("off")
        ax.set_title(
            "Decision Pipeline",
            color=SVL_TEXT,
            fontsize=9,
            fontfamily="monospace",
            loc="left",
        )

        refusal = p.refusal_breakdown or {}
        layers = [
            ("Auth", "authority"),
            ("Market", "market"),
            ("Meta", "meta_strategy"),
            ("Portf.", "portfolio"),
            ("Risk", "risk"),
            ("Exec.", "execution"),
        ]

        n_sig = p.n_signals or 1
        x = 0.05
        y_bar, y_lbl, y_pct = 0.60, 0.80, 0.35
        bar_w = (0.90) / len(layers)
        gap = bar_w * 0.15

        for label, key in layers:
            refused = refusal.get(key, 0)
            pass_pct = max(0.0, 100.0 - refused / n_sig * 100) if refused else 100.0
            color = pct_to_color(pass_pct)

            bar_h = 0.35 * pass_pct / 100
            rect = plt.Rectangle(
                (x + gap / 2, y_bar - bar_h),
                bar_w - gap,
                bar_h,
                facecolor=color + "70",
                edgecolor=color,
                linewidth=1,
                transform=ax.transAxes,
            )
            ax.add_patch(rect)

            ax.text(
                x + bar_w / 2,
                y_lbl,
                label,
                ha="center",
                color=SVL_TEXT,
                fontsize=7,
                fontfamily="monospace",
                transform=ax.transAxes,
            )
            ax.text(
                x + bar_w / 2,
                y_pct - 0.06,
                f"{pass_pct:.0f}%",
                ha="center",
                color=color,
                fontsize=7.5,
                fontweight="bold",
                fontfamily="monospace",
                transform=ax.transAxes,
            )
            x += bar_w

        ax.text(
            0.5,
            0.10,
            f"{p.n_signals} signals → {p.n_traded} traded  ({p.pass_rate_pct:.1f}%)",
            ha="center",
            color=SVL_TEXT_DIM,
            fontsize=8,
            fontfamily="monospace",
            transform=ax.transAxes,
        )

    # ── Portfolio KPIs (bottom-right) ────────────────────────────────────────

    def _draw_portfolio_kpis(self, ax, p: PortfolioSnapshot):
        ax.axis("off")
        ax.set_title(
            "Portfolio", color=SVL_TEXT, fontsize=9, fontfamily="monospace", loc="left"
        )

        kpis = [
            ("Trades", f"{p.n_trades}", SVL_TEXT),
            ("Win Rate", f"{p.win_rate_pct:.1f}%", pct_to_color(p.win_rate_pct)),
            (
                "Profit Factor",
                f"{p.profit_factor:.2f}",
                pct_to_color(min(p.profit_factor / 3 * 100, 100)),
            ),
            ("Max DD", f"{p.max_drawdown_pct:.2f}%", SVL_COLORS["DRIFT"]),
            ("Sharpe", f"{p.sharpe:.2f}", SVL_TEXT),
            (
                "Total PnL",
                f"${p.total_pnl_usd:+.2f}",
                pct_to_color(60 if p.total_pnl_usd >= 0 else 30),
            ),
            ("Capital", f"${p.capital_usd:,.0f}", SVL_TEXT),
            ("Expectancy", f"{p.expectancy_pct:+.3f}%", SVL_TEXT),
        ]

        cols = 2
        y = 0.85
        for i, (label, val, color) in enumerate(kpis):
            col = i % cols
            x = 0.05 + col * 0.50
            if col == 0 and i > 0:
                y -= 0.17
            ax.text(
                x,
                y,
                label,
                color=SVL_TEXT_DIM,
                fontsize=7.5,
                fontfamily="monospace",
                transform=ax.transAxes,
            )
            ax.text(
                x,
                y - 0.09,
                val,
                color=color,
                fontsize=10,
                fontweight="bold",
                fontfamily="monospace",
                transform=ax.transAxes,
            )
