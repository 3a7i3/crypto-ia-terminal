from __future__ import annotations

import importlib
import sys

import pytest


pytest.importorskip("matplotlib")


def test_evolution_3d_view_exposes_main() -> None:
    if "evolution_3d_view" in sys.modules:
        del sys.modules["evolution_3d_view"]
    module = importlib.import_module("evolution_3d_view")
    assert hasattr(module, "main")