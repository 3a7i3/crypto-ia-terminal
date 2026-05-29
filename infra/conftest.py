"""Pytest: racine du dépôt sur sys.path ; ignore certains scripts d'intégration UI."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_root_str = str(_ROOT)
if _root_str not in sys.path:
    sys.path.insert(0, _root_str)

# Scripts lancés manuellement (Selenium / HTTP), pas des modules pytest.
_IGNORE_SCRIPT_NAMES = frozenset(
    {
        "panel_selenium_test.py",
        "panel_http_test.py",
        "orchestrate_panels_test.py",
    }
)


def pytest_ignore_collect(collection_path: Path, config) -> bool | None:
    """Évite collecte / import de scripts lourds ou e2e sans variable d'environnement."""
    try:
        name = Path(collection_path).name
    except TypeError:
        name = Path(str(collection_path)).name

    if os.environ.get("PLAYWRIGHT_E2E", "") != "1" and "playwright" in name.lower():
        return True

    if os.environ.get("SELENIUM_PANEL_E2E", "") != "1" and name in _IGNORE_SCRIPT_NAMES:
        return True

    return None
