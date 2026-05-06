from __future__ import annotations

import asyncio

import pytest

from event_bus.bus import EventBus
from event_bus.events import (
    IncidentResolvedEvent,
    IncidentStartedEvent,
    PieuvreRegrowthEvent,
    SecurityAlertEvent,
)
from pieuvre.brain import BrainState, PieuvreGigante
from pieuvre.incidents.models import Finding, Severity


@pytest.fixture(autouse=True)
def fresh_bus():
    EventBus.reset()
    yield EventBus.get()
    EventBus.reset()


def _finding(severity: Severity = Severity.HIGH) -> Finding:
    return Finding(
        file="danger.py",
        line=12,
        rule="eval_usage",
        message="eval detected",
        severity=severity,
        tentacle="securite",
    )


def test_pieuvre_builds_exactly_eight_named_tentacles(tmp_path):
    pieuvre = PieuvreGigante(repo_path=str(tmp_path))

    assert [t.name for t in pieuvre.tentacles] == [
        "securite",
        "audit_commits",
        "surveillance",
        "evolution",
        "memoire",
        "guerison",
        "performance",
        "resilience",
    ]


def test_enter_alert_emits_incident_and_security_events(tmp_path, fresh_bus):
    pieuvre = PieuvreGigante(repo_path=str(tmp_path))
    events = []
    fresh_bus.subscribe(IncidentStartedEvent, events.append)
    fresh_bus.subscribe(SecurityAlertEvent, events.append)

    asyncio.run(pieuvre._enter_alert(_finding(), [_finding()]))

    assert pieuvre.state is BrainState.ALERT
    assert [type(event) for event in events] == [
        IncidentStartedEvent,
        SecurityAlertEvent,
    ]
    assert events[1].rule == "eval_usage"


def test_alert_cycle_pauses_non_healing_tentacles(tmp_path):
    pieuvre = PieuvreGigante(repo_path=str(tmp_path))
    asyncio.run(pieuvre._enter_alert(_finding(), [_finding()]))

    asyncio.run(pieuvre._alert_cycle())

    assert pieuvre.state is BrainState.RECOVERY
    assert pieuvre._guerison.active is True
    assert all(not t.active for t in pieuvre.tentacles if t is not pieuvre._guerison)


def test_regrowth_resumes_tentacles_and_emits_events(tmp_path, fresh_bus):
    pieuvre = PieuvreGigante(repo_path=str(tmp_path))
    resolved = []
    regrowth = []
    fresh_bus.subscribe(IncidentResolvedEvent, resolved.append)
    fresh_bus.subscribe(PieuvreRegrowthEvent, regrowth.append)

    asyncio.run(pieuvre._enter_alert(_finding(), [_finding()]))
    asyncio.run(pieuvre._alert_cycle())
    pieuvre.state = BrainState.REGROWTH
    asyncio.run(pieuvre._regrowth_cycle())

    assert pieuvre.state is BrainState.ACTIVE
    assert pieuvre.force > 1.0
    assert all(t.active for t in pieuvre.tentacles)
    assert resolved and resolved[0].strength_gained > 0
    assert regrowth and regrowth[0].generation == pieuvre.generation


def test_active_cycle_enters_alert_for_high_severity(monkeypatch, tmp_path):
    pieuvre = PieuvreGigante(repo_path=str(tmp_path))

    async def fake_findings():
        return [_finding(Severity.HIGH)]

    monkeypatch.setattr(pieuvre, "_run_all_tentacles", fake_findings)

    asyncio.run(pieuvre._active_cycle())

    assert pieuvre.state is BrainState.ALERT
    assert pieuvre._active_incident is not None


def test_active_cycle_stays_active_for_medium_findings(monkeypatch, tmp_path):
    pieuvre = PieuvreGigante(repo_path=str(tmp_path))
    pieuvre.state = BrainState.ACTIVE

    async def fake_findings():
        return [_finding(Severity.MEDIUM)]

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(pieuvre, "_run_all_tentacles", fake_findings)
    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    asyncio.run(pieuvre._active_cycle())

    assert pieuvre.state is BrainState.ACTIVE
    assert pieuvre._active_incident is None
