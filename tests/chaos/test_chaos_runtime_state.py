"""
Chaos — RuntimeStateMachine.

Tests de la machine d'état runtime à 5 niveaux.
Utilise une horloge factice (_clock) pour éviter tout sleep() dans les tests.
Invariants vérifiés :
  - Transitions montantes correctes (NORMAL → DEGRADED → CRITICAL → SAFE_MODE)
  - Politiques de trading respectées à chaque état
  - Transitions descendantes correctes (CRITICAL → RECOVERY → NORMAL)
  - Callbacks déclenchés à chaque transition
  - Fenêtre glissante evict les erreurs expirées
  - force_safe_mode() et force_recovery() overrides manuels
"""

from __future__ import annotations

from quant_hedge_ai.runtime.runtime_state_machine import (
    RuntimeStateMachine,
    SystemState,
)

# ── Horloge factice ──────────────────────────────────────────────────────────


class _FakeClock:
    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, s: float) -> None:
        self.t += s


def _sm(
    degraded=3,
    critical=7,
    safe=10,
    window_s=60.0,
    silence_s=30.0,
    stability_s=60.0,
    clock=None,
) -> tuple[RuntimeStateMachine, _FakeClock]:
    clk = clock or _FakeClock()
    return (
        RuntimeStateMachine(
            degraded_threshold=degraded,
            critical_threshold=critical,
            safe_threshold=safe,
            window_s=window_s,
            silence_s=silence_s,
            stability_s=stability_s,
            _clock=clk,
        ),
        clk,
    )


# ── Transitions montantes ──────────────────────────────────────────────────────


class TestDegradation:
    def test_initial_state_is_normal(self):
        sm, _ = _sm()
        assert sm.state == SystemState.NORMAL

    def test_single_error_stays_normal(self):
        sm, _ = _sm(degraded=3)
        sm.report_error()
        assert sm.state == SystemState.NORMAL

    def test_threshold_triggers_degraded(self):
        sm, _ = _sm(degraded=3)
        for _ in range(3):
            sm.report_error()
        assert (
            sm.state == SystemState.DEGRADED
        ), "INVARIANT BRISÉ: 3 erreurs doivent déclencher DEGRADED"

    def test_threshold_triggers_critical(self):
        sm, _ = _sm(degraded=3, critical=7)
        for _ in range(7):
            sm.report_error()
        assert sm.state == SystemState.CRITICAL

    def test_threshold_triggers_safe_mode(self):
        sm, _ = _sm(degraded=3, critical=7, safe=10)
        for _ in range(10):
            sm.report_error()
        assert (
            sm.state == SystemState.SAFE_MODE
        ), "INVARIANT BRISÉ: 10 erreurs doivent déclencher SAFE_MODE"

    def test_safe_mode_not_exited_by_more_errors(self):
        sm, _ = _sm(safe=5)
        for _ in range(20):
            sm.report_error()
        assert sm.state == SystemState.SAFE_MODE

    def test_no_skip_straight_to_critical_below_threshold(self):
        sm, _ = _sm(degraded=3, critical=7)
        for _ in range(4):
            sm.report_error()
        assert sm.state == SystemState.DEGRADED  # pas CRITICAL (seuil=7)


# ── Politiques par état ────────────────────────────────────────────────────────


class TestPolicies:
    def test_normal_allows_trading(self):
        sm, _ = _sm()
        assert sm.can_trade is True
        assert sm.can_fetch_data is True
        assert sm.size_factor == 1.0

    def test_degraded_allows_trading_reduced(self):
        sm, _ = _sm(degraded=3)
        for _ in range(3):
            sm.report_error()
        assert sm.can_trade is True
        assert sm.size_factor == 0.5

    def test_critical_blocks_trading(self):
        sm, _ = _sm(critical=3, degraded=1)
        for _ in range(3):
            sm.report_error()
        assert sm.can_trade is False
        assert sm.can_fetch_data is True

    def test_safe_mode_blocks_everything(self):
        sm, _ = _sm(safe=3, degraded=1, critical=2)
        for _ in range(3):
            sm.report_error()
        assert sm.can_trade is False
        assert sm.can_fetch_data is False
        assert sm.size_factor == 0.0

    def test_recovery_blocks_trading(self):
        sm, clk = _sm(degraded=3, silence_s=30.0, window_s=60.0)
        for _ in range(3):
            sm.report_error()
        # window_s=60 : les erreurs expirent à t>60. silence_s=30 : silence requis.
        # Il faut avancer au-delà des deux : max(window_s, silence_s) + marge.
        clk.advance(70.0)  # erreurs expirées (70 > 60) ET silence atteint (70 > 30)
        sm.report_ok()
        assert (
            sm.state == SystemState.RECOVERY
        ), f"INVARIANT BRISÉ: après silence, état = {sm.state}"
        assert sm.can_trade is False
        assert sm.can_fetch_data is True


