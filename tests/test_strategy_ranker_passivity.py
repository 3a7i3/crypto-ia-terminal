"""
tests/test_strategy_ranker_passivity.py — S-02B.1 (graph-closure) : passivité
de StrategyRanker.

Forensique complémentaire : `StrategyRanker.best_sharpe(regime)` a la
PRIORITÉ sur le fallback `StrategyMemoryStore` déjà gaté — mais le chemin
prioritaire lui-même n'était pas couvert par
`FEATURE_ADAPTIVE_DECISION_FEEDBACK`. Un `best_sharpe()` appris et positif
atteignait donc toujours `memory_sharpe` (→ `meta_engine.select()` +
`engine.evaluate()`), quel que soit le flag.

Un second chemin décision-actif a été découvert lors de la trace complète du
graphe d'appel : `capital_engine.stats_from_ranker(ranker, ...)` alimente
`capital_engine.allocate()` → `order_size_usd` (sizing réel). Ce chemin est
gaté de la même façon.

`StrategyRanker.record_trade()`, `.auto_demote()`, `.check_probation_alerts()`
et `_top_strategies_for_display()` (affichage) restent OBSERVATION_ONLY /
LEARNING_WRITE — non gatés, toujours actifs (apprentissage préservé).
`StrategyRanker.size_factor()` et `.blacklisted()` sont vérifiés UNREACHABLE
depuis le graphe de décision live (aucun appelant dans advisor_loop.py) —
documentés, non modifiés.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))

from quant_hedge_ai.ai_evolution.strategy_ranker import StrategyRanker


# ── Layer 1 — StrategyRanker isolée : provenance ─────────────────────────────


def _seed_ranker_with_learned_sharpe(tmp_path: Path, monkeypatch) -> StrategyRanker:
    """Construit un StrategyRanker réel avec un best_sharpe() positif appris."""
    db_path = tmp_path / "strategy_ranking.json"
    monkeypatch.setenv("RANKER_DB", str(db_path))
    import importlib

    import quant_hedge_ai.ai_evolution.strategy_ranker as ranker_module

    importlib.reload(ranker_module)
    ranker = ranker_module.StrategyRanker()
    for _ in range(ranker.MIN_TRADES_RANK):
        ranker.record_trade(
            strategy_name="momentum_v1",
            regime="bull_trend",
            pnl_pct=0.02,
            sharpe=1.8,
        )
    assert ranker.best_sharpe("bull_trend") > 0
    return ranker


class TestStrategyRankerProvenance:
    def test_state_provenance_reflects_volume(self, tmp_path, monkeypatch):
        ranker = _seed_ranker_with_learned_sharpe(tmp_path, monkeypatch)
        prov = ranker.state_provenance()
        assert prov["subsystem"] == "StrategyRanker"
        assert prov["n_strategies"] == 1
        assert prov["source_path"].endswith("strategy_ranking.json")

    def test_state_provenance_empty_ranker(self, tmp_path, monkeypatch):
        db_path = tmp_path / "empty_ranking.json"
        monkeypatch.setenv("RANKER_DB", str(db_path))
        import importlib

        import quant_hedge_ai.ai_evolution.strategy_ranker as ranker_module

        importlib.reload(ranker_module)
        ranker = ranker_module.StrategyRanker()
        prov = ranker.state_provenance()
        assert prov["n_strategies"] == 0


# ── UNREACHABLE proof — size_factor()/blacklisted() jamais appelés en live ──


class TestSizeFactorUnreachable:
    """Test requis #6 — preuve statique que ranker.size_factor()/.blacklisted()
    ne sont consommés par aucun chemin de décision live dans advisor_loop.py
    (confirmé par ADR-0014 et par cette trace) : documentés UNREACHABLE, non
    modifiés."""

    def test_size_factor_never_called_from_advisor_loop(self):
        source = Path("core/advisor_loop.py").read_text(encoding="utf-8")
        assert "ranker.size_factor(" not in source, (
            "S-02B.1 VIOLATION : ranker.size_factor() est maintenant consommé "
            "par le chemin de décision live — doit être gaté derrière "
            "FEATURE_ADAPTIVE_DECISION_FEEDBACK"
        )

    def test_blacklisted_never_called_from_advisor_loop(self):
        source = Path("core/advisor_loop.py").read_text(encoding="utf-8")
        assert "ranker.blacklisted(" not in source

    def test_top_strategies_never_called_directly_from_advisor_loop(self):
        """ranker.top_strategies() n'est utilisé qu'indirectement via
        best_sharpe()/leaderboard() (déjà tracés), jamais appelé directement."""
        source = Path("core/advisor_loop.py").read_text(encoding="utf-8")
        assert "ranker.top_strategies(" not in source


# ── Layer 2 — Intégration advisor_loop.analyze_symbol() ─────────────────────


def _actionable_signal() -> SimpleNamespace:
    return SimpleNamespace(
        signal="BUY", score=80, actionable=True, confirmed=True,
        strength=1.0, timestamp=time.time(),
    )


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


class _FakeStrategyMemoryStore:
    """Fallback StrategyMemoryStore — jamais de candidat exploitable (déjà
    testé isolément dans test_strategy_memory_passivity.py); ici on isole le
    comportement du ranker en gardant ce fallback neutre."""

    def load_by_regime(self, regime, limit=10, record_usage=True):
        return []

    def state_provenance(self):
        return {"subsystem": "StrategyMemoryStore"}


class _FakeStrategyMemoryStoreWithCandidate:
    """Fallback avec un candidat exploitable — pour le test requis #3."""

    def __init__(self):
        self.record_usage_calls: list[bool] = []

    def load_by_regime(self, regime, limit=10, record_usage=True):
        self.record_usage_calls.append(record_usage)
        return [{"strategy": {"name": "fallback_v1"}, "sharpe": 1.2}]

    def state_provenance(self):
        return {"subsystem": "StrategyMemoryStore"}


