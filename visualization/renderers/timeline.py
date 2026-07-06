"""TimelineRenderer — SVL canonical chart for RegimeSnapshot.

SVL v1.0 § 6.7 — Regime Timeline — Colored Timeline
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from visualization.api.models import RegimeSnapshot, PipelineSnapshot
from visualization.renderers.base import (
    BaseRenderer, SVL_BG, SVL_TEXT, SVL_TEXT_DIM, SVL_GRID,
    SVL_COLORS, SVL_DPI, SVL_W, SVL_H,
)

_REGIME_COLORS = {
    "bull_trend":              SVL_COLORS["STRONG"],
    "bear_trend":              SVL_COLORS["CONTRADICTED"],
    "sideways":                SVL_COLORS["ARCHIVED"],
    "high_volatility_regime":  SVL_COLORS["DRIFT"],
    "flash_crash":             SVL_COLORS["CONTRADICTED"],
    "VOLATILE":                SVL_COLORS["DRIFT"],
}


def _regime_color(name: str) -> str:
    return _REGIME_COLORS.get(name, SVL_COLORS["EMERGING"])


class TimelineRenderer(BaseRenderer):

    def render(self, obj: object) -> bytes:
        # Accept either RegimeSnapshot or PipelineSnapshot
        if isinstance(obj, PipelineSnapshot):
            distribution = obj.regime_distribution
            ts = obj.ts
        else:
            assert isinstance(obj, RegimeSnapshot)
            distribution = obj.distribution
            ts = obj.ts

        fig = plt.figure(figsize=(SVL_W / SVL_DPI, SVL_H / SVL_DPI), dpi=SVL_DPI, facecolor=SVL_BG)
        ax = fig.add_subplot(111, facecolor=SVL_BG)

        self._draw_bars(ax, distribution)

        fig.suptitle(
            f"SDOS REGIME — {ts.strftime('%Y-%m-%d %H:%M')} UTC",
            color=SVL_TEXT, fontsize=12, fontweight="bold",
            fontfamily="monospace", y=0.98,
        )
        fig.tight_layout(rect=[0, 0, 1, 0.96])
        return self._to_png(fig)

    def _draw_bars(self, ax, distribution: dict[str, int]):
        ax.axis("off")

        if not distribution:
            ax.text(0.5, 0.5, "No regime data", ha="center", va="center",
                    color=SVL_TEXT_DIM, fontfamily="monospace", transform=ax.transAxes)
            return

        total = sum(distribution.values()) or 1
        items = sorted(distribution.items(), key=lambda x: x[1], reverse=True)

        y = 0.80
        for regime, count in items:
            pct = count / total * 100
            color = _regime_color(regime)
            bar_w = pct / 100 * 0.65

            # Bar
            rect = mpatches.FancyBboxPatch(
                (0.15, y - 0.035), bar_w, 0.06,
                boxstyle="round,pad=0.005",
                linewidth=0, facecolor=color + "99",
                transform=ax.transAxes,
            )
            ax.add_patch(rect)

            # Label
            ax.text(0.13, y, regime, ha="right", va="center",
                    color=SVL_TEXT, fontsize=9, fontfamily="monospace",
                    transform=ax.transAxes)
            # Percentage
            ax.text(0.15 + bar_w + 0.01, y, f"{pct:.1f}%  ({count})",
                    ha="left", va="center",
                    color=color, fontsize=9, fontweight="bold",
                    fontfamily="monospace", transform=ax.transAxes)

            y -= 0.12

        # Legend
        handles = [
            mpatches.Patch(color=_regime_color(r), label=r)
            for r, _ in items[:5]
        ]
        ax.legend(handles=handles, loc="lower right", framealpha=0.1,
                  fontsize=7, labelcolor=SVL_TEXT, facecolor=SVL_BG)
