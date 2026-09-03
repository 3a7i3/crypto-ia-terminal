import copy
from datetime import datetime, timezone

from observability.operator.contracts import FreshnessStatus, observed
from observability.operator.domains.operator_summary import compose_operator_summary
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
