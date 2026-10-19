from copy import deepcopy
from decimal import Decimal

import pytest

from observability.burn_in_statistics import build_burn_in_statistics
from tests.test_burn_in_status_snapshot import _snapshot


def test_excludes_open_unresolved_and_keeps_source_boundary():
    snapshot = _snapshot()
    before = deepcopy(snapshot)
    result = build_burn_in_statistics(snapshot)
    assert snapshot == before
    assert result["population"] == dict(
        snapshot["lifecycle_counts"], wins=1, losses=0, breakeven=0
    )
    assert Decimal(result["metrics"]["net_realized_pnl_usd"]) == Decimal("0.98")
    assert result["metrics"]["profit_factor"] is None
    assert result["metrics"]["average_loss_usd"] is None
    assert result["ppl_stream_sha256"] == snapshot["ppl_stream_sha256"]


def test_mixed_net_results_include_breakeven_in_denominator():
    snapshot = _snapshot()
    row = next(r for r in snapshot["lifecycle_history"] if r["status"] == "CLOSED")
    snapshot["lifecycle_history"] = [
        dict(row, trade_id=str(i), net_realized_pnl_usd=n, gross_pnl_usd=n + 0.02)
        for i, n in enumerate([3.0, -1.0, 0.0, -0.5])
    ]
    snapshot["lifecycle_counts"] = dict(total=4, closed=4, open=0, unresolved=0)
    result = build_burn_in_statistics(snapshot)
    assert result["metrics"]["win_rate_pct"] == "25"
    assert result["metrics"]["profit_factor"] == "2"
    assert result["metrics"]["net_realized_pnl_usd"] == "1.5"
    assert result["metrics"]["average_loss_usd"] == "-0.75"
    assert result["population"]["breakeven"] == 1


def test_no_closures_is_not_zero_performance():
    snapshot = _snapshot()
    snapshot["lifecycle_history"] = [
        r for r in snapshot["lifecycle_history"] if r["status"] != "CLOSED"
    ]
    snapshot["lifecycle_counts"].update(total=2, closed=0)
    assert all(
        value is None
        for value in build_burn_in_statistics(snapshot)["metrics"].values()
    )


def test_incomplete_population_is_refused():
    snapshot = _snapshot()
    snapshot["lifecycle_history"].pop()
    with pytest.raises(ValueError, match="INCOMPLETE"):
        build_burn_in_statistics(snapshot)


def test_cancellation_does_not_erase_a_small_result():
    snapshot = _snapshot()
    row = next(r for r in snapshot["lifecycle_history"] if r["status"] == "CLOSED")
    snapshot["lifecycle_history"] = [
        dict(row, net_realized_pnl_usd=value) for value in [1e100, 1.0, -1e100]
    ]
    snapshot["lifecycle_counts"] = dict(total=3, closed=3, open=0, unresolved=0)
    assert (
        Decimal(build_burn_in_statistics(snapshot)["metrics"]["net_realized_pnl_usd"])
        == 1
    )
