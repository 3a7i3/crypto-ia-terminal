"""
tests/test_strategy_memory_passivity.py — S-02B.1 : passivité de StrategyMemoryStore.

Forensique S-02B.1 (§9) : `StrategyMemoryStore.load_by_regime()` alimente,
via le fallback `memory_sharpe` d'`analyze_symbol()`, à la fois la sélection de
personnalité (`meta_engine.select`) et le signal lui-même
(`engine.evaluate(..., memory_sharpe=...)`) — donc décision-active. Cette
recommandation ne doit atteindre ces consommateurs que si
FEATURE_ADAPTIVE_DECISION_FEEDBACK est explicitement activé ; en mode passif,
`load_by_regime()` continue d'être appelée (observation/compteurs d'usage
préservés) mais son résultat n'est pas transmis à la décision.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))

from quant_hedge_ai.ai_evolution.strategy_memory import MemoryConfig, StrategyMemoryStore


# ── Layer 1 — StrategyMemoryStore isolée ─────────────────────────────────────


def _store(tmp_path: Path) -> StrategyMemoryStore:
    cfg = MemoryConfig(file_path=tmp_path / "strategy_memory.json")
    return StrategyMemoryStore(cfg)


class TestStrategyMemoryStoreProvenance:
    def test_state_provenance_empty_store(self, tmp_path):
        store = _store(tmp_path)
        prov = store.state_provenance()
        assert prov["subsystem"] == "StrategyMemoryStore"
        assert prov["regime_count"] == 0

    def test_state_provenance_reflects_regime_count(self, tmp_path):
        store = _store(tmp_path)
        store.save_for_regime(
            "bull_trend",
            [{"strategy": {"name": "s1"}, "sharpe": 1.5, "win_rate": 0.6, "pnl": 10}],
        )
        prov = store.state_provenance()
        assert prov["regime_count"] == 1
        assert prov["state_mtime"] is not None


# ── Layer 2 — Intégration advisor_loop.analyze_symbol() ─────────────────────


class _FakeMultiTimeframeScanner:
    @staticmethod
    def merge_base(mtf_data, symbol, candles_1h):
        return {}


class _FakeFeatureEngineer:
    def extract_features(self, candles):
        return {}


class _FakeRegimeDetector:
    def classify(self, features):
        return "unknown"


class _FakeConfidenceExplainer:
    def explain(self, signal):
        return None


class _FakeRuntime:
    MultiTimeframeScanner = _FakeMultiTimeframeScanner
    FeatureEngineer = _FakeFeatureEngineer
    AdvancedRegimeDetector = _FakeRegimeDetector
    ConfidenceExplainer = _FakeConfidenceExplainer


class _FakeScanner1h:
    last_stability: dict = {}

    def scan(self):
        return {}


class _FakeScannerMtf:
    def scan(self, cycle):
        return {}


class _FakeGate:
    def check(self, signal, portfolio_drawdown, order_size_usd):
        return SimpleNamespace(allowed=True, failed=[], reason=None)


class _FakeAdvisor:
    def explain(self, signal):
        return SimpleNamespace(risk_level="low", confidence="high", text="ok")


class _FakeShadow:
    pass


class _FakeWatchdog:
    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def measure(self, *_a, **_k):
        return self._Ctx()


class _FakeStrategyMemoryStoreWithCandidate:
    """load_by_regime() renvoie toujours une stratégie valide (sharpe=1.8)."""

    def __init__(self):
        self.calls = 0

    def load_by_regime(self, regime, limit=10):
        self.calls += 1
        return [{"strategy": {"name": "momentum_v1"}, "sharpe": 1.8}]

    def state_provenance(self):
        return {"subsystem": "StrategyMemoryStore", "regime_count": 1}


def _actionable_signal() -> SimpleNamespace:
    return SimpleNamespace(
        signal="BUY",
        score=80,
        actionable=True,
        confirmed=True,
        strength=1.0,
        timestamp=time.time(),
    )


def _run_analyze_symbol_capturing_memory_sharpe(memory, monkeypatch):
    import core.advisor_loop as advisor_loop

    monkeypatch.setattr(advisor_loop, "_cb_mistake_memory", None)

    from quant_hedge_ai.runtime.runtime_state_machine import RuntimeStateMachine
    from core.authority import init_authority, reset_authority

    rsm = RuntimeStateMachine()
    init_authority(rsm)
    captured: dict = {}
    try:

        def _fake_evaluate(symbol, mtf_candles, features=None, memory_sharpe=None):
            captured["memory_sharpe"] = memory_sharpe
            return _actionable_signal()

        scanners = {
            "1h": {"BTC/USDT": _FakeScanner1h()},
            "mtf": {"BTC/USDT": _FakeScannerMtf()},
        }
        engine = SimpleNamespace(evaluate=_fake_evaluate)
        advisor_loop.analyze_symbol(
            symbol="BTC/USDT",
            scanners=scanners,
            engine=engine,
            gate=_FakeGate(),
            advisor=_FakeAdvisor(),
            shadow=_FakeShadow(),
            watchdog=_FakeWatchdog(),
            memory=memory,
            cycle=1,
            runtime=_FakeRuntime(),
        )
    finally:
        reset_authority()
    return captured


class TestAdvisorLoopStrategyMemoryPassivity:
    def test_default_feedback_false_recommendation_not_transmitted(self, monkeypatch):
        import core.advisor_loop as advisor_loop

        assert advisor_loop.FEATURE_ADAPTIVE_DECISION_FEEDBACK is False
        memory = _FakeStrategyMemoryStoreWithCandidate()
        captured = _run_analyze_symbol_capturing_memory_sharpe(memory, monkeypatch)

        assert memory.calls == 1, "load_by_regime doit rester appelée (observation)"
        assert captured["memory_sharpe"] is None, (
            "S-02B.1 VIOLATION : la recommandation StrategyMemoryStore a atteint "
            "le signal alors que FEATURE_ADAPTIVE_DECISION_FEEDBACK=false"
        )

    def test_feedback_true_transmits_recommendation_legacy_behavior(self, monkeypatch):
        import core.advisor_loop as advisor_loop

        monkeypatch.setattr(advisor_loop, "FEATURE_ADAPTIVE_DECISION_FEEDBACK", True)
        memory = _FakeStrategyMemoryStoreWithCandidate()
        captured = _run_analyze_symbol_capturing_memory_sharpe(memory, monkeypatch)

        assert captured["memory_sharpe"] == 1.8
