"""SVA invariants enforced at runtime."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RendererContract:
    """Normative binding between a scientific type and its SVL renderer."""
    type_name: str
    renderer_name: str
    supported_levels: tuple[int, ...]   # SOI viewer levels (0–4)
    svl_version: str = "1.0"


# Canonical VES table (ADR-0010 § 2.2)
CANONICAL_CONTRACTS: list[RendererContract] = [
    RendererContract("HealthSnapshot",    "RadarRenderer",      (2, 3)),
    RendererContract("PipelineSnapshot",  "PipelineRenderer",   (1, 2, 3)),
    RendererContract("PortfolioSnapshot", "EquityRenderer",     (2, 3)),
    RendererContract("RegimeSnapshot",    "TimelineRenderer",   (2, 3)),
]
