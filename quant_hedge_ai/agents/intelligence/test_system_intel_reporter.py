"""Tests SystemIntelReporter — filtre CLEAN_DATA_SINCE_V3 (ADR-0011).

Cas synthétiques uniquement (comme tests/test_cri_calculator.py) : vérifie
que le rapport Intel compte le même N canonique que le CRI, et ne recommande
plus jamais un burn-in sur la base du volume brut historique.
"""

from __future__ import annotations

import json

import quant_hedge_ai.agents.intelligence.system_intel_reporter as sir
from tools.cri_calculator import CLEAN_DATA_SINCE_V3

_AFTER = CLEAN_DATA_SINCE_V3.timestamp() + 3600  # 1h après la borne
_BEFORE = CLEAN_DATA_SINCE_V3.timestamp() - 3600  # 1h avant la borne


def _close(ts: float, pnl_usd: float = 1.0) -> dict:
    return {"event": "CLOSE", "ts": ts, "pnl_usd": pnl_usd, "pnl_pct": 1.0}


def _write_trades(path, events: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")


class TestReadClosesFiltersCleanDataSince:
    def test_trades_before_cutoff_excluded(self, tmp_path, monkeypatch):
        trades_path = tmp_path / "paper_trades.jsonl"
        _write_trades(trades_path, [_close(_BEFORE), _close(_AFTER)])
        monkeypatch.setattr(sir, "_TRADES_LOG", trades_path)

        closes = sir._read_closes()
        assert len(closes) == 1
        assert closes[0]["ts"] == _AFTER

    def test_recommendation_uses_canonical_n_not_raw_total(self, tmp_path, monkeypatch):
        """Le bug original : 487 trades bruts (dont la majorité avant la borne)
        déclenchait la recommandation de calibration alors que le N canonique
        était de 24. Ici : 150 trades avant la borne (bruit), 5 après —
        la recommandation ne doit PAS dire que le seuil de 100 est atteint."""
        trades_path = tmp_path / "paper_trades.jsonl"
        events = [_close(_BEFORE) for _ in range(150)] + [
            _close(_AFTER) for _ in range(5)
        ]
        _write_trades(trades_path, events)
        monkeypatch.setattr(sir, "_TRADES_LOG", trades_path)
        monkeypatch.setattr(sir, "_SNAPSHOT_PATH", tmp_path / "last_snapshot.json")

        reporter = sir.SystemIntelReporter()
        text = reporter.build_report(cycle=1, results=[])
        assert "Seuil 100 trades" not in text
        assert "5 trade(s) canonique(s) restant" in text
