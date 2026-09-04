import pytest

from observability.operator.contracts import FreshnessStatus
from observability.operator.freshness import classify_freshness


def test_no_observation_is_unknown():
    assert classify_freshness(None, fresh_threshold_s=60, stale_threshold_s=300) == FreshnessStatus.UNKNOWN


def test_no_thresholds_defined_is_unknown_never_invented():
    assert classify_freshness(5.0, fresh_threshold_s=None, stale_threshold_s=None) == FreshnessStatus.UNKNOWN


def test_within_fresh_threshold():
    assert classify_freshness(30, fresh_threshold_s=60, stale_threshold_s=300) == FreshnessStatus.FRESH


def test_boundary_is_fresh_inclusive():
    assert classify_freshness(60, fresh_threshold_s=60, stale_threshold_s=300) == FreshnessStatus.FRESH


def test_between_thresholds_is_degraded():
    assert classify_freshness(120, fresh_threshold_s=60, stale_threshold_s=300) == FreshnessStatus.DEGRADED


def test_beyond_stale_threshold():
    assert classify_freshness(999, fresh_threshold_s=60, stale_threshold_s=300) == FreshnessStatus.STALE


def test_rejects_negative_age():
    with pytest.raises(ValueError):
        classify_freshness(-1, fresh_threshold_s=60, stale_threshold_s=300)


def test_rejects_inverted_thresholds():
    with pytest.raises(ValueError):
        classify_freshness(10, fresh_threshold_s=300, stale_threshold_s=60)
