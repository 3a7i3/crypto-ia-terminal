"""
Dependency graph for system modules.
Validates startup order, detects cycles, prevents a module from starting
before its dependencies are healthy.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, List, Optional, Set


class CircularDependency(Exception):
    pass


class DependencyNotMet(Exception):
    pass


class DependencyManager:
    """
    Directed acyclic graph of module dependencies.
    edge A → B means "A depends on B" (B must start first).
    """

    def __init__(self) -> None:
        # name -> set of names this module depends on
        self._deps: Dict[str, Set[str]] = defaultdict(set)
        # name -> set of names that depend on this module
        self._rdeps: Dict[str, Set[str]] = defaultdict(set)

    # ------------------------------------------------------------------
    # Graph building
    # ------------------------------------------------------------------

    def declare(self, module: str, depends_on: Optional[List[str]] = None) -> None:
        """Register a module and its dependencies."""
        if module not in self._deps:
            self._deps[module] = set()
        for dep in depends_on or []:
            self._deps[module].add(dep)
            self._rdeps[dep].add(module)
        self._validate_no_cycle()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def startup_order(self) -> List[str]:
        """
        Topological sort — returns modules in the order they should start.
        Modules with no dependencies come first.
        """
        in_degree: Dict[str, int] = {m: len(deps) for m, deps in self._deps.items()}
        # Ensure all referenced deps are also in the graph
        for dep_set in self._deps.values():
            for dep in dep_set:
                if dep not in in_degree:
                    in_degree[dep] = 0

        queue: deque[str] = deque(m for m, d in in_degree.items() if d == 0)
        order: List[str] = []

        while queue:
            node = queue.popleft()
            order.append(node)
            for dependent in self._rdeps.get(node, set()):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(order) != len(in_degree):
            raise CircularDependency("Cycle detected in dependency graph")
        return order

    def shutdown_order(self) -> List[str]:
        """Reverse of startup order."""
        return list(reversed(self.startup_order()))

    def dependencies_of(self, module: str) -> Set[str]:
        """All direct dependencies of a module."""
        return self._deps.get(module, set())

    def dependents_of(self, module: str) -> Set[str]:
        """Modules that directly depend on this module."""
        return self._rdeps.get(module, set())

    def all_dependencies_of(self, module: str) -> Set[str]:
        """Transitive closure of dependencies."""
        visited: Set[str] = set()
        queue = deque(self._deps.get(module, set()))
        while queue:
            dep = queue.popleft()
            if dep not in visited:
                visited.add(dep)
                queue.extend(self._deps.get(dep, set()))
        return visited

    def can_start(self, module: str, healthy_modules: Set[str]) -> bool:
        """Returns True if all dependencies of module are in healthy_modules."""
        return self.dependencies_of(module).issubset(healthy_modules)

    def impact_of_failure(self, module: str) -> Set[str]:
        """Which modules are affected if this module goes down (transitive)."""
        affected: Set[str] = set()
        queue = deque(self._rdeps.get(module, set()))
        while queue:
            dep = queue.popleft()
            if dep not in affected:
                affected.add(dep)
                queue.extend(self._rdeps.get(dep, set()))
        return affected

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_no_cycle(self) -> None:
        try:
            self.startup_order()
        except CircularDependency as e:
            raise CircularDependency(str(e)) from e

    def validate_all_deps_declared(self) -> List[str]:
        """Returns list of dependency names referenced but never declared."""
        all_declared = set(self._deps.keys())
        missing = []
        for deps in self._deps.values():
            for dep in deps:
                if dep not in all_declared:
                    missing.append(dep)
        return missing

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        try:
            order = self.startup_order()
        except CircularDependency as e:
            order = [f"ERROR: {e}"]
        return {
            "modules": list(self._deps.keys()),
            "startup_order": order,
            "edges": {m: list(deps) for m, deps in self._deps.items() if deps},
        }


# Singleton
dependency_manager = DependencyManager()

# ------------------------------------------------------------------
# Pre-declare the known dependency graph
# ------------------------------------------------------------------
# Anything that doesn't exist yet can still be declared — the graph
# is purely logical and doesn't require the modules to be importable.

_KNOWN_GRAPH = [
    # (module, [depends_on])
    ("exchange_connector", []),
    ("market_data_feed", ["exchange_connector"]),
    ("event_bus", []),
    ("state_manager", []),
    ("module_registry", []),
    ("risk_engine", ["exchange_connector", "market_data_feed"]),
    ("position_truth_engine", ["exchange_connector"]),
    ("signal_engine", ["market_data_feed", "event_bus"]),
    ("decision_router", ["signal_engine", "risk_engine", "state_manager"]),
    (
        "execution_engine",
        [
            "decision_router",
            "risk_engine",
            "position_truth_engine",
            "exchange_connector",
        ],
    ),
    ("advisor_loop", ["signal_engine", "risk_engine", "decision_router"]),
    ("portfolio_brain", ["position_truth_engine", "risk_engine"]),
    ("chief_officer", ["advisor_loop", "portfolio_brain"]),
    ("self_healing_bot", ["module_registry", "state_manager"]),
    ("dashboard", ["event_bus"]),
    ("audit_ledger", ["event_bus"]),
]

for _mod, _deps in _KNOWN_GRAPH:
    dependency_manager.declare(_mod, _deps)
