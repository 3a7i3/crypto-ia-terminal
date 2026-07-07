"""RadarRenderer — SVL canonical chart for HealthSnapshot (6-axis radar).

SVL v1.0 § 6.6 — System Health — Radar Chart
"""

from __future__ import annotations

import math

import matplotlib.pyplot as plt
import numpy as np  # noqa: F401

from visualization.api.models import HealthSnapshot
from visualization.renderers.base import (
    SVL_BG,
    SVL_COLORS,
    SVL_DPI,
    SVL_GRID,
    SVL_H,
    SVL_TEXT,
    SVL_TEXT_DIM,
    SVL_W,
    BaseRenderer,
    pct_to_color,
    pct_to_icon,
)


class RadarRenderer(BaseRenderer):

    AXES = ["Observer", "Dataset", "Knowledge", "Evidence", "Capital", "Drift"]

    def render(self, obj: object) -> bytes:
        assert isinstance(
            obj, HealthSnapshot
        ), f"RadarRenderer expects HealthSnapshot, got {type(obj)}"
        h = obj

        # Drift: invert (lower drift = better health → display as 100-drift)
        values = [
            h.observer_pct,
            h.dataset_pct,
            h.knowledge_pct,
            h.evidence_pct,
            h.capital_pct,
            100.0 - h.drift_pct,  # Inverted: 0% drift → 100% score
        ]

        N = len(self.AXES)
        angles = [n / float(N) * 2 * math.pi for n in range(N)]
        angles_closed = angles + [angles[0]]
        values_closed = values + [values[0]]

        fig = plt.figure(
            figsize=(SVL_W / SVL_DPI, SVL_H / SVL_DPI), dpi=SVL_DPI, facecolor=SVL_BG
        )

        # Left: radar chart
        ax_radar = fig.add_subplot(121, polar=True, facecolor=SVL_BG)
        self._draw_radar(ax_radar, angles, angles_closed, values_closed, values)

        # Right: text panel (V3 dashboard)
        ax_text = fig.add_subplot(122, facecolor=SVL_BG)
        self._draw_panel(ax_text, h, values)

        fig.suptitle(
            f"SDOS HEALTH — {h.ts.strftime('%Y-%m-%d %H:%M')} UTC",
            color=SVL_TEXT,
            fontsize=13,
            fontweight="bold",
            fontfamily="monospace",
            y=0.98,
        )
        fig.tight_layout(rect=[0, 0, 1, 0.96])
        return self._to_png(fig)

    def _draw_radar(self, ax, angles, angles_closed, values_closed, values):
        N = len(self.AXES)
        ax.set_facecolor(SVL_BG)

        # Grid circles
        for level in [25, 50, 75, 100]:
            ax.plot(
                [a for a in angles] + [angles[0]],
                [level] * (N + 1),
                color=SVL_GRID,
                linewidth=0.5,
                linestyle="--",
            )
            ax.text(
                0,
                level,
                f"{level}%",
                color=SVL_TEXT_DIM,
                fontsize=6,
                ha="center",
                va="center",
                fontfamily="monospace",
            )

        # Axis lines
        for angle in angles:
            ax.plot([angle, angle], [0, 100], color=SVL_GRID, linewidth=0.5)

        # Data polygon — color by average health
        avg = sum(values) / len(values)
        fill_color = pct_to_color(avg)

        ax.plot(angles_closed, values_closed, color=fill_color, linewidth=2)
        ax.fill(angles_closed, values_closed, alpha=0.25, color=fill_color)

        # Value dots
        for a, v in zip(angles, values):
            ax.scatter([a], [v], color=pct_to_color(v), s=40, zorder=5)

        # Axis labels
        ax.set_xticks(angles)
        ax.set_xticklabels(
            self.AXES,
            fontsize=9,
            fontfamily="monospace",
            color=SVL_TEXT,
        )
        ax.set_ylim(0, 100)
        ax.set_yticks([])
        ax.spines["polar"].set_visible(False)
        ax.tick_params(colors=SVL_TEXT)

    def _draw_panel(self, ax, h: HealthSnapshot, values: list[float]):
        ax.axis("off")

        lines = []
        state_icon = (
            "[OK]"
            if h.system_state == "NORMAL"
            else ("[!!]" if h.system_state == "HALTED" else "[ !]")
        )
        lines.append(("", SVL_TEXT, 12, "bold"))
        lines.append(
            (
                f"{state_icon} {h.system_state}  |  "
                f"Trading: {'ON' if h.trading_enabled else 'OFF'}",
                SVL_TEXT,
                10,
                "bold",
            )
        )
        lines.append(("", SVL_TEXT, 6, "normal"))

        axis_labels = self.AXES
        axis_values = values
        for label, val, orig in [
            ("Observer", values[0], h.observer_pct),
            ("Dataset", values[1], h.dataset_pct),
            ("Knowledge", values[2], h.knowledge_pct),
            ("Evidence", values[3], h.evidence_pct),
            ("Capital", values[4], h.capital_pct),
            ("Drift", values[5], h.drift_pct),
        ]:
            bar = "█" * round(val / 10) + "░" * (10 - round(val / 10))
            color = pct_to_color(val)
            icon = pct_to_icon(val)
            display = orig if label != "Drift" else h.drift_pct
            lines.append(
                (f"{label:<10} {bar} {display:>5.1f}%  {icon}", color, 9, "normal")
            )

        lines.append(("", SVL_TEXT, 6, "normal"))
        lines.append(("─" * 42, SVL_TEXT_DIM, 8, "normal"))

        lines.append((f"Trades     N={h.n_trades}", SVL_TEXT, 9, "normal"))
        lines.append((f"Win Rate   {h.win_rate_pct:.1f}%", SVL_TEXT, 9, "normal"))
        lines.append((f"Prof. Factor {h.profit_factor:.2f}", SVL_TEXT, 9, "normal"))
        lines.append((f"Capital    ${h.capital_usd:,.2f}", SVL_TEXT, 9, "normal"))

        if h.top_root_cause:
            lines.append(("", SVL_TEXT, 6, "normal"))
            lines.append(("Top Root Cause:", SVL_TEXT_DIM, 8, "normal"))
            lines.append(
                (
                    f"  {h.top_root_cause}  {h.top_root_cause_pct:.0f}%",
                    SVL_COLORS["DRIFT"],
                    9,
                    "bold",
                )
            )

        if h.heartbeat_age_seconds is not None:
            age_m = h.heartbeat_age_seconds / 60
            lines.append(("", SVL_TEXT, 4, "normal"))
            lines.append((f"Heartbeat  {age_m:.0f}m ago", SVL_TEXT_DIM, 7, "normal"))

        y = 0.97
        for text, color, size, weight in lines:
            ax.text(
                0.02,
                y,
                text,
                transform=ax.transAxes,
                color=color,
                fontsize=size,
                fontweight=weight,
                fontfamily="monospace",
                va="top",
            )
            y -= size * 0.012 + 0.005
