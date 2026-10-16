"""GT-M3 — observation hôte SANS POUVOIR (fixtures, snapshots locaux, Operator API)."""

from __future__ import annotations

import ast
import copy
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from governance_tower.contracts import (
    Availability,
    ContractError,
    Domain,
    HostSnapshot,
    Provenance,
)
from governance_tower.providers import HostObservationProvider
from governance_tower.providers import host as host_module
from governance_tower.providers.host import (
    FIXTURE_SCENARIOS,
    LIMITE_PONCTUELLE,
    FixtureHostProvider,
    HttpReponse,
    NotConfiguredHostProvider,
    OperatorApiHostProvider,
    SnapshotDirectoryHostProvider,
    fixture_path,
)
from observability.runtime_service_contract import validate_runtime_service_snapshot
from observability.storage_contract import validate_storage_snapshot

FROZEN_SHA = "116634be0d3c015cce1cfa58be7da7255414fbfd"
DRIFT_SHA = "de5e000000000000000000000000000000000bad"
NOW = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)


def clock(moment: datetime = NOW):
    return lambda: moment


def fixture_doc(scenario: str = "nominal") -> dict:
    return json.loads(fixture_path(scenario).read_text(encoding="utf-8"))


def obs_of(snapshot: HostSnapshot, observation_id: str):
    (found,) = [o for o in snapshot.observations if o.observation_id == observation_id]
    return found


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def fresh_docs(observed: datetime = NOW - timedelta(seconds=10)) -> tuple[dict, dict]:
    """Snapshots valides (contrats existants) observés à ``observed``."""
    nominal = fixture_doc("nominal")
    rs, st = copy.deepcopy(nominal["runtime_service"]), copy.deepcopy(nominal["storage"])
    for doc in (rs, st):
        doc["generated_at_utc"] = doc["observed_at_utc"] = stamp(observed)
    st["latest_file_modified_at_utc"] = stamp(observed - timedelta(seconds=30))
    assert validate_runtime_service_snapshot(rs) and validate_storage_snapshot(st)
    return rs, st


