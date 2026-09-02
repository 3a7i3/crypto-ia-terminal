"""Q3 — change-driven @QuantCrypto_bot pinned LIVE tests.

The transport is fully mocked. Tests prove that only the canonical scientific
projection (or the independent safety refresh) can cause editMessageText, and
that Q2 delivery evidence alone decides whether a fingerprint is confirmed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

import pytest

from src.telegram.quant_observer import bot
from src.telegram.quant_observer.bot import (
    ChangeDrivenLiveState,
    DeliveryKind,
    DeliveryState,
    TransportResult,
)
from visualization.api.models import QuantLiveSnapshot


def _result(kind: DeliveryKind) -> TransportResult:
    status = {
        DeliveryKind.ACK: 200,
        DeliveryKind.NO_CHANGE: 400,
        DeliveryKind.HTTP_ERROR: 500,
    }.get(kind, 400)
    return TransportResult(kind=kind, method="editMessageText", http_status=status)


@pytest.fixture
def snapshot() -> QuantLiveSnapshot:
    return QuantLiveSnapshot(
        ts=datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc),
        cycle=597,
        engine_version="v9.1",
        snapshot_age_s=2.0,
        health_market=True,
        health_api=True,
        regime="bull_trend",
        exchange_latency_ms=225.0,
        exchange_uptime_pct=100.0,
        state="ACTIVE",
        top_candidate_symbol="MORPHO/USDT",
        top_candidate_score=85.0,
        required_score=70.0,
        mean_signal_score=54,
        reason_text="20 setup(s) tradable",
        gate_reason="signal_score (66<72)",
        next_evaluation_sec=300,
        refusal_breakdown={"gate": 45, "meta_strategy": 7},
        pipeline_stages=[
            {"name": "Scanner", "status": "OK", "message": "135/135"},
            {"name": "Risk Manager", "status": "OK", "message": "R000"},
            {"name": "Execution", "status": "ACTIVE", "message": ""},
        ],
        decision_trace=[
            {
                "node": "Signal Generator",
                "decision": "SCORED",
                "score": 85,
                "reason_code": "R000",
            },
            {
                "node": "Execution",
                "decision": "ACTIVE",
                "score": 85,
                "reason_code": "R000",
            },
        ],
    )


@dataclass
class LiveHarness:
    snapshot: QuantLiveSnapshot
    edit_results: list[TransportResult] = field(default_factory=list)
    edits: list[tuple[str, str, str]] = field(default_factory=list)
    last_pinned_update: float = 0.0

    def tick(self, now: float) -> float:
        self.last_pinned_update = bot._change_driven_live_tick(
            now, self.last_pinned_update
        )
        return self.last_pinned_update


@pytest.fixture
def live(monkeypatch, snapshot) -> LiveHarness:
    harness = LiveHarness(snapshot=snapshot)
    monkeypatch.setattr(bot, "QC_PINNED_MSG", "123")
    monkeypatch.setattr(bot, "QC_CHAT_ID", "456")
    monkeypatch.setattr(bot, "QC_SAFETY_REFRESH_S", 1800)
    monkeypatch.setattr(bot, "QC_LIVE_RETRY_S", 30)
    monkeypatch.setattr(bot, "_QC_LIVE_STATE", ChangeDrivenLiveState())
    monkeypatch.setattr(bot, "_QC_DELIVERY", DeliveryState())
    monkeypatch.setattr(bot, "_load_quant_live_snapshot", lambda: harness.snapshot)

    def edit(chat_id: str, message_id: str, text: str) -> TransportResult:
        harness.edits.append((chat_id, message_id, text))
        if harness.edit_results:
            return harness.edit_results.pop(0)
        return _result(DeliveryKind.ACK)

    monkeypatch.setattr(bot, "edit_message", edit)
    return harness


def test_projection_has_exact_scientific_fields(snapshot):
    projection = bot._quant_live_semantic_projection(snapshot)
    assert set(projection) == {
        "health_market",
        "health_api",
        "regime",
        "exchange_latency_ms",
        "exchange_uptime_pct",
        "state",
        "top_candidate_symbol",
        "top_candidate_score",
        "required_score",
        "mean_signal_score",
        "reason_text",
        "gate_reason",
        "refusal_breakdown",
        "total_refusals",
        "dominant_filter",
        "dominant_filter_pct",
        "pipeline_stages",
        "decision_trace",
    }
    assert "snapshot_age_s" not in projection
    assert "next_evaluation_sec" not in projection
    assert "cycle" not in projection
    assert "ts" not in projection


def test_first_snapshot_edits_and_records_inspection(live):
    assert live.tick(100.0) == 100.0
    assert len(live.edits) == 1
    assert bot._QC_LIVE_STATE.last_inspection_ts == 100.0
    assert bot._QC_LIVE_STATE.last_delivery_attempt_ts == 100.0


def test_retry_floor_default_is_30_seconds():
    assert bot.QC_LIVE_RETRY_S == 30


def test_identical_semantic_snapshot_does_not_edit(live):
    live.tick(100.0)
    live.tick(800.0)  # beyond the former 600 s edit cadence, below safety refresh
    assert len(live.edits) == 1
    assert bot._QC_LIVE_STATE.last_inspection_ts == 800.0
    assert bot._QC_LIVE_STATE.last_delivery_attempt_ts == 100.0


@pytest.mark.parametrize(
    ("field_name", "changed_value"),
    [
        ("snapshot_age_s", 57.0),
        ("next_evaluation_sec", 42),
        ("cycle", 598),
    ],
)
def test_display_clock_changes_do_not_edit(live, field_name, changed_value):
    live.tick(100.0)
    live.snapshot = replace(live.snapshot, **{field_name: changed_value})
    live.tick(800.0)
    assert len(live.edits) == 1


@pytest.mark.parametrize(
    ("field_name", "changed_value"),
    [
        ("regime", "bear_trend"),
        ("top_candidate_symbol", "BTC/USDT"),
        ("top_candidate_score", 86.0),
    ],
)
def test_core_scientific_change_edits(live, field_name, changed_value):
    live.tick(100.0)
    live.snapshot = replace(live.snapshot, **{field_name: changed_value})
    live.tick(200.0)
    assert len(live.edits) == 2


def test_attrition_change_edits(live):
    live.tick(100.0)
    live.snapshot = replace(
        live.snapshot, refusal_breakdown={"gate": 46, "meta_strategy": 7}
    )
    live.tick(200.0)
    assert len(live.edits) == 2


def test_pipeline_change_edits(live):
    live.tick(100.0)
    stages = [dict(stage) for stage in live.snapshot.pipeline_stages]
    stages[1]["status"] = "BLOCKED"
    live.snapshot = replace(live.snapshot, pipeline_stages=stages)
    live.tick(200.0)
    assert len(live.edits) == 2


def test_decision_trace_change_edits(live):
    live.tick(100.0)
    trace = [dict(node) for node in live.snapshot.decision_trace]
    trace[-1]["decision"] = "REFUSED"
    live.snapshot = replace(live.snapshot, decision_trace=trace)
    live.tick(200.0)
    assert len(live.edits) == 2


def test_mapping_order_is_canonical(snapshot):
    reordered = replace(
        snapshot, refusal_breakdown={"meta_strategy": 7, "gate": 45}
    )
    assert bot._quant_live_fingerprint(reordered) == bot._quant_live_fingerprint(
        snapshot
    )


def test_integer_and_integral_float_have_same_fingerprint(snapshot):
    integer = replace(snapshot, top_candidate_score=1)
    integral_float = replace(snapshot, top_candidate_score=1.0)
    assert bot._quant_live_fingerprint(integer) == bot._quant_live_fingerprint(
        integral_float
    )


def test_integer_zero_and_float_zero_have_same_fingerprint(snapshot):
    integer = replace(snapshot, exchange_latency_ms=0)
    floating = replace(snapshot, exchange_latency_ms=0.0)
    assert bot._quant_live_fingerprint(integer) == bot._quant_live_fingerprint(
        floating
    )


def test_signed_zero_matches_distinct_rendered_representation(snapshot):
    positive = replace(snapshot, exchange_latency_ms=0.0)
    negative = replace(snapshot, exchange_latency_ms=-0.0)
    assert bot.render_quant_live_panel(positive) != bot.render_quant_live_panel(
        negative
    )
    assert bot._quant_live_fingerprint(positive) != bot._quant_live_fingerprint(
        negative
    )


def test_true_is_distinct_from_integer_one(snapshot):
    boolean = replace(snapshot, health_market=True)
    integer = replace(snapshot, health_market=1)
    assert bot._quant_live_fingerprint(boolean) != bot._quant_live_fingerprint(integer)


def test_false_is_distinct_from_integer_zero(snapshot):
    boolean = replace(snapshot, health_market=False)
    integer = replace(snapshot, health_market=0)
    assert bot._quant_live_fingerprint(boolean) != bot._quant_live_fingerprint(integer)


def test_list_and_tuple_share_ordered_sequence_canonical_form():
    assert bot._canonicalize_fingerprint_value([None, 1, "x"]) == (
        bot._canonicalize_fingerprint_value((None, 1.0, "x"))
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (math.nan, ["nonfinite", "nan"]),
        (math.inf, ["nonfinite", "+inf"]),
        (-math.inf, ["nonfinite", "-inf"]),
    ],
)
def test_non_finite_float_has_deterministic_canonical_form(value, expected):
    assert bot._canonicalize_fingerprint_value(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (math.nan, ["nonfinite", "nan"]),
        (math.inf, ["nonfinite", "+inf"]),
        (-math.inf, ["nonfinite", "-inf"]),
    ],
)
def test_non_finite_exchange_metric_is_explicit_in_projection(
    snapshot, value, expected
):
    anomalous = replace(snapshot, exchange_latency_ms=value)
    projection = bot._quant_live_semantic_projection(anomalous)

    assert projection["exchange_latency_ms"] == expected


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_visible_state_edits_once_then_stabilizes(live, value):
    live.tick(100.0)
    live.snapshot = replace(live.snapshot, exchange_latency_ms=value)

    live.tick(101.0)
    live.tick(102.0)

    assert len(live.edits) == 2
    assert f"{value:.0f} ms" in live.edits[-1][2]
    assert bot._QC_LIVE_STATE.confirmed_fingerprint == bot._quant_live_fingerprint(
        live.snapshot
    )


@pytest.mark.parametrize(
    ("field_name", "first", "second"),
    [
        ("exchange_latency_ms", 225.1, 225.4),
        ("exchange_uptime_pct", 99.91, 100.0),
    ],
)
def test_render_equivalent_exchange_metrics_share_fingerprint(
    snapshot, field_name, first, second
):
    first_snapshot = replace(snapshot, **{field_name: first})
    second_snapshot = replace(snapshot, **{field_name: second})

    assert bot.render_quant_live_panel(first_snapshot) == bot.render_quant_live_panel(
        second_snapshot
    )
    assert bot._quant_live_fingerprint(first_snapshot) == bot._quant_live_fingerprint(
        second_snapshot
    )


@pytest.mark.parametrize(
    ("field_name", "first", "second"),
    [
        ("exchange_latency_ms", 225.4, 225.6),
        ("exchange_uptime_pct", 99.4, 99.6),
    ],
)
def test_visibly_different_exchange_metrics_change_fingerprint(
    snapshot, field_name, first, second
):
    first_snapshot = replace(snapshot, **{field_name: first})
    second_snapshot = replace(snapshot, **{field_name: second})

    assert bot.render_quant_live_panel(first_snapshot) != bot.render_quant_live_panel(
        second_snapshot
    )
    assert bot._quant_live_fingerprint(first_snapshot) != bot._quant_live_fingerprint(
        second_snapshot
    )


def test_tied_dominant_filter_preserves_q1_visible_difference(snapshot):
    gate_first = replace(snapshot, refusal_breakdown={"gate": 1, "risk": 1})
    risk_first = replace(snapshot, refusal_breakdown={"risk": 1, "gate": 1})

    assert gate_first.dominant_filter == "gate"
    assert risk_first.dominant_filter == "risk"
    assert bot.render_quant_live_panel(gate_first) != bot.render_quant_live_panel(
        risk_first
    )
    assert bot._quant_live_fingerprint(gate_first) != bot._quant_live_fingerprint(
        risk_first
    )


def test_collection_order_is_explicitly_significant(snapshot):
    reordered = replace(snapshot, pipeline_stages=list(reversed(snapshot.pipeline_stages)))
    assert bot._quant_live_fingerprint(reordered) != bot._quant_live_fingerprint(
        snapshot
    )


def test_decision_trace_order_is_explicitly_significant(snapshot):
    reordered = replace(
        snapshot, decision_trace=list(reversed(snapshot.decision_trace))
    )
    assert bot._quant_live_fingerprint(reordered) != bot._quant_live_fingerprint(
        snapshot
    )


def test_ack_confirms_fingerprint(live):
    live.edit_results = [_result(DeliveryKind.ACK)]
    expected = bot._quant_live_fingerprint(live.snapshot)
    live.tick(100.0)
    assert bot._QC_LIVE_STATE.confirmed_fingerprint == expected
    assert bot._QC_LIVE_STATE.last_confirmed_ts == 100.0
    assert bot._QC_DELIVERY.last_ack_ts == 100.0


def test_no_change_confirms_fingerprint(live):
    live.edit_results = [_result(DeliveryKind.NO_CHANGE)]
    expected = bot._quant_live_fingerprint(live.snapshot)
    live.tick(100.0)
    assert bot._QC_LIVE_STATE.confirmed_fingerprint == expected
    assert bot._QC_LIVE_STATE.last_confirmed_ts == 100.0
    assert bot._QC_DELIVERY.last_ack_ts is None
    assert bot._QC_DELIVERY.last_confirmed_current_ts == 100.0


def test_failure_does_not_confirm_fingerprint(live):
    live.edit_results = [_result(DeliveryKind.HTTP_ERROR)]
    live.tick(100.0)
    assert bot._QC_LIVE_STATE.confirmed_fingerprint is None
    assert bot._QC_LIVE_STATE.last_confirmed_ts is None
    assert bot._QC_LIVE_STATE.last_delivery_attempt_ts == 100.0
    assert bot._QC_LIVE_STATE.last_delivery_failed
    assert bot._QC_DELIVERY.last_failure_ts == 100.0


def test_failure_preserves_preceding_confirmed_fingerprint(live):
    live.tick(100.0)
    confirmed = bot._QC_LIVE_STATE.confirmed_fingerprint
    live.snapshot = replace(live.snapshot, regime="bear_trend")
    live.edit_results = [_result(DeliveryKind.NETWORK_ERROR)]
    live.tick(200.0)
    assert bot._QC_LIVE_STATE.confirmed_fingerprint == confirmed
    assert bot._QC_LIVE_STATE.last_confirmed_ts == 100.0


def test_failure_at_t100_attempts_edit(live):
    live.edit_results = [_result(DeliveryKind.HTTP_ERROR)]
    live.tick(100.0)
    assert len(live.edits) == 1
    assert bot._QC_LIVE_STATE.last_delivery_attempt_ts == 100.0


def test_failure_same_state_at_t101_does_not_edit(live):
    live.edit_results = [_result(DeliveryKind.HTTP_ERROR)]
    live.tick(100.0)
    live.tick(101.0)
    assert len(live.edits) == 1


def test_failure_same_state_before_t130_does_not_edit(live):
    live.edit_results = [_result(DeliveryKind.HTTP_ERROR)]
    live.tick(100.0)
    live.tick(129.999)
    assert len(live.edits) == 1


def test_failure_same_state_at_t130_retries(live):
    live.edit_results = [
        _result(DeliveryKind.HTTP_ERROR),
        _result(DeliveryKind.HTTP_ERROR),
    ]
    live.tick(100.0)
    live.tick(130.0)
    assert len(live.edits) == 2


def test_fast_getupdates_cannot_bypass_retry_floor(live, monkeypatch):
    live.edit_results = [_result(DeliveryKind.NETWORK_ERROR)]
    monkeypatch.setattr(bot, "get_updates", lambda offset=0: [])

    live.tick(100.0)
    assert bot.get_updates(offset=0) == []
    live.tick(102.0)
    assert len(live.edits) == 1


def test_changed_state_during_backoff_does_not_edit(live):
    live.edit_results = [_result(DeliveryKind.HTTP_ERROR)]
    live.tick(100.0)
    live.snapshot = replace(live.snapshot, regime="bear_trend")
    live.tick(101.0)
    assert len(live.edits) == 1


def test_changed_state_after_retry_floor_edits(live):
    live.edit_results = [_result(DeliveryKind.HTTP_ERROR)]
    live.tick(100.0)
    live.snapshot = replace(live.snapshot, regime="bear_trend")
    live.tick(130.0)
    assert len(live.edits) == 2


def test_ack_after_retry_confirms_and_clears_backoff(live):
    live.edit_results = [
        _result(DeliveryKind.HTTP_ERROR),
        _result(DeliveryKind.ACK),
    ]
    live.tick(100.0)
    live.tick(130.0)
    assert len(live.edits) == 2
    assert bot._QC_LIVE_STATE.confirmed_fingerprint == bot._quant_live_fingerprint(
        live.snapshot
    )
    assert bot._QC_LIVE_STATE.last_confirmed_ts == 130.0
    assert not bot._QC_LIVE_STATE.last_delivery_failed

    live.snapshot = replace(live.snapshot, regime="bear_trend")
    live.tick(131.0)
    assert len(live.edits) == 3


def test_no_change_after_retry_confirms_and_clears_backoff(live):
    live.edit_results = [
        _result(DeliveryKind.NETWORK_ERROR),
        _result(DeliveryKind.NO_CHANGE),
    ]
    live.tick(100.0)
    live.tick(130.0)
    assert bot._QC_LIVE_STATE.confirmed_fingerprint == bot._quant_live_fingerprint(
        live.snapshot
    )
    assert bot._QC_LIVE_STATE.last_confirmed_ts == 130.0
    assert not bot._QC_LIVE_STATE.last_delivery_failed

    live.snapshot = replace(live.snapshot, state="REFUSED")
    live.tick(131.0)
    assert len(live.edits) == 3


def test_restart_unknown_fingerprint_edits(live, monkeypatch):
    live.tick(100.0)
    monkeypatch.setattr(bot, "_QC_LIVE_STATE", ChangeDrivenLiveState())
    live.tick(101.0)
    assert len(live.edits) == 2
    assert bot._QC_LIVE_STATE.confirmed_fingerprint == bot._quant_live_fingerprint(
        live.snapshot
    )


def test_safety_refresh_revalidates_unchanged_state(live):
    live.tick(100.0)
    live.tick(1899.0)
    assert len(live.edits) == 1

    live.tick(1900.0)
    assert len(live.edits) == 2
    assert bot._QC_LIVE_STATE.last_confirmed_ts == 1900.0


def test_q1_rendered_content_is_forwarded_unchanged(live):
    expected = bot.render_quant_live_panel(live.snapshot)
    live.tick(100.0)
    assert live.edits[0] == ("456", "123", expected)


def test_q2_transport_contract_is_unchanged():
    ack = _result(DeliveryKind.ACK)
    no_change = _result(DeliveryKind.NO_CHANGE)
    failure = _result(DeliveryKind.TELEGRAM_ERROR)

    assert ack.is_ack and ack.is_delivered and not ack.is_failure
    assert not no_change.is_ack and no_change.is_delivered and not no_change.is_failure
    assert not failure.is_ack and not failure.is_delivered and failure.is_failure
    assert bot.QC_LONGPOLL_S == 20
    assert bot._GETUPDATES_HTTP_TIMEOUT_S == 25
    assert bot._GETUPDATES_HTTP_TIMEOUT_S > bot.QC_LONGPOLL_S
