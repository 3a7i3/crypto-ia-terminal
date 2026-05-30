"""
Tests des 12 invariants système — Phase 4.

Chaque test valide qu'un garde-fou est effectivement actif.
Référence: docs/SYSTEM_INVARIANTS.md
"""

from __future__ import annotations

import json
import time

import pytest

# ── I-01 ─────────────────────────────────────────────────────────────────────


def test_i01_size_zero_auto_healed():
    """I-01: size=0 → alert critique + auto-heal à 1.0 (jamais envoyé avec size=0)."""
    from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

    engine = ExecutionEngine(live=False)
    result = engine.create_order("BTC/USDT", "BUY", size=0.0)
    # L'invariant garantit que size=0 n'est JAMAIS envoyé tel quel à l'exchange
    assert (
        result.get("size", 0.0) != 0.0
    ), f"size=0 ne doit pas être transmis tel quel: {result}"


def test_i01_negative_size_auto_healed():
    """I-01 bis: size négative → auto-heal (jamais transmise négative)."""
    from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

    engine = ExecutionEngine(live=False)
    result = engine.create_order("ETH/USDT", "SELL", size=-50.0)
    assert (
        result.get("size", 0.0) >= 0.0
    ), f"size négative ne doit pas être transmise: {result}"


# ── I-02 ─────────────────────────────────────────────────────────────────────


def test_i02_session_halt_on_drawdown():
    """I-02: drawdown > seuil → SessionHaltedError sur la prochaine order."""
    from quant_hedge_ai.agents.risk.session_guard import (
        SessionGuard,
        SessionHaltedError,
    )

    guard = SessionGuard(max_session_drawdown=0.05)
    guard.start_session(equity=1000.0)
    # Drawdown de 10% (> 5% limite)
    guard.record_trade(pnl=-100.0, equity=900.0)

    assert guard.is_halted, "SessionGuard doit être halted après 10% drawdown"
    with pytest.raises(SessionHaltedError):
        guard.check_order("BTC/USDT", "BUY", size_usd=100.0)


# ── I-03 ─────────────────────────────────────────────────────────────────────


def test_i03_session_halt_on_consecutive_losses():
    """I-03: N pertes consécutives > max_consecutive_losses → halt."""
    from quant_hedge_ai.agents.risk.session_guard import (
        SessionGuard,
        SessionHaltedError,
    )

    guard = SessionGuard(max_consecutive_losses=3, max_session_drawdown=1.0)
    guard.start_session(equity=10_000.0)

    # 3 pertes consécutives légères (< drawdown limit)
    for i in range(3):
        guard.record_trade(pnl=-1.0, equity=9_997.0 - i)

    assert guard.is_halted, "Doit être halted après 3 pertes consécutives"
    with pytest.raises(SessionHaltedError):
        guard.check_order("BTC/USDT", "BUY", size_usd=50.0)


# ── I-04 ─────────────────────────────────────────────────────────────────────


def test_i04_duplicate_order_blocked(tmp_path, monkeypatch):
    """I-04: même ordre dans la fenêtre → OrderDeduplicator bloque."""
    monkeypatch.setenv("EXEC_MAX_ORDER_USD", "10000")
    monkeypatch.setenv("EXEC_TRADE_LOG", str(tmp_path / "trades.sqlite"))
    from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

    engine = ExecutionEngine(live=False)
    # Premier ordre: doit passer
    r1 = engine.create_order("BTC/USDT", "BUY", size=100.0)
    assert r1["mode"] != "rejected", f"Premier ordre doit passer, obtenu: {r1}"

    # Deuxième ordre identique immédiat: doit être bloqué
    r2 = engine.create_order("BTC/USDT", "BUY", size=100.0)
    assert r2["mode"] == "rejected", f"Doublon doit être rejeté, obtenu: {r2}"
    assert "duplicate" in r2.get("error", "").lower()


# ── I-05 ─────────────────────────────────────────────────────────────────────


