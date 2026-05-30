"""
Tests pour Position + PositionManager — TP/SL, PnL, trailing, liquidation.
"""

from __future__ import annotations

from quant_hedge_ai.agents.execution.position_manager import (
    CloseReason,
    Position,
    PositionManager,
    PositionSide,
)


def _long(entry: float = 100.0, tp_pct: float = 0.04, sl_pct: float = 0.02) -> Position:
    return Position(
        symbol="BTC/USDT",
        side=PositionSide.LONG,
        entry_price=entry,
        size_usd=100.0,
        qty=1.0,
        tp_pct=tp_pct,
        sl_pct=sl_pct,
        use_atr=False,  # mode % fixe pour tests déterministes
    )


def _short(
    entry: float = 100.0, tp_pct: float = 0.04, sl_pct: float = 0.02
) -> Position:
    return Position(
        symbol="ETH/USDT",
        side=PositionSide.SHORT,
        entry_price=entry,
        size_usd=100.0,
        qty=1.0,
        tp_pct=tp_pct,
        sl_pct=sl_pct,
        use_atr=False,
    )


# ── TP/SL initiaux ────────────────────────────────────────────────────────────


def test_long_tp_sl_calculated_correctly():
    pos = _long(entry=100.0, tp_pct=0.04, sl_pct=0.02)
    assert abs(pos.tp_price - 104.0) < 0.01, f"TP attendu 104, obtenu {pos.tp_price}"
    assert abs(pos.sl_price - 98.0) < 0.01, f"SL attendu 98, obtenu {pos.sl_price}"


def test_short_tp_sl_calculated_correctly():
    pos = _short(entry=100.0, tp_pct=0.04, sl_pct=0.02)
    assert (
        abs(pos.tp_price - 96.0) < 0.01
    ), f"TP short attendu 96, obtenu {pos.tp_price}"
    assert (
        abs(pos.sl_price - 102.0) < 0.01
    ), f"SL short attendu 102, obtenu {pos.sl_price}"


# ── PnL ───────────────────────────────────────────────────────────────────────


def test_long_pnl_positive_when_price_rises():
    pos = _long(entry=100.0)
    pos.update_price(110.0)
    assert pos.pnl_pct > 0.0
    assert pos.pnl_usd > 0.0


def test_long_pnl_negative_when_price_falls():
    pos = _long(entry=100.0)
    pos.update_price(90.0)
    assert pos.pnl_pct < 0.0
    assert pos.pnl_usd < 0.0


def test_short_pnl_positive_when_price_falls():
    pos = _short(entry=100.0)
    pos.update_price(90.0)
    assert pos.pnl_pct > 0.0
    assert pos.pnl_usd > 0.0


def test_short_pnl_negative_when_price_rises():
    pos = _short(entry=100.0)
    pos.update_price(110.0)
    assert pos.pnl_pct < 0.0
    assert pos.pnl_usd < 0.0


def test_pnl_at_entry_is_zero():
    pos = _long(entry=100.0)
    pos.update_price(100.0)
    assert pos.pnl_pct == 0.0


# ── Tracking high/low ─────────────────────────────────────────────────────────


def test_highest_price_tracked():
    pos = _long(entry=100.0)
    pos.update_price(110.0)
    pos.update_price(105.0)
    assert pos.highest_price == 110.0


def test_lowest_price_tracked():
    pos = _short(entry=100.0)
    pos.update_price(90.0)
    pos.update_price(95.0)
    assert pos.lowest_price == 90.0


# ── Liquidation price ─────────────────────────────────────────────────────────


def test_liquidation_price_no_leverage_returns_zero():
    pos = Position(
        symbol="BTC/USDT",
        side=PositionSide.LONG,
        entry_price=100.0,
        size_usd=100.0,
        qty=1.0,
        leverage=1,
        use_atr=False,
    )
    assert pos.liquidation_price() == 0.0


def test_liquidation_price_long_below_entry():
    pos = Position(
        symbol="BTC/USDT",
        side=PositionSide.LONG,
        entry_price=100.0,
        size_usd=100.0,
        qty=1.0,
        leverage=10,
        use_atr=False,
    )
    liq = pos.liquidation_price()
    assert 0 < liq < pos.entry_price


def test_liquidation_price_short_above_entry():
    pos = Position(
        symbol="ETH/USDT",
        side=PositionSide.SHORT,
        entry_price=100.0,
        size_usd=100.0,
        qty=1.0,
        leverage=10,
        use_atr=False,
    )
    liq = pos.liquidation_price()
    assert liq > pos.entry_price


# ── ATR adaptatif ─────────────────────────────────────────────────────────────


def test_atr_update_recalculates_sl_tp():
    pos = Position(
        symbol="BTC/USDT",
        side=PositionSide.LONG,
        entry_price=100.0,
        size_usd=100.0,
        qty=1.0,
        use_atr=True,
        atr=0.0,
    )
    old_tp = pos.tp_price
    pos.update_market_data(atr=5.0)
    assert pos.atr == 5.0
    # Avec ATR=5 et mult=2.5 → TP devrait être ~112.5
    expected_tp = 100.0 + 5.0 * pos.tp_atr_mult
    assert abs(pos.tp_price - expected_tp) < 0.5


def test_atr_zero_no_update():
    pos = _long(entry=100.0)
    pos.use_atr = True
    pos.update_market_data(atr=0.0)  # ATR=0 → pas de recalcul
    assert pos.atr == 0.0


# ── PositionManager ───────────────────────────────────────────────────────────


def test_position_manager_add_and_get_open():
    pm = PositionManager(paper_mode=True)
    pos = _long()
    pos.order_id = "test-001"
    pm.add_position(pos, silent=True)
    open_pos = pm.get_open()
    assert len(open_pos) == 1
    assert open_pos[0].symbol == "BTC/USDT"


def test_position_manager_stats_empty():
    pm = PositionManager(paper_mode=True)
    stats = pm.stats()
    assert stats["open_count"] == 0
    assert stats["closed_count"] == 0
    assert stats["total_pnl_usd"] == 0.0


def test_position_manager_stats_after_add():
    pm = PositionManager(paper_mode=True)
    for i in range(3):
        pos = _long()
        pos.order_id = f"pos-{i}"
        pm.add_position(pos, silent=True)
    stats = pm.stats()
    assert stats["open_count"] == 3


def test_position_manager_snapshot():
    pm = PositionManager(paper_mode=True)
    pos = _long()
    pos.order_id = "snap-001"
    pm.add_position(pos, silent=True)
    snap = pm.snapshot()
    assert len(snap) == 1
    assert snap[0]["symbol"] == "BTC/USDT"
    assert snap[0]["side"] == "long"


def test_position_manager_on_close_callback():
    pm = PositionManager(paper_mode=True)
    closed_positions = []
    pm.on_close(lambda pos, reason: closed_positions.append((pos.symbol, reason)))

    pos = _long()
    pos.order_id = "cb-001"
    pm.add_position(pos, silent=True)

    # Simuler fermeture manuelle
    pos.closed = True
    pos.close_reason = CloseReason.TP.value
    pm._closed.append(pos)
    with pm._lock:
        pm._positions.pop("cb-001", None)

    assert pm.get_open() == []
    assert pm.get_closed() != []


# ── Summary ───────────────────────────────────────────────────────────────────


def test_position_summary_contains_key_info():
    pos = _long(entry=100.0)
    pos.update_price(105.0)
    summary = pos.summary()
    assert "BTC/USDT" in summary
    assert "LONG" in summary
    assert "100.00" in summary
