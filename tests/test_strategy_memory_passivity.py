"""
tests/test_strategy_memory_passivity.py — S-02B.1 : passivité de StrategyMemoryStore.

Forensique S-02B.1 (§9) : `StrategyMemoryStore.load_by_regime()` alimente,
via le fallback `memory_sharpe` d'`analyze_symbol()`, à la fois la sélection de
personnalité (`meta_engine.select`) et le signal lui-même
(`engine.evaluate(..., memory_sharpe=...)`) — donc décision-active. Cette
recommandation ne doit atteindre ces consommateurs que si
FEATURE_ADAPTIVE_DECISION_FEEDBACK est explicitement activé.

Remédiation blocker 2 (revue indépendante post-#111) : `load_by_regime()`
incrémentait `usage_count` (et l'écrivait sur disque) à CHAQUE appel, y compris
en mode passif — une lecture contrefactuelle se faisait donc passer pour un
usage réel et biaisait le classement futur via `_rank_for_loading()`'s
usage_penalty. `load_by_regime(..., record_usage: bool = True)` sépare
maintenant la lecture/recommandation (toujours possible) de la comptabilité
d'usage (uniquement quand `record_usage=True`, câblé sur
FEATURE_ADAPTIVE_DECISION_FEEDBACK dans advisor_loop.py).
"""
from __future__ import annotations

import json
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


def _seed_one_strategy(store: StrategyMemoryStore, regime: str = "bull_trend") -> None:
    store.save_for_regime(
        regime,
        [{"strategy": {"name": "momentum_v1"}, "sharpe": 1.8, "win_rate": 0.6, "pnl": 10}],
    )


class TestStrategyMemoryStoreProvenance:
    def test_state_provenance_empty_store(self, tmp_path):
        store = _store(tmp_path)
        prov = store.state_provenance()
        assert prov["subsystem"] == "StrategyMemoryStore"
        assert prov["regime_count"] == 0

    def test_state_provenance_reflects_regime_count(self, tmp_path):
        store = _store(tmp_path)
        _seed_one_strategy(store)
        prov = store.state_provenance()
        assert prov["regime_count"] == 1
        assert prov["state_mtime"] is not None