def test_i05_cache_stale_returns_none(tmp_path, monkeypatch):
    """I-05: cache avec timestamp ancien → load_config() retourne None."""
    from startup_cache import StartupCache

    stale_file = tmp_path / "configs.json"
    stale_data = {
        "timestamp": time.time() - 7200,  # 2h dans le passé
        "config": {"key": "value"},
    }
    stale_file.write_text(json.dumps(stale_data))

    cache = StartupCache()
    monkeypatch.setattr(cache, "CONFIG_CACHE", stale_file)

    result = cache.load_config(max_age_seconds=3600)  # TTL 1h
    assert result is None, "Cache périmé doit retourner None"


def test_i05_fresh_cache_returned(tmp_path, monkeypatch):
    """I-05 bis: cache frais → load_config() retourne les données."""
    from startup_cache import StartupCache

    fresh_file = tmp_path / "configs.json"
    fresh_data = {
        "timestamp": time.time() - 10,  # 10s dans le passé
        "config": {"key": "value"},
    }
    fresh_file.write_text(json.dumps(fresh_data))

    cache = StartupCache()
    monkeypatch.setattr(cache, "CONFIG_CACHE", fresh_file)

    result = cache.load_config(max_age_seconds=3600)
    assert result == {"key": "value"}, f"Cache frais doit être retourné: {result}"


# ── I-06 ─────────────────────────────────────────────────────────────────────


def test_i06_signal_timestamp_always_set():
    """I-06: SignalResult() a toujours un timestamp > 0."""
    from quant_hedge_ai.agents.execution.live_signal_engine import SignalResult

    sig = SignalResult(symbol="BTC/USDT", signal="BUY", score=75)
    assert sig.timestamp > 0, f"timestamp doit être > 0, obtenu: {sig.timestamp}"
    assert isinstance(sig.timestamp, float)


def test_i06_signal_timestamp_is_recent():
    """I-06 bis: timestamp généré maintenant (delta < 1s)."""
    from quant_hedge_ai.agents.execution.live_signal_engine import SignalResult

    before = time.time()
    sig = SignalResult(symbol="ETH/USDT", signal="HOLD", score=50)
    after = time.time()
    assert before <= sig.timestamp <= after + 0.1


# ── I-07 ─────────────────────────────────────────────────────────────────────


def test_i07_gate_blocked_result_is_not_allowed():
    """I-07: GlobalRiskGateResult avec allowed=False reflète le blocage."""
    from core.contracts import GlobalRiskGateResult

    result = GlobalRiskGateResult(
        allowed=False,
        failed=["min_score", "drawdown"],
        score=20.0,
    )
    assert not result.allowed
    assert "min_score" in result.failed
    assert "drawdown" in result.failed


def test_i07_gate_allowed_requires_no_failures():
    """I-07 bis: gate allowed=True doit avoir une liste failed vide."""
    from core.contracts import GlobalRiskGateResult

    result = GlobalRiskGateResult(allowed=True, score=85.0)
    assert result.allowed
    assert result.failed == []


# ── I-08 ─────────────────────────────────────────────────────────────────────


def test_i08_veto_vote_blocks_decision():
    """I-08: un AgentVote(veto=True) → REJECT indépendamment des autres votes."""
    from quant_hedge_ai.agents.intelligence.decision_arbitrator import (
        AgentVote,
        ArbitrationDecision,
        DecisionArbitrator,
    )

    arb = DecisionArbitrator()
    votes = [
        AgentVote("regime", score=0.9),
        AgentVote("signal", score=0.8),
        AgentVote("executive_override", score=-1.0, veto=True),  # VETO
    ]
    result = arb.arbitrate(votes)
    assert (
        result.decision == ArbitrationDecision.REJECT
    ), f"VETO doit produire REJECT, obtenu: {result.decision}"
    assert "executive_override" in result.veto_agents


def test_i08_no_veto_allows_decision():
    """I-08 bis: sans veto, décision positive possible."""
    from quant_hedge_ai.agents.intelligence.decision_arbitrator import (
        AgentVote,
        ArbitrationDecision,
        DecisionArbitrator,
    )

    arb = DecisionArbitrator()
    votes = [
        AgentVote("regime", score=0.9),
        AgentVote("signal", score=0.85),
        AgentVote("risk_gate", score=0.8),
    ]
    result = arb.arbitrate(votes)
    assert result.decision != ArbitrationDecision.REJECT
    assert result.veto_agents == []


