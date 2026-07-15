"""Alerte famine de trading — SystemIntelReporter (observateur passif).

Régression 2026-07-14 : 26h sans aucun trade après le restart du 13/07
(rotation d'univers, plus aucun candidat ne franchissait son seuil de
régime) et aucun panneau ne le signalait — l'opérateur a dû le déduire
d'un N figé à 36 entre plusieurs rapports espacés de 6h.
"""

from quant_hedge_ai.agents.intelligence.system_intel_reporter import _stall_anomaly


def test_stall_alert_fires_after_threshold(monkeypatch):
    monkeypatch.setenv("INTEL_TRADE_STALL_ALERT_H", "12")

    msg = _stall_anomaly(trade_stall_h=26.0, n_total=36)

    assert msg is not None
    assert "26h" in msg
    assert "36" in msg


def test_stall_alert_silent_below_threshold(monkeypatch):
    monkeypatch.setenv("INTEL_TRADE_STALL_ALERT_H", "12")

    assert _stall_anomaly(trade_stall_h=3.0, n_total=36) is None


def test_stall_alert_silent_when_dataset_empty(monkeypatch):
    """N=0 = phase d'accumulation initiale, pas une famine — le message
    'Aucun trade fermé encore' du reporter couvre déjà ce cas."""
    monkeypatch.setenv("INTEL_TRADE_STALL_ALERT_H", "12")

    assert _stall_anomaly(trade_stall_h=100.0, n_total=0) is None


def test_stall_alert_disabled_with_zero_threshold(monkeypatch):
    monkeypatch.setenv("INTEL_TRADE_STALL_ALERT_H", "0")

    assert _stall_anomaly(trade_stall_h=100.0, n_total=36) is None
