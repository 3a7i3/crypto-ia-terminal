"""
Live Topology — dependency graph with real-time health overlay.

Shows each module as a node with its current status.
If a node dies, every dependent node is flagged as "at risk".

Usage:
    from observability.live_topology import live_topology

    print(live_topology.render_ascii())   # terminal view
    topology_dict = live_topology.snapshot()  # for dashboard JSON
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Set

from system.dependency_manager import dependency_manager
from system.module_registry import ModuleStatus, module_registry

# Status → display symbol (terminal-friendly)
_STATUS_ICON = {
    ModuleStatus.HEALTHY: "OK",
    ModuleStatus.DEGRADED: "~~",
    ModuleStatus.UNHEALTHY: "XX",
    ModuleStatus.STARTING: "..",
    ModuleStatus.STOPPED: "--",
    ModuleStatus.DISABLED: "//",
}

_STATUS_COLOR = {
    ModuleStatus.HEALTHY: "GREEN",
    ModuleStatus.DEGRADED: "YELLOW",
    ModuleStatus.UNHEALTHY: "RED",
    ModuleStatus.STARTING: "CYAN",
    ModuleStatus.STOPPED: "GREY",
    ModuleStatus.DISABLED: "GREY",
}


class TopologyNode:
    def __init__(self, name: str) -> None:
        self.name = name
        self.status: ModuleStatus = ModuleStatus.STOPPED
        self.latency_ms: float = 0.0
        self.heartbeat_age: float = 0.0
        self.error_count: int = 0
        self.dependencies: List[str] = []
        self.dependents: List[str] = []
        self.at_risk: bool = False  # True if an upstream dependency is unhealthy

    @property
    def icon(self) -> str:
        return _STATUS_ICON.get(self.status, "?")

    @property
    def color(self) -> str:
        if self.at_risk and self.status == ModuleStatus.HEALTHY:
            return "YELLOW"
        return _STATUS_COLOR.get(self.status, "WHITE")

    def snapshot(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.name,
            "color": self.color,
            "icon": self.icon,
            "latency_ms": round(self.latency_ms, 1),
            "heartbeat_age_sec": round(self.heartbeat_age, 2),
            "error_count": self.error_count,
            "dependencies": self.dependencies,
            "dependents": self.dependents,
            "at_risk": self.at_risk,
        }


class LiveTopology:
    """
    Builds a live view of the system topology by merging:
    - dependency graph (structure)
    - module registry (health status)
    """

    def build(self) -> Dict[str, TopologyNode]:
        """Compute the current topology snapshot."""
        graph = dependency_manager.snapshot()
        nodes: Dict[str, TopologyNode] = {}

        # Create a node for every known module
        for mod_name in graph["modules"]:
            node = TopologyNode(mod_name)
            node.dependencies = list(dependency_manager.dependencies_of(mod_name))
            node.dependents = list(dependency_manager.dependents_of(mod_name))
            nodes[mod_name] = node

        # Overlay registry health
        for info in module_registry.all_modules():
            if info.name not in nodes:
                node = TopologyNode(info.name)
                node.dependencies = list(dependency_manager.dependencies_of(info.name))
                node.dependents = list(dependency_manager.dependents_of(info.name))
                nodes[info.name] = node
            node = nodes[info.name]
            node.status = info.status
            node.latency_ms = info.latency_ms
            node.heartbeat_age = info.heartbeat_age
            node.error_count = info.error_count

        # Mark at-risk nodes (upstream dependency is unhealthy/stopped)
        unhealthy_names: Set[str] = {
            n.name
            for n in nodes.values()
            if n.status in {ModuleStatus.UNHEALTHY, ModuleStatus.STOPPED}
        }
        for node in nodes.values():
            if node.name in unhealthy_names:
                continue
            # If any transitive dependency is unhealthy → at_risk
            all_deps = dependency_manager.all_dependencies_of(node.name)
            if all_deps & unhealthy_names:
                node.at_risk = True

        return nodes

    def snapshot(self) -> Dict[str, Any]:
        nodes = self.build()
        try:
            startup_order = dependency_manager.startup_order()
        except Exception:
            startup_order = list(nodes.keys())

        healthy = sum(1 for n in nodes.values() if n.status == ModuleStatus.HEALTHY)
        unhealthy = sum(1 for n in nodes.values() if n.status == ModuleStatus.UNHEALTHY)
        at_risk = sum(1 for n in nodes.values() if n.at_risk)

        return {
            "timestamp": time.time(),
            "summary": {
                "total": len(nodes),
                "healthy": healthy,
                "unhealthy": unhealthy,
                "at_risk": at_risk,
            },
            "flow": startup_order,
            "nodes": {name: node.snapshot() for name, node in nodes.items()},
        }

    def render_ascii(self) -> str:
        """
        Render the topology as a readable ASCII cockpit panel.

        Example output:
          [✓ GREEN ] exchange_connector       latency=8ms
               ↓
          [✓ GREEN ] market_data_feed         latency=12ms
               ↓
          [~ YELLOW] signal_engine            latency=45ms  [AT RISK]
               ↓
          [✗ RED   ] execution_engine         UNHEALTHY errors=3
        """
        nodes = self.build()
        try:
            order = dependency_manager.startup_order()
        except Exception:
            order = list(nodes.keys())

        lines = [
            "",
            "  +--------------------------------------------------+",
            "  |         SYSTEM TOPOLOGY -- LIVE                  |",
            "  +--------------------------------------------------+",
            "",
        ]

        for i, name in enumerate(order):
            node = nodes.get(name)
            if node is None:
                continue

            icon = node.icon
            color = node.color
            lat = f"latency={node.latency_ms:.0f}ms" if node.latency_ms else ""
            err = f"errors={node.error_count}" if node.error_count else ""
            risk = "[AT RISK]" if node.at_risk else ""
            status_str = node.status.name.ljust(9)

            parts = [p for p in [lat, err, risk] if p]
            detail = "  ".join(parts)

            line = f"  [{icon} {color:<6}] {name:<30} {status_str}  {detail}"
            lines.append(line)

            if i < len(order) - 1:
                lines.append("        |")

        lines.append("")
        return "\n".join(lines)

    def render_flow(self) -> str:
        """One-line flow: A → B → C (with dead nodes marked ✗)."""
        nodes = self.build()
        try:
            order = dependency_manager.startup_order()
        except Exception:
            return "dependency graph error"

        parts = []
        for name in order:
            node = nodes.get(name)
            icon = node.icon if node else "?"
            parts.append(f"[{icon}]{name}")

        return " -> ".join(parts)


# Singleton
live_topology = LiveTopology()