def write_dir(directory: Path, rs: dict | None = None, st: dict | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    if rs is not None:
        (directory / "runtime_service_snapshot.json").write_text(json.dumps(rs), encoding="utf-8")
    if st is not None:
        (directory / "storage_snapshot.json").write_text(json.dumps(st), encoding="utf-8")
    return directory


def assert_limits(snapshot: HostSnapshot) -> None:
    for o in snapshot.observations:
        assert LIMITE_PONCTUELLE in o.limits, o.observation_id


# ── Défaut : non configuré ────────────────────────────────────────────────────


def test_not_configured_is_default_and_carries_no_value():
    provider = NotConfiguredHostProvider(clock())
    assert isinstance(provider, HostObservationProvider)
    assert provider.info.live is False
    snap = provider.host_snapshot()
    assert snap.availability is Availability.NOT_AVAILABLE
    assert snap.reason == "VPS_NOT_CONFIGURED"
    assert snap.deployed_source_sha is None
    assert all(o.value is None and o.reason == "VPS_NOT_CONFIGURED" for o in snap.observations)
    assert all(not o.evidence for o in snap.observations)
    assert_limits(snap)


# ── Fixtures SYNTHETIC ────────────────────────────────────────────────────────


@pytest.mark.parametrize("scenario", FIXTURE_SCENARIOS)
def test_fixture_snapshots_pass_existing_validators_and_are_synthetic(scenario):
    data = fixture_doc(scenario)
    for name, validate in (("runtime_service", validate_runtime_service_snapshot), ("storage", validate_storage_snapshot)):
        if data[name] is not None:
            assert validate(data[name]), (scenario, name)
    provider = FixtureHostProvider(fixture_path(scenario), clock())
    assert isinstance(provider, HostObservationProvider)
    assert provider.info.provenance is Provenance.SYNTHETIC
    snap = provider.host_snapshot()
    evidence = [e for o in snap.observations for e in o.evidence]
    assert all(e.provenance is Provenance.SYNTHETIC for e in evidence)
    assert all(e.locator.startswith(f"fixture:host/{scenario}#") for e in evidence)
    assert_limits(snap)
    journaux = obs_of(snap, "host.journaux")
    assert journaux.reason == "NO_GOVERNED_LOG_PUBLISHER" and journaux.value is None


def test_fixture_nominal():
    snap = FixtureHostProvider(fixture_path("nominal"), clock()).host_snapshot()
    assert snap.availability is Availability.AVAILABLE
    assert snap.deployed_source_sha == FROZEN_SHA
    service = obs_of(snap, "host.service")
    assert service.value["active_state"] == "active" and service.value["sub_state"] == "running"
    assert "main_pid" not in service.value
    assert len(service.value["invocation_id_prefix"]) == 8
    assert service.freshness_age_s == pytest.approx(31.0)
    deployment = obs_of(snap, "host.deployment")
    assert deployment.value["source_code_sha"] == FROZEN_SHA
    assert deployment.evidence[0].source_sha == FROZEN_SHA
    assert deployment.evidence[0].locator == "fixture:host/nominal#runtime_service"
    storage = obs_of(snap, "host.storage")
    assert storage.availability is Availability.AVAILABLE and storage.value["matched_file_count"] == 12
    assert storage.evidence[0].locator == "fixture:host/nominal#storage"


def test_fixture_is_deterministic_regardless_of_injected_clock():
    a = FixtureHostProvider(fixture_path("nominal"), clock()).host_snapshot()
    b = FixtureHostProvider(fixture_path("nominal"), clock(NOW + timedelta(days=400))).host_snapshot()
    assert a == b


def test_fixture_drift_reports_observed_sha_without_judging():
    snap = FixtureHostProvider(fixture_path("drift"), clock()).host_snapshot()
    assert snap.availability is Availability.AVAILABLE
    assert snap.deployed_source_sha == DRIFT_SHA


def test_fixture_stale():
    snap = FixtureHostProvider(fixture_path("stale"), clock()).host_snapshot()
    assert snap.availability is Availability.STALE
    service = obs_of(snap, "host.service")
    assert service.availability is Availability.STALE and service.freshness_age_s == pytest.approx(1801.0)
    assert obs_of(snap, "host.storage").availability is Availability.STALE


def test_fixture_host_unavailable():
    snap = FixtureHostProvider(fixture_path("host_unavailable"), clock()).host_snapshot()
    assert snap.availability is Availability.NOT_AVAILABLE and snap.reason == "UNREACHABLE"
    assert snap.deployed_source_sha is None
    assert all(o.value is None for o in snap.observations)


def test_fixture_injection_is_quoted_untrusted_data():
    snap = FixtureHostProvider(fixture_path("injection"), clock()).host_snapshot()
    excerpt = obs_of(snap, "host.journal_excerpt")
    assert excerpt.domain is Domain.HOST_SERVICE and excerpt.subject == "journal_excerpt"
    assert excerpt.untrusted_content is True
    assert "SYSTEM:" in excerpt.value["text"]
    assert excerpt.evidence[0].locator == "fixture:host/injection#journal_excerpt"
    # Le contenu hostile ne modifie rien d'autre : même verdict que nominal.
    nominal = FixtureHostProvider(fixture_path("nominal"), clock()).host_snapshot()
    assert snap.availability is nominal.availability
    assert snap.deployed_source_sha == nominal.deployed_source_sha
    # Aucun fournisseur n'expose de méthode d'action.
    public = {n for n in dir(FixtureHostProvider) if not n.startswith("_")}
    assert public == {"info", "host_snapshot", "scenario"}


def test_fixture_injection_secret_is_redacted(tmp_path):
    data = fixture_doc("injection")
    data["journal_excerpt"] = "API_KEY=abcdef123456 puis Bearer abcdefghijklmnopqrstuvwxyz"
    path = tmp_path / "f.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    excerpt = obs_of(FixtureHostProvider(path, clock()).host_snapshot(), "host.journal_excerpt")
    assert "abcdef123456" not in excerpt.value["text"] and excerpt.value["redactions"] >= 2


def test_fixture_unknown_key_refused(tmp_path):
    data = fixture_doc("nominal")
    data["ssh_command"] = "x"
    path = tmp_path / "f.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ContractError, match="inconnus"):
        FixtureHostProvider(path, clock())


def test_fixture_symlink_and_size_refused(tmp_path):
    link = tmp_path / "link.json"
    link.symlink_to(fixture_path("nominal"))
    with pytest.raises(ContractError):
        FixtureHostProvider(link, clock())
    big = tmp_path / "big.json"
    big.write_text(" " * (256 * 1024 + 1))
    with pytest.raises(ContractError):
        FixtureHostProvider(big, clock())


def test_fixture_live_provenance_refused(tmp_path):
    data = fixture_doc("nominal")
    data["provenance"] = "LIVE_READ"
    path = tmp_path / "f.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ContractError):
        FixtureHostProvider(path, clock())


def test_fixture_invalid_embedded_contract_is_error(tmp_path):
    data = fixture_doc("nominal")
    data["runtime_service"]["service"]["unit"] = "other.service"
    data["storage"]["total_bytes"] = -1
    path = tmp_path / "f.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    snap = FixtureHostProvider(path, clock()).host_snapshot()
    assert snap.availability is Availability.ERROR and snap.reason == "CONTRACT_INVALID"
    assert snap.deployed_source_sha is None
    assert obs_of(snap, "host.service").reason == "CONTRACT_INVALID"
    assert obs_of(snap, "host.storage").reason == "CONTRACT_INVALID"


# ── Répertoire local de snapshots publiés ────────────────────────────────────


def test_directory_fresh(tmp_path):
    rs, st = fresh_docs()
    directory = write_dir(tmp_path / "snap", rs, st)
    (directory / "secrets.env").write_text("NE_PAS_LIRE")
    provider = SnapshotDirectoryHostProvider(directory, clock())
    assert isinstance(provider, HostObservationProvider)
    assert provider.info.provenance is Provenance.LIVE_READ and provider.info.live is True
    snap = provider.host_snapshot()
    assert snap.availability is Availability.AVAILABLE
    assert snap.deployed_source_sha == FROZEN_SHA
    assert snap.host_label == "VPS"
    service = obs_of(snap, "host.service")
    assert service.freshness_age_s == pytest.approx(10.0)
    ev = service.evidence[0]
    assert ev.locator == "snapshot:runtime_service" and ev.provenance is Provenance.LIVE_READ
    assert ev.observed_at_utc == rs["observed_at_utc"] and ev.source_sha == FROZEN_SHA
    import hashlib

    raw = (directory / "runtime_service_snapshot.json").read_bytes()
    assert ev.content_sha256 == hashlib.sha256(raw).hexdigest()
    storage = obs_of(snap, "host.storage")
    assert storage.evidence[0].locator == "snapshot:storage" and storage.evidence[0].source_sha is None
    assert storage.value["total_bytes"] == st["total_bytes"]
    assert obs_of(snap, "host.journaux").reason == "NO_GOVERNED_LOG_PUBLISHER"
    assert_limits(snap)


def test_directory_reads_only_the_two_snapshot_files(tmp_path, monkeypatch):
    rs, st = fresh_docs()
    directory = write_dir(tmp_path / "snap", rs, st)
    opened = []
    original = os.open

    def spy(path, flags, *args, **kwargs):
        opened.append(str(path))
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(host_module.os, "open", spy)
    SnapshotDirectoryHostProvider(directory, clock()).host_snapshot()
    assert opened == [str(directory), "runtime_service_snapshot.json", "storage_snapshot.json"]


def test_directory_missing_is_not_available(tmp_path):
    snap = SnapshotDirectoryHostProvider(tmp_path / "absent", clock()).host_snapshot()
    assert snap.availability is Availability.NOT_AVAILABLE and snap.reason == "SNAPSHOT_DIRECTORY_MISSING"
    assert snap.deployed_source_sha is None


def test_directory_symlink_refused(tmp_path):
    rs, st = fresh_docs()
    real = write_dir(tmp_path / "real", rs, st)
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    snap = SnapshotDirectoryHostProvider(alias, clock()).host_snapshot()
    assert snap.availability is Availability.ERROR and snap.reason == "INVALID_PATH"
    assert all(o.value is None for o in snap.observations)


def test_file_symlink_refused(tmp_path):
    rs, st = fresh_docs()
    real = write_dir(tmp_path / "real", rs, st)
    directory = write_dir(tmp_path / "snap", None, st)
    (directory / "runtime_service_snapshot.json").symlink_to(real / "runtime_service_snapshot.json")
    snap = SnapshotDirectoryHostProvider(directory, clock()).host_snapshot()
    assert snap.availability is Availability.ERROR and snap.reason == "INVALID_PATH"
    assert obs_of(snap, "host.storage").availability is Availability.AVAILABLE


def test_fifo_refused(tmp_path):
    directory = write_dir(tmp_path / "snap")
    os.mkfifo(directory / "runtime_service_snapshot.json")
    os.mkfifo(directory / "storage_snapshot.json")
    snap = SnapshotDirectoryHostProvider(directory, clock()).host_snapshot()
    assert snap.availability is Availability.ERROR and snap.reason == "INVALID_PATH"
    assert obs_of(snap, "host.storage").reason == "INVALID_PATH"


def test_oversized_files_refused(tmp_path):
    rs, st = fresh_docs()
    directory = write_dir(tmp_path / "snap")
    (directory / "runtime_service_snapshot.json").write_text(json.dumps(rs) + " " * 16_384)
    (directory / "storage_snapshot.json").write_text(json.dumps(st) + " " * (64 * 1024))
    snap = SnapshotDirectoryHostProvider(directory, clock()).host_snapshot()
    assert snap.reason == "OUTPUT_LIMIT"
    assert obs_of(snap, "host.storage").reason == "OUTPUT_LIMIT"


def test_storage_between_16_and_64_kib_accepted(tmp_path):
    rs, st = fresh_docs()
    directory = write_dir(tmp_path / "snap", rs)
    (directory / "storage_snapshot.json").write_text(json.dumps(st) + " " * 30_000)
    snap = SnapshotDirectoryHostProvider(directory, clock()).host_snapshot()
    assert obs_of(snap, "host.storage").availability is Availability.AVAILABLE


@pytest.mark.parametrize("payload", ["{not json", '{"a": 1, "a": 2}', '{"x": NaN}', "\xff"])
def test_invalid_json(tmp_path, payload):
    _, st = fresh_docs()
    directory = write_dir(tmp_path / "snap", None, st)
    (directory / "runtime_service_snapshot.json").write_bytes(payload.encode("latin-1"))
    snap = SnapshotDirectoryHostProvider(directory, clock()).host_snapshot()
    assert snap.availability is Availability.ERROR and snap.reason == "INVALID_JSON"
    assert obs_of(snap, "host.service").evidence[0].content_sha256 is not None


def test_invalid_contract(tmp_path):
    rs, st = fresh_docs()
    rs["service"]["unit"] = "ssh.service"
    st["extra"] = 1
    snap = SnapshotDirectoryHostProvider(write_dir(tmp_path / "snap", rs, st), clock()).host_snapshot()
    assert snap.availability is Availability.ERROR and snap.reason == "CONTRACT_INVALID"
    assert obs_of(snap, "host.storage").reason == "CONTRACT_INVALID"
    assert snap.deployed_source_sha is None


def test_missing_files(tmp_path):
    snap = SnapshotDirectoryHostProvider(write_dir(tmp_path / "snap"), clock()).host_snapshot()
    assert snap.availability is Availability.NOT_AVAILABLE and snap.reason == "MISSING"
    assert obs_of(snap, "host.storage").availability is Availability.NOT_AVAILABLE


def test_stale_snapshot(tmp_path):
    rs, st = fresh_docs(NOW - timedelta(minutes=30))
    snap = SnapshotDirectoryHostProvider(write_dir(tmp_path / "snap", rs, st), clock()).host_snapshot()
    assert snap.availability is Availability.STALE
    assert snap.deployed_source_sha == FROZEN_SHA
    assert obs_of(snap, "host.service").freshness_age_s == pytest.approx(1800.0)
    assert obs_of(snap, "host.storage").availability is Availability.STALE


def test_stale_threshold_configurable(tmp_path):
    rs, st = fresh_docs(NOW - timedelta(seconds=60))
    directory = write_dir(tmp_path / "snap", rs, st)
    assert SnapshotDirectoryHostProvider(directory, clock()).host_snapshot().availability is Availability.AVAILABLE
    tight = SnapshotDirectoryHostProvider(directory, clock(), stale_after_s=30.0)
    assert tight.host_snapshot().availability is Availability.STALE
    with pytest.raises(ContractError):
        SnapshotDirectoryHostProvider(directory, clock(), stale_after_s=float("nan"))


def test_future_timestamp(tmp_path):
    rs, st = fresh_docs(NOW + timedelta(minutes=10))
    snap = SnapshotDirectoryHostProvider(write_dir(tmp_path / "snap", rs, st), clock()).host_snapshot()
    assert snap.availability is Availability.ERROR and snap.reason == "FUTURE_TIMESTAMP"
    assert obs_of(snap, "host.storage").reason == "FUTURE_TIMESTAMP"


def test_small_skew_within_tolerance_is_fresh(tmp_path):
    rs, st = fresh_docs(NOW + timedelta(seconds=30))
    snap = SnapshotDirectoryHostProvider(write_dir(tmp_path / "snap", rs, st), clock()).host_snapshot()
    assert snap.availability is Availability.AVAILABLE
    assert obs_of(snap, "host.service").freshness_age_s == 0.0


def test_deployment_not_available_means_no_deployed_sha(tmp_path):
    rs, st = fresh_docs()
    rs["deployment"] = {
        "status": "NOT_AVAILABLE", "reason": "NO_EVIDENCE", "source_code_sha": None, "evidence_ref": None,
        "observed_at_utc": None, "artifact_sha256": None, "host_id": None, "invocation_id": None,
    }
    assert validate_runtime_service_snapshot(rs)
    snap = SnapshotDirectoryHostProvider(write_dir(tmp_path / "snap", rs, st), clock()).host_snapshot()
    assert snap.availability is Availability.AVAILABLE
    assert snap.deployed_source_sha is None
    deployment = obs_of(snap, "host.deployment")
    assert deployment.availability is Availability.NOT_AVAILABLE and deployment.reason == "NO_EVIDENCE"
    assert deployment.value is None
    assert obs_of(snap, "host.service").evidence[0].source_sha is None


@pytest.mark.parametrize("status", ["MISSING", "NOT_CONFIGURED", "READ_ERROR"])
def test_storage_metrics_none_are_never_zero(tmp_path, status):
    rs, st = fresh_docs()
    st["source_status"] = status
    for key in ("entries_observed", "matched_file_count", "total_bytes", "latest_file_modified_at_utc", "inventory_sha256"):
        st[key] = None
    assert validate_storage_snapshot(st)
    snap = SnapshotDirectoryHostProvider(write_dir(tmp_path / "snap", rs, st), clock()).host_snapshot()
    storage = obs_of(snap, "host.storage")
    assert storage.availability is Availability.NOT_AVAILABLE and storage.reason == status
    assert storage.value is None


def test_storage_present_empty_is_a_real_zero(tmp_path):
    rs, st = fresh_docs()
    st.update(matched_file_count=0, total_bytes=0, latest_file_modified_at_utc=None)
    assert validate_storage_snapshot(st)
    snap = SnapshotDirectoryHostProvider(write_dir(tmp_path / "snap", rs, st), clock()).host_snapshot()
    assert obs_of(snap, "host.storage").value["matched_file_count"] == 0


# ── Operator API (GET uniquement) ────────────────────────────────────────────


def transport_doc(doc: dict, age: float = 5.0, classification: str = "FRESH") -> bytes:
    return json.dumps({**doc, "snapshot_age_s": age, "freshness_classification": classification}).encode()


class FakeTransport:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, url, timeout_s, max_bytes):
        self.calls.append((url, timeout_s, max_bytes))
        result = self.responses[url.rsplit("/", 1)[1]]
        if isinstance(result, BaseException):
            raise result
        return result


