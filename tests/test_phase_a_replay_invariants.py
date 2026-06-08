"""
tests/test_phase_a_replay_invariants.py
=======================================
Protocole de validation Phase A — Replay Invariants.

Principe : tout changement Phase A doit être behavior-preserving.
Ce fichier est la barrière formelle de non-régression.

  Avant changement  →  pytest tests/test_phase_a_replay_invariants.py -v
  Après changement  →  idem, tout doit passer

────────────────────────────────────────────────────────────────────────────────
TIER 1 — Déterminisme      : même run deux fois → résultats bit-identiques
TIER 2 — Snapshot fixe     : output identique avant/après refactor (tolérance 0)
TIER 3 — Isolation struct. : Simulator absent de src/ → suppression safe
TIER 4 — Cohérence régimes : RegimeDetector strings ↔ MarketRegime enum
TIER 5 — Équivalence ENL   : NoisyExchange ≡ _enl_fill (±1% mean, ±5% std)
────────────────────────────────────────────────────────────────────────────────

Établir le snapshot (première fois) :
    python tests/test_phase_a_replay_invariants.py
Puis coller les valeurs imprimées dans _GOLDEN ci-dessous.

Forcer la réinitialisation (après changement intentionnel de comportement) :
    Mettre _GOLDEN = None, relancer le script, coller les nouvelles valeurs.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from src.agent.codex_agent import CodexAgent
from src.agent.sma_strategy import SMAStrategy
from src.analytics.regime_detector import RegimeDetector
from src.backtest.data_feed import HistoricalDataFeed
from src.backtest.engine import BacktestEngine
from src.domain.trade_event import MarketRegime
from src.engine.execution_router import ExecutionRouter
from src.engine.virtual_exchange import VirtualExchange
from src.execution.enl import ENLConfig, NoisyExchange
from src.portfolio.portfolio_state import PortfolioState
from src.risk.kill_switch import KillSwitch
from src.runtime.run_context import RunContext

# ── Snapshot de référence ─────────────────────────────────────────────────────
# Mettre à None pour régénérer (voir docstring).
# Valeurs établies sur : SMA(3,10), 120 candles synthétiques seed=42, balance=10 000
_GOLDEN: dict | None = {
    "total_trades": 10,
    "total_pnl": 7.6295,
    "win_rate": 1.0,
    "max_drawdown": 0.0,
    "final_balance": 10007.6295,
    "regime": "sideways",  # A1: "range" → "sideways" (aligné MarketRegime.SIDEWAYS)
}

# ── Tolérances ────────────────────────────────────────────────────────────────
_ENL_TOLERANCE_MEAN = 0.01  # ±1 % sur la moyenne des fill prices
_ENL_TOLERANCE_STD = 0.05  # ±5 % sur l'écart-type
_ENL_N_SAMPLES = 5_000
_FLOAT_ABS = 1e-6  # tolérance flottante pour snapshot
_FIXED_BALANCE = 10_000.0
_FIXED_PRICE = 4_000.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _candles_seed42(n: int = 120) -> list[dict]:
    """Réplique exacte de _synthetic_candles(seed=42) dans SimBot — déterministe."""
    candles, price, seed = [], 100.0, 42
    for i in range(n):
        noise = math.sin(i * 0.3 + seed) * 0.8 + math.cos(i * 0.1) * 0.4
        price = max(1.0, price + noise + 0.05)
        candles.append(
            {
                "timestamp": i,
                "symbol": "BTC",
                "open": round(price - 0.1, 4),
                "high": round(price + 0.3, 4),
                "low": round(price - 0.3, 4),
                "close": round(price, 4),
                "volume": 1000.0 + (i % 10) * 50,
            }
        )
    return candles


def _run_fixed_backtest(candles: list[dict] | None = None) -> dict:
    """BacktestEngine avec données et run_id fixes — sans aléatoire."""
    if candles is None:
        candles = _candles_seed42()
    portfolio = PortfolioState(balance=_FIXED_BALANCE)
    exchange = VirtualExchange(portfolio)
    router = ExecutionRouter(exchange)
    feed = HistoricalDataFeed(list(candles))
    agent = CodexAgent(SMAStrategy(3, 10), KillSwitch())
    ctx = RunContext(strategy_id="PHASE_A_INVARIANT", run_id="PHASE_A_RUN_0")
    return BacktestEngine(agent, router, feed, portfolio, ctx).run()


def _compute_snapshot() -> dict:
    r = _run_fixed_backtest()
    return {
        "total_trades": r["total_trades"],
        "total_pnl": round(r["total_pnl"], 8),
        "win_rate": round(r["win_rate"], 8),
        "max_drawdown": round(r["max_drawdown"], 8),
        "final_balance": round(r["final_balance"], 8),
        "regime": r.get("regime", "range"),
    }


def _std(values: list[float]) -> float:
    m = sum(values) / len(values)
    return math.sqrt(sum((x - m) ** 2 for x in values) / len(values))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TIER 1 — Déterminisme strict
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestTier1Determinism:
    """Deux runs sur données identiques → sorties bit-identiques."""

    def test_backtest_engine_two_runs_identical(self):
        candles = _candles_seed42()
        r1 = _run_fixed_backtest(candles[:])
        r2 = _run_fixed_backtest(candles[:])
        assert (
            r1["total_trades"] == r2["total_trades"]
        ), "total_trades diverge entre deux runs"
        assert r1["total_pnl"] == r2["total_pnl"], "total_pnl diverge entre deux runs"
        assert r1["win_rate"] == r2["win_rate"], "win_rate diverge entre deux runs"
        assert (
            r1["max_drawdown"] == r2["max_drawdown"]
        ), "max_drawdown diverge entre deux runs"
        assert (
            r1["final_balance"] == r2["final_balance"]
        ), "final_balance diverge entre deux runs"
        assert r1.get("regime") == r2.get("regime"), "regime diverge entre deux runs"

    def test_noisyexchange_same_seed_deterministic(self):
        """NoisyExchange avec seed fixe → séquence identique à chaque instanciation."""
        cfg = ENLConfig(spread_bps=10.0, slippage_sigma=0.002, fill_rate=1.0, seed=99)

        def _prices():
            nx = NoisyExchange(VirtualExchange(PortfolioState(_FIXED_BALANCE)), cfg)
            return [nx._fill_price("buy", _FIXED_PRICE) for _ in range(30)]

        assert _prices() == _prices()

    def test_candles_seed42_deterministic(self):
        """Générateur de candles déterministe à chaque appel."""
        assert _candles_seed42() == _candles_seed42()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TIER 2 — Snapshot de référence
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestTier2GoldenSnapshot:
    """
    Output figé. Toute modification Phase A doit produire des valeurs identiques.
    Si _GOLDEN est None : skip avec instructions.
    """

    def test_backtest_matches_golden(self):
        if _GOLDEN is None:
            pytest.skip(
                "Snapshot non établi. Lancer : python tests/test_phase_a_replay_invariants.py"
            )
        r = _run_fixed_backtest()
        assert (
            r["total_trades"] == _GOLDEN["total_trades"]
        ), f"total_trades: obtenu {r['total_trades']}, attendu {_GOLDEN['total_trades']}"
        assert r["total_pnl"] == pytest.approx(
            _GOLDEN["total_pnl"], abs=_FLOAT_ABS
        ), f"total_pnl diverge : {r['total_pnl']} ≠ {_GOLDEN['total_pnl']}"
        assert r["win_rate"] == pytest.approx(
            _GOLDEN["win_rate"], abs=_FLOAT_ABS
        ), f"win_rate diverge : {r['win_rate']} ≠ {_GOLDEN['win_rate']}"
        assert r["max_drawdown"] == pytest.approx(
            _GOLDEN["max_drawdown"], abs=_FLOAT_ABS
        ), f"max_drawdown diverge : {r['max_drawdown']} ≠ {_GOLDEN['max_drawdown']}"
        assert r["final_balance"] == pytest.approx(
            _GOLDEN["final_balance"], abs=_FLOAT_ABS
        ), f"final_balance diverge : {r['final_balance']} ≠ {_GOLDEN['final_balance']}"
        assert (
            r.get("regime", "range") == _GOLDEN["regime"]
        ), f"regime: obtenu {r.get('regime')}, attendu {_GOLDEN['regime']}"

    def test_snapshot_is_established(self):
        """Rappel explicite si le snapshot n'est pas encore établi."""
        if _GOLDEN is None:
            pytest.skip(
                "ACTION REQUISE : établir le snapshot de référence.\n"
                "  python tests/test_phase_a_replay_invariants.py\n"
                "Puis coller les valeurs imprimées dans _GOLDEN."
            )
        assert isinstance(_GOLDEN["total_trades"], int)
        assert isinstance(_GOLDEN["total_pnl"], float)
        assert _GOLDEN["regime"] in (
            "trend",
            "range",
            "volatile",
            "trending",
            "sideways",
            "volatile",
            "TRENDING",
            "SIDEWAYS",
            "VOLATILE",
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TIER 3 — Isolation structurelle
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestTier3StructuralIsolation:
    """
    Simulator ne doit pas être importé dans src/.
    Condition nécessaire pour que sa suppression soit safe.
    """

    def test_simulator_absent_from_production_src(self):
        """Aucun fichier src/ ne référence runtime.simulator."""
        src_root = Path(__file__).parent.parent / "src"
        violators = [
            str(f.relative_to(src_root.parent))
            for f in src_root.rglob("*.py")
            if "runtime.simulator" in f.read_text(encoding="utf-8", errors="ignore")
            or "from src.runtime import simulator"
            in f.read_text(encoding="utf-8", errors="ignore")
        ]
        assert (
            not violators
        ), "Simulator importé dans src/ — suppression non safe :\n" + "\n".join(
            f"  {v}" for v in violators
        )

    def test_simulator_test_files_identified(self):
        """
        Inventaire des tests qui importent Simulator.
        Ces fichiers devront être migrés AVANT la suppression.
        Informatif — ne bloque pas.
        """
        tests_root = Path(__file__).parent
        files = [
            str(f.relative_to(tests_root.parent))
            for f in tests_root.rglob("*.py")
            if "runtime.simulator" in f.read_text(encoding="utf-8", errors="ignore")
        ]
        # Documente l'état actuel — attend tests/test_cmvk.py
        # À passer à 0 avant la suppression de runtime/simulator.py
        if files:
            print(
                f"\n[TIER3 INFO] Tests à migrer avant suppression de Simulator ({len(files)}) :\n"
                + "\n".join(f"  {f}" for f in files)
            )
        # Non-bloquant : c'est un état connu et prévu

    def test_enl_fill_not_duplicated_beyond_paper_runner(self):
        """_enl_fill ne doit être défini que dans paper_runner.py."""
        src_root = Path(__file__).parent.parent / "src"
        files_with_enl = [
            str(f.relative_to(src_root.parent))
            for f in src_root.rglob("*.py")
            if "def _enl_fill" in f.read_text(encoding="utf-8", errors="ignore")
        ]
        assert len(files_with_enl) <= 1, (
            f"_enl_fill défini dans plusieurs fichiers — duplication ENL :\n"
            + "\n".join(f"  {v}" for v in files_with_enl)
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TIER 4 — Cohérence des nommages de régimes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Table de mapping Phase A (action 1) : RegimeDetector → MarketRegime — post-A1 aligné
_REGIME_MAPPING = {
    "trending": MarketRegime.TRENDING,
    "sideways": MarketRegime.SIDEWAYS,
    "volatile": MarketRegime.VOLATILE,
}


class TestTier4RegimeConsistency:
    """
    Documente et vérifie l'état du nommage régimes.
    Avant Phase A : strings incohérents (test_misalignment passe).
    Après Phase A : strings alignés (test_misalignment skip).
    """

    def test_regime_detector_outputs_known_strings(self):
        """RegimeDetector ne retourne que des strings alignés avec MarketRegime."""
        detector = RegimeDetector()
        candles = _candles_seed42()
        result = detector.classify(candles)
        assert result in (
            "trending",
            "sideways",
            "volatile",
        ), f"RegimeDetector a retourné un string inattendu : {result!r}"

    def test_regime_misalignment_documented(self):
        """
        Avant Phase A : "trend" et "range" ne sont pas dans MarketRegime.
        Après Phase A  : tous alignés → test skip.
        Ce test valide que le problème connu est bien présent avant correction.
        """
        enum_vals = {e.value for e in MarketRegime}
        detector_outputs = {"trend", "range", "volatile"}
        mismatches = detector_outputs - enum_vals

        if not mismatches:
            pytest.skip("Régimes déjà alignés — Phase A action 1 complète.")

        assert mismatches == {"trend", "range"}, (
            f"Mismatches inattendus (ni {{'trend', 'range'}} ni vide) : {mismatches}\n"
            "Vérifier MarketRegime enum et RegimeDetector."
        )

    def test_regime_mapping_table_covers_all_detector_outputs(self):
        """La table _REGIME_MAPPING couvre tous les outputs possibles du RegimeDetector."""
        for regime_str in ("trending", "sideways", "volatile"):
            assert (
                regime_str in _REGIME_MAPPING
            ), f"Régime {regime_str!r} absent de _REGIME_MAPPING — mapping Phase A incomplet"
            assert (
                _REGIME_MAPPING[regime_str] in MarketRegime
            ), f"Valeur cible {_REGIME_MAPPING[regime_str]!r} inexistante dans MarketRegime"

    def test_regime_mapping_is_injective(self):
        """Chaque régime source mappe sur un régime cible distinct (pas de collision)."""
        targets = list(_REGIME_MAPPING.values())
        assert len(targets) == len(
            set(targets)
        ), "Collision dans _REGIME_MAPPING — deux sources mappent sur la même cible"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TIER 5 — Équivalence distributionnelle ENL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestTier5ENLEquivalence:
    """
    Prérequis à Phase A action 3 (substitution _enl_fill → NoisyExchange).
    NoisyExchange(ENLConfig.light, seed=42) doit produire la même distribution
    que _enl_fill avec les mêmes paramètres.

    Tolérance : ±1% sur mean, ±5% sur std.
    """

    _SPREAD_BPS = 5.0
    _SLIPPAGE_SIGMA = 0.001

    def _reference_fill_prices(self, n: int, side: str) -> list[float]:
        """
        Distribution de référence — reproduit _enl_fill avec seed fixe.
        (La vraie _enl_fill utilise un RNG non-seedé → non comparable directement.)
        """
        import random

        rng = random.Random(42)
        prices = []
        for _ in range(n):
            half_spread = _FIXED_PRICE * (self._SPREAD_BPS / 10_000) / 2
            slip = abs(rng.gauss(0, _FIXED_PRICE * self._SLIPPAGE_SIGMA))
            if side == "buy":
                prices.append(_FIXED_PRICE + half_spread + slip)
            else:
                prices.append(_FIXED_PRICE - half_spread - slip)
        return prices

    def _noisyexchange_fill_prices(self, n: int, side: str) -> list[float]:
        """Distribution NoisyExchange avec seed=42 — doit être équivalente."""
        cfg = ENLConfig(
            spread_bps=self._SPREAD_BPS,
            slippage_sigma=self._SLIPPAGE_SIGMA,
            fill_rate=1.0,
            seed=42,
        )
        nx = NoisyExchange(VirtualExchange(PortfolioState(_FIXED_BALANCE)), cfg)
        return [nx._fill_price(side, _FIXED_PRICE) for _ in range(n)]

    def test_buy_mean_equivalent(self):
        """Mean fill price buy : |δ| ≤ 1%."""
        ref = self._reference_fill_prices(_ENL_N_SAMPLES, "buy")
        nx = self._noisyexchange_fill_prices(_ENL_N_SAMPLES, "buy")
        ref_mean = sum(ref) / len(ref)
        nx_mean = sum(nx) / len(nx)
        delta = abs(nx_mean - ref_mean) / ref_mean
        assert delta <= _ENL_TOLERANCE_MEAN, (
            f"Mean buy diverge : {delta:.2%} > {_ENL_TOLERANCE_MEAN:.2%}\n"
            f"  Référence : {ref_mean:.4f} | NoisyExchange : {nx_mean:.4f}"
        )

    def test_sell_mean_equivalent(self):
        """Mean fill price sell : |δ| ≤ 1%."""
        ref = self._reference_fill_prices(_ENL_N_SAMPLES, "sell")
        nx = self._noisyexchange_fill_prices(_ENL_N_SAMPLES, "sell")
        ref_mean = sum(ref) / len(ref)
        nx_mean = sum(nx) / len(nx)
        delta = abs(nx_mean - ref_mean) / ref_mean
        assert (
            delta <= _ENL_TOLERANCE_MEAN
        ), f"Mean sell diverge : {delta:.2%} > {_ENL_TOLERANCE_MEAN:.2%}"

    def test_buy_std_equivalent(self):
        """Std fill price buy : |δ| ≤ 5%."""
        ref = self._reference_fill_prices(_ENL_N_SAMPLES, "buy")
        nx = self._noisyexchange_fill_prices(_ENL_N_SAMPLES, "buy")
        ref_std = _std(ref)
        nx_std = _std(nx)
        if ref_std == 0:
            pytest.skip("Std référence = 0 — impossible de calculer le ratio")
        delta = abs(nx_std - ref_std) / ref_std
        assert delta <= _ENL_TOLERANCE_STD, (
            f"Std buy diverge : {delta:.2%} > {_ENL_TOLERANCE_STD:.2%}\n"
            f"  Référence std : {ref_std:.6f} | NoisyExchange : {nx_std:.6f}"
        )

    def test_fill_always_unfavorable_buy(self):
        """Fill buy ≥ market price (friction toujours défavorable)."""
        cfg = ENLConfig(spread_bps=5.0, slippage_sigma=0.001, fill_rate=1.0, seed=0)
        nx = NoisyExchange(VirtualExchange(PortfolioState(_FIXED_BALANCE)), cfg)
        violations = [nx._fill_price("buy", _FIXED_PRICE) for _ in range(200)]
        assert all(
            p >= _FIXED_PRICE for p in violations
        ), "Fill buy en dessous du prix marché — friction incorrecte"

    def test_fill_always_unfavorable_sell(self):
        """Fill sell ≤ market price (friction toujours défavorable)."""
        cfg = ENLConfig(spread_bps=5.0, slippage_sigma=0.001, fill_rate=1.0, seed=1)
        nx = NoisyExchange(VirtualExchange(PortfolioState(_FIXED_BALANCE)), cfg)
        violations = [nx._fill_price("sell", _FIXED_PRICE) for _ in range(200)]
        assert all(
            p <= _FIXED_PRICE for p in violations
        ), "Fill sell au-dessus du prix marché — friction incorrecte"

    def test_noisyexchange_preserves_backtest_pnl_direction(self):
        """
        Sur données trend_up : backtest ENL clean ≥ backtest ENL heavy.
        Vérifie que substituer NoisyExchange ne retourne pas la logique de friction.
        """
        from src.backtest.market_generator import trend_up

        candles = trend_up(n=120, seed=0)

        def _run(cfg: ENLConfig) -> float:
            portfolio = PortfolioState(balance=_FIXED_BALANCE)
            nx = NoisyExchange(VirtualExchange(portfolio), cfg)
            router = ExecutionRouter(nx)
            feed = HistoricalDataFeed(list(candles))
            agent = CodexAgent(SMAStrategy(3, 10), KillSwitch())
            ctx = RunContext(strategy_id="ENL_DIR_TEST", run_id="DIR_0")
            return BacktestEngine(
                agent, nx if False else router, feed, portfolio, ctx
            ).run()["total_pnl"]

        clean = _run(ENLConfig.clean())
        heavy = _run(ENLConfig.heavy())
        assert (
            clean >= heavy
        ), f"Friction heavy ({heavy:.2f}) > friction clean ({clean:.2f}) — logique inversée"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TIER 6 — Cohérence économique (Phase B)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestTier6EconomicConsistency:
    """
    TradeEvent = source unique de vérité économique.

    T6 vérifie que :
      - _trades contient des TradeEvent (plus des dicts)
      - sum(net_pnl_usd) == total_pnl reporté
      - net_pnl_usd = gross_pnl_usd - fees_usd - slippage_usd (identité)
      - execution_mode == "backtest" pour tous les trades BacktestEngine
      - trade_ids uniques
    """

    def test_trades_are_trade_events(self):
        """BacktestEngine._trades contient des TradeEvent, pas des dicts."""
        from src.domain.trade_event import TradeEvent

        r = _run_fixed_backtest()
        assert len(r["trades"]) > 0, "Aucun trade — vérifier le générateur de candles"
        for t in r["trades"]:
            assert isinstance(
                t, TradeEvent
            ), f"Type attendu TradeEvent, obtenu {type(t).__name__}"

    def test_total_pnl_equals_sum_net_pnl(self):
        """sum(TradeEvent.net_pnl_usd) == total_pnl du rapport."""
        r = _run_fixed_backtest()
        computed = sum(t.net_pnl_usd for t in r["trades"])
        assert (
            abs(computed - r["total_pnl"]) < _FLOAT_ABS
        ), f"Divergence économique : sum(net_pnl)={computed:.8f} ≠ total_pnl={r['total_pnl']:.8f}"

    def test_net_pnl_identity(self):
        """net_pnl_usd = gross_pnl_usd - fees_usd - slippage_usd — toujours."""
        r = _run_fixed_backtest()
        for t in r["trades"]:
            expected = t.gross_pnl_usd - t.fees_usd - t.slippage_usd
            assert abs(t.net_pnl_usd - expected) < 1e-10, (
                f"Invariant PnL violé pour trade {t.trade_id}: "
                f"net={t.net_pnl_usd} ≠ gross-fees-slip={expected}"
            )

    def test_execution_mode_is_backtest(self):
        """Tous les trades produits par BacktestEngine ont execution_mode == 'backtest'."""
        r = _run_fixed_backtest()
        for t in r["trades"]:
            assert (
                t.execution_mode == "backtest"
            ), f"execution_mode inattendu : {t.execution_mode!r}"

    def test_trade_ids_are_unique(self):
        """Chaque trade_id est unique dans un run."""
        r = _run_fixed_backtest()
        ids = [t.trade_id for t in r["trades"]]
        assert len(ids) == len(set(ids)), "Collision de trade_id détectée"

    def test_timestamps_are_utc(self):
        """opened_at et closed_at sont timezone-aware UTC."""
        from datetime import timezone

        r = _run_fixed_backtest()
        for t in r["trades"]:
            assert t.opened_at.tzinfo is not None, "opened_at sans timezone"
            assert t.closed_at.tzinfo is not None, "closed_at sans timezone"
            assert t.opened_at.utcoffset().total_seconds() == 0
            assert t.closed_at.utcoffset().total_seconds() == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Établissement du snapshot (script direct)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import json

    snapshot = _compute_snapshot()
    print("\n" + "=" * 60)
    print("GOLDEN SNAPSHOT — coller dans _GOLDEN ci-dessus :")
    print("=" * 60)
    print(json.dumps(snapshot, indent=4))
    print("=" * 60)
    print("\nInstruction : remplacer `_GOLDEN: dict | None = None`")
    print("par         : `_GOLDEN = " + repr(snapshot) + "`")