class TestLoadByRegimeRecordUsage:
    """S-02B.1 blocker 2 — record_usage sépare lecture de comptabilité d'usage."""

    def test_default_record_usage_true_preserves_legacy_behavior(self, tmp_path):
        """Aucun appelant existant (autre que advisor_loop) ne passe
        record_usage — le défaut doit rester le comportement historique."""
        store = _store(tmp_path)
        _seed_one_strategy(store)

        selected = store.load_by_regime("bull_trend", limit=10)
        assert len(selected) == 1
        assert selected[0]["usage_count"] == 1

        payload = json.loads(store.cfg.file_path.read_text(encoding="utf-8"))
        assert payload["regimes"]["bull_trend"][0]["usage_count"] == 1

    def test_record_usage_false_recommendation_visible_usage_unchanged(self, tmp_path):
        """Test requis #1 — feedback false : recommandation visible, usage_count
        inchangé, JSON sur disque octet pour octet inchangé."""
        store = _store(tmp_path)
        _seed_one_strategy(store)
        before_bytes = store.cfg.file_path.read_bytes()

        selected = store.load_by_regime("bull_trend", limit=10, record_usage=False)

        assert len(selected) == 1, "la recommandation reste visible en mode passif"
        assert selected[0]["strategy"]["name"] == "momentum_v1"
        assert selected[0]["usage_count"] == 0, "usage_count ne doit pas être gonflé"

        after_bytes = store.cfg.file_path.read_bytes()
        assert after_bytes == before_bytes, (
            "S-02B.1 VIOLATION : le fichier a été réécrit par une lecture passive"
        )

    def test_record_usage_true_matches_legacy_increment(self, tmp_path):
        """Test requis #2 — feedback true : incrément identique au legacy."""
        store = _store(tmp_path)
        _seed_one_strategy(store)

        store.load_by_regime("bull_trend", limit=10, record_usage=True)
        payload = json.loads(store.cfg.file_path.read_text(encoding="utf-8"))
        assert payload["regimes"]["bull_trend"][0]["usage_count"] == 1

    def test_repeated_passive_observations_no_usage_accumulation(self, tmp_path):
        """Test requis #3 — observations passives répétées : pas d'accumulation."""
        store = _store(tmp_path)
        _seed_one_strategy(store)

        for _ in range(5):
            store.load_by_regime("bull_trend", limit=10, record_usage=False)

        payload = json.loads(store.cfg.file_path.read_text(encoding="utf-8"))
        assert payload["regimes"]["bull_trend"][0].get("usage_count", 0) == 0

    def test_passive_mode_cannot_bias_future_ranking(self, tmp_path):
        """Test requis #4 — le mode passif ne peut pas modifier le classement
        futur via usage_penalty (car usage_count reste à 0)."""
        store = _store(tmp_path)
        store.save_for_regime(
            "bull_trend",
            [
                {"strategy": {"name": "a"}, "sharpe": 1.0, "win_rate": 0.5, "pnl": 5},
                {"strategy": {"name": "b"}, "sharpe": 1.0, "win_rate": 0.5, "pnl": 5},
            ],
        )
        # 20 lectures passives répétées de "a" seul ne doivent jamais le pénaliser
        # au point d'inverser le classement face à "b" (jamais lu).
        for _ in range(20):
            passive = store.load_by_regime("bull_trend", limit=1, record_usage=False)
            assert passive, "candidat toujours visible"

        ranked = store.load_by_regime("bull_trend", limit=2, record_usage=False)
        scores = {row["strategy"]["name"]: row.get("usage_count", 0) for row in ranked}
        assert scores == {"a": 0, "b": 0}, (
            "S-02B.1 VIOLATION : usage_count a été modifié par des lectures passives"
        )

    def test_provenance_remains_available_in_passive_mode(self, tmp_path):
        """Test requis #5 — observabilité/provenance toujours disponible."""
        store = _store(tmp_path)
        _seed_one_strategy(store)
        store.load_by_regime("bull_trend", limit=10, record_usage=False)
        prov = store.state_provenance()
        assert prov["subsystem"] == "StrategyMemoryStore"
        assert prov["regime_count"] == 1

    def test_no_candidate_no_write_regardless_of_flag(self, tmp_path):
        store = _store(tmp_path)
        _seed_one_strategy(store)
        before = store.cfg.file_path.read_bytes()
        empty = store.load_by_regime("nonexistent_regime", limit=10, record_usage=True)
        assert empty == []
        assert store.cfg.file_path.read_bytes() == before


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
    """load_by_regime() renvoie toujours une stratégie valide (sharpe=1.8) et
    capture la valeur de record_usage reçue à chaque appel."""

    def __init__(self):
        self.calls = 0
        self.record_usage_calls: list[bool] = []

    def load_by_regime(self, regime, limit=10, record_usage=True):
        self.calls += 1
        self.record_usage_calls.append(record_usage)
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
        assert memory.record_usage_calls == [False], (
            "S-02B.1 VIOLATION : record_usage doit être False en mode passif "
            "(sinon une lecture contrefactuelle se fait passer pour un usage réel)"
        )
        assert captured["memory_sharpe"] is None, (
            "S-02B.1 VIOLATION : la recommandation StrategyMemoryStore a atteint "
            "le signal alors que FEATURE_ADAPTIVE_DECISION_FEEDBACK=false"
        )

    def test_feedback_true_transmits_recommendation_legacy_behavior(self, monkeypatch):
        import core.advisor_loop as advisor_loop

        monkeypatch.setattr(advisor_loop, "FEATURE_ADAPTIVE_DECISION_FEEDBACK", True)
        memory = _FakeStrategyMemoryStoreWithCandidate()
        captured = _run_analyze_symbol_capturing_memory_sharpe(memory, monkeypatch)

        assert memory.record_usage_calls == [True]
        assert captured["memory_sharpe"] == 1.8