BASE = "http://127.0.0.1:18080"


def test_operator_api_200_valid_transport():
    rs, st = fresh_docs()
    fake = FakeTransport({"runtime-service": HttpReponse(200, transport_doc(rs)), "storage": HttpReponse(200, transport_doc(st))})
    provider = OperatorApiHostProvider(BASE, clock(), transport=fake)
    assert isinstance(provider, HostObservationProvider)
    snap = provider.host_snapshot()
    assert [c[0] for c in fake.calls] == [f"{BASE}/api/operator/v1/runtime-service", f"{BASE}/api/operator/v1/storage"]
    assert all(c[2] == 64 * 1024 for c in fake.calls)
    assert snap.availability is Availability.AVAILABLE and snap.deployed_source_sha == FROZEN_SHA
    ev = obs_of(snap, "host.service").evidence[0]
    assert ev.locator == "snapshot:runtime_service" and ev.note == "via Operator API"
    assert ev.provenance is Provenance.LIVE_READ
    assert obs_of(snap, "host.service").freshness_age_s == 5.0
    assert obs_of(snap, "host.storage").availability is Availability.AVAILABLE


def test_operator_api_server_stale_classification():
    rs, st = fresh_docs()
    fake = FakeTransport({
        "runtime-service": HttpReponse(200, transport_doc(rs, 120.0, "STALE")),
        "storage": HttpReponse(200, transport_doc(st, 120.0, "STALE")),
    })
    snap = OperatorApiHostProvider(BASE, clock(), transport=fake).host_snapshot()
    assert snap.availability is Availability.STALE


