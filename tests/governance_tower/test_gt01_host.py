"""GOV-TOWER-01 M2 — observation des snapshots publiés : contrôles supplémentaires (FIXTURES UNIQUEMENT).

Aucune lecture VPS réelle : transports factices et répertoires temporaires. La
preuve du connecteur distant (gate GT01-V) reste NOT_PROVEN.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from governance_tower.contracts import Availability, ContractError
from governance_tower.providers.host import (
    FixtureHostProvider,
    HttpReponse,
    OperatorApiHostProvider,
    SnapshotDirectoryHostProvider,
    fixture_path,
)
from tests.governance_tower.test_gt_host_provider import (
    NOW,
    clock,
    fresh_docs,
    obs_of,
    stamp,
    transport_doc,
    write_dir,
)

BASE = "http://127.0.0.1:18080"
JSON = {"Content-Type": "application/json; charset=utf-8"}


class Scripted:
    """Réponses successives par route ; chaque appel consomme la suivante."""

    def __init__(self, **routes):
        self.routes = {k: list(v) for k, v in routes.items()}
        self.calls: list[str] = []

    def __call__(self, url, timeout_s, max_bytes):
        self.calls.append(url)
        key = url.rsplit("/", 1)[1].replace("-", "_")
        item = self.routes[key].pop(0) if len(self.routes[key]) > 1 else self.routes[key][0]
        if isinstance(item, BaseException):
            raise item
        return item


def ok(doc, headers=JSON, age=5.0, cls="FRESH"):
    return HttpReponse(200, transport_doc(doc, age, cls), headers)


def api(transport, **kw):
    return OperatorApiHostProvider(BASE, clock(), transport=transport, **kw)


# ── Identité d'hôte ──────────────────────────────────────────────────────────


def test_expected_host_id_mismatch_refuses_runtime_but_keeps_storage():
    rs, st = fresh_docs()
    snap = api(Scripted(runtime_service=[ok(rs)], storage=[ok(st)]), expected_host_id="crypto-advisor-2").host_snapshot()
    assert snap.availability is Availability.ERROR and snap.reason == "HOST_MISMATCH"
    assert snap.deployed_source_sha is None
    assert obs_of(snap, "host.service").value is None
    assert obs_of(snap, "host.storage").availability is Availability.AVAILABLE  # champ restant prouvé conservé


def test_expected_host_id_match_is_accepted():
    rs, st = fresh_docs()
    snap = api(Scripted(runtime_service=[ok(rs)], storage=[ok(st)]), expected_host_id=rs["host_id"]).host_snapshot()
    assert snap.availability is Availability.AVAILABLE and snap.deployed_source_sha is not None


@pytest.mark.parametrize("bad", ["", "a b", "x" * 200, 42, "../etc"])
def test_expected_host_id_is_validated(bad):
    with pytest.raises(ContractError):
        api(Scripted(), expected_host_id=bad)


def test_directory_provider_checks_host_identity(tmp_path):
    rs, st = fresh_docs()
    snap = SnapshotDirectoryHostProvider(write_dir(tmp_path, rs, st), clock(), expected_host_id="autre-hote").host_snapshot()
    assert snap.reason == "HOST_MISMATCH"


# ── Monotonicité (rejeu, cache inversé) ──────────────────────────────────────


def test_snapshot_going_back_in_time_is_refused():
    new_rs, new_st = fresh_docs(NOW - timedelta(seconds=10))
    old_rs, old_st = fresh_docs(NOW - timedelta(seconds=40))
    t = Scripted(runtime_service=[ok(new_rs), ok(old_rs)], storage=[ok(new_st), ok(old_st)])
    p = api(t)
    first = p.host_snapshot()
    assert first.availability is Availability.AVAILABLE
    second = p.host_snapshot()
    assert second.availability is Availability.ERROR and second.reason == "NON_MONOTONIC"
    assert obs_of(second, "host.storage").reason == "NON_MONOTONIC"
    assert all(o.value is None for o in second.observations if o.observation_id != "host.journaux")


def test_same_snapshot_twice_is_accepted():
    rs, st = fresh_docs()
    p = api(Scripted(runtime_service=[ok(rs)], storage=[ok(st)]))
    p.host_snapshot()
    assert p.host_snapshot().availability is Availability.AVAILABLE


# ── En-têtes HTTP ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ctype", ["text/html", "application/javascript", ""])
def test_unexpected_content_type_is_error(ctype):
    rs, st = fresh_docs()
    snap = api(Scripted(runtime_service=[ok(rs, {"Content-Type": ctype})], storage=[ok(st)])).host_snapshot()
    assert snap.reason == "UNEXPECTED_CONTENT_TYPE" and snap.deployed_source_sha is None


def test_safe_etag_is_recorded_as_evidence_and_unsafe_one_ignored():
    rs, st = fresh_docs()
    headers = {**JSON, "ETag": '"abc123"'}
    forged = {**JSON, "ETag": '"<script>"; injected'}
    snap = api(Scripted(runtime_service=[ok(rs, headers)], storage=[ok(st, forged)])).host_snapshot()
    assert obs_of(snap, "host.service").evidence[0].note == 'via Operator API · ETag "abc123"'
    assert obs_of(snap, "host.storage").evidence[0].note == "via Operator API"


def test_malformed_headers_are_transport_error():
    rs, st = fresh_docs()
    bad = HttpReponse(200, transport_doc(rs), headers=["not", "a", "mapping"])  # type: ignore[arg-type]
    snap = api(Scripted(runtime_service=[bad], storage=[ok(st)])).host_snapshot()
    assert snap.reason == "TRANSPORT_ERROR"


# ── Matrice de défaillances partielles ───────────────────────────────────────


@pytest.mark.parametrize(
    "response, availability, reason",
    [
        (HttpReponse(401, b"{}"), Availability.DENIED, "DENIED"),
        (HttpReponse(403, b"{}"), Availability.DENIED, "DENIED"),
        (HttpReponse(404, b"{}"), Availability.NOT_AVAILABLE, "HTTP_404"),
        (HttpReponse(429, b"{}"), Availability.RATE_LIMITED, "RATE_LIMITED"),
        (HttpReponse(500, b"{}"), Availability.ERROR, "HTTP_500"),
        (HttpReponse(301, b""), Availability.ERROR, "REDIRECT_REFUSED"),
        (HttpReponse(200, b'{"truncated": '), Availability.ERROR, "INVALID_JSON"),
        (TimeoutError(), Availability.NOT_AVAILABLE, "TIMEOUT"),
    ],
)
def test_storage_failure_keeps_proven_runtime_fields(response, availability, reason):
    rs, _ = fresh_docs()
    snap = api(Scripted(runtime_service=[ok(rs)], storage=[response])).host_snapshot()
    storage = obs_of(snap, "host.storage")
    assert (storage.availability, storage.reason, storage.value) == (availability, reason, None)
    assert snap.availability is Availability.AVAILABLE and snap.deployed_source_sha == rs["deployment"]["source_code_sha"]
    assert obs_of(snap, "host.service").value["active_state"] == "active"


def test_denied_is_never_converted_to_zero_or_success():
    snap = api(Scripted(runtime_service=[HttpReponse(403, b'{"active_state":"active"}')],
                        storage=[HttpReponse(401, b'{"total_bytes":0}')])).host_snapshot()
    assert snap.availability is Availability.DENIED
    assert all(o.value is None for o in snap.observations)
    assert "0" not in json.dumps([o.value for o in snap.observations])


def test_future_clock_and_forged_payload():
    rs, st = fresh_docs(NOW + timedelta(hours=2))
    snap = api(Scripted(runtime_service=[ok(rs)], storage=[ok(st)])).host_snapshot()
    assert snap.reason == "FUTURE_TIMESTAMP" and snap.deployed_source_sha is None
    rs, st = fresh_docs()
    rs["deployment"]["source_code_sha"] = "NOT-A-SHA"
    snap = api(Scripted(runtime_service=[ok(rs)], storage=[ok(st)])).host_snapshot()
    assert snap.reason == "CONTRACT_INVALID"


def test_stale_server_cache_is_stale_not_current():
    rs, st = fresh_docs()
    snap = api(Scripted(runtime_service=[ok(rs, age=3600.0, cls="STALE")], storage=[ok(st, age=3600.0, cls="STALE")])).host_snapshot()
    assert snap.availability is Availability.STALE
    assert obs_of(snap, "host.service").freshness_age_s == 3600.0


# ── Fixtures SYNTHETIC nouvelles ─────────────────────────────────────────────


def test_no_deployment_id_fixture():
    snap = FixtureHostProvider(fixture_path("no_deployment_id"), clock()).host_snapshot()
    assert snap.availability is Availability.AVAILABLE and snap.deployed_source_sha is None
    dep = obs_of(snap, "host.deployment")
    assert dep.availability is Availability.NOT_AVAILABLE and dep.reason == "NO_EVIDENCE"


def test_partial_fixture_one_fresh_snapshot():
    snap = FixtureHostProvider(fixture_path("partial"), clock()).host_snapshot()
    assert obs_of(snap, "host.service").availability is Availability.AVAILABLE
    storage = obs_of(snap, "host.storage")
    assert storage.availability is Availability.STALE and storage.freshness_age_s > 3600


def test_no_real_host_access_in_tests():
    """Garde-fou : les tests M2 n'utilisent que loopback factice et fichiers temporaires."""
    assert BASE.startswith("http://127.0.0.1:") and stamp(NOW).endswith("Z")
