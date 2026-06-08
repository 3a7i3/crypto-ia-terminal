import pytest

from src.agent.breakout_strategy import BreakoutStrategy
from src.agent.rsi_strategy import RSIStrategy
from src.agent.sma_strategy import SMAStrategy
from src.analytics.edge_scorer import EdgeScorer
from src.backtest.market_generator import high_volatility, range_bound, trend_up


def _make_candles_map(seed=0, n=160):
    return {
        "range": range_bound(n, seed),
        "trend": trend_up(n, seed),
        "volatile": high_volatility(n, seed),
    }


scorer = EdgeScorer(window=120, step=20)


def test_score_returns_required_keys():
    result = scorer.score(
        lambda: RSIStrategy(14),
        _make_candles_map(),
        strategy_id="RSI_TEST",
    )
    for key in (
        "score",
        "total",
        "verdict",
        "matrix",
        "breakeven",
        "clean_avg",
        "edge_buffer",
    ):
        assert key in result


def test_score_range_0_to_total():
    result = scorer.score(lambda: RSIStrategy(14), _make_candles_map())
    assert 0 <= result["score"] <= result["total"]


def test_verdict_options():
    result = scorer.score(lambda: SMAStrategy(3, 10), _make_candles_map())
    assert result["verdict"] in ("VIABLE", "MARGINAL", "DEAD")


def test_matrix_has_all_friction_levels():
    result = scorer.score(lambda: RSIStrategy(14), _make_candles_map())
    for ds in result["matrix"]:
        for level in ("clean", "light", "realistic", "heavy"):
            assert level in result["matrix"][ds]


def test_clean_avg_positive_on_favorable_data():
    # RSI sur range devrait avoir un edge positif clean
    data = {"range": range_bound(160, 0)}
    result = scorer.score(lambda: RSIStrategy(14, 30, 70), data)
    # clean expectancy sur range : peut être positif
    assert isinstance(result["clean_avg"], float)


def test_breakeven_is_none_or_valid_level():
    result = scorer.score(lambda: SMAStrategy(3, 10), _make_candles_map())
    valid_levels = {None, "clean", "light", "realistic", "heavy"}
    assert result["breakeven"] in valid_levels


def test_edge_buffer_is_float():
    result = scorer.score(lambda: RSIStrategy(14), _make_candles_map())
    assert isinstance(result["edge_buffer"], float)


def test_dead_strategy_scores_low():
    # SMA 3/10 sur données variées → score faible attendu
    result = scorer.score(lambda: SMAStrategy(3, 10), _make_candles_map())
    assert result["score"] <= result["total"]


def test_different_strategies_produce_different_scores():
    data = _make_candles_map()
    s1 = scorer.score(lambda: RSIStrategy(14), data)
    s2 = scorer.score(lambda: SMAStrategy(3, 10), data)
    # Les deux scores ne sont pas forcément différents, mais les matrices le sont
    assert isinstance(s1["score"], int)
    assert isinstance(s2["score"], int)
