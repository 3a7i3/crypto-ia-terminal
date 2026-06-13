"""
conftest.py (root) — fixtures partagées pour toute la suite de tests.

Isolation recorder:
  Chaque test obtient un PaperTradeRecorder pointant vers un fichier
  temporaire (tmp_path). Cela évite que les tests écrivent dans
  databases/paper_trades.jsonl (le journal de production).
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_paper_recorder(monkeypatch, tmp_path):
    """Redirect paper trade recorder to a per-test temp file.

    Prevents test runs from polluting databases/paper_trades.jsonl.
    Applied automatically to every test in the project.
    """
    import paper_trading.recorder as _rec

    test_log = str(tmp_path / "paper_trades_test.jsonl")
    monkeypatch.setenv("PAPER_TRADE_LOG", test_log)
    monkeypatch.setattr(_rec, "_DEFAULT_PATH", test_log)
    monkeypatch.setattr(_rec, "_recorder", None)
    yield
    monkeypatch.setattr(_rec, "_recorder", None)