# ── Transitions descendantes ──────────────────────────────────────────────────


class TestRecovery:
    def test_degraded_to_recovery_after_silence(self):
        sm, clk = _sm(degraded=3, silence_s=30.0, window_s=60.0)
        for _ in range(3):
            sm.report_error()
        assert sm.state == SystemState.DEGRADED
        clk.advance(35.0)  # erreurs pas encore expirées mais silence atteint
        # Les erreurs ont 35s → pas encore expirées (window=60), mais silence=30 atteint
        # _evict purge >60s, ici 35s donc encore dans la fenêtre
        # La transition RECOVERY nécessite aussi count==0 (erreurs expirées)
        clk.advance(30.0)  # total 65s : erreurs expirées (window_s=60)
        sm.report_ok()
        assert (
            sm.state == SystemState.RECOVERY
        ), f"INVARIANT BRISÉ: état après silence = {sm.state}"

    def test_recovery_to_normal_after_stability(self):
        sm, clk = _sm(degraded=3, silence_s=30.0, stability_s=60.0, window_s=60.0)
        for _ in range(3):
            sm.report_error()
        clk.advance(65.0)  # erreurs expirées + silence atteint
        sm.report_ok()
        assert sm.state == SystemState.RECOVERY
        clk.advance(61.0)  # stability_s atteint
        sm.report_ok()
        assert (
            sm.state == SystemState.NORMAL
        ), "INVARIANT BRISÉ: RECOVERY → NORMAL après stabilité non déclenché"

    def test_force_safe_mode_immediate(self):
        sm, _ = _sm()
        sm.force_safe_mode("test manual override")
        assert sm.state == SystemState.SAFE_MODE

    def test_force_recovery_clears_errors(self):
        sm, _ = _sm(degraded=3, critical=5)
        for _ in range(8):
            sm.report_error()
        assert sm.state in (SystemState.CRITICAL, SystemState.SAFE_MODE)
        sm.force_recovery()
        assert sm.state == SystemState.RECOVERY
        assert sm.error_count == 0

    def test_reset_returns_to_normal(self):
        sm, _ = _sm(safe=3)
        for _ in range(5):
            sm.report_error()
        sm.reset()
        assert sm.state == SystemState.NORMAL
        assert sm.error_count == 0


# ── Callbacks ──────────────────────────────────────────────────────────────────


class TestCallbacks:
    def test_callback_fired_on_transition(self):
        sm, _ = _sm(degraded=2)
        fired = []
        sm.on_transition(lambda old, new: fired.append((old.value, new.value)))
        sm.report_error()
        sm.report_error()
        assert len(fired) == 1
        assert fired[0] == ("NORMAL", "DEGRADED")

    def test_callback_fired_for_each_transition(self):
        sm, _ = _sm(degraded=2, critical=4, safe=6)
        fired = []
        sm.on_transition(lambda old, new: fired.append(new.value))
        for _ in range(6):
            sm.report_error()
        assert "DEGRADED" in fired
        assert "CRITICAL" in fired
        assert "SAFE_MODE" in fired

    def test_broken_callback_does_not_crash_sm(self):
        sm, _ = _sm(degraded=2)
        sm.on_transition(lambda o, n: (_ for _ in ()).throw(RuntimeError("bad cb")))
        # Ne doit pas lever d'exception
        sm.report_error()
        sm.report_error()
        assert sm.state == SystemState.DEGRADED


# ── Fenêtre glissante ─────────────────────────────────────────────────────────


class TestSlidingWindow:
    def test_expired_errors_evicted(self):
        sm, clk = _sm(degraded=3, window_s=60.0)
        sm.report_error()
        sm.report_error()
        clk.advance(70.0)  # les 2 erreurs expirent
        assert sm.error_count == 0

    def test_errors_within_window_counted(self):
        sm, clk = _sm(degraded=3, window_s=60.0)
        sm.report_error()
        clk.advance(30.0)
        sm.report_error()
        clk.advance(20.0)  # premier encore dans la fenêtre (50s < 60s)
        assert sm.error_count == 2

    def test_snapshot_coherent(self):
        sm, _ = _sm()
        snap = sm.snapshot()
        assert snap["state"] == "NORMAL"
        assert snap["can_trade"] is True
        assert snap["size_factor"] == 1.0
