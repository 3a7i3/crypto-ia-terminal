"""
tests/stress/test_d07_fuzz_testing.py — D-07 Continuous Fuzz Testing

Test aléatoire continu des composants critiques.
Aucun crash, aucune exception non capturée en 10 000+ itérations.

Cibles :
  Entrées API (symboles invalides, prix aberrants, timeframes inconnus)
  Fichiers JSON (snapshots corrompus, clés manquantes, types incorrects)
  Arguments de fonction (None, vide, négatif, infini, NaN)

Total : 10 tests
"""

from __future__ import annotations

import json
import math
import random
import string
import time
from typing import Any

import pytest

SEED = 2026
_RNG = random.Random(SEED)

# ── Générateurs aléatoires ─────────────────────────────────────────────────────


def _rand_symbol() -> str:
    choices = [
        "BTC/USDT",
        "ETH/USDT",
        "",
        None,
        "INVALID",
        "X" * 200,
        "BTC/BTC/USDT",
        "123/456",
        "!@#/$%^",
        "\x00\xff",
        "SOL/USDT",
        "A/B",
    ]
    return _RNG.choice(choices)


def _rand_price() -> Any:
    choices = [
        50000.0,
        0.0,
        -100.0,
        float("inf"),
        float("-inf"),
        float("nan"),
        1e308,
        -1e308,
        0.000001,
        None,
        "not_a_price",
        [],
        {},
    ]
    return _RNG.choice(choices)


def _rand_snapshot() -> dict:
    """Snapshot aléatoire — valeurs valides ou corrompues."""

    def rand_float(lo=-1e6, hi=1e6):
        choices = [
            _RNG.uniform(lo, hi),
            float("nan"),
            float("inf"),
            None,
            "bad",
            -999,
        ]
        return _RNG.choice(choices)

    def rand_bool():
        return _RNG.choice([True, False, None, 0, 1, "yes"])

    return {
        "capital_total": rand_float(0, 100_000),
        "symbols_ready": _RNG.choice([-10, 0, 50, 100, 200, None, "x"]),
        "symbols_total": _RNG.choice([0, 1, 100, None]),
        "avg_feature_confidence": rand_float(-1, 2),
        "regime_stability": rand_float(-1, 2),
        "regime_last_updated_ts": _RNG.choice(
            [
                time.time(),
                time.time() - 3600,
                0,
                -1,
                None,
                "bad",
            ]
        ),
        "risk_sync": rand_bool(),
        "hard_limits_ok": rand_bool(),
        "probation_consistent": rand_bool(),
        "evolution_memory_loaded": rand_bool(),
        "transition_cache_populated": rand_bool(),
        "open_positions_unknown": rand_bool(),
        "kill_switch_safe_mode": rand_bool(),
        "anomaly_count": _RNG.choice([-5, 0, 3, 100, None]),
        "dwe_sample_coverage": rand_float(-1, 2),
        "strategy_weights": _RNG.choice([{}, None, "bad", {"x": -1}]),
    }


def _rand_json_string() -> str:
    """Chaîne JSON potentiellement invalide."""
    choices = [
        "{}",
        '{"key": "value"}',
        '{"key": null}',
        "{invalid}",
        '{"a": [1,2,3}',
        "",
        "null",
        "[]",
        '{"nested": {"deep": {"x": 1}}}',
        "X" * 1000,
        '{"key": ' + "1" * 1000 + "}",
    ]
    return _RNG.choice(choices)


# ── §1 : Fuzz WarmupInvariants ────────────────────────────────────────────────


class TestFuzzWarmupInvariants:
    def test_fuzz_invariants_no_crash_10k(self):
        """10 000 snapshots aléatoires → WarmupInvariants ne crash jamais."""
        from cold_start.warmup_invariants import WarmupInvariants

        inv = WarmupInvariants()
        _RNG.seed(SEED)
        errors = []
        for i in range(10_000):
            snap = _rand_snapshot()
            try:
                results, critical_fail = inv.check("BOOTING", snap)
                assert isinstance(results, list)
                assert isinstance(critical_fail, bool)
            except Exception as e:
                errors.append((i, type(e).__name__, str(e)[:80]))
        assert len(errors) == 0, f"Crashes invariants: {errors[:5]}"

    def test_fuzz_individual_invariants_no_crash(self):
        """Chaque invariant individuel → aucun crash sur entrée aléatoire."""
        from cold_start.warmup_invariants import (
            inv_capital_not_negative,
            inv_hard_limits_not_breached,
            inv_kill_switch_not_active,
            inv_no_unknown_positions,
        )

        fns = [
            inv_capital_not_negative,
            inv_no_unknown_positions,
            inv_hard_limits_not_breached,
            inv_kill_switch_not_active,
        ]
        _RNG.seed(SEED + 1)
        errors = []
        for i in range(2_500):
            snap = _rand_snapshot()
            for fn in fns:
                try:
                    result = fn(snap)
                    assert hasattr(result, "passed")
                except Exception as e:
                    errors.append((fn.__name__, type(e).__name__, str(e)[:60]))
        assert len(errors) == 0, f"Crashes: {errors[:5]}"


# ── §2 : Fuzz ColdStartManager ────────────────────────────────────────────────


