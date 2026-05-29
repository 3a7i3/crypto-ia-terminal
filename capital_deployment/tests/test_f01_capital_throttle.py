"""
capital_deployment/tests/test_f01_capital_throttle.py — F-01 Capital Throttle

Tests de certification :
  - F-01 capital plafonné à 100 EUR absolus
  - throttled_size clamp correct
  - is_within_limit correct
  - advance_to requiert certified=True
  - PHASE_CONFIGS contient les 5 phases
  - PhaseAllocation.to_dict() complet
  - min_duration_days correct par phase
  - max_single_position correct
  - erreur sur phase inconnue
  - erreur sur capital nul ou négatif
  - next_phase() navigation correcte
  - F-05 est la phase finale (next_phase = None)

Total : 12 tests
"""

from __future__ import annotations

import time

import pytest

from capital_deployment.capital_throttle import (
    PHASE_CONFIGS,
    PHASE_ORDER,
    CapitalThrottle,
    PhaseAllocation,
)


class TestPhaseConfigs:
    def test_five_phases_defined(self):
        """Les 5 phases sont définies dans PHASE_CONFIGS."""
        assert set(PHASE_CONFIGS.keys()) == {"F-01", "F-02", "F-03", "F-04", "F-05"}

    def test_phase_order_correct(self):
        """PHASE_ORDER va de F-01 à F-05."""
        assert PHASE_ORDER == ["F-01", "F-02", "F-03", "F-04", "F-05"]

    def test_min_duration_days(self):
        """Durées minimales correctes par phase."""
        expected = {"F-01": 7, "F-02": 14, "F-03": 21, "F-04": 30, "F-05": 0}
        for phase, days in expected.items():
            assert PHASE_CONFIGS[phase]["min_duration_days"] == days

    def test_capital_pct(self):
        """Pourcentages de capital par phase."""
        expected = {
            "F-01": 0.01,
            "F-02": 0.05,
            "F-03": 0.25,
            "F-04": 0.50,
            "F-05": 1.00,
        }
        for phase, pct in expected.items():
            assert PHASE_CONFIGS[phase]["capital_pct"] == pytest.approx(pct)


class TestF01Cap:
    def test_f01_large_capital_capped_at_100(self):
        """F-01 : capital de 100 000 EUR → alloué 100 EUR max."""
        throttle = CapitalThrottle(total_capital=100_000.0, phase="F-01")
        assert throttle.allocated_capital == pytest.approx(100.0)

    def test_f01_small_capital_uses_1pct(self):
        """F-01 : capital de 5 000 EUR → alloué 50 EUR (1% < 100)."""
        throttle = CapitalThrottle(total_capital=5_000.0, phase="F-01")
        assert throttle.allocated_capital == pytest.approx(50.0)

    def test_f02_no_absolute_cap(self):
        """F-02 : 5% du capital sans plafond absolu."""
        throttle = CapitalThrottle(total_capital=100_000.0, phase="F-02")
        assert throttle.allocated_capital == pytest.approx(5_000.0)


class TestThrottledSize:
    def test_throttled_size_clamps_to_allocated(self):
        """throttled_size clamp la demande au capital alloué."""
        throttle = CapitalThrottle(total_capital=10_000.0, phase="F-01")
        # allocated = 100.0 (F-01 cap)
        assert throttle.throttled_size(500.0) == pytest.approx(100.0)

    def test_throttled_size_allows_smaller_orders(self):
        """throttled_size laisse passer les ordres sous le plafond."""
        throttle = CapitalThrottle(total_capital=10_000.0, phase="F-01")
        assert throttle.throttled_size(50.0) == pytest.approx(50.0)

    def test_throttled_size_zero_input(self):
        """throttled_size retourne 0 pour une demande nulle ou négative."""
        throttle = CapitalThrottle(total_capital=1_000.0, phase="F-01")
        assert throttle.throttled_size(0.0) == 0.0
        assert throttle.throttled_size(-10.0) == 0.0

    def test_is_within_limit(self):
        """is_within_limit correct pour ordes dans/hors limite."""
        throttle = CapitalThrottle(total_capital=10_000.0, phase="F-02")
        # F-02: 5% × 10000 = 500
        assert throttle.is_within_limit(200.0) is True
        assert throttle.is_within_limit(600.0) is False
        assert throttle.is_within_limit(0.0) is False

    def test_max_single_position(self):
        """max_single_position = 20% du capital alloué par défaut."""
        throttle = CapitalThrottle(total_capital=10_000.0, phase="F-02")
        # allocated = 500 → max_pos = 100
        assert throttle.max_single_position() == pytest.approx(100.0)


class TestPhaseAdvancement:
    def test_advance_to_requires_certified(self):
        """advance_to sans certification → PermissionError."""
        throttle = CapitalThrottle(total_capital=10_000.0, phase="F-01")
        with pytest.raises(PermissionError):
            throttle.advance_to("F-02", certified=False)

    def test_advance_to_with_certification(self):
        """advance_to avec certified=True → nouveau CapitalThrottle F-02."""
        throttle = CapitalThrottle(total_capital=10_000.0, phase="F-01")
        next_throttle = throttle.advance_to("F-02", certified=True)
        assert next_throttle.phase == "F-02"
        assert next_throttle.allocated_capital == pytest.approx(500.0)

    def test_next_phase_navigation(self):
        """next_phase() retourne la phase suivante correctement."""
        t01 = CapitalThrottle(total_capital=1_000.0, phase="F-01")
        assert t01.next_phase() == "F-02"
        t05 = CapitalThrottle(total_capital=1_000.0, phase="F-05")
        assert t05.next_phase() is None


class TestValidation:
    def test_unknown_phase_raises(self):
        """Phase inconnue → ValueError."""
        with pytest.raises(ValueError, match="Phase inconnue"):
            CapitalThrottle(total_capital=1_000.0, phase="F-99")

    def test_nonpositive_capital_raises(self):
        """Capital ≤ 0 → ValueError."""
        with pytest.raises(ValueError):
            CapitalThrottle(total_capital=0.0, phase="F-01")

    def test_allocation_to_dict_complete(self):
        """PhaseAllocation.to_dict() contient tous les champs requis."""
        throttle = CapitalThrottle(total_capital=1_000.0, phase="F-01")
        d = throttle.allocation().to_dict()
        for key in (
            "phase",
            "total_capital",
            "allocated_capital",
            "capital_pct",
            "min_duration_days",
            "days_elapsed",
            "time_requirement_met",
        ):
            assert key in d, f"Clé manquante: {key}"
