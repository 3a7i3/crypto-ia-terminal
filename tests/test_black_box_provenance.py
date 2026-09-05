"""
tests/test_black_box_provenance.py — S-03D mission section 8/19 (items 11-14).

Vérifie l'agrégat de provenance PROCESS-EPOCH ajouté sur BlackBox :
  - incrémente uniquement après succès d'écriture disque (durabilité S-03B-R1)
  - n'applique jamais le contrat de provenance aux types non concernés
    (SYSTEM_EVENT)
  - le dénominateur canonical_first_blocker est propre à TRADE_REFUSED

Toutes les instances BlackBox de ce module pointent vers tmp_path — jamais
databases/ réel (DS-001).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from quant_hedge_ai.agents.intelligence.black_box import BlackBox, DecisionType


@pytest.fixture()
def bb(tmp_path):
    return BlackBox(path=str(tmp_path / "black_box.jsonl"))


def _analysis_result(
    *,
    actionable: bool,
    trade_allowed: bool,
    futures_mode: str | None,
    packet_id: str = "pkt-1",
    trace_id: str = "trace-1",
    packet_side: str = "LONG",
    blockers: str = "",
) -> dict:
    signal = SimpleNamespace(actionable=actionable, signal="BUY", score=80)
    decision_packet = SimpleNamespace(
        packet_id=packet_id,
        side=SimpleNamespace(value=packet_side),
        metadata={"trace_id": trace_id},
    )
    return {
        "signal": signal,
        "gate": None,
        "conviction": None,
        "awareness_state": None,
        "pb_verdict": None,
        "allocation": None,
        "mm_check": None,
        "personality": None,
        "features": {},
        "no_trade_verdict": None,
        "trade_allowed": trade_allowed,
        "meta_allowed": True,
        "futures_result": (
            {"mode": futures_mode} if futures_mode is not None else {}
        ),
        "symbol": "BTC/USDT",
        "regime": "trend",
        "prix": 100.0,
        "blockers": blockers,
        "decision_packet": decision_packet,
        "trace_id": trace_id,
    }


def test_successful_trade_executed_increments_persisted_aggregate(bb):
    r = _analysis_result(actionable=True, trade_allowed=True, futures_mode="futures_demo")
    entry = bb.record_decision(r, cycle=1)
    assert entry.decision_type == DecisionType.TRADE_EXECUTED.value

    prov = bb.get_provenance_stats()
    assert prov["decision_records_persisted"] == 1
    assert prov["packet_id_present"] == 1
    assert prov["packet_id_missing"] == 0
    assert prov["trace_id_present"] == 1
    assert prov["schema_v2"] == 1
    assert prov["packet_side_present"] == 1


def test_failed_persistence_does_not_increment_persisted_aggregate(bb, monkeypatch):
    def _boom(*_a, **_k):
        raise OSError("disk full (simulated)")

    monkeypatch.setattr("builtins.open", _boom)

    r = _analysis_result(actionable=True, trade_allowed=True, futures_mode="futures_demo")
    bb.record_decision(r, cycle=1)

    write_stats = bb.get_write_stats()
    assert write_stats["write_failures"] == 1
    assert write_stats["write_successes"] == 0

    prov = bb.get_provenance_stats()
    assert prov["decision_records_persisted"] == 0
    assert prov["packet_id_present"] == 0


def test_system_event_without_packet_id_not_counted_as_missing(bb):
    bb.record_system_event("BOOT", "pid=1")

    prov = bb.get_provenance_stats()
    # SYSTEM_EVENT is not provenance-applicable — it must not move any
    # packet_id counter, present or missing.
    assert prov["decision_records_persisted"] == 0
    assert prov["packet_id_present"] == 0
    assert prov["packet_id_missing"] == 0


def test_refused_record_canonical_first_blocker_present(bb):
    r = _analysis_result(
        actionable=True,
        trade_allowed=False,
        futures_mode=None,
        blockers="gate,conviction",
    )
    entry = bb.record_decision(r, cycle=2)
    assert entry.decision_type == DecisionType.TRADE_REFUSED.value

    prov = bb.get_provenance_stats()
    assert prov["refused_records_persisted"] == 1
    assert prov["canonical_first_blocker_present"] == 1
    assert prov["canonical_first_blocker_missing"] == 0


def test_refused_record_canonical_first_blocker_missing_is_explicit(bb):
    r = _analysis_result(
        actionable=True,
        trade_allowed=False,
        futures_mode=None,
        blockers="",
    )
    entry = bb.record_decision(r, cycle=3)
    assert entry.decision_type == DecisionType.TRADE_REFUSED.value

    prov = bb.get_provenance_stats()
    assert prov["refused_records_persisted"] == 1
    assert prov["canonical_first_blocker_present"] == 0
    assert prov["canonical_first_blocker_missing"] == 1


def test_hold_record_not_counted_in_refused_denominator(bb):
    r = _analysis_result(actionable=False, trade_allowed=False, futures_mode=None)
    entry = bb.record_decision(r, cycle=4)
    assert entry.decision_type == DecisionType.HOLD.value

    prov = bb.get_provenance_stats()
    assert prov["decision_records_persisted"] == 1
    assert prov["refused_records_persisted"] == 0


def test_position_closed_not_provenance_applicable(bb):
    pos = SimpleNamespace(
        symbol="ETH/USDT",
        side=SimpleNamespace(value="long"),
        signal_score=0,
        regime="trend",
        current_price=1.0,
        pnl_pct=1.0,
        order_id="",
        conviction_level="unknown",
        size_usd=0.0,
    )
    bb.record_position_closed(pos, reason="TP")

    prov = bb.get_provenance_stats()
    assert prov["decision_records_persisted"] == 0
