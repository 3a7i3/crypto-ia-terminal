"""BaseRenderer — abstract contract all SVL renderers must implement."""
from __future__ import annotations

import io
from abc import ABC, abstractmethod

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

# SVL v1.0 color palette (docs/constitution/07_visual_language.md § 4)
SVL_COLORS = {
    "EXPERIMENTAL":  "#9E9E9E",
    "EMERGING":      "#4499FF",
    "OPERATIONAL":   "#FFCC00",
    "STRONG":        "#22BB55",
    "PREDICTIVE":    "#9933CC",
    "ARCHIVED":      "#555555",
    "CONTRADICTED":  "#FF3333",
    "DRIFT":         "#FF8800",
    "UNKNOWN":       "#EEEEEE",
}

SVL_BG = "#1A1A2E"       # Dark background — mobile-optimized
SVL_TEXT = "#E8E8E8"     # Primary text
SVL_TEXT_DIM = "#888888" # Dimmed / secondary
SVL_GRID = "#2A2A40"     # Grid lines
SVL_ACCENT = "#4499FF"   # Accent (EMERGING blue)

SVL_DPI = 120
SVL_W, SVL_H = 1200, 800  # px → inches = W/DPI, H/DPI


def pct_to_icon(pct: float) -> str:
    """Text status icon — emoji-free for matplotlib compatibility."""
    if pct >= 80:
        return "[OK]"
    if pct >= 50:
        return "[ !]"
    return "[!!]"


def pct_to_color(pct: float) -> str:
    """Map a 0-100 percentage to the appropriate SVL state color."""
    if pct >= 80:
        return SVL_COLORS["STRONG"]
    if pct >= 60:
        return SVL_COLORS["OPERATIONAL"]
    if pct >= 40:
        return SVL_COLORS["EMERGING"]
    return SVL_COLORS["CONTRADICTED"]


def bar_text(pct: float, width: int = 10) -> str:
    """ASCII progress bar for V3 text messages."""
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


class BaseRenderer(ABC):
    """Abstract renderer. Subclasses implement render() and return PNG bytes."""

    SVL_VERSION = "1.0"

    def __init__(self, viewer_level: int = 3):
        self.viewer_level = viewer_level

    def _new_figure(self, w: int = SVL_W, h: int = SVL_H) -> tuple[Figure, plt.Axes | None]:
        fig = plt.figure(
            figsize=(w / SVL_DPI, h / SVL_DPI),
            dpi=SVL_DPI,
            facecolor=SVL_BG,
        )
        return fig, None

    def _to_png(self, fig: Figure) -> bytes:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=SVL_DPI, bbox_inches="tight", facecolor=SVL_BG)
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    @abstractmethod
    def render(self, obj: object) -> bytes:
        """Render obj to PNG bytes."""