def test_operator_api_untransported_document_is_contract_invalid():
    rs, st = fresh_docs()
    fake = FakeTransport({"runtime-service": HttpReponse(200, json.dumps(rs).encode()), "storage": HttpReponse(200, json.dumps(st).encode())})
    snap = OperatorApiHostProvider(BASE, clock(), transport=fake).host_snapshot()
    assert snap.reason == "CONTRACT_INVALID"


def test_operator_api_503_and_404_not_available():
    fake = FakeTransport({
        "runtime-service": HttpReponse(503, b'{"error_code": "RUNTIME_SERVICE_MISSING"}'),
        "storage": HttpReponse(404, b"<html>nope</html>"),
    })
    snap = OperatorApiHostProvider(BASE, clock(), transport=fake).host_snapshot()
    assert snap.availability is Availability.NOT_AVAILABLE
    assert snap.reason == "HTTP_503:RUNTIME_SERVICE_MISSING"
    assert obs_of(snap, "host.storage").reason == "HTTP_404"


def test_operator_api_timeout_and_unreachable():
    fake = FakeTransport({"runtime-service": TimeoutError("t"), "storage": ConnectionRefusedError("r")})
    snap = OperatorApiHostProvider(BASE, clock(), transport=fake).host_snapshot()
    assert snap.availability is Availability.NOT_AVAILABLE and snap.reason == "TIMEOUT"
    assert obs_of(snap, "host.storage").reason == "UNREACHABLE"


