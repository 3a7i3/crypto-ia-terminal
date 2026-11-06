"""The live entry stays locked before DNS or socket; the lock fails for the intended reason only."""

import copy
import hashlib
import json
import shutil
import socket
import subprocess
import sys
import types
from pathlib import Path

import pytest

from observability.flux_collection_pilot import __main__ as cli, protocol as P
from observability.flux_collection_pilot.live_gate import ENV_ACK, ApprovedLive, LiveLocked, require_live_authorization
from observability.flux_collection_pilot.live_transport import LiveTransport
from observability.flux_collection_pilot.transport import AccessRefused, ConnectionClosed, FrameTooLarge, subscribe_messages

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "docs/research/market_flux_553/pilot_coinbase_btc_usd/OPERATOR_COLLECTION_MANIFEST.template.json"


def good_manifest():
    return {
        "schema": "flux-pilot-collection-manifest/1", "status": "APPROVED", "package_digest": P.package_digest(),
        "target": {"provider": P.PROVIDER, "host": P.HOST, "product": P.PRODUCT, "channels": list(P.SUBSCRIBE_CHANNELS)},
        "caps": P.PROTOCOL_CAPS.document(), "sequence_policy": "PER_CHANNEL",
        "authorization": {"issue_286_exception_ref": "TEST-REF-1", "approved_by": "test operator",
                          "approved_at_utc": "2026-11-05T00:00:00Z"},
        "admissibility": {"region_evidence_ref": "TEST-REGION", "terms_evidence_ref": "TEST-TERMS"},
        "observer_clock": {"before_check_ref": "TEST-B", "after_check_ref": "TEST-A"},
        "storage": {"root": "/var/tmp/private-campaigns"}, "stop_policy": "first cap or safety stop closes the collection",
    }


def write(tmp_path, m, name="m.json"):
    p = tmp_path / name
    p.write_text(json.dumps(m))
    return str(p), {ENV_ACK: hashlib.sha256(p.read_bytes()).hexdigest()}


def test_a_complete_manifest_with_matching_acknowledgement_is_accepted(tmp_path):  # the positive control
    path, env = write(tmp_path, good_manifest())
    a = require_live_authorization(path, env)
    assert type(a) is ApprovedLive and a.caps == P.PROTOCOL_CAPS and a.package_digest == P.package_digest()


def mutate(fn):
    def apply(m):
        m = copy.deepcopy(m)
        fn(m)
        return m
    return apply


@pytest.mark.parametrize("code, change", [
    ("MANIFEST_NOT_APPROVED", mutate(lambda m: m.update(status="TEMPLATE_NOT_APPROVED"))),
    ("PACKAGE_DIGEST_MISMATCH", mutate(lambda m: m.update(package_digest="0" * 64))),
    ("TARGET_NOT_THE_FIXED_PILOT_TARGET", mutate(lambda m: m["target"].update(host="other.example"))),
    ("TARGET_NOT_THE_FIXED_PILOT_TARGET", mutate(lambda m: m["target"].update(product="ETH-USD"))),
    ("TARGET_NOT_THE_FIXED_PILOT_TARGET", mutate(lambda m: m["target"].update(channels=["level2", "user"]))),
    ("CAPS_ABOVE_PROTOCOL", mutate(lambda m: m["caps"].update(max_messages=100_001))),
    ("CAPS_ABOVE_PROTOCOL", mutate(lambda m: m["caps"].update(max_connections=3))),
    ("CAPS_INVALID", mutate(lambda m: m["caps"].update(max_messages=0))),
    ("MANIFEST_FIELD_MISSING:authorization.issue_286_exception_ref", mutate(lambda m: m["authorization"].pop("issue_286_exception_ref"))),
    ("MANIFEST_FIELD_NOT_COMPLETED:admissibility.region_evidence_ref", mutate(lambda m: m["admissibility"].update(region_evidence_ref="<À COMPLÉTER>"))),
    ("MANIFEST_FIELD_NOT_COMPLETED:admissibility.terms_evidence_ref", mutate(lambda m: m["admissibility"].update(terms_evidence_ref=""))),
    ("MANIFEST_FIELD_MISSING:observer_clock.after_check_ref", mutate(lambda m: m["observer_clock"].pop("after_check_ref"))),
    ("STORAGE_ROOT_NOT_ABSOLUTE", mutate(lambda m: m["storage"].update(root="relative"))),
    ("SEQUENCE_POLICY_UNKNOWN", mutate(lambda m: m.update(sequence_policy="WHATEVER"))),
    ("SECRET_FIELD_IN_MANIFEST:/authorization/jwt", mutate(lambda m: m["authorization"].update(jwt="x"))),
])
def test_each_missing_or_wrong_element_locks_for_its_own_reason(tmp_path, code, change):
    path, env = write(tmp_path, change(good_manifest()))
    with pytest.raises(LiveLocked) as e:
        require_live_authorization(path, env)
    assert str(e.value) == code  # not merely "something failed": the intended check fired


