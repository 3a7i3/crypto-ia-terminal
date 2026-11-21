from datetime import datetime, timedelta, timezone
from decimal import Decimal

from observability.market_stress import metrics
from observability.market_stress.models import TradeTape
from tests.market_stress.support import NOW, sha, tape

START = datetime(2026, 11, 20, 11, tzinfo=timezone.utc)


def make(events, *, resolution=1, kind="MATCHING_ENGINE"):
    return TradeTape(tuple(events), resolution, kind, START, START + timedelta(hours=1), sha("t"))


def ms(offset):
    return int(START.timestamp() * 1000) + offset


def test_all_trades_on_the_quarter_hour_give_full_share_and_exact_baseline():
    out = metrics.timing(make((ms(900_000 * (i % 4)), "0.5") for i in range(1000)))
    row = next(r for r in out["scan"] if (r["period_s"], r["radius_ms"]) == (900, 1000))
    assert out["status"] == "AVAILABLE" and out["events"] == 1000 and out["volume_base"] == "500.0"
    assert row["boundary_count_share"] == "1.00000000" and row["boundary_volume_share"] == "1.00000000"
    assert row["expected_share"] == "0.00222333"  # (2 x 1000 + 1) ms cells of 900 000
    assert row["placebo_events"] == 0
    # one-hour boundaries are also quarter-hour boundaries, but not the other way round
    hourly = next(r for r in out["scan"] if r["period_s"] == 3600)
    assert hourly["boundary_events"] == 250


def test_baseline_follows_the_declared_timestamp_grid():
    out = metrics.timing(make(((ms(900_000), "1") for _ in range(1000)), resolution=1000))
    row = next(r for r in out["scan"] if (r["period_s"], r["radius_ms"]) == (900, 500))
    assert row["expected_share"] == "0.00111111"  # a 1 s grid has a single cell within 500 ms: 1 of 900


def test_clustered_tape_beats_its_placebo_and_baseline_but_uniform_does_not():
    clustered = metrics.timing(tape(True))
    flat = metrics.timing(tape(False))
    def pick(out):
        return next(r for r in out["scan"] if (r["period_s"], r["radius_ms"]) == (900, 1000))
    assert Decimal(pick(clustered)["boundary_count_lift"]) > 20
    assert Decimal(pick(clustered)["placebo_count_lift"]) < 3
    assert Decimal(pick(flat)["boundary_count_lift"]) < 5
    assert sum(clustered["histogram"]["counts"]) == 5000
    assert len(clustered["histogram"]["counts"]) == 900


def test_refusals_are_typed_never_zero():
    good = [(ms(i * 1000), "1") for i in range(1000)]
    assert metrics.timing(None)["reason"] == "NO_TRADE_TAPE"
    assert metrics.timing(make(good, kind="RECEIPT"))["reason"] == "TIMESTAMP_KIND_NOT_MATCHING_ENGINE"
    assert metrics.timing(make(good[:999]))["reason"] == "SAMPLE_TOO_SMALL"
    assert metrics.timing(make(good, resolution=7))["reason"] == "RESOLUTION_NOT_ADMITTED"
    assert metrics.timing(make([(ms(1), "1")] * 1000, resolution=1000))["reason"] == "TIMESTAMP_NOT_ON_DECLARED_RESOLUTION"
    assert metrics.timing(make([(ms(-1000), "1")] * 1000))["reason"] == "EVENT_OUTSIDE_WINDOW"
    assert metrics.timing(make([(ms(0), "0")] * 1000))["reason"] == "EVENT_MALFORMED"
    assert metrics.timing(make([(ms(0), 1.5)] * 1000))["reason"] == "EVENT_MALFORMED"  # floats are never admitted
    assert metrics.timing(make([(ms(0), float("nan"))] * 1000))["reason"] == "EVENT_MALFORMED"


def test_annualised_basis_is_simple_and_refuses_expired_contracts():
    pct, why = metrics.annualized_basis("100.000000", NOW + timedelta(days=73), NOW)
    assert (pct, why) == ("5.000000", None)  # 100 bps over 73 days = 5 % per year, simple
    assert metrics.annualized_basis("1", NOW - timedelta(seconds=1), NOW)[1] == "EXPIRED_OR_EXPIRING"
    assert metrics.annualized_basis("1", None, NOW)[1] == "PERPETUAL_HAS_NO_EXPIRY"


def test_funding_conversion_labels():
    f = metrics.funding("0.0001", 3600, NOW + timedelta(minutes=5), NOW)
    assert f["rate_8h_equivalent"] == "0.0008000000" and f["annualized_simple_pct"] == "87.600000"
    assert metrics.funding("0.0001", 3600, NOW - timedelta(minutes=5), NOW)["reason"] == "NEXT_FUNDING_IN_PAST"
    assert metrics.funding(None, 3600, None, NOW)["reason"] == "FUNDING_RATE_MISSING"
    assert metrics.funding("0", 28_800, None, NOW)["rate"] == "0.0000000000"  # zero funding is a value, absence is not
