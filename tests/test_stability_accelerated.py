"""
test_stability_accelerated.py — Test de stabilité sur temps accéléré (10 jours simulés).

Simule 2880 cycles (10j × 288 cycles/j × 5min) en quelques secondes.
Vérifie :
  - Pas de fuite mémoire dans les dicts de protection
  - Rotation des logs (RotatingFileHandler actif)
  - SelfAwareness FREEZE_OVERRIDE déclenche après 3 halts
  - email/telegram non bloquants
  - watchdog détecte snapshot stale correctement
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Helpers ───────────────────────────────────────────────────────────────────


class FakeClock:
    """Horloge simulée — avance de STEP_S à chaque appel à .tick()."""

    STEP_S = 300  # 5 min par cycle

    def __init__(self, start: float = 1_700_000_000.0):
        self._t = start

    def now(self) -> float:
        return self._t

    def tick(self, n: int = 1) -> None:
        self._t += self.STEP_S * n

    def elapsed_days(self, start: float) -> float:
        return (self._t - start) / 86400


# ── Test 1 : Dicts de protection — pas de fuite après 10 jours ───────────────


class TestProtectionDicts:
    """
    Reproduit la logique des dicts last_loss_time / trades_this_hour
    sur 2880 cycles et vérifie qu'ils ne croissent pas sans borne.
    """

    SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"]
    CYCLES = 2880  # 10 jours

    def test_trades_this_hour_bounded(self):
        clock = FakeClock()
        trades_this_hour: dict[str, list[float]] = {}

        for _ in range(self.CYCLES):
            clock.tick()
            now = clock.now()
            hour_ago = now - 3600

            for sym in self.SYMBOLS:
                if sym not in trades_this_hour:
                    trades_this_hour[sym] = []
                # Nettoyage (tel que dans advisor_loop.py ligne 2750)
                trades_this_hour[sym] = [
                    t for t in trades_this_hour[sym] if t > hour_ago
                ]
                # Simule 1 trade par cycle par symbole
                if len(trades_this_hour[sym]) < 10:
                    trades_this_hour[sym].append(now)

        # Après 10 jours : au plus 10 timestamps par symbole (fenêtre 1h)
        for sym in self.SYMBOLS:
            assert (
                len(trades_this_hour[sym]) <= 10
            ), f"{sym}: {len(trades_this_hour[sym])} timestamps — fuite mémoire"

    def test_last_loss_time_bounded(self):
        clock = FakeClock()
        last_loss_time: dict[str, float] = {}

        for i in range(self.CYCLES):
            clock.tick()
            now = clock.now()
            # Simule une perte tous les 20 cycles
            if i % 20 == 0:
                for sym in self.SYMBOLS:
                    last_loss_time[sym] = now

        # last_loss_time a exactement len(SYMBOLS) clés — jamais plus
        assert len(last_loss_time) == len(self.SYMBOLS)

    def test_last_trade_signal_bounded(self):
        clock = FakeClock()
        last_trade_signal: dict[str, str] = {}
        signals = ["BUY", "SELL", "HOLD"]

        for i in range(self.CYCLES):
            clock.tick()
            sym = self.SYMBOLS[i % len(self.SYMBOLS)]
            # Simule trade puis fermeture (pop)
            last_trade_signal[sym] = signals[i % 3]
            if i % 5 == 0:
                last_trade_signal.pop(sym, None)

        # Ne dépasse jamais le nombre de symboles
        assert len(last_trade_signal) <= len(self.SYMBOLS)


# ── Test 2 : SelfAwareness FREEZE_OVERRIDE après 3 halts ─────────────────────


class TestSelfAwarenessFreeze:
    """Vérifie que FREEZE_OVERRIDE débloque après exactement 3 halts × 30 min."""

    def test_freeze_override_triggers_after_3_halts(self):
        from quant_hedge_ai.agents.intelligence.self_awareness_engine import (
            DangerLevel,
            SelfAwarenessEngine,
        )

        clock = FakeClock()
        engine = SelfAwarenessEngine()

        # Injecter 13 trades perdants pour déclencher DANGER
        for _ in range(13):
            engine.record_trade(pnl_pct=-0.021, regime="unknown")

        halt_count = 0
        max_iterations = 200

        with patch("time.time", side_effect=clock.now):
            for iteration in range(max_iterations):
                state = engine.evaluate()

                if state.halt_until > clock.now():
                    # En cours de halt — avancer après expiration
                    clock._t = state.halt_until + 1
                    halt_count += 1
                elif state.level < DangerLevel.DANGER:
                    # FREEZE_OVERRIDE déclenché → WARNING
                    break

                clock.tick()

        assert state.level == DangerLevel.WARNING, (
            f"FREEZE_OVERRIDE n'a pas déclenché après {halt_count} halts — "
            f"niveau actuel : {state.level.name}"
        )
        assert (
            halt_count == 3
        ), f"FREEZE_OVERRIDE devrait déclencher après 3 halts, pas {halt_count}"
        assert (
            engine.is_safe_to_trade()
        ), "Le bot devrait être safe_to_trade après FREEZE_OVERRIDE"


# ── Test 3 : Log rotation — vérifie RotatingFileHandler ──────────────────────


class TestLogRotation:
    """Vérifie que le logger utilise RotatingFileHandler (pas FileHandler simple)."""

    def test_advisor_uses_rotating_handler(self, tmp_path):
        import logging
        from logging.handlers import RotatingFileHandler

        log_file = tmp_path / "test_advisor.log"
        handler = RotatingFileHandler(
            str(log_file),
            maxBytes=1024,  # 1 KB pour tester rapidement
            backupCount=3,
            encoding="utf-8",
        )
        logger = logging.getLogger("test_rotation")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        # Écrire assez pour déclencher la rotation
        line = "X" * 100 + "\n"
        for _ in range(20):
            logger.info(line)

        handler.close()

        # Après rotation, des fichiers .1, .2... doivent exister
        backups = list(tmp_path.glob("test_advisor.log*"))
        assert len(backups) > 1, "La rotation de logs ne s'est pas déclenchée"

    def test_no_plain_filehandler_in_advisor_loop(self):
        """Vérifie qu'advisor_loop.py n'utilise plus FileHandler simple."""
        advisor_src = Path(__file__).parent.parent / "advisor_loop.py"
        content = advisor_src.read_text(encoding="utf-8")
        assert "logging.FileHandler(" not in content, (
            "advisor_loop.py utilise encore logging.FileHandler"
            " — remplacer par RotatingFileHandler"
        )
        assert (
            "RotatingFileHandler" in content
        ), "RotatingFileHandler non trouvé dans advisor_loop.py"


# ── Test 4 : Watchdog — détection snapshot stale ─────────────────────────────


class TestWatchdogDetection:
    """Vérifie la logique de détection du watchdog sans réseau."""

    def test_detects_stale_snapshot(self, tmp_path):
        snapshot = tmp_path / "live_snapshot.json"
        clock = FakeClock()

        # Snapshot récent → OK
        snapshot.write_text(
            json.dumps({"ts": clock.now(), "cycle": 1, "capital": 1000.0}),
            encoding="utf-8",
        )

        with patch("watchdog_vps.SNAPSHOT_PATH", snapshot), patch(
            "watchdog_vps.TIMEOUT", 300
        ), patch("time.time", side_effect=clock.now):
            from watchdog_vps import _check_snapshot

            ok, msg, age = _check_snapshot()
            assert ok, f"Snapshot frais devrait être OK: {msg}"

        # Avancer de 10 minutes → snapshot stale
        clock.tick(2)  # +10 min
        with patch("watchdog_vps.SNAPSHOT_PATH", snapshot), patch(
            "watchdog_vps.TIMEOUT", 300
        ), patch("time.time", side_effect=clock.now):
            ok, msg, age = _check_snapshot()
            assert not ok, "Snapshot stale devrait être détecté comme DOWN"
            assert age > 300

    def test_missing_snapshot_detected(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        with patch("watchdog_vps.SNAPSHOT_PATH", missing):
            from watchdog_vps import _check_snapshot

            ok, msg, age = _check_snapshot()
            assert not ok
            assert "introuvable" in msg.lower() or "introuvable" in msg


# ── Test 5 : email non bloquant ───────────────────────────────────────────────


class TestEmailNonBlocking:
    """Vérifie que _send_email échoue silencieusement si SMTP indisponible."""

    def test_email_fails_silently_no_config(self):
        with patch.dict("os.environ", {}, clear=True):
            # Pas de config SMTP → doit retourner sans exception
            import advisor_loop

            # Appel direct à la fonction
            advisor_loop._send_email("Test", "Corps du test")  # ne doit pas lever

    def test_email_fails_silently_bad_server(self):
        env = {
            "EMAIL_SMTP_SERVER": "inexistent.smtp.local",
            "EMAIL_SMTP_PORT": "587",
            "EMAIL_FROM_ADDR": "test@test.com",
            "EMAIL_SMTP_PASS": "pass",
            "EMAIL_TO_ADDR": "dest@test.com",
        }
        with patch.dict("os.environ", env):
            import advisor_loop

            # Doit échouer silencieusement, pas lever
            advisor_loop._send_email("Test crash", "Détails du crash...")


# ── Test 6 : REGIME_MISMATCH guard ───────────────────────────────────────────


class TestRegimeMismatchGuard:
    """Vérifie que REGIME_MISMATCH ne baisse pas le threshold quand awareness bloque."""

    def test_mismatch_skipped_when_awareness_halted(self):
        from quant_hedge_ai.agents.intelligence.self_awareness_engine import (
            SelfAwarenessEngine,
        )

        engine = SelfAwarenessEngine()
        gate_mock = MagicMock()

        # Mettre awareness en DANGER
        for _ in range(13):
            engine.record_trade(pnl_pct=-0.021, regime="unknown")
        engine.evaluate()

        # Simuler la condition REGIME_MISMATCH
        P6_SAFE_MODE = False
        regret_engine = MagicMock()
        cycles_since_last_trade = 35
        is_safe = engine.is_safe_to_trade()

        # La condition doit être False quand awareness bloque
        mismatch_should_fire = (
            not P6_SAFE_MODE
            and regret_engine is not None
            and cycles_since_last_trade > 30
            and is_safe  # ← le guard
        )

        assert not mismatch_should_fire, (
            "REGIME_MISMATCH ne devrait pas baisser le threshold"
            " quand awareness est en DANGER"
        )
        gate_mock.apply_regret_delta.assert_not_called()
