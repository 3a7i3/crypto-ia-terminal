"""
smoke_test_ci.py — Vérification rapide que tous les modules s'importent et
s'initialisent correctement. Zéro réseau, zéro DB, tourne partout (Linux CI + Windows).

Retourne exit code 0 si tout est OK, 1 si un module échoue.
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback

# ── Racine du projet dans le PYTHONPATH ───────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Forcer le mode synthétique pour éviter tout appel réseau
os.environ.setdefault("MARKET_SCANNER_SYNTHETIC", "true")

_PASS = []
_FAIL = []


def check(name: str, fn):
    try:
        fn()
        _PASS.append(name)
        print(f"  OK  {name}")
    except Exception:
        _FAIL.append(name)
        print(f"  FAIL {name}")
        traceback.print_exc()


# ── 1. Imports de base ────────────────────────────────────────────────────────
print("\n[1/5] Imports modules")

check("supervision.alert_manager", lambda: __import__(
    "supervision.alert_manager", fromlist=["Alert", "AlertManager"]
))
check("supervision.notifications.telegram_notifier", lambda: __import__(
    "supervision.notifications.telegram_notifier", fromlist=["TelegramNotifier"]
))
check("supervision.notifications.ops_notifier", lambda: __import__(
    "supervision.notifications.ops_notifier", fromlist=["OpsNotifier"]
))
check("supervision.ops_watchdog", lambda: __import__(
    "supervision.ops_watchdog", fromlist=["OpsWatchdog"]
))
check("ohlcv_validator", lambda: __import__(
    "quant_hedge_ai.agents.market.ohlcv_validator",
    fromlist=["validate_candles", "is_series_fresh"],
))
check("retry_policy", lambda: __import__(
    "quant_hedge_ai.agents.market.retry_policy",
    fromlist=["retry_with_backoff", "CircuitBreaker"],
))
check("backtest_lab", lambda: __import__(
    "quant_hedge_ai.agents.quant.backtest_lab", fromlist=["BacktestLab"]
))
check("walk_forward", lambda: __import__(
    "quant_hedge_ai.agents.quant.walk_forward",
    fromlist=["WalkForwardValidator", "WalkForwardResult"],
))
check("order_deduplicator", lambda: __import__(
    "quant_hedge_ai.agents.execution.order_deduplicator",
    fromlist=["OrderDeduplicator"],
))
check("trade_logger", lambda: __import__(
    "quant_hedge_ai.agents.execution.trade_logger", fromlist=["TradeLogger"]
))
check("session_guard", lambda: __import__(
    "quant_hedge_ai.agents.risk.session_guard",
    fromlist=["SessionGuard", "SessionHaltedError", "OrderTooLargeError"],
))
check("execution_engine", lambda: __import__(
    "quant_hedge_ai.agents.execution.execution_engine", fromlist=["ExecutionEngine"]
))

# ── 2. Pipeline données ───────────────────────────────────────────────────────
print("\n[2/5] Pipeline données (synthétique)")

def _test_ohlcv_validator():
    from quant_hedge_ai.agents.market.ohlcv_validator import validate_candles
    candles = [
        {"symbol": "BTC/USDT", "timestamp": "2024-01-01T00:00:00+00:00",
         "open": 100, "high": 110, "low": 90, "close": 105, "volume": 1000},
        {"symbol": "BTC/USDT", "timestamp": "2024-01-01T01:00:00+00:00",
         "open": float("nan"), "high": 110, "low": 90, "close": 105, "volume": 1000},
    ]
    clean, report = validate_candles(candles, symbol="BTC/USDT")
    assert len(clean) == 1, f"attendu 1 bougie valide, obtenu {len(clean)}"
    assert report.dropped == 1

check("ohlcv_validator fonctionnel", _test_ohlcv_validator)

def _test_circuit_breaker():
    from quant_hedge_ai.agents.market.retry_policy import CircuitBreaker
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=9999, label="test")
    assert cb.is_closed
    cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
    cb.call(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
    assert cb.is_open
    cb.reset()
    assert cb.is_closed

check("circuit_breaker fonctionnel", _test_circuit_breaker)

# ── 3. Backtest + Walk-Forward ────────────────────────────────────────────────
print("\n[3/5] Backtest & Walk-Forward")

def _test_backtest():
    import math, random
    from quant_hedge_ai.agents.quant.backtest_lab import BacktestLab
    random.seed(42)
    price = 100.0
    candles = []
    for i in range(120):
        price = max(price * (1 + random.gauss(0, 0.01)), 1.0)
        candles.append({"open": price, "high": price * 1.005, "low": price * 0.995,
                        "close": price, "volume": 1000.0})
    lab = BacktestLab()
    result = lab.run_backtest({"entry_indicator": "EMA", "period": 14, "threshold": 1.0}, candles)
    assert "sharpe" in result and "pnl" in result

check("BacktestLab fonctionnel", _test_backtest)

def _test_walk_forward():
    import random
    from quant_hedge_ai.agents.quant.walk_forward import WalkForwardValidator
    random.seed(0)
    price = 100.0
    candles = []
    for i in range(200):
        price = max(price * (1 + random.gauss(0, 0.01)), 1.0)
        candles.append({"open": price, "high": price * 1.005, "low": price * 0.995,
                        "close": price, "volume": 1000.0})
    validator = WalkForwardValidator()
    result = validator.validate({"entry_indicator": "RSI", "period": 14, "threshold": 1.0}, candles)
    assert result.verdict in ("ROBUSTE", "ACCEPTABLE", "SUSPECT", "OVERFIT")

check("WalkForwardValidator fonctionnel", _test_walk_forward)

# ── 4. Couche sécurité ────────────────────────────────────────────────────────
print("\n[4/5] Couche sécurité")

def _test_dedup():
    from quant_hedge_ai.agents.execution.order_deduplicator import OrderDeduplicator
    d = OrderDeduplicator(window_seconds=10)
    assert not d.is_duplicate("BTC/USDT", "BUY", 1.0)
    d.register("BTC/USDT", "BUY", 1.0)
    assert d.is_duplicate("BTC/USDT", "BUY", 1.0)

check("OrderDeduplicator fonctionnel", _test_dedup)

def _test_session_guard():
    from quant_hedge_ai.agents.risk.session_guard import SessionGuard, SessionHaltedError
    g = SessionGuard(max_consecutive_losses=2, max_session_drawdown=0.99, max_session_loss=0.99)
    g.start_session(1000.0)
    g.record_trade(-10, 990)
    g.record_trade(-10, 980)
    assert g.is_halted
    try:
        g.check_order("BTC/USDT", "BUY", 10.0)
        assert False, "aurait dû lever SessionHaltedError"
    except SessionHaltedError:
        pass

check("SessionGuard fonctionnel", _test_session_guard)

def _test_trade_logger():
    from quant_hedge_ai.agents.execution.trade_logger import TradeLogger
    with tempfile.TemporaryDirectory() as tmp:
        tl = TradeLogger(db_path=os.path.join(tmp, "log.sqlite"))
        tl.log({"symbol": "BTC/USDT", "action": "BUY", "size": 0.1, "mode": "paper"})
        tl.log_rejected("ETH/USDT", "BUY", 500.0, "ordre trop grand")
        stats = tl.stats()
        assert stats["total_trades"] == 2
        assert stats["rejected"] == 1

check("TradeLogger fonctionnel", _test_trade_logger)

def _test_execution_engine():
    from quant_hedge_ai.agents.execution.execution_engine import ExecutionEngine
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["EXEC_TRADE_LOG"] = os.path.join(tmp, "t.sqlite")
        os.environ["EXEC_DEDUP_WINDOW"] = "5"
        eng = ExecutionEngine(live=False)
        eng.start_session(1000.0)
        r = eng.create_order("BTC/USDT", "BUY", 0.1)
        assert r["mode"] == "paper"
        r2 = eng.create_order("BTC/USDT", "BUY", 0.1)
        assert r2["mode"] == "rejected"
        del os.environ["EXEC_TRADE_LOG"]
        del os.environ["EXEC_DEDUP_WINDOW"]

check("ExecutionEngine pipeline complet", _test_execution_engine)

# ── 5. Monitoring ─────────────────────────────────────────────────────────────
print("\n[5/5] Monitoring opérationnel")

def _test_ops_notifier():
    from supervision.notifications.ops_notifier import OpsNotifier
    n = OpsNotifier(bot_token="", chat_id="")
    assert not n.enabled
    n.crash("test", ValueError("boom"))
    n.session_halt("drawdown 6%")
    n.ws_disconnect("BTC/USDT", 90.0)
    n.order_rejected("BTC/USDT", "BUY", 0.1, "trop grand")
    n.live_order_failed("BTC/USDT", "BUY", "InsufficientFunds")

check("OpsNotifier (mode silencieux)", _test_ops_notifier)

def _test_ops_watchdog():
    import time
    from supervision.ops_watchdog import OpsWatchdog
    w = OpsWatchdog(notifier=None)
    w.on_order_result({"mode": "paper", "symbol": "BTC/USDT", "action": "BUY", "size": 0.1})
    stale = not w.check_ws_staleness("BTC/USDT", time.time() - 10, threshold_seconds=120.0)
    assert stale, "données fraîches détectées comme stales"
    alerte = w.check_ws_staleness("BTC/USDT", time.time() - 200, threshold_seconds=120.0)
    assert alerte, "données stales non détectées"

check("OpsWatchdog fonctionnel", _test_ops_watchdog)

# ── Résultat final ────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"  Réussis : {len(_PASS)}/{len(_PASS)+len(_FAIL)}")
if _FAIL:
    print(f"  Echecs  : {', '.join(_FAIL)}")
    print("='*50}")
    sys.exit(1)
else:
    print("  Tous les checks OK — smoke test réussi.")
    print(f"{'='*50}\n")
    sys.exit(0)