class TestFuzzColdStartManager:
    def test_fuzz_cold_start_tick_no_crash_1k(self):
        """1 000 snapshots aléatoires → tick() ne crash jamais."""
        import cold_start.cold_start_manager as _csm_module
        from cold_start.cold_start_manager import ColdStartManager
        from cold_start.warmup_state_machine import WarmupState

        _csm_module._SHADOW_VALIDATION_CYCLES = 2
        _RNG.seed(SEED + 2)
        errors = []
        for i in range(1_000):
            cs = ColdStartManager()
            snap = _rand_snapshot()
            try:
                state = cs.tick(snap)
                assert isinstance(state, WarmupState)
            except Exception as e:
                errors.append((i, type(e).__name__, str(e)[:80]))
        _csm_module._SHADOW_VALIDATION_CYCLES = 10
        assert len(errors) == 0, f"Crashes ColdStartManager: {errors[:5]}"


# ── §3 : Fuzz DecisionPacket ──────────────────────────────────────────────────


class TestFuzzDecisionPacket:
    def test_fuzz_from_dict_no_crash_1k(self):
        """1 000 dicts aléatoires → from_dict() ne crash jamais (sauf ValueError attendu)."""
        from core.decision_packet import DecisionPacket

        _RNG.seed(SEED + 3)
        errors = []
        for i in range(1_000):
            d: dict = {}
            # Mélanger les champs valides et invalides
            if _RNG.random() > 0.5:
                d["symbol"] = _rand_symbol()
            if _RNG.random() > 0.5:
                d["side"] = _RNG.choice(["LONG", "SHORT", "FLAT", "BAD", None, 42])
            if _RNG.random() > 0.5:
                d["confidence"] = _rand_price()
            if _RNG.random() > 0.5:
                d["lifecycle_state"] = _RNG.choice(["CREATED", "EXECUTED", "BAD"])
            try:
                p = DecisionPacket.from_dict(d)
                assert p is not None
            except (ValueError, KeyError, TypeError):
                pass  # exceptions attendues sur input invalide
            except Exception as e:
                errors.append((i, type(e).__name__, str(e)[:80]))
        assert len(errors) == 0, f"Crashes inattendus: {errors[:5]}"

    def test_fuzz_to_dict_no_crash(self):
        """to_dict() sur un packet valide ne doit jamais crasher."""
        from core.decision_packet import DecisionPacket, DecisionSide, MarketRegime

        _RNG.seed(SEED + 4)
        for _ in range(500):
            p = DecisionPacket(
                symbol=str(_RNG.choice(["BTC/USDT", "ETH/USDT", ""])),
                confidence=float(_RNG.uniform(0, 100)),
            )
            d = p.to_dict()
            assert "packet_id" in d
            assert "lifecycle_state" in d


# ── §4 : Fuzz BlackBoxEncryption ─────────────────────────────────────────────


class TestFuzzBlackBoxEncryption:
    def test_fuzz_encrypt_any_bytes_no_crash(self):
        """Chiffrer des bytes aléatoires → aucun crash."""
        from crypto.blackbox_encryption import BlackBoxEncryption

        enc = BlackBoxEncryption(master_secret=b"fuzz_key")
        _RNG.seed(SEED + 5)
        errors = []
        for i in range(500):
            size = _RNG.randint(0, 4096)
            data = bytes(_RNG.randint(0, 255) for _ in range(size))
            try:
                blob = enc.encrypt(data)
                result = enc.decrypt(blob)
                assert result == data
            except Exception as e:
                errors.append((i, type(e).__name__, str(e)[:80]))
        assert len(errors) == 0, f"Crashes: {errors[:5]}"

    def test_fuzz_decrypt_garbage_always_raises(self):
        """Déchiffrer du garbage → doit toujours lever une exception (pas crash silencieux)."""
        from crypto.blackbox_encryption import BlackBoxEncryption

        enc = BlackBoxEncryption(master_secret=b"fuzz_key")
        _RNG.seed(SEED + 6)
        raised = 0
        for _ in range(200):
            size = _RNG.randint(28, 512)
            garbage = bytes(_RNG.randint(0, 255) for _ in range(size))
            try:
                enc.decrypt(garbage)
                # Si pas d'exception → le tag a accidentellement matchà (très improbable)
            except Exception:
                raised += 1
        # Au moins 95% des décryptages de garbage doivent lever une exception
        assert raised >= 190, f"Trop peu d'exceptions sur garbage: {raised}/200"


# ── §5 : Fuzz JSON files ──────────────────────────────────────────────────────


class TestFuzzJSONFiles:
    def test_fuzz_json_parse_no_unhandled_crash(self):
        """Parsing de JSON aléatoire → seul JSONDecodeError est acceptable."""
        _RNG.seed(SEED + 7)
        errors = []
        for i in range(2_000):
            s = _rand_json_string()
            try:
                json.loads(s)
            except json.JSONDecodeError:
                pass  # attendu
            except Exception as e:
                errors.append((i, type(e).__name__, str(e)[:60]))
        assert len(errors) == 0, f"Exceptions inattendues: {errors[:5]}"

    def test_fuzz_audit_trail_append_no_crash(self):
        """AuditTrail.append() avec données aléatoires → aucun crash."""
        import tempfile

        from crypto.audit_trail import AuditTrail

        _RNG.seed(SEED + 8)
        errors = []
        with tempfile.TemporaryDirectory() as td:
            trail = AuditTrail(trail_path=__import__("pathlib").Path(td) / "t.jsonl")
            for i in range(500):
                event = _RNG.choice(["TRADE", "", None, "X" * 100, 42])
                data = _RNG.choice([{}, None, {"x": float("nan")}, {"k": None}])
                try:
                    if event is not None:
                        trail.append(str(event), data if isinstance(data, dict) else {})
                except Exception as e:
                    errors.append((i, type(e).__name__, str(e)[:80]))
        assert len(errors) == 0, f"Crashes AuditTrail: {errors[:5]}"