def test_acknowledgement_must_be_bound_to_the_exact_manifest_bytes(tmp_path):
    path, env = write(tmp_path, good_manifest())
    for bad in ({}, {ENV_ACK: ""}, {ENV_ACK: "0" * 64}, {"OTHER": env[ENV_ACK]}):
        with pytest.raises(LiveLocked, match="OPERATOR_ACK_MISSING_OR_NOT_BOUND_TO_MANIFEST"):
            require_live_authorization(path, bad)
    Path(path).write_text(json.dumps(good_manifest(), indent=1))  # same content, different bytes
    with pytest.raises(LiveLocked, match="OPERATOR_ACK_MISSING"):
        require_live_authorization(path, env)


def test_missing_or_unparsable_manifest_locks(tmp_path):
    for p, code in ((None, "MANIFEST_MISSING"), (str(tmp_path / "nope.json"), "MANIFEST_MISSING")):
        with pytest.raises(LiveLocked, match=code):
            require_live_authorization(p, {})
    (tmp_path / "bad.json").write_text("{")
    with pytest.raises(LiveLocked, match="MANIFEST_UNPARSABLE"):
        require_live_authorization(str(tmp_path / "bad.json"), {})


def test_an_approval_cannot_be_forged_and_the_transport_needs_one():
    with pytest.raises(LiveLocked, match="APPROVAL_ONLY_THROUGH_GATE"):
        ApprovedLive({}, "x", P.PROTOCOL_CAPS, "PER_CHANNEL", "d")
    with pytest.raises(LiveLocked, match="APPROVAL_REQUIRED"):
        LiveTransport(None)
    with pytest.raises(LiveLocked, match="APPROVAL_REQUIRED"):
        LiveTransport(types.SimpleNamespace(caps=P.PROTOCOL_CAPS))


def test_the_operator_template_is_not_an_approval(tmp_path):
    assert TEMPLATE.exists()
    t = json.loads(TEMPLATE.read_text())
    assert t["status"] != "APPROVED"
    with pytest.raises(LiveLocked, match="MANIFEST_NOT_APPROVED"):
        require_live_authorization(str(TEMPLATE), {ENV_ACK: hashlib.sha256(TEMPLATE.read_bytes()).hexdigest()})
    forged = copy.deepcopy(t)
    forged["status"] = "APPROVED"  # flipping the status alone must still not unlock (placeholders remain)
    path, env = write(tmp_path, forged)
    with pytest.raises(LiveLocked):
        require_live_authorization(path, env)


def test_cli_live_without_authorisation_is_blocked_before_dns_or_socket_with_zero_network_calls(monkeypatch, network_guard, capsys):
    created = []
    real_init = socket.socket.__init__
    monkeypatch.setattr(socket.socket, "__init__", lambda self, *a, **k: (created.append(a), real_init(self, *a, **k))[1])
    monkeypatch.delenv(ENV_ACK, raising=False)
    sys.modules.pop("websockets", None)
    assert cli.main(["live"]) == 3
    assert "LIVE_LOCKED: MANIFEST_MISSING" in capsys.readouterr().err
    assert cli.main(["live", "--manifest", str(TEMPLATE)]) == 3
    assert network_guard == [] and created == []  # no DNS call, no connect, no socket object
    assert "websockets" not in sys.modules  # the client library was not even imported


def test_importing_the_package_and_running_the_default_demo_touch_no_network(tmp_path, network_guard):
    for m in [k for k in sys.modules if k.startswith("observability.flux_collection_pilot")]:
        del sys.modules[m]
    import observability.flux_collection_pilot.__main__ as fresh  # noqa: F401
    res = fresh.synthetic_demo(tmp_path, "d")
    assert res.complete and network_guard == [] and "websockets" not in sys.modules


@pytest.mark.expect_network_attempts
def test_the_guard_itself_works_and_cannot_be_swallowed(network_guard):
    with pytest.raises(BaseException) as e:
        try:
            socket.getaddrinfo("advanced-trade-ws.coinbase.com", 443)
        except Exception:  # a broad handler in the code under test must not hide the attempt
            pytest.fail("swallowed")
    assert type(e.value).__name__ == "NetworkAttempt"
    with pytest.raises(BaseException):
        socket.create_connection(("127.0.0.1", 9))
    with pytest.raises(BaseException):
        socket.socket().connect(("127.0.0.1", 9))
    assert network_guard == ["getaddrinfo", "create_connection", "connect"]
    network_guard.clear()  # the probe itself is the only expected attempt