def test_operator_api_other_status_and_oversize_are_errors():
    fake = FakeTransport({"runtime-service": HttpReponse(500, b""), "storage": HttpReponse(200, b"{" + b" " * (64 * 1024))})
    snap = OperatorApiHostProvider(BASE, clock(), transport=fake).host_snapshot()
    assert snap.availability is Availability.ERROR and snap.reason == "HTTP_500"
    assert obs_of(snap, "host.storage").reason == "OUTPUT_LIMIT"


@pytest.mark.parametrize(
    "base_url",
    [
        "http://203.0.113.7:8080",
        "http://example.org:8080",
        "http://127.0.0.1",
        "http://user:pw@127.0.0.1:8080",
        "https://user@example.org",
        "ftp://127.0.0.1:21",
        "file:///etc/passwd",
        "https://example.org/api?x=1",
        "https://example.org/autre",
        "http://127.0.0.1:99999",
    ],
)
def test_operator_api_base_url_refused_before_request(base_url):
    fake = FakeTransport({})
    with pytest.raises(ContractError):
        OperatorApiHostProvider(base_url, clock(), transport=fake)
    assert fake.calls == []


@pytest.mark.parametrize("base_url", ["http://127.0.0.1:18080", "http://localhost:8000/", "https://operator.example.org"])
def test_operator_api_base_url_admitted(base_url):
    OperatorApiHostProvider(base_url, clock(), transport=FakeTransport({}))


