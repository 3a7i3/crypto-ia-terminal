import copy
from datetime import datetime, timezone

import pytest

from observability.operator.contracts import DOMAIN_STATUSES, FreshnessStatus, observed
from observability.operator.domains.operator_summary import (
    _HEALTHY_STATUSES,
    _aggregate_freshness,
    compose_operator_summary,
)
from observability.operator.domains.system_health import compose_system_health_snapshot

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


def _healthy_system_health_snapshot():
    return compose_system_health_snapshot(
        observed_at_utc=NOW,
        boot_alive=observed(True),
        health_score=observed(95.0),
        health_level=observed("HEALTHY"),
        exchange_connectivity_healthy=observed(True),
        exchange_latency_ms=observed(20.0),
        module_statuses={"advisor_loop": "HEALTHY"},
        freshness=FreshnessStatus.FRESH,
        status="OK",
    )


def test_operator_summary_marks_missing_domains_as_needing_attention():
    summary = compose_operator_summary(observed_at_utc=NOW, system_health=_healthy_system_health_snapshot())
    by_domain = {c.domain: c for c in summary.components}
    assert by_domain["system_health"].needs_attention is False
    assert by_domain["market_state"].status == "UNAVAILABLE"
    assert by_domain["market_state"].needs_attention is True
    assert summary.status == "ATTENTION_REQUIRED"


def test_operator_summary_ok_when_all_present_components_are_healthy():
    summary = compose_operator_summary(observed_at_utc=NOW, system_health=_healthy_system_health_snapshot())
    sh = next(c for c in summary.components if c.domain == "system_health")
    assert sh.status == "OK"
    assert sh.freshness == FreshnessStatus.FRESH


def test_operator_summary_does_not_mutate_source_snapshots():
    sh_snapshot = _healthy_system_health_snapshot()
    before = copy.deepcopy(sh_snapshot.to_dict())
    compose_operator_summary(observed_at_utc=NOW, system_health=sh_snapshot)
    after = sh_snapshot.to_dict()
    assert before == after


def test_operator_summary_does_not_invent_unavailable_domains():
    summary = compose_operator_summary(observed_at_utc=NOW)
    for component in summary.components:
        assert component.status == "UNAVAILABLE"
        assert component.freshness == FreshnessStatus.UNKNOWN


def test_operator_summary_has_no_opaque_global_score():
    summary = compose_operator_summary(observed_at_utc=NOW, system_health=_healthy_system_health_snapshot())
    assert summary.status in ("OK", "ATTENTION_REQUIRED")
    assert isinstance(summary.attention_items, tuple)
    for item in summary.attention_items:
        assert ":" in item  # domain-qualified, never a bare number


def test_operator_summary_schema_and_domain_are_valid():
    summary = compose_operator_summary(observed_at_utc=NOW, system_health=_healthy_system_health_snapshot())
    assert summary.domain == "operator_summary"
    assert summary.schema_version


def _snapshot_with(*, status: str, freshness: FreshnessStatus):
    return compose_system_health_snapshot(
        observed_at_utc=NOW,
        boot_alive=observed(True),
        health_score=observed(95.0),
        health_level=observed("HEALTHY"),
        exchange_connectivity_healthy=observed(True),
        exchange_latency_ms=observed(20.0),
        module_statuses={},
        freshness=freshness,
        status=status,
    )


# --- Blocker C remediation: explicit freshness severity, never a silent
# DEGRADED -> FRESH collapse (independent review, O01_REMEDIATION_REQUIRED
# §4). Required cases, verified both on the pure aggregation helper and
# end-to-end through compose_operator_summary. ---


def test_aggregate_freshness_all_fresh_is_fresh():
    assert _aggregate_freshness([FreshnessStatus.FRESH] * 3) == FreshnessStatus.FRESH


def test_aggregate_freshness_one_degraded_among_fresh_is_degraded():
    freshnesses = [FreshnessStatus.FRESH, FreshnessStatus.DEGRADED, FreshnessStatus.FRESH]
    assert _aggregate_freshness(freshnesses) == FreshnessStatus.DEGRADED


