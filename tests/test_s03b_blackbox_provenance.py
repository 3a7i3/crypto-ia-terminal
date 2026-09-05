"""
S-03B — tests focalisés BlackBox : schéma étendu, compat historique, lecture
legacy plaintext, writers bypass canoniques, non-crash sur ligne malformée.

Fixtures temporaires uniquement — jamais de fichier runtime réel.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from quant_hedge_ai.agents.intelligence.black_box import BlackBox


@pytest.fixture()
def bb_path(tmp_path, monkeypatch):
    p = tmp_path / "black_box.jsonl"
    monkeypatch.setenv("BB_PATH", str(p))
    return p


def _fake_enc():
    """Chiffrement no-op déterministe pour les tests (base64 JSON)."""
    import base64

    class _FakeEnc:
        def encrypt_line(self, data: dict) -> str:
            return base64.b64encode(json.dumps(data).encode()).decode()

        def decrypt_line(self, line: str) -> dict:
            return json.loads(base64.b64decode(line.encode()).decode())

    return _FakeEnc()


@pytest.fixture(autouse=True)
def _patch_encryption(monkeypatch):
    import quant_hedge_ai.agents.intelligence.black_box as bbmod

    monkeypatch.setattr(bbmod, "_get_enc", lambda: _fake_enc())
    yield


def _minimal_analysis_result(**kwargs):
    dp = SimpleNamespace(
        packet_id=str(uuid.uuid4()),
        metadata={"trace_id": "trace-abc"},
        side=SimpleNamespace(value="LONG"),
    )
    r = dict(
        signal=SimpleNamespace(signal="BUY", score=80, actionable=True),
        gate=SimpleNamespace(allowed=True, failed=[]),
        conviction=None,
        awareness_state=None,
        pb_verdict=None,
        allocation=None,
        mm_check=None,
        personality=None,
        features={},
        no_trade_verdict=None,
        trade_allowed=False,
        meta_allowed=True,
        blockers="conviction,portfolio",
        symbol="BTC/USDT",
        prix=67000.0,
        regime="bull_trend",
        decision_packet=dp,
        trace_id="trace-abc",
    )
    r.update(kwargs)
    return r


def test_record_decision_includes_canonical_provenance_fields(bb_path):
    bb = BlackBox(path=str(bb_path))
    r = _minimal_analysis_result()
    entry = bb.record_decision(r, cycle=1)
    assert entry.schema_version == 2
    assert entry.packet_id == r["decision_packet"].packet_id
    assert entry.trace_id == "trace-abc"
    assert entry.canonical_first_blocker == "conviction"
    assert entry.canonical_all_blockers == ["conviction", "portfolio"]
    assert entry.packet_side == "LONG"


def test_historical_entry_without_new_fields_loads_via_defaults(bb_path):
    # Simule une ligne historique chiffrée (pré-S-03B) sans les nouveaux champs
    old_data = {
        "ts": 1.0,
        "decision_type": "HOLD",
        "symbol": "ETH/USDT",
        "signal": "HOLD",
        "score": 10,
        "regime": "range",
        "personality": "N/A",
        "price": 3000.0,
        "reason": "HOLD",
    }
    enc = _fake_enc()
    bb_path.write_text(enc.encrypt_line(old_data) + "\n")

    bb = BlackBox(path=str(bb_path))
    entries = bb.query(limit=10)
    assert len(entries) == 1
    assert entries[0].schema_version == 1
    assert entries[0].packet_id == ""
    stats = bb.get_load_stats()
    assert stats["encrypted_records"] == 1


def test_legacy_plaintext_warmup_complete_recognized_not_dropped(bb_path):
    legacy = {"event": "WARMUP_COMPLETE", "session_id": "s1", "ts": 1.0}
    bb_path.write_text(json.dumps(legacy) + "\n")

    bb = BlackBox(path=str(bb_path))
    entries = bb.query(limit=10)
    assert len(entries) == 1
    assert entries[0].event_payload is not None
    assert entries[0].event_payload["session_id"] == "s1"
    stats = bb.get_load_stats()
    assert stats["legacy_plaintext_records"] == 1


def test_malformed_line_does_not_crash_reader(bb_path):
    bb_path.write_text("not valid json at all {{{\n")
    bb = BlackBox(path=str(bb_path))
    entries = bb.query(limit=10)
    assert entries == []
    stats = bb.get_load_stats()
    assert stats["invalid_records"] == 1


def test_record_structured_event_roundtrips_via_canonical_reader(bb_path):
    bb = BlackBox(path=str(bb_path))
    bb.record_structured_event("BYPASS_DETECTED", {"reason": "no token"})

    bb2 = BlackBox(path=str(bb_path))
    entries = bb2.query(limit=10)
    assert len(entries) == 1
    assert entries[0].event_payload["event_type"] == "BYPASS_DETECTED"
    assert entries[0].event_payload["reason"] == "no token"
    assert entries[0].schema_version == 2


def test_bypass_writers_route_through_canonical_blackbox(bb_path, monkeypatch):
    from cold_start.bypass_detector import _archive_bypass_event

    _archive_bypass_event("missing token", str(bb_path))

    bb = BlackBox(path=str(bb_path))
    entries = bb.query(limit=10)
    assert len(entries) == 1
    assert entries[0].event_payload["reason"] == "missing token"


def test_write_stats_track_attempts_successes(bb_path):
    bb = BlackBox(path=str(bb_path))
    bb.record_structured_event("X", {"a": 1})
    stats = bb.get_write_stats()
    assert stats["write_attempts"] == 1
    assert stats["write_successes"] == 1
    assert stats["write_failures"] == 0


# ── S-03B-R1: memory/disk durability (MASTER §5) ─────────────────────────────


def test_successful_write_is_durable_and_queryable(bb_path):
    bb = BlackBox(path=str(bb_path))
    bb.record_structured_event("DURABLE_OK", {"a": 1})

    stats = bb.get_write_stats()
    assert stats == {"write_attempts": 1, "write_successes": 1, "write_failures": 0}

    entries = bb.query(limit=10)
    assert len(entries) == 1
    assert entries[0].event_payload["event_type"] == "DURABLE_OK"


def test_failed_disk_write_does_not_appear_as_persisted_entry(bb_path, monkeypatch):
    import quant_hedge_ai.agents.intelligence.black_box as bbmod

    class _FailingEnc:
        def encrypt_line(self, data: dict) -> str:
            raise RuntimeError("simulated encryption failure")

        def decrypt_line(self, line: str) -> dict:
            raise AssertionError("should not be called")

    bb = BlackBox(path=str(bb_path))
    monkeypatch.setattr(bbmod, "_get_enc", lambda: _FailingEnc())

    bb.record_structured_event("DURABLE_FAIL", {"a": 1})

    stats = bb.get_write_stats()
    assert stats == {"write_attempts": 1, "write_successes": 0, "write_failures": 1}

    # The failed record must not be visible via the same instance's canonical
    # in-memory cache — it was never durably persisted.
    entries = bb.query(limit=10)
    assert entries == []
    assert not bb_path.exists() or bb_path.read_text() == ""
