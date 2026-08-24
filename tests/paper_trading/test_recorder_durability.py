"""
tests/paper_trading/test_recorder_durability.py

R4 (audit forensic 2026-08-24) — durability of the paper_trades source of truth.
Each append flushes and fsyncs so the last record survives a power loss, unless
explicitly disabled via PAPER_TRADE_FSYNC=0.
"""

from __future__ import annotations

import json
import os

import paper_trading.recorder as rec


def _close(r):
    r.record_close(
        trade_id="x",
        exit_price=1.0,
        pnl_usd=0.1,
        pnl_pct=0.01,
        reason="TP",
        symbol="BTC/USDT",
        side="buy",
    )


def test_fsync_called_by_default(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(os, "fsync", lambda fd: calls.append(fd))
    r = rec.PaperTradeRecorder(log_path=str(tmp_path / "t.jsonl"))
    _close(r)
    assert len(calls) >= 1  # append fsynced the source of truth


def test_fsync_disabled_by_env(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(os, "fsync", lambda fd: calls.append(fd))
    monkeypatch.setenv("PAPER_TRADE_FSYNC", "0")
    r = rec.PaperTradeRecorder(log_path=str(tmp_path / "t.jsonl"))
    _close(r)
    assert calls == []  # opt-out honoured


def test_content_intact_regardless(tmp_path):
    r = rec.PaperTradeRecorder(log_path=str(tmp_path / "t.jsonl"))
    _close(r)
    d = json.loads((tmp_path / "t.jsonl").read_text().strip())
    assert d["symbol"] == "BTC/USDT"
    assert d["reason"] == "TP"


def test_fsync_oserror_is_swallowed(tmp_path, monkeypatch):
    def _boom(fd):
        raise OSError("fsync unsupported")

    monkeypatch.setattr(os, "fsync", _boom)
    r = rec.PaperTradeRecorder(log_path=str(tmp_path / "t.jsonl"))
    _close(r)  # must not raise
    d = json.loads((tmp_path / "t.jsonl").read_text().strip())
    assert d["reason"] == "TP"
