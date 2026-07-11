"""
test_adr0013_safe_mode_recovery_deadlock.py — Régression ADR-0013.

Incident 2026-07-10/11 : self_awareness a déclenché SAFE_MODE sur un
échantillon de 5 trades (drawdown_acceleration, seul signal de dérive non
protégé par la garde RECENT_WINDOW), puis RECOVERY est resté bloqué car
report_ok() n'était jamais appelé en production. Voir
docs/adr/0013-safe-mode-recovery-deadlock.md.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from quant_hedge_ai.agents.intelligence.self_awareness_engine import (
    DangerLevel,
    SelfAwarenessEngine,
)
from quant_hedge_ai.runtime.runtime_state_machine import (
    RuntimeStateMachine,
    SystemState,
)


class _FakeClock:
    """Horloge simulée — espace les trades pour ne pas déclencher le
    signal 'overtrading' (OVERTRADE_WINDOW=60s, OVERTRADE_MAX=3), qui est
    hors du périmètre de ce test (ADR-0013 ne touche que performance drift)."""

    def __init__(self, start: float = 1_700_000_000.0, step_s: float = 90.0):
        self._t = start
        self._step_s = step_s

    def now(self) -> float:
        val = self._t
        self._t += self._step_s
        return val


# ── Fix #1 — garde RECENT_WINDOW étendue à drawdown_acceleration ────────────


class TestDrawdownAccelerationGuard:
    def _record_incident_pattern(
        self, engine: SelfAwarenessEngine, n: int, clock: _FakeClock
    ) -> None:
        """W=2/L=3 répété — reproduit le pattern de l'incident 2026-07-10
        (cumdd ≈ 5% sur les 5 premiers trades, largement > DD_ACCEL_WARN=3%)."""
        pattern = [0.01, -0.02, -0.015, 0.005, -0.02]
        for i in range(n):
            with patch("time.time", side_effect=clock.now):
                engine.record_trade(
                    pnl_pct=pattern[i % len(pattern)], regime="sideways"
                )

    def test_no_warning_below_recent_window(self):
        """N=5 (< RECENT_WINDOW=10) : plus de WARNING malgré un drawdown
        > DD_ACCEL_WARN — c'est exactement le scénario de l'incident."""
        engine = SelfAwarenessEngine()
        clock = _FakeClock()
        self._record_incident_pattern(engine, 5, clock)

        with patch("time.time", side_effect=clock.now):
            state = engine.evaluate()

        assert state.level < DangerLevel.WARNING, (
            f"Régression ADR-0013 : WARNING déclenché sur N=5 trades "
            f"(level={state.level.name}, drifts={state.active_drifts})"
        )
        assert not any(d.metric == "drawdown_acceleration" for d in state.active_drifts)

    def test_warning_still_fires_at_recent_window(self):
        """N=RECENT_WINDOW (10), même pattern de pertes concentrées sur la
        fenêtre récente : le signal doit toujours pouvoir se déclencher —
        le fix resserre la garde, il ne désactive pas la détection."""
        engine = SelfAwarenessEngine()
        clock = _FakeClock()
        # 5 trades neutres pour peupler le baseline, puis le pattern de perte
        # concentré dans la fenêtre récente (RECENT_WINDOW=10 au total).
        for _ in range(5):
            with patch("time.time", side_effect=clock.now):
                engine.record_trade(pnl_pct=0.0, regime="sideways")
        self._record_incident_pattern(engine, 5, clock)

        with patch("time.time", side_effect=clock.now):
            state = engine.evaluate()

        assert state.level >= DangerLevel.WARNING, (
            f"drawdown_acceleration ne se déclenche plus du tout à "
            f"N=RECENT_WINDOW — le fix a désactivé la détection au lieu de "
            f"resserrer sa garde (level={state.level.name})"
        )
        assert any(d.metric == "drawdown_acceleration" for d in state.active_drifts)

    def test_win_rate_and_sharpe_unaffected_by_guard_change(self):
        """Le fix ne resserre que drawdown_acceleration — win_rate/sharpe ne
        pouvaient déjà rien produire sous RECENT_WINDOW (fallback
        baseline==recent, drop=0), comportement inchangé."""
        engine = SelfAwarenessEngine()
        clock = _FakeClock()
        self._record_incident_pattern(engine, 5, clock)

        with patch("time.time", side_effect=clock.now):
            state = engine.evaluate()

        assert not any(d.metric in ("win_rate", "sharpe") for d in state.active_drifts)


# ── Fix #2 — report_ok() câblé une fois par cycle réussi ────────────────────


class TestReportOkWiredInMainLoop:
    def test_report_ok_called_in_main_loop_success_path(self):
        """core/advisor_loop.py doit appeler runtime_authority.report_ok()
        sur le chemin de sortie normal du cycle (symétrique de
        report_error("cycle_exception")) — sinon RECOVERY/DEGRADED/CRITICAL
        restent des états terminaux (incident 2026-07-10/11)."""
        src = (Path(__file__).parent.parent / "core" / "advisor_loop.py").read_text(
            encoding="utf-8"
        )

        assert "runtime_authority.report_ok()" in src, (
            "Régression ADR-0013 : report_ok() n'est plus appelé dans "
            "core/advisor_loop.py — RECOVERY ne pourra plus jamais graduer "
            "vers NORMAL sans redémarrage."
        )

        # Doit être sur le chemin normal (avant le bloc except du cycle),
        # pas seulement présent quelque part dans le fichier.
        try_idx = src.index("\n        try:\n            if cycle == 1")
        except_idx = src.index("\n        except KeyboardInterrupt:")
        report_ok_idx = src.index("runtime_authority.report_ok()")

        assert try_idx < report_ok_idx < except_idx, (
            "report_ok() doit être appelé à l'intérieur du try du cycle "
            "principal, avant le except — pas dans le chemin d'erreur ni "
            "ailleurs dans le fichier."
        )


# ── Bout en bout — machine d'état seule, chaîne causale complète ────────────
# Complète le test de câblage ci-dessus (qui vérifie seulement que
# advisor_loop.py APPELLE report_ok() au bon endroit) par un test
# comportemental sur RuntimeStateMachine elle-même : verrouille la vraie
# transition, indépendamment de tout refactor futur du texte source.


class TestRuntimeStateMachineEndToEnd:
    def test_safe_mode_resume_report_ok_reaches_normal(self):
        """Reproduit la chaîne complète de l'incident 2026-07-10/11 :
        SAFE_MODE -> /RESUME (clear_all_safe_mode_requests) -> RECOVERY
        -> report_ok() -> NORMAL. stability_s=0 pour un test déterministe
        et rapide (équivalent à laisser le temps réel s'écouler)."""
        rsm = RuntimeStateMachine(stability_s=0)

        rsm.request_safe_mode("self_awareness", "level=WARNING")
        assert rsm.state == SystemState.SAFE_MODE

        rsm.clear_all_safe_mode_requests()
        assert rsm.state == SystemState.RECOVERY, (
            "/RESUME doit transitionner SAFE_MODE -> RECOVERY (jamais "
            "directement NORMAL, cf. runtime_state_machine.py:217-227)"
        )

        rsm.report_ok()
        assert rsm.state == SystemState.NORMAL, (
            "Régression ADR-0013 : report_ok() n'a pas fait graduer "
            "RECOVERY -> NORMAL — c'était le point mort n°2 de l'incident."
        )

    def test_recovery_stuck_without_report_ok(self):
        """Contre-épreuve : sans appel à report_ok(), RECOVERY reste
        RECOVERY indéfiniment, même après un temps arbitrairement long —
        documente le point mort exact qui a nécessité un redémarrage
        complet du process le 2026-07-11."""
        rsm = RuntimeStateMachine(stability_s=0)
        rsm.request_safe_mode("self_awareness", "level=WARNING")
        rsm.clear_all_safe_mode_requests()
        assert rsm.state == SystemState.RECOVERY

        # Aucun report_ok() appelé — rien d'autre ne fait avancer l'état.
        assert rsm.state == SystemState.RECOVERY

    def test_degraded_report_ok_reaches_normal(self):
        """Cas symétrique documenté dans l'ADR : DEGRADED/CRITICAL sont
        condamnés par le même défaut que RECOVERY -> NORMAL. Horloge
        simulée (injectée via _clock) plutôt que des fenêtres à 0 sur le
        temps réel — évite toute dépendance à la résolution de l'horloge
        système sur une machine rapide."""
        fake_now = [1_700_000_000.0]
        rsm = RuntimeStateMachine(
            degraded_threshold=1,
            window_s=1.0,
            silence_s=1.0,
            stability_s=1.0,
            _clock=lambda: fake_now[0],
        )

        rsm.report_error("transient_fault")
        assert rsm.state == SystemState.DEGRADED

        # Avancer au-delà de window_s (évince l'erreur) et silence_s.
        fake_now[0] += 2.0
        rsm.report_ok()
        assert rsm.state == SystemState.RECOVERY

        # Avancer au-delà de stability_s pour graduer vers NORMAL.
        fake_now[0] += 2.0
        rsm.report_ok()
        assert rsm.state == SystemState.NORMAL
