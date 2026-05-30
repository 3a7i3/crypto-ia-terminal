from __future__ import annotations

import importlib
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIRS = {
    "lm_studio": set(),
    "meta_learning": set(),
}
ROOT_MODULES = {
    "bootstrap_integration",
    "circuit_breaker",
    "daily_analyzer",
    "evolution_memory",
    "lazy_loader",
    "population_csv_validator",
}


def _discover_smoke_modules() -> list[str]:
    modules = set(ROOT_MODULES)
    for package_name, excluded_files in PACKAGE_DIRS.items():
        package_dir = WORKSPACE_ROOT / package_name
        for module_path in package_dir.glob("*.py"):
            if module_path.name == "__init__.py" or module_path.name in excluded_files:
                continue
            modules.add(f"{package_name}.{module_path.stem}")
        modules.add(package_name)
    return sorted(modules)


def test_library_modules_import_cleanly() -> None:
    failures: list[tuple[str, str]] = []

    for module_name in _discover_smoke_modules():
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - exercised only on failures
            failures.append((module_name, str(exc)))

    assert not failures, "\n".join(
        f"[FAIL] {module_name}: {error}" for module_name, error in failures
    )
