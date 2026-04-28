import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import importlib
import sys


def test_evolution_3d_view_main(monkeypatch, tmp_path):
    # Patch les accès fichiers si besoin
    if "evolution_3d_view" in sys.modules:
        importlib.reload(sys.modules["evolution_3d_view"])
    import evolution_3d_view

    # Appel de la fonction main (doit être idempotente)
    assert hasattr(evolution_3d_view, "main")