@pytest.mark.parametrize(
    "others",
    [
        [FreshnessStatus.DEGRADED, FreshnessStatus.FRESH],
        [FreshnessStatus.FRESH, FreshnessStatus.FRESH],
        [FreshnessStatus.DEGRADED, FreshnessStatus.DEGRADED],
    ],
)
def test_aggregate_freshness_stale_dominates_degraded_and_fresh(others):
    assert _aggregate_freshness([FreshnessStatus.STALE, *others]) == FreshnessStatus.STALE


@pytest.mark.parametrize(
    "others",
    [
        [FreshnessStatus.FRESH],
        [FreshnessStatus.DEGRADED],
        [FreshnessStatus.STALE],
        [FreshnessStatus.FRESH, FreshnessStatus.DEGRADED, FreshnessStatus.STALE],
    ],
)
def test_aggregate_freshness_unknown_dominates_all_other_states(others):
    # UNKNOWN outranks even STALE: not knowing whether a domain is fresh
    # is strictly less actionable than a domain confirmed stale.
    assert _aggregate_freshness([FreshnessStatus.UNKNOWN, *others]) == FreshnessStatus.UNKNOWN


def test_aggregate_freshness_not_applicable_mixed_with_fresh_does_not_degrade_it():
    freshnesses = [FreshnessStatus.NOT_APPLICABLE, FreshnessStatus.FRESH]
    assert _aggregate_freshness(freshnesses) == FreshnessStatus.FRESH


def test_aggregate_freshness_not_applicable_mixed_with_degraded_still_reports_degraded():
    freshnesses = [FreshnessStatus.NOT_APPLICABLE, FreshnessStatus.DEGRADED]
    assert _aggregate_freshness(freshnesses) == FreshnessStatus.DEGRADED


def test_aggregate_freshness_all_not_applicable_is_not_applicable_not_invented_fresh():
    freshnesses = [FreshnessStatus.NOT_APPLICABLE, FreshnessStatus.NOT_APPLICABLE]
    assert _aggregate_freshness(freshnesses) == FreshnessStatus.NOT_APPLICABLE


def test_aggregate_freshness_of_empty_sequence_is_not_applicable():
    assert _aggregate_freshness([]) == FreshnessStatus.NOT_APPLICABLE


def test_operator_summary_end_to_end_does_not_collapse_degraded_component_to_fresh():
    # This is the literal regression: under the old
    # UNKNOWN > STALE > (else FRESH) logic, a DEGRADED-only mix with no
    # STALE/UNKNOWN present silently became FRESH.
    summary = compose_operator_summary(
        observed_at_utc=NOW,
        system_health=_snapshot_with(status="OK", freshness=FreshnessStatus.DEGRADED),
    )
    # Every other domain is absent -> UNKNOWN (dominant), so isolate the
    # DEGRADED-vs-FRESH question directly on the aggregation helper using
    # the same components compose_operator_summary actually builds.
    only_present = [c.freshness for c in summary.components if c.domain == "system_health"]
    assert only_present == [FreshnessStatus.DEGRADED]
    assert _aggregate_freshness([FreshnessStatus.DEGRADED, FreshnessStatus.FRESH]) == FreshnessStatus.DEGRADED


# --- §5 remediation: status/needs_attention vocabulary audit ---


def test_healthy_statuses_is_a_subset_of_the_closed_domain_status_vocabulary():
    assert _HEALTHY_STATUSES <= DOMAIN_STATUSES


@pytest.mark.parametrize("status", sorted(DOMAIN_STATUSES))
def test_every_canonical_status_maps_to_the_expected_attention_flag(status):
    summary = compose_operator_summary(
        observed_at_utc=NOW,
        system_health=_snapshot_with(status=status, freshness=FreshnessStatus.FRESH),
    )
    component = next(c for c in summary.components if c.domain == "system_health")
    expected_needs_attention = status not in _HEALTHY_STATUSES
    assert component.needs_attention is expected_needs_attention, status


def test_domain_snapshot_rejects_a_status_outside_the_closed_vocabulary():
    with pytest.raises(ValueError):
        _snapshot_with(status="NOMINAL", freshness=FreshnessStatus.FRESH)