# ── I-09 ─────────────────────────────────────────────────────────────────────


def test_i09_order_sizer_output_clamped():
    """I-09: OrderSizer respecte toujours [min_size, max_size]."""
    from quant_hedge_ai.agents.risk.order_sizer import OrderSizer

    sizer = OrderSizer(
        kelly_fraction=0.25,
        min_size_usd=10.0,
        max_size_usd=500.0,
    )

    # Capital très faible → clampé au minimum
    result_min = sizer.compute(
        capital=50.0, win_rate=0.5, avg_win_pct=0.02, avg_loss_pct=0.01, price=100.0
    )
    assert (
        result_min.size_usd >= 10.0
    ), f"Taille doit être >= min (10): {result_min.size_usd}"

    # Capital énorme → clampé au maximum
    result_max = sizer.compute(
        capital=100_000.0, win_rate=0.9, avg_win_pct=0.5, avg_loss_pct=0.1, price=100.0
    )
    assert (
        result_max.size_usd <= 500.0
    ), f"Taille doit être <= max (500): {result_max.size_usd}"


# ── I-10 ─────────────────────────────────────────────────────────────────────


def test_i10_drawdown_guard_floor():
    """I-10: DrawdownGuard.adjust_position_size() ne retourne jamais < 0.1."""
    from quant_hedge_ai.agents.risk.drawdown_guard import DrawdownGuard

    guard = DrawdownGuard()

    for drawdown in [0.0, 0.2, 0.5, 0.9, 1.0, 10.0]:
        factor = guard.adjust_position_size(drawdown, base_size=1.0)
        assert (
            factor >= 0.1
        ), f"Factor doit être >= 0.1 pour drawdown={drawdown}, obtenu: {factor}"


def test_i10_drawdown_zero_returns_full():
    """I-10 bis: drawdown=0 → factor = base_size."""
    from quant_hedge_ai.agents.risk.drawdown_guard import DrawdownGuard

    guard = DrawdownGuard()
    assert guard.adjust_position_size(0.0, base_size=1.0) == 1.0


# ── I-11 ─────────────────────────────────────────────────────────────────────


def test_i11_trace_id_generated_unique():
    """I-11: new_trace_id() retourne des strings non-vides et uniques."""
    from observability.json_logger import new_trace_id

    ids = {new_trace_id() for _ in range(10)}
    assert len(ids) == 10, "Chaque trace_id doit être unique"
    for tid in ids:
        assert isinstance(tid, str) and len(tid) > 0, f"trace_id invalide: {tid!r}"


def test_i11_trace_id_not_empty():
    """I-11 bis: trace_id n'est jamais vide ou None."""
    from observability.json_logger import new_trace_id

    tid = new_trace_id()
    assert tid is not None
    assert tid != ""
    assert tid.strip() != ""


# ── I-12 ─────────────────────────────────────────────────────────────────────


def test_i12_oversized_order_rejected():
    """I-12: ordre > max_order_usd → mode='rejected' (OrderTooLargeError)."""
    from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

    engine = ExecutionEngine(live=False)
    # EXEC_MAX_ORDER_USD default = 10_000, forcer via guard direct
    engine._guard._max_order_usd = 100.0  # limite à 100 USD pour le test

    result = engine.create_order("BTC/USDT", "BUY", size=500.0)
    assert result["mode"] == "rejected", f"Ordre oversized doit être rejeté: {result}"
    assert "error" in result


def test_i12_normal_order_passes():
    """I-12 bis: ordre dans les limites → pas rejeté pour taille."""
    from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine

    engine = ExecutionEngine(live=False)
    # Taille normale (100 USD << default 10_000 USD max)
    result = engine.create_order("BTC/USDT", "BUY", size=100.0)
    # Ne doit pas être rejeté pour raison de taille
    if result["mode"] == "rejected":
        assert (
            "oversized" not in result.get("error", "").lower()
        ), f"Ordre normal ne doit pas être rejeté pour taille: {result}"
