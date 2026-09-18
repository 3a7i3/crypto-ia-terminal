from pathlib import Path

import pytest

from paper_trading.mexc_simulator import MexcSimulator, OrderStatus
from paper_trading.paper_authority import (
    PaperAuthorityConfigError,
    PaperLifecycleAuthority,
    parse_paper_lifecycle_authority,
    resolve_paper_lifecycle_authority,
)


def test_r1_default_preserves_legacy_authority():
    assert (
        resolve_paper_lifecycle_authority({})
        is PaperLifecycleAuthority.LEGACY_AUTHORITY
    )
    assert parse_paper_lifecycle_authority("") is PaperLifecycleAuthority.LEGACY_AUTHORITY


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("legacy", PaperLifecycleAuthority.LEGACY_AUTHORITY),
        ("LEGACY_AUTHORITY", PaperLifecycleAuthority.LEGACY_AUTHORITY),
        ("shadow", PaperLifecycleAuthority.PPL_SHADOW),
        ("PPL_SHADOW", PaperLifecycleAuthority.PPL_SHADOW),
        ("ppl", PaperLifecycleAuthority.PPL_AUTHORITY),
        ("PPL_AUTHORITY", PaperLifecycleAuthority.PPL_AUTHORITY),
    ],
)
def test_r1_authority_vocabulary_is_closed(raw, expected):
    assert parse_paper_lifecycle_authority(raw) is expected


def test_r1_invalid_authority_fails_closed():
    with pytest.raises(PaperAuthorityConfigError):
        parse_paper_lifecycle_authority("dual")


def test_r1_ppl_authority_blocks_legacy_market_mutation(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_TRADE_LOG", str(tmp_path / "paper.jsonl"))
    sim = MexcSimulator(lifecycle_authority=PaperLifecycleAuthority.PPL_AUTHORITY)
    sim._capital = 100.0
    sim._initial_capital = 100.0

    order = sim.place_market_order(
        symbol="BTC/USDT",
        side="BUY",
        qty_usd=10.0,
        current_price=100.0,
        decision_id="decision-1",
    )

    assert order is not None
    assert order.status is OrderStatus.REJECTED
    assert sim._positions == {}
    assert sim._capital == pytest.approx(100.0)
    assert not (tmp_path / "paper.jsonl").exists()


@pytest.mark.parametrize("kind", ["limit", "stop_limit"])
def test_r1_ppl_authority_blocks_pending_legacy_orders(kind):
    sim = MexcSimulator(lifecycle_authority=PaperLifecycleAuthority.PPL_AUTHORITY)
    if kind == "limit":
        order = sim.place_limit_order(
            symbol="ETH/USDT",
            side="BUY",
            qty_usd=10.0,
            limit_price=100.0,
        )
    else:
        order = sim.place_stop_limit_order(
            symbol="ETH/USDT",
            side="BUY",
            qty_usd=10.0,
            stop_price=101.0,
            limit_price=100.0,
        )

    assert order.status is OrderStatus.REJECTED
    assert sim._orders == {}


def test_r1_shadow_keeps_legacy_mutation_authority(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPER_TRADE_LOG", str(tmp_path / "paper.jsonl"))
    sim = MexcSimulator(lifecycle_authority=PaperLifecycleAuthority.PPL_SHADOW)
    sim._capital = 100.0
    sim._initial_capital = 100.0

    order = sim.place_market_order(
        symbol="SOL/USDT",
        side="BUY",
        qty_usd=10.0,
        current_price=100.0,
    )

    assert order is not None
    assert order.status is OrderStatus.FILLED
    assert "SOL/USDT" in sim._positions


def test_r1_advisor_suppresses_only_secondary_position_manager_paper_lifecycle():
    source = Path("core/advisor_loop.py").read_text(encoding="utf-8")
    assert 'if result_mode == "paper" and _paper_trading_enabled:' in source
    assert "secondary PositionManager PAPER lifecycle" in source


def test_r1_advisor_bootstrap_fails_before_legacy_dataset_gate_for_ppl_authority():
    source = Path("core/advisor_loop.py").read_text(encoding="utf-8")
    helper_start = source.index("def _bootstrap_paper_lifecycle_authority(")
    helper_end = source.index("def _op_legacy_first_blocker(", helper_start)
    helper = source[helper_start:helper_end]
    resolve_pos = helper.index("resolve_paper_lifecycle_authority(os.environ)")
    barrier_pos = helper.index("if authority.ppl_is_authoritative:")
    gate_pos = helper.index("_gate_paper_dataset()")
    assert resolve_pos < barrier_pos < gate_pos
    assert "PPL_AUTHORITY is not runtime-ready" in helper
