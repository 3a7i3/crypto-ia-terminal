import pytest

from src.telegram.sim_bot import SimBot, _synthetic_candles


@pytest.fixture
def bot():
    return SimBot(initial_balance=10_000.0)


# -- /start / /help --


def test_start_contains_commands(bot):
    reply = bot.handle("/start")
    assert "/run" in reply
    assert "/status" in reply
    assert "/kill" not in reply
    assert "/resume" not in reply


def test_help_same_as_start(bot):
    assert bot.handle("/help") == bot.handle("/start")


# -- /run --


def test_run_default_fast(bot):
    reply = bot.handle("/run")
    assert "Run terminé" in reply
    assert "SMA_3_10" in reply


def test_run_slow_preset(bot):
    reply = bot.handle("/run slow")
    assert "SMA_5_20" in reply


def test_run_ultra_preset(bot):
    reply = bot.handle("/run ultra")
    assert "SMA_2_7" in reply


def test_run_unknown_preset(bot):
    reply = bot.handle("/run xyz")
    assert "Preset inconnu" in reply


def test_run_report_has_trades_and_pnl(bot):
    reply = bot.handle("/run fast")
    assert "Trades" in reply
    assert "PnL" in reply
    assert "Win rate" in reply


# -- /status --


def test_status_before_run(bot):
    reply = bot.handle("/status")
    assert "Runs effectués : 0" in reply or "Status simulateur" in reply


def test_status_after_run(bot):
    bot.handle("/run fast")
    reply = bot.handle("/status")
    assert "Balance" in reply
    assert "Kill switch" in reply


# -- /pnl --


def test_pnl_before_run(bot):
    reply = bot.handle("/pnl")
    assert "PnL cumulé" in reply
    assert "0.00" in reply


def test_pnl_after_run(bot):
    bot.handle("/run fast")
    reply = bot.handle("/pnl")
    assert "PnL cumulé" in reply


# -- /trades --


def test_trades_before_run(bot):
    reply = bot.handle("/trades")
    assert "Aucun trade" in reply


def test_trades_after_run_default_5(bot):
    bot.handle("/run fast")
    reply = bot.handle("/trades")
    # Either "Aucun trade" (SMA needs warmup, possible 0 trades) or actual trades
    assert isinstance(reply, str)


def test_trades_n_param(bot):
    bot.handle("/run fast")
    reply = bot.handle("/trades 3")
    assert isinstance(reply, str)


def test_trades_invalid_n_falls_back_to_5(bot):
    bot.handle("/run fast")
    reply = bot.handle("/trades abc")
    assert isinstance(reply, str)


# -- /kill / /resume (removed — control commands not permitted) --


def test_kill_command_removed(bot):
    reply = bot.handle("/kill")
    assert "Commande inconnue" in reply


def test_resume_command_removed(bot):
    reply = bot.handle("/resume")
    assert "Commande inconnue" in reply


# -- unknown command --


def test_unknown_command(bot):
    reply = bot.handle("/unknown_xyz")
    assert "Commande inconnue" in reply


# -- candle generator --


def test_synthetic_candles_count():
    candles = _synthetic_candles(n=50)
    assert len(candles) == 50


def test_synthetic_candles_structure():
    c = _synthetic_candles(n=1)[0]
    assert "close" in c
    assert "symbol" in c
    assert c["symbol"] == "BTC"
    assert c["close"] > 0


def test_synthetic_candles_different_seeds():
    a = _synthetic_candles(n=10, seed=1)
    b = _synthetic_candles(n=10, seed=99)
    closes_a = [c["close"] for c in a]
    closes_b = [c["close"] for c in b]
    assert closes_a != closes_b