# --- the live transport, against a FAKE client library (nothing here reaches a server) ----------
class FakeWS:
    def __init__(self, calls, frames):
        self.calls, self.frames, self.sent = calls, list(frames), []

    def send(self, m):
        self.sent.append(m)

    def recv(self, timeout=None):
        self.calls.append(("recv", timeout))
        f = self.frames.pop(0)
        if isinstance(f, BaseException):
            raise f
        return f

    def close(self):
        self.calls.append(("close",))


def fake_websockets(monkeypatch, calls, frames=(), connect_error=None):
    ws = FakeWS(calls, frames)

    def connect(uri, **kw):
        calls.append(("connect", uri, kw))
        if connect_error:
            raise connect_error
        return ws
    for name in ("websockets", "websockets.sync", "websockets.sync.client"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    sys.modules["websockets.sync.client"].connect = connect
    return ws


def approval(tmp_path):
    path, env = write(tmp_path, good_manifest())
    return require_live_authorization(path, env)


class InvalidStatus(Exception):
    def __init__(self, code):
        self.response = types.SimpleNamespace(status_code=code)


class ConnectionClosedError(Exception):
    def __init__(self, code):
        self.rcvd = types.SimpleNamespace(code=code)


def test_live_transport_bounds_the_stream_at_the_client_and_sends_only_public_subscribes(tmp_path, monkeypatch):
    calls = []
    ws = fake_websockets(monkeypatch, calls, frames=["text-frame", b"bytes-frame", TimeoutError()])
    t = LiveTransport(approval(tmp_path))
    t.open(subscribe_messages(P.PRODUCT, P.SUBSCRIBE_CHANNELS))
    _, uri, kw = calls[0]
    assert uri == "wss://advanced-trade-ws.coinbase.com"
    assert kw["max_size"] == 512_000 and kw["compression"] is None and kw["proxy"] is None
    assert kw["ping_interval"] is None and kw["open_timeout"] == 5 and kw["max_queue"] == 16
    assert [json.loads(m)["channel"] for m in ws.sent] == ["level2", "market_trades", "heartbeats"]
    assert all("jwt" not in json.loads(m) and json.loads(m)["product_ids"] == ["BTC-USD"] for m in ws.sent)
    assert t.recv(2_500_000_000).raw == b"text-frame" and t.recv(1).raw == b"bytes-frame"
    assert calls[1] == ("recv", 2.5) and t.recv(1) is None  # a timeout is "nothing yet", not an error
    t.close()
    assert calls[-1] == ("close",)


@pytest.mark.parametrize("failure, expected", [
    (InvalidStatus(403), AccessRefused), (InvalidStatus(429), AccessRefused), (InvalidStatus(451), AccessRefused),
    (ConnectionClosedError(1009), FrameTooLarge), (ConnectionClosedError(1008), AccessRefused),
    (ConnectionClosedError(1006), ConnectionClosed),
])
def test_live_transport_maps_provider_refusals_to_stops(tmp_path, monkeypatch, failure, expected):
    calls = []
    fake_websockets(monkeypatch, calls, frames=[failure])
    t = LiveTransport(approval(tmp_path))
    t.open([])
    with pytest.raises(expected):
        t.recv(1)
    # open-time refusal
    fake_websockets(monkeypatch, [], connect_error=failure if isinstance(failure, InvalidStatus) else None)
    if isinstance(failure, InvalidStatus):
        with pytest.raises(AccessRefused):
            LiveTransport(approval(tmp_path)).open([])


def test_package_digest_pins_the_exact_package_bytes(tmp_path):
    src = Path(P.__file__).parent
    copy_dir = tmp_path / "pkg"
    shutil.copytree(src, copy_dir, ignore=shutil.ignore_patterns("__pycache__"))
    assert P.package_digest(copy_dir) == P.package_digest()
    (copy_dir / "runner.py").write_text((copy_dir / "runner.py").read_text() + "\n# one byte of change\n")
    assert P.package_digest(copy_dir) != P.package_digest()


def test_data_limit_is_applied_and_read_back_in_a_subprocess_never_in_the_test_process():
    code = (
        "from observability.flux_collection_pilot.memory import apply_data_limit\n"
        "print(apply_data_limit(200*1024*1024))\n"
        "try:\n    bytearray(400*1024*1024); print('ALLOCATED')\nexcept MemoryError:\n    print('MEMORYERROR')\n")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT,
                         env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin"}, check=True).stdout.split("\n")
    assert out[0] == "(209715200, 209715200)" and out[1] == "MEMORYERROR"