class _FakeRankerWithLearnedSharpe:
    """ranker.best_sharpe() positif appris — capture les appels."""

    def __init__(self, sharpe: float = 1.8):
        self._sharpe = sharpe
        self.best_sharpe_calls: list[str] = []

    def best_sharpe(self, regime):
        self.best_sharpe_calls.append(regime)
        return self._sharpe

    def state_provenance(self):
        return {"subsystem": "StrategyRanker", "n_strategies": 1}


class _FakeRankerNoRecommendation:
    """ranker.best_sharpe() renvoie 0.0 — aucune recommandation exploitable."""

    def __init__(self):
        self.best_sharpe_calls: list[str] = []

    def best_sharpe(self, regime):
        self.best_sharpe_calls.append(regime)
        return 0.0

    def state_provenance(self):
        return {"subsystem": "StrategyRanker", "n_strategies": 0}


def _run_analyze_symbol_capturing_memory_sharpe(ranker, memory, monkeypatch):
    import core.advisor_loop as advisor_loop

    monkeypatch.setattr(advisor_loop, "_cb_mistake_memory", None)

    from core.authority import init_authority, reset_authority
    from quant_hedge_ai.runtime.runtime_state_machine import RuntimeStateMachine

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
            ranker=ranker,
            runtime=_FakeRuntime(),
        )
    finally:
        reset_authority()
    return captured


