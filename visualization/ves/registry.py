"""VES Registry — lazily loads renderer classes, never hard-codes diagram choices."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from visualization.renderers.base import BaseRenderer

# Deferred imports — renderers are only loaded when actually needed
_RENDERER_MAP: dict[str, str] = {
    "HealthSnapshot":    "visualization.renderers.radar:RadarRenderer",
    "PipelineSnapshot":  "visualization.renderers.pipeline:PipelineRenderer",
    "PortfolioSnapshot": "visualization.renderers.equity:EquityRenderer",
    "RegimeSnapshot":    "visualization.renderers.timeline:TimelineRenderer",
    "SnapshotBundle":    "visualization.renderers.snapshot:SnapshotRenderer",
}


class VESError(Exception):
    """Raised when a type has no canonical renderer registered."""


def get_renderer(type_name: str) -> type["BaseRenderer"]:
    """Return the renderer class for a given scientific type name.

    Raises VESError if the type has no canonical mapping — never falls back
    to a default, as that would violate R-VES-01.
    """
    module_path = _RENDERER_MAP.get(type_name)
    if module_path is None:
        raise VESError(
            f"No canonical renderer for '{type_name}'. "
            f"Add it to visualization/ves/registry.py and docs/constitution/07_visual_language.md."
        )

    module_name, class_name = module_path.rsplit(":", 1)
    import importlib
    mod = importlib.import_module(module_name)
    return getattr(mod, class_name)


def list_registered_types() -> list[str]:
    return list(_RENDERER_MAP.keys())
