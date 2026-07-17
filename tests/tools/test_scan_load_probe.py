"""Sonde de charge T4 (ADR-0017) — extrapolation pure, zéro réseau."""

from tools.scan_load_probe import CYCLE_BUDGET_S, extrapolate


def test_extrapolate_linear_projection():
    # 150 paires mesurées en 60 s → 0.4 s/paire
    proj = extrapolate(elapsed_s=60.0, n_measured=150)

    assert proj["200"]["cycle_s"] == 80.0
    assert proj["200"]["sous_budget_200s"] is True
    assert proj["1000"]["cycle_s"] == 400.0
    assert proj["1000"]["sous_budget_200s"] is False


def test_extrapolate_budget_boundary():
    proj = extrapolate(elapsed_s=CYCLE_BUDGET_S, n_measured=100)

    # 2 s/paire → 100 paires = exactement le budget → non strictement sous
    assert proj["100"]["sous_budget_200s"] is False


def test_extrapolate_empty_measurement():
    assert extrapolate(elapsed_s=0.0, n_measured=0) == {}