class TestAdvisorLoopStrategyRankerPassivity:
    def test_default_feedback_false_ranker_recommendation_not_transmitted(
        self, monkeypatch
    ):
        """Tests requis #1 et #5 — feedback false : ranker interrogé
        (observable) mais son best_sharpe n'atteint pas memory_sharpe ; aucune
        décision appliquée comptée."""
        import core.advisor_loop as advisor_loop

        assert advisor_loop.FEATURE_ADAPTIVE_DECISION_FEEDBACK is False
        ranker = _FakeRankerWithLearnedSharpe(sharpe=1.8)
        memory = _FakeStrategyMemoryStore()
        captured = _run_analyze_symbol_capturing_memory_sharpe(
            ranker, memory, monkeypatch
        )

        assert ranker.best_sharpe_calls, "le ranker doit rester interrogé (observation)"
        assert captured["memory_sharpe"] is None, (
            "S-02B.1 VIOLATION : le best_sharpe() appris du ranker a atteint "
            "le signal alors que FEATURE_ADAPTIVE_DECISION_FEEDBACK=false"
        )

    def test_feedback_true_ranker_recommendation_reaches_memory_sharpe(
        self, monkeypatch
    ):
        """Test requis #2 — feedback true : comportement legacy (ranker en
        priorité) restauré."""
        import core.advisor_loop as advisor_loop

        monkeypatch.setattr(advisor_loop, "FEATURE_ADAPTIVE_DECISION_FEEDBACK", True)
        ranker = _FakeRankerWithLearnedSharpe(sharpe=1.8)
        memory = _FakeStrategyMemoryStore()
        captured = _run_analyze_symbol_capturing_memory_sharpe(
            ranker, memory, monkeypatch
        )

        assert captured["memory_sharpe"] == 1.8

    def test_ranker_recommendation_present_feedback_false_fallback_not_applied(
        self, monkeypatch
    ):
        """Test requis #3 — ranker a une recommandation, feedback false :
        le fallback StrategyMemoryStore n'est PAS déclenché à sa place (le
        code legacy ne consulte le fallback que si `not memory_sharpe`, donc
        le fallback EST bien consulté en mode passif — mais son propre
        record_usage reste False et son résultat n'est pas non plus
        appliqué). Aucune des deux sources ne doit être appliquée."""
        import core.advisor_loop as advisor_loop

        assert advisor_loop.FEATURE_ADAPTIVE_DECISION_FEEDBACK is False
        ranker = _FakeRankerWithLearnedSharpe(sharpe=1.8)
        memory = _FakeStrategyMemoryStoreWithCandidate()
        captured = _run_analyze_symbol_capturing_memory_sharpe(
            ranker, memory, monkeypatch
        )

        assert ranker.best_sharpe_calls
        assert memory.record_usage_calls == [False], (
            "le fallback StrategyMemoryStore est consulté (memory_sharpe est "
            "None côté ranker en mode passif) mais ne doit pas enregistrer "
            "d'usage réel"
        )
        assert captured["memory_sharpe"] is None, (
            "S-02B.1 VIOLATION : ni le ranker ni le fallback StrategyMemoryStore "
            "ne doivent atteindre le signal en mode passif"
        )

    def test_ranker_no_recommendation_feedback_true_fallback_still_works(
        self, monkeypatch
    ):
        """Test requis #4 — ranker sans recommandation exploitable, feedback
        true : le fallback StrategyMemoryStore legacy fonctionne toujours."""
        import core.advisor_loop as advisor_loop

        monkeypatch.setattr(advisor_loop, "FEATURE_ADAPTIVE_DECISION_FEEDBACK", True)
        ranker = _FakeRankerNoRecommendation()
        memory = _FakeStrategyMemoryStoreWithCandidate()
        captured = _run_analyze_symbol_capturing_memory_sharpe(
            ranker, memory, monkeypatch
        )

        assert ranker.best_sharpe_calls
        assert memory.record_usage_calls == [True]
        assert captured["memory_sharpe"] == 1.2

    def test_counterfactual_ranker_recommendation_observable_via_logging(
        self, monkeypatch, caplog
    ):
        """Test requis #7 — la recommandation contrefactuelle du ranker reste
        observable (logguée) en mode passif, distincte d'une application."""
        import logging

        import core.advisor_loop as advisor_loop

        assert advisor_loop.FEATURE_ADAPTIVE_DECISION_FEEDBACK is False
        ranker = _FakeRankerWithLearnedSharpe(sharpe=2.5)
        memory = _FakeStrategyMemoryStore()
        with caplog.at_level(logging.DEBUG, logger="advisor_loop"):
            _run_analyze_symbol_capturing_memory_sharpe(ranker, memory, monkeypatch)

        assert any(
            "StrategyRanker" in rec.message and "contrefactuelle" in rec.message
            for rec in caplog.records
        ), "la recommandation contrefactuelle du ranker doit rester observable"

    def test_passive_mode_survives_missing_ranker_state_provenance(self, monkeypatch):
        """Test requis #8 — une provenance ranker indisponible ne doit jamais
        casser le traitement passif."""

        class _RankerNoProvenance:
            def best_sharpe(self, regime):
                return 3.0

        ranker = _RankerNoProvenance()
        memory = _FakeStrategyMemoryStore()
        captured = _run_analyze_symbol_capturing_memory_sharpe(
            ranker, memory, monkeypatch
        )
        assert captured["memory_sharpe"] is None
