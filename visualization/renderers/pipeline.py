"""PipelineRenderer — SVL canonical chart for PipelineSnapshot.

SVL v1.0 § 6.1 — Decision Pipeline — Horizontal Pipeline
"""
from __future__ import annotations

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

from visualization.api.models import PipelineSnapshot
from visualization.renderers.base import (
    BaseRenderer, SVL_BG, SVL_TEXT, SVL_TEXT_DIM, SVL_GRID,
    SVL_COLORS, pct_to_color, SVL_DPI, SVL_W, SVL_H,
)

# Known pipeline layers in order (subset visible in refusal_breakdown keys)
_LAYERS = [
    ("Authority",     "authority"),
    ("Market",        "market"),
    ("Meta Strategy", "meta_strategy"),
    ("Portfolio",     "portfolio"),
    ("Risk Gate",     "risk"),
    ("Execution",     "execution"),
]


class PipelineRenderer(BaseRenderer):

    def render(self, obj: object) -> bytes:
        assert isinstance(obj, PipelineSnapshot)
        p = obj

        fig = plt.figure(figsize=(SVL_W / SVL_DPI, SVL_H / SVL_DPI), dpi=SVL_DPI, facecolor=SVL_BG)
        ax = fig.add_subplot(111, facecolor=SVL_BG)
        ax.axis("off")

        self._draw_pipeline(ax, p)

        fig.suptitle(
            f"SDOS PIPELINE — {p.ts.strftime('%Y-%m-%d %H:%M')} UTC  |  Cycle {p.cycle}",
            color=SVL_TEXT, fontsize=12, fontweight="bold",
            fontfamily="monospace", y=0.98,
        )
        fig.tight_layout(rect=[0, 0, 1, 0.96])
        return self._to_png(fig)

    def _draw_pipeline(self, ax, p: PipelineSnapshot):
        n_layers = len(_LAYERS)
        box_w, box_h = 0.12, 0.20
        gap = 0.03
        total_w = n_layers * box_w + (n_layers - 1) * gap
        x_start = (1.0 - total_w) / 2
        y_center = 0.55

        refusal = p.refusal_breakdown or {}
        total_refused = sum(refusal.values()) or 1

        for i, (label, key) in enumerate(_LAYERS):
            x = x_start + i * (box_w + gap)
            refused_n = refusal.get(key, 0)

            # Pass rate for this layer: 100% if not a blocker
            if p.n_signals > 0 and refused_n > 0:
                block_pct = refused_n / p.n_signals * 100
                pass_pct = max(0.0, 100.0 - block_pct)
            else:
                pass_pct = 100.0

            color = pct_to_color(pass_pct)

            # Box
            rect = mpatches.FancyBboxPatch(
                (x, y_center - box_h / 2), box_w, box_h,
                boxstyle="round,pad=0.01",
                linewidth=1.5, edgecolor=color,
                facecolor=color + "30",  # 30 = ~19% alpha hex
                transform=ax.transAxes,
            )
            ax.add_patch(rect)

            # Fill bar (pass rate)
            fill_h = box_h * pass_pct / 100
            fill_rect = mpatches.FancyBboxPatch(
                (x, y_center - box_h / 2), box_w, fill_h,
                boxstyle="round,pad=0.005",
                linewidth=0, facecolor=color + "60",
                transform=ax.transAxes,
            )
            ax.add_patch(fill_rect)

            # Label
            ax.text(
                x + box_w / 2, y_center + box_h / 2 + 0.03, label,
                ha="center", va="bottom",
                color=SVL_TEXT, fontsize=7.5, fontfamily="monospace",
                transform=ax.transAxes,
            )
            # Percentage
            ax.text(
                x + box_w / 2, y_center,
                f"{pass_pct:.0f}%",
                ha="center", va="center",
                color=color, fontsize=10, fontweight="bold",
                fontfamily="monospace",
                transform=ax.transAxes,
            )
            # Refused count below
            if refused_n > 0:
                ax.text(
                    x + box_w / 2, y_center - box_h / 2 - 0.04,
                    f"−{refused_n}",
                    ha="center", va="top",
                    color=SVL_COLORS["CONTRADICTED"], fontsize=7,
                    fontfamily="monospace",
                    transform=ax.transAxes,
                )

            # Arrow to next box
            if i < n_layers - 1:
                ax.annotate(
                    "", xy=(x + box_w + gap, y_center),
                    xytext=(x + box_w, y_center),
                    xycoords="axes fraction", textcoords="axes fraction",
                    arrowprops=dict(arrowstyle="->", color=SVL_GRID, lw=1.2),
                )

        # Bottom summary
        ax.text(
            0.5, 0.18,
            f"Signals: {p.n_signals}  |  Traded: {p.n_traded}  |  Refused: {p.n_refused}  |  Pass rate: {p.pass_rate_pct:.1f}%",
            ha="center", va="center", color=SVL_TEXT_DIM,
            fontsize=9, fontfamily="monospace",
            transform=ax.transAxes,
        )

        # Regime
        if p.regime_distribution:
            dominant = max(p.regime_distribution, key=p.regime_distribution.get)
            total = sum(p.regime_distribution.values()) or 1
            dom_pct = p.regime_distribution[dominant] / total * 100
            ax.text(
                0.5, 0.10,
                f"Dominant regime: {dominant}  {dom_pct:.0f}%",
                ha="center", va="center", color=SVL_COLORS["EMERGING"],
                fontsize=9, fontfamily="monospace",
                transform=ax.transAxes,
            )
