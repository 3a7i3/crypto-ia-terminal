"""
Chaos — Mode Dégradé (Phase 6).

Valide que le système survit au kill de chaque module critique.
Matrice de décision (SYSTEM_DEGRADATION_POLICY §6) :

  Module mort              | Comportement attendu
  -------------------------|--------------------------------------------
  Telegram DOWN            | Trading continue, logs bufferisés
  RegimeEngine timeout     | Fallback régime neutral, levier réduit 0.5
  Redis DOWN               | Cache désactivé, lecture directe
  Binance WS freeze        | Polling fallback, état DEGRADED
  Signal confidence invalid| Trade refusé, pas de crash

Invariant global :
  Après chaque kill, le système produit encore une décision.
  L'état peut être DEGRADED mais JAMAIS SAFE_MODE (sauf si cumulé).
"""

from __future__ import annotations

import time

import pytest

from quant_hedge_ai.runtime.fault_containment import ContainmentGuard, Zone
from quant_hedge_ai.runtime.runtime_state_machine import (
    RuntimeStateMachine,
    SystemState,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _sm_paper() -> RuntimeStateMachine:
    """Thresholds paper/testnet (SYSTEM_DEGRADATION_POLICY §6)."""
    return RuntimeStateMachine(
        degraded_threshold=3,
        critical_threshold=7,
        safe_threshold=10,
        window_s=60.0,
        silence_s=30.0,
        stability_s=60.0,
    )


def _assert_system_alive(sm: RuntimeStateMachine, label: str) -> None:
    """Le système est DEGRADED ou mieux — jamais SAFE_MODE sur un seul kill."""
    assert (
        sm.state != SystemState.SAFE_MODE
    ), f"INVARIANT BRISÉ [{label}]: un seul kill module ne doit pas entrer en SAFE_MODE"
    snap = sm.snapshot()
    assert snap["state"] in (
        "NORMAL",
        "DEGRADED",
        "RECOVERY",
    ), f"INVARIANT BRISÉ [{label}]: état inattendu {snap['state']}"


# ── Scénario 1 : Telegram DOWN ────────────────────────────────────────────────


class TestTelegramDown:
    """DASHBOARD zone : trading et décisions non impactés."""

    def test_trading_continues_when_telegram_down(self):
        sm = _sm_paper()
        guard = ContainmentGuard(sm)

        def telegram_send(*_):
            raise ConnectionError("Telegram: connection refused")

        # 5 pannes Telegram (zone DASHBOARD)
        for _ in range(5):
            guard.run(Zone.DASHBOARD, telegram_send, fallback=None)

        _assert_system_alive(sm, "Telegram DOWN")
        assert (
            sm.can_trade
        ), "INVARIANT BRISÉ: Telegram down ne doit pas bloquer le trading"

    def test_telegram_down_does_not_block_execution_zone(self):
        sm = _sm_paper()
        guard = ContainmentGuard(sm)

        # Pannes Telegram jusqu'au bord de DEGRADED
        for _ in range(6):
            guard.run(Zone.DASHBOARD, lambda: 1 / 0, fallback=None)

        # La zone EXECUTION reste fonctionnelle
        result = guard.run(Zone.EXECUTION, lambda: "order_ok", fallback="rejected")
        assert (
            result == "order_ok"
        ), "INVARIANT BRISÉ: panne DASHBOARD ne doit pas bloquer EXECUTION"

    def test_telegram_down_decision_still_produced(self):
        sm = _sm_paper()
        guard = ContainmentGuard(sm)

        # Telegram crashe
        for _ in range(3):
            guard.run(
                Zone.DASHBOARD,
                lambda: (_ for _ in ()).throw(RuntimeError("tg down")),
                fallback=None,
            )

        # Le système produit toujours un signal
        signal = guard.run(Zone.AI_SCORING, lambda: "BUY", fallback="HOLD")
        assert signal in (
            "BUY",
            "SELL",
            "HOLD",
        ), "Le système doit toujours produire une décision"


# ── Scénario 2 : RegimeEngine timeout ─────────────────────────────────────────


class TestRegimeEngineTimeout:
    """AI_SCORING timeout → fallback 'neutral', size_factor réduit si DEGRADED."""

    def test_fallback_neutral_on_regime_timeout(self):
        sm = _sm_paper()
        guard = ContainmentGuard(sm)

        def slow_regime():
            time.sleep(2.0)  # bien au-dessus du timeout AI_SCORING (0.5s)
            return "bull"

        regime = guard.run(
            Zone.AI_SCORING, slow_regime, timeout_s=0.05, fallback="neutral"
        )
        assert (
            regime == "neutral"
        ), "INVARIANT BRISÉ: timeout RegimeEngine doit retourner fallback 'neutral'"

    def test_regime_timeout_escalates_to_degraded(self):
        sm = _sm_paper()
        guard = ContainmentGuard(sm)

        def slow_regime():
            time.sleep(2.0)

        # 3 timeouts → seuil DEGRADED
        for _ in range(3):
            guard.run(Zone.AI_SCORING, slow_regime, timeout_s=0.05, fallback="neutral")

        assert (
            sm.state == SystemState.DEGRADED
        ), f"INVARIANT BRISÉ: 3 timeouts RegimeEngine → {sm.state}, attendu DEGRADED"

    def test_degraded_size_factor_halved(self):
        sm = _sm_paper()

        # Forcer DEGRADED directement
        for _ in range(3):
            sm.report_error("regime_timeout")

        assert (
            sm.size_factor == 0.5
        ), f"INVARIANT BRISÉ: size_factor DEGRADED = {sm.size_factor}, attendu 0.5"
        assert (
            sm.can_trade is True
        ), "DEGRADED doit toujours permettre le trading (taille réduite)"

    def test_regime_timeout_no_crash(self):
        sm = _sm_paper()
        guard = ContainmentGuard(sm)

        try:
            for _ in range(5):
                guard.run(
                    Zone.AI_SCORING,
                    lambda: time.sleep(2),
                    timeout_s=0.05,
                    fallback="neutral",
                )
        except Exception as exc:
            pytest.fail(f"CRASH SILENCIEUX: RegimeEngine timeout a levé {exc}")


# ── Scénario 3 : Redis DOWN ───────────────────────────────────────────────────


class TestRedisDown:
    """MONITORING zone : cache désactivé, exécution directe continue."""

    def test_execution_continues_without_redis(self):
        sm = _sm_paper()
        guard = ContainmentGuard(sm)

        def redis_get(*_):
            raise ConnectionRefusedError("Redis: connection refused")

        # Redis crashe à chaque accès cache
        for _ in range(4):
            guard.run(Zone.MONITORING, redis_get, fallback=None)

        # L'exécution tourne toujours directement
        result = guard.run(Zone.EXECUTION, lambda: "direct_read_ok", fallback="error")
        assert (
            result == "direct_read_ok"
        ), "INVARIANT BRISÉ: Redis down ne doit pas bloquer l'exécution directe"

    def test_redis_down_max_degraded_not_safe_mode(self):
        sm = _sm_paper()
        guard = ContainmentGuard(sm)

        def redis_fail():
            raise ConnectionRefusedError("Redis down")

        # 6 pannes Redis → DEGRADED ou CRITICAL mais pas SAFE_MODE (seuil=10)
        for _ in range(6):
            guard.run(Zone.MONITORING, redis_fail, fallback=None)

        assert (
            sm.state != SystemState.SAFE_MODE
        ), "INVARIANT BRISÉ: 6 pannes Redis seules ne doivent pas entrer en SAFE_MODE"

    def test_cache_miss_fallback_to_direct(self):
        sm = _sm_paper()
        guard = ContainmentGuard(sm)

        # Cache miss → retour valeur directe
        cache_result = guard.run(
            Zone.MONITORING,
            lambda: (_ for _ in ()).throw(KeyError("cache_miss")),
            fallback="direct_value",
        )
        assert (
            cache_result == "direct_value"
        ), "Cache miss doit retourner la valeur directe sans crash"


# ── Scénario 4 : Binance WebSocket freeze ─────────────────────────────────────


class TestBinanceWsFreeze:
    """Exchange offline / WS freeze → état DEGRADED, polling fallback."""

    def test_ws_freeze_triggers_degraded(self):
        sm = _sm_paper()

        # 3 erreurs WS → DEGRADED
        for _ in range(3):
            sm.report_error("ws_freeze")

        assert (
            sm.state == SystemState.DEGRADED
        ), f"INVARIANT BRISÉ: 3 ws_freeze → état {sm.state}, attendu DEGRADED"

    def test_polling_fallback_still_returns_decision(self):
        sm = _sm_paper()
        guard = ContainmentGuard(sm)

        def ws_receive():
            raise TimeoutError("WebSocket: connection timed out")

        # WS freeze
        for _ in range(3):
            guard.run(Zone.MONITORING, ws_receive, fallback=None)

        # Polling fallback (REST API simulée)
        price_rest = guard.run(Zone.AI_SCORING, lambda: 65_000.0, fallback=0.0)
        assert price_rest == 65_000.0, "Polling REST doit retourner un prix valide"
        assert (
            sm.state != SystemState.SAFE_MODE
        ), "WS freeze seul ne doit pas entrer en SAFE_MODE"

    def test_ws_freeze_fault_type_tracked(self):
        sm = _sm_paper()
        for _ in range(4):
            sm.report_error("ws_freeze")

        assert (
            sm.fault_counts.get("ws_freeze", 0) == 4
        ), "Le fault_count ws_freeze doit être tracké correctement"

    def test_system_snapshot_shows_degraded_not_down(self):
        sm = _sm_paper()
        for _ in range(3):
            sm.report_error("exchange_offline")

        snap = sm.snapshot()
        assert snap["state"] in (
            "DEGRADED",
            "CRITICAL",
        ), f"Snapshot doit afficher 'degraded' ou 'critical', pas '{snap['state']}'"
        # Vérifie la sémantique de l'endpoint /health
        status = snap["state"].lower()
        assert status != "down", "Le statut ne doit jamais être 'down'"
        assert status in ("degraded", "critical", "normal", "safe_mode", "recovery")


# ── Scénario 5 : Signal confidence invalide ───────────────────────────────────


class TestSignalConfidenceInvalid:
    """Signal invalide → HOLD retourné, pas de trade, pas de crash."""

    def _validate_signal(self, signal: str) -> bool:
        """Retourne True si le signal est valide et exploitable."""
        if signal not in ("BUY", "SELL", "HOLD"):
            return False
        return True

    def test_invalid_signal_returns_hold(self):
        sm = _sm_paper()
        guard = ContainmentGuard(sm)

        def bad_signal_engine():
            return float("nan")  # confidence invalide → NaN

        raw = guard.run(Zone.AI_SCORING, bad_signal_engine, fallback="HOLD")
        # Si NaN reçu → fallback ou validation → HOLD
        final_signal = raw if self._validate_signal(raw) else "HOLD"
        assert (
            final_signal == "HOLD"
        ), "INVARIANT BRISÉ: signal invalide doit produire HOLD"

    def test_invalid_signal_no_crash(self):
        sm = _sm_paper()
        guard = ContainmentGuard(sm)

        def crashing_signal_engine():
            raise ValueError("confidence score out of range: -0.3")

        try:
            signal = guard.run(Zone.AI_SCORING, crashing_signal_engine, fallback="HOLD")
        except Exception as exc:
            pytest.fail(f"CRASH SILENCIEUX: signal invalide a levé {exc}")

        assert signal == "HOLD", "Crash du signal engine → HOLD systématique"

    def test_invalid_signal_escalates_state_machine(self):
        sm = _sm_paper()
        guard = ContainmentGuard(sm)

        def crash():
            raise RuntimeError("invalid confidence")

        # 3 erreurs signal
        for _ in range(3):
            guard.run(Zone.AI_SCORING, crash, fallback="HOLD")

        assert (
            sm.state == SystemState.DEGRADED
        ), f"3 erreurs signal → attendu DEGRADED, obtenu {sm.state}"
        assert (
            sm.can_trade is True
        ), "DEGRADED permet encore le trading (taille réduite)"

    def test_none_signal_handled(self):
        sm = _sm_paper()
        guard = ContainmentGuard(sm)

        def none_engine():
            return None

        raw = guard.run(Zone.AI_SCORING, none_engine, fallback="HOLD")
        final = raw if self._validate_signal(str(raw)) else "HOLD"
        assert final == "HOLD", "Signal None → HOLD sans crash"

    def test_partial_signal_object_handled(self):
        sm = _sm_paper()
        guard = ContainmentGuard(sm)

        def partial_engine():
            raise TypeError("missing field 'confidence_score'")

        signal = guard.run(Zone.AI_SCORING, partial_engine, fallback="HOLD")
        assert signal == "HOLD", "Signal partiel/corrompu → HOLD"


# ── Tests transversaux : décision produite dans tous les états ────────────────


class TestDecisionSurvival:
    """Après n'importe quel kill, le système produit toujours une décision."""

    @pytest.mark.parametrize(
        "fault_type,zone,n_errors",
        [
            ("telegram", Zone.DASHBOARD, 5),
            ("regime_timeout", Zone.AI_SCORING, 3),
            ("redis", Zone.MONITORING, 4),
            ("ws_freeze", Zone.MONITORING, 3),
            ("signal_invalid", Zone.AI_SCORING, 3),
        ],
    )
    def test_decision_produced_after_kill(self, fault_type, zone, n_errors):
        sm = _sm_paper()
        guard = ContainmentGuard(sm)

        for _ in range(n_errors):
            guard.run(
                zone,
                lambda: (_ for _ in ()).throw(RuntimeError(fault_type)),
                fallback=None,
            )

        # Le système doit encore produire une décision (HOLD au minimum)
        decision = guard.run(Zone.AI_SCORING, lambda: "HOLD", fallback="HOLD")
        assert decision in (
            "BUY",
            "SELL",
            "HOLD",
        ), f"INVARIANT BRISÉ [{fault_type}]: aucune décision produite après kill"

        # L'état ne doit pas être SAFE_MODE (un seul kill ne suffit pas)
        _assert_system_alive(sm, fault_type)
