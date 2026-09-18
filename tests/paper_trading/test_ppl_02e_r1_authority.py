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


def test_r1_ppl_authority_without_runtime_fails_closed_at_construction():
    """R4 supersedes R1's temporary rejected-order shim with a harder boundary."""
    with pytest.raises(ValueError, match="requires an authority_runtime"):
        MexcSimulator(lifecycle_authority=PaperLifecycleAuthority.PPL_AUTHORITY)


def test_r1_pending_legacy_orders_remain_blocked_when_ppl_runtime_exists():
    # The runtime object is intentionally opaque here: LIMIT/STOP_LIMIT are
    # rejected before any authoritative runtime method can be invoked.
    sim = MexcSimulator(
        lifecycle_authority=PaperLifecycleAuthority.PPL_AUTHORITY,
        authority_runtime=object(),
    )
    limit_order = sim.place_limit_order(
        symbol="ETH/USDT",
        side="BUY",
        qty_usd=10.0,
        limit_price=100.0,
    )
    stop_order = sim.place_stop_limit_order(
        symbol="SOL/USDT",
        side="BUY",
        qty_usd=10.0,
        stop_price=101.0,
        limit_price=100.0,
    )

    assert limit_order.status is OrderStatus.REJECTED
    assert stop_order.status is OrderStatus.REJECTED
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


def test_r1_advisor_bootstrap_preserves_single_authority_barrier():
    """R4 replaces the temporary R1 block with explicit authority-runtime binding."""
    source = Path("core/advisor_loop.py").read_text(encoding="utf-8")
    helper_start = source.index("def _bootstrap_paper_lifecycle_authority(")
    helper_end = source.index("def _op_legacy_first_blocker(", helper_start)
    helper = source[helper_start:helper_end]

    resolve_pos = helper.index("resolve_paper_lifecycle_authority(os.environ)")
    authority_pos = helper.index("if authority.ppl_is_authoritative:")
    runtime_pos = helper.index("build_authority_runtime_from_env()")
    bind_pos = helper.index("authority_runtime.bind(now=time.time())")
    rollback_pos = helper.index("configured_rollback_disposition()")
    gate_pos = helper.index("_gate_paper_dataset()")

    assert resolve_pos < authority_pos < runtime_pos < bind_pos
    assert bind_pos < rollback_pos < gate_pos
    assert "PPL_AUTHORITY requires PAPER_TRADING_ENABLED=true" in helper
    assert "return authority, authority_runtime" in helper