def test_operator_api_redirect_refused_with_fake_transport():
    fake = FakeTransport({"runtime-service": HttpReponse(302, b""), "storage": HttpReponse(307, b"")})
    snap = OperatorApiHostProvider(BASE, clock(), transport=fake).host_snapshot()
    assert snap.availability is Availability.ERROR and snap.reason == "REDIRECT_REFUSED"


def test_default_transport_never_follows_redirect_nor_sends_auth(monkeypatch):
    """Transport urllib par défaut, chaîne de gestionnaires réelle, sans réseau.

    Seule l'ouverture de connexion HTTP est simulée : elle répond 302 vers un
    autre hôte. La redirection n'est pas suivie et aucun en-tête d'auth/cookie
    n'est émis.
    """
    import email.message
    import io
    import urllib.request
    from urllib.response import addinfourl

    calls = []

    def fake_http_open(self, req):
        calls.append((req.get_method(), req.full_url, {k.lower() for k, _ in req.header_items()}, req.timeout))
        headers = email.message.Message()
        headers["Location"] = "https://evil.example/x"
        response = addinfourl(io.BytesIO(b""), headers, req.full_url, 302)
        response.msg = "Found"
        return response

    monkeypatch.setattr(urllib.request.HTTPHandler, "http_open", fake_http_open)
    response = host_module._transport_urllib(f"{BASE}/api/operator/v1/storage", 5.0, 1024)
    assert response.status == 302
    assert len(calls) == 1, "redirection suivie"
    method, url, headers, timeout = calls[0]
    assert method == "GET" and url == f"{BASE}/api/operator/v1/storage" and timeout == 5.0
    assert not {"authorization", "cookie", "proxy-authorization"} & headers
    snap = OperatorApiHostProvider(BASE, clock()).host_snapshot()
    assert snap.availability is Availability.ERROR and snap.reason == "REDIRECT_REFUSED"
    assert len(calls) == 3


