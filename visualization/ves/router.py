"""VES Router — single entry point for all visualization requests."""

from __future__ import annotations

from pathlib import Path
from typing import Union  # noqa: F401

from visualization.ves.registry import VESError, get_renderer  # noqa: F401

# SOI viewer levels
V0, V1, V2, V3, V4 = 0, 1, 2, 3, 4


class VisualizationEngine:
    """
    Entry point for SVA.

    Usage:
        ves = VisualizationEngine()
        png_bytes = ves.render(health_snapshot, viewer_level=V3)
    """

    def __init__(self, output_dir: Path | None = None):
        self._output_dir = output_dir or Path("cache") / "viz_output"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def render(
        self,
        obj: object,
        viewer_level: int = V3,
        save_path: Path | None = None,
    ) -> bytes:
        """Render a scientific object to PNG bytes via its canonical SVL renderer.

        Args:
            obj: Any typed scientific object registered in the VES.
            viewer_level: SOI level (0=machine … 4=executive). Controls detail.
            save_path: Optional path to also write the PNG to disk.

        Returns:
            PNG image as bytes.

        Raises:
            VESError: If obj's type has no canonical renderer.
        """
        type_name = type(obj).__name__
        renderer_cls = get_renderer(type_name)
        renderer = renderer_cls(viewer_level=viewer_level)
        png_bytes = renderer.render(obj)

        if save_path:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(png_bytes)

        return png_bytes

    def render_snapshot(self, viewer_level: int = V3) -> bytes:
        """Shortcut: load all sources and render the 4-panel SDOS snapshot."""
        from visualization.api import (
            load_health_snapshot,
            load_pipeline_snapshot,
            load_portfolio_snapshot,
        )
        from visualization.renderers.snapshot import SnapshotBundle, SnapshotRenderer

        bundle = SnapshotBundle(
            health=load_health_snapshot(),
            pipeline=load_pipeline_snapshot(),
            portfolio=load_portfolio_snapshot(),
        )
        renderer = SnapshotRenderer(viewer_level=viewer_level)
        return renderer.render(bundle)
