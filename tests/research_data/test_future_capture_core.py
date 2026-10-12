"""Synthetic laboratory evidence only; never production receipts."""

import hashlib
import json
from dataclasses import FrozenInstanceError

import pytest

from research_data.future_capture_core import BoundedCapture, CaptureLimits
from research_data.stress_d1_evidence_contract import EvidenceIntegrityError

IDENTITY = {
    "stream_id": "synthetic-selection",
    "producer_id": "synthetic",
    "producer_version": "v1",
    "process_boot_id": "boot-A",
    "paper_epoch_id": "SYNTHETIC",
    "code_sha": "a" * 40,
    "config_sha256": "b" * 64,
    "capture_campaign_id": "lab-only",
}


def event(seq=1, **changes):
    d = {
        **IDENTITY,
        "schema_version": "FUTURE_NATIVE_EVENT_V1",
        "producer_sequence": seq,
        "event_id": f"e{seq}",
        "event_time_utc": "2026-10-12T00:00:00Z",
        "monotonic_ns": seq,
        "clock_domain": "boot-monotonic",
        "clock_quality": "UNKNOWN",
        "payload": {"selected_for_analysis": None},
    }
    d.update(changes)
    return json.dumps(d, separators=(",", ":")).encode()


def capture(**kw):
    return BoundedCapture(
        identity=dict(IDENTITY),
        limits=CaptureLimits(
            kw.get("max_events", 10),
            kw.get("max_bytes", 10000),
            kw.get("max_event_bytes", 2000),
        ),
    )


def doc(c):
    return json.loads(c.seal().manifest_bytes)


def test_exact_bytes_and_stable_freeze_no_certification():
    c = capture()
    raw = event()
    assert c.append(raw)
    s = c.seal()
    assert s.events == (raw,)
    assert c.seal() is s
    assert hashlib.sha256(s.manifest_bytes).hexdigest() == s.manifest_sha256
    d = doc(c)
    assert d["producer_completeness"] == "NOT_PROVEN"
    assert d["actual_persistence_proof"] == "NOT_OBSERVED"
    assert d["queue_quiescence"] == "NOT_PROVEN"
    assert d["future_capture_activation"] == d["paper_stress_runtime_go"] == "DENIED"
    with pytest.raises(FrozenInstanceError):
        s.events = ()
    with pytest.raises(EvidenceIntegrityError, match="CAPTURE_SEALED"):
        c.append(event(2))
    assert c.seal() is s


def test_count_saturation_no_eviction_gap_or_refusal_hidden():
    c = capture(max_events=1)
    assert c.append(event(1))
    assert not c.append(event(3))
    s = c.seal()
    assert s.events == (event(1),)
    d = doc(c)
    assert d["refusals"] == {"EVENT_COUNT_LIMIT": 1}
    assert d["declared_sequence_gap_count"] == 1
    assert d["observed_last_sequence"] == 3
    assert d["capture_status"] == "INCOMPLETE"


def test_byte_limit_preserves_record_and_refuses_next():
    raw = event()
    c = capture(max_bytes=len(raw), max_event_bytes=len(raw))
    assert c.append(raw)
    assert not c.append(event(2))
    assert doc(c)["refusals"] == {"BYTE_LIMIT": 1}
    assert c.seal().events == (raw,)


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"producer_sequence": True}, "SEQUENCE_NOT_INCREASING"),
        ({"process_boot_id": "boot-B"}, "IDENTITY_MISMATCH"),
        ({"paper_epoch_id": "other"}, "IDENTITY_MISMATCH"),
        ({"config_sha256": "c" * 64}, "IDENTITY_MISMATCH"),
        ({"event_time_utc": "2026-10-12T00:00:00"}, "NAIVE_OR_NON_UTC_TIME"),
        ({"monotonic_ns": -1}, "MONOTONIC_TIME_REVERSED"),
        ({"clock_quality": "CERTIFIED"}, "INVALID_CLOCK_QUALITY"),
        ({"payload": []}, "INVALID_NATIVE_PAYLOAD"),
        ({"extra": "ignored"}, "INVALID_EVENT_FIELDS"),
    ],
)
def test_invalid_event_visible_not_empty_certified(changes, code):
    c = capture()
    with pytest.raises(EvidenceIntegrityError, match=code):
        c.append(event(**changes))
    d = doc(c)
    assert d["refusals"] == {"INVALID_EVENT": 1}
    assert d["capture_status"] == "INCOMPLETE"


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e400", "-1e400"])
def test_nonfinite_unused_nested_field(token):
    c = capture()
    raw = event().replace(b"null", token.encode())
    with pytest.raises(EvidenceIntegrityError, match="NONFINITE_JSON"):
        c.append(raw)
    assert doc(c)["refusals"] == {"INVALID_EVENT": 1}


@pytest.mark.parametrize("raw", [b"not json", b"\xff", b"[]", bytearray(b"{}")])
def test_malformed_or_mutable_bytes(raw):
    c = capture()
    with pytest.raises(EvidenceIntegrityError):
        c.append(raw)
    assert doc(c)["capture_status"] == "INCOMPLETE"


def test_duplicate_json_key():
    c = capture()
    raw = event().replace(
        b'"selected_for_analysis":null',
        b'"selected_for_analysis":null,"selected_for_analysis":false',
    )
    with pytest.raises(EvidenceIntegrityError, match="DUPLICATE_JSON_KEY"):
        c.append(raw)


@pytest.mark.parametrize(
    "seq,event_id,mono,domain,code",
    [
        (2, "e1", 2, "boot-monotonic", "DUPLICATE_EVENT_ID"),
        (1, "other", 2, "boot-monotonic", "SEQUENCE_NOT_INCREASING"),
        (2, "e2", 0, "boot-monotonic", "MONOTONIC_TIME_REVERSED"),
        (2, "e2", 2, "other-clock", "CLOCK_DOMAIN_MISMATCH"),
    ],
)
def test_contradictions_preserve_accepted_bytes(seq, event_id, mono, domain, code):
    c = capture()
    assert c.append(event())
    with pytest.raises(EvidenceIntegrityError, match=code):
        c.append(event(seq, event_id=event_id, monotonic_ns=mono, clock_domain=domain))
    assert c.seal().events == (event(),)
    assert doc(c)["capture_status"] == "INCOMPLETE"


def test_input_identity_copy_and_manifest_copy():
    identity = dict(IDENTITY)
    c = BoundedCapture(identity=identity, limits=CaptureLimits(2, 4000, 2000))
    identity["paper_epoch_id"] = "changed"
    assert c.append(event())
    d = doc(c)
    d["identity"]["paper_epoch_id"] = "changed"
    assert doc(c)["identity"]["paper_epoch_id"] == "SYNTHETIC"


def test_initial_gap_and_unknown_payload_never_repaired():
    c = capture()
    raw = event(4)
    assert c.append(raw)
    assert doc(c)["declared_sequence_gap_count"] == 3
    assert json.loads(c.seal().events[0])["payload"]["selected_for_analysis"] is None


def test_oversize_bound_before_json_decode():
    c = capture()
    with pytest.raises(EvidenceIntegrityError, match="EVENT_TOO_LARGE"):
        c.append(b"x" * 2001)
    assert doc(c)["accepted_bytes"] == 0


@pytest.mark.parametrize("limits", [(0, 1, 1), (True, 1, 1), (1, 1, 2)])
def test_invalid_limits(limits):
    with pytest.raises(EvidenceIntegrityError):
        CaptureLimits(*limits)