# ── Hygiène du module : aucun pouvoir ────────────────────────────────────────

FORBIDDEN_IMPORTS = {"subprocess", "socket", "core", "paper_trading", "governance", "financial_institute", "shlex", "pty", "paramiko"}
ALLOWED_OBSERVABILITY = {"observability.runtime_service_contract", "observability.storage_contract"}


def _module_tree() -> ast.Module:
    return ast.parse(Path(host_module.__file__).read_text(encoding="utf-8"))


def test_host_module_imports_are_restricted():
    for node in ast.walk(_module_tree()):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        for name in names:
            top = name.split(".")[0]
            assert top not in FORBIDDEN_IMPORTS, name
            if top == "observability":
                assert name in ALLOWED_OBSERVABILITY, name


def test_host_module_has_no_process_or_service_control():
    tree = _module_tree()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "os":
            assert node.attr not in {"system", "popen", "fork", "kill", "remove", "unlink", "rename", "replace"}
            assert not node.attr.startswith(("exec", "spawn", "posix_spawn"))
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            lowered = node.value.lower()
            assert "systemctl" not in lowered and "journalctl" not in lowered
        if isinstance(node, ast.Name):
            assert node.id not in {"eval", "exec", "__import__"}
    source = Path(host_module.__file__).read_text(encoding="utf-8").lower()
    assert "systemctl" not in source and "journalctl" not in source


def test_providers_expose_only_read_methods():
    for cls in (NotConfiguredHostProvider, FixtureHostProvider, SnapshotDirectoryHostProvider, OperatorApiHostProvider):
        public = {n for n in vars(cls) if not n.startswith("_")}
        assert public <= {"info", "host_snapshot", "scenario"}, cls
