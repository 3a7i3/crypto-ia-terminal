from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import observability.ppl_comparison as ppl_comparison
from observability.ppl_comparison import build_ppl_comparison_snapshot
from paper_trading.durable_event_store import DurableEventStore
from paper_trading.mexc_simulator import MexcPosition, MexcSimulator, OrderSide
from paper_trading.ppl_shadow import PPLShadowRuntime, ShadowEpochManifest


def _patch_recorder_to_tmp(monkeypatch, tmp_path):
    """Redirect the legacy PaperTradeRecorder singleton to a scratch file."""
    import paper_trading.recorder as recorder_module

    rec = recorder_module.PaperTradeRecorder(
        log_path=str(tmp_path / "paper_trades.jsonl")
    )
    monkeypatch.setattr(recorder_module, "_recorder", rec)
    return rec


def _reader(price: float = 100.0) -> MagicMock:
    reader = MagicMock()
    reader.spot.fetch_ticker.return_value = {"last": price}
    return reader


class _Sim:
    def __init__(self, shadow=None):
        import threading

        self._lock = threading.Lock()
        self._capital = 100.0
        self._initial_capital = 100.0
        self._positions = {}
        self._closed = []
        self._shadow_observer = shadow


def _active_shadow(tmp_path, capital=100.0):
    manifest = ShadowEpochManifest(
        paper_epoch_id="web02-epoch",
        created_at=1.0,
        initial_virtual_capital=capital,
        code_sha="a" * 40,
        config_snapshot_hash="b" * 64,
    )
    shadow = PPLShadowRuntime(
        manifest=manifest,
        store=DurableEventStore(tmp_path / "ppl"),
    )
    assert shadow.bind_legacy_state(
        available_capital=capital,
        open_positions=[],
    )
    return shadow


def _build(sim):
    return build_ppl_comparison_snapshot(
        sim,
        cycle=7,
        process_instance_id="pid-1",
        source_sha="c" * 40,
        now_fn=lambda: 10.0,
    )


def _by_field(doc, domain, field, trade_id=None):
    return next(
        row
        for row in doc["comparisons"]
        if row["domain"] == domain
        and row["field"] == field
        and row["trade_id"] == trade_id
    )


def test_off_shadow_never_fabricates_convergence():
    doc = _build(_Sim())
    assert doc["shadow_status"] == "OFF"
    assert doc["comparison_available"] is False
    assert doc["comparisons"] == []
    assert doc["summary"]["total"] == 0
    assert "convergence must not be inferred" in doc[
        "comparison_unavailable_reason"
    ]


def test_active_zero_position_snapshot_compares_cash_and_unrealized(tmp_path):
    shadow = _active_shadow(tmp_path)
    doc = _build(_Sim(shadow))

    assert doc["comparison_available"] is True
    cash = _by_field(doc, "accounting", "free_cash")
    assert cash["relation"] == "EQUAL"
    assert cash["delta_ppl_minus_legacy"] == pytest.approx(0.0)

    unrealized = _by_field(doc, "valuation", "unrealized_pnl")
    assert unrealized["classification"] == "COMPARABLE"
    assert unrealized["relation"] == "EQUAL"



def test_legacy_quiescence_exposes_pending_and_transition_facts_without_freeze_inference(tmp_path):
    sim = _Sim(_active_shadow(tmp_path))
    sim._orders = {
        "pending": SimpleNamespace(status="PENDING"),
        "filled": SimpleNamespace(status="FILLED"),
    }
    sim._legacy_transitions_in_flight = 2

    legacy = ppl_comparison._snapshot_legacy(sim)
    quiescence = ppl_comparison._legacy_quiescence(legacy)
    assert quiescence["pending_order_count"]["value"] == 1
    assert quiescence["pending_order_count"]["status"] == "PRESENT"
    assert quiescence["lifecycle_transitions_in_flight"]["value"] == 2
    assert quiescence["admissions_state"]["value"] is None
    assert quiescence["admissions_state"]["status"] == "UNRESOLVED"


def test_known_cash_divergence_is_visible_not_repaired(tmp_path):
    shadow = _active_shadow(tmp_path)
    sim = _Sim(shadow)
    sim._capital = 99.99

    cash = _by_field(_build(sim), "accounting", "free_cash")
    assert cash["legacy"]["value"] == pytest.approx(99.99)
    assert cash["ppl"]["value"] == pytest.approx(100.0)
    assert cash["relation"] == "DIFFERENT"
    assert cash["delta_ppl_minus_legacy"] == pytest.approx(0.01)


def test_restored_unknown_entry_fee_stays_unresolved(tmp_path):
    shadow = _active_shadow(tmp_path)
    from paper_trading.ppl_shadow import ShadowOpenFact

    shadow.observe_open(
        ShadowOpenFact(
            trade_id="T1",
            symbol="BTC/USDT",
            side="BUY",
            principal=10.0,
            entry_price=100.0,
            entry_fee=0.01,
            timestamp=2.0,
        )
    )

    sim = _Sim(shadow)
    sim._capital = 89.99
    sim._positions["BTC/USDT"] = MexcPosition(
        pos_id="T1",
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        qty_usd=10.0,
        entry_price=100.0,
        tp_price=104.0,
        sl_price=98.0,
        fee_entry_usd=0.0,
        score=70,
        personality="restored",
        opened_ts=2.0,
        restored_evidence_gaps=["fee_entry_unknown"],
    )

    fee = _by_field(
        _build(sim), "open_position", "entry_fee", "T1"
    )
    assert fee["classification"] == "UNRESOLVED"
    assert fee["relation"] == "NOT_COMPARABLE"
    assert fee["legacy"]["value"] == 0.0
    assert fee["legacy"]["status"] == "UNRESOLVED"
    assert fee["delta_ppl_minus_legacy"] is None


def test_side_compares_canonically_but_preserves_raw_values(tmp_path):
    shadow = _active_shadow(tmp_path)
    from paper_trading.ppl_shadow import ShadowOpenFact

    shadow.observe_open(
        ShadowOpenFact(
            trade_id="T2",
            symbol="ETH/USDT",
            side="SELL",
            principal=10.0,
            entry_price=100.0,
            entry_fee=0.01,
            timestamp=2.0,
        )
    )
    sim = _Sim(shadow)
    sim._capital = 89.99
    sim._positions["ETH/USDT"] = MexcPosition(
        pos_id="T2",
        symbol="ETH/USDT",
        side=OrderSide.SELL,
        qty_usd=10.0,
        entry_price=100.0,
        tp_price=96.0,
        sl_price=102.0,
        fee_entry_usd=0.01,
        score=70,
        personality="test",
        opened_ts=2.0,
    )

    side = _by_field(_build(sim), "open_position", "side", "T2")
    assert side["legacy"]["value"] == "SELL"
    assert side["ppl"]["value"] == "SHORT"
    assert side["relation"] == "EQUAL"
    assert side["comparison_rule"] == "canonical_side"


def test_realized_and_fee_domains_do_not_invent_equivalence(tmp_path):
    shadow = _active_shadow(tmp_path)
    sim = _Sim(shadow)
    sim._closed.append(
        SimpleNamespace(
            pos_id="OLD",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            qty_usd=10.0,
            entry_price=100.0,
            fee_entry_usd=0.01,
            exit_price=101.0,
            pnl_usd=0.08,
            closed_ts=3.0,
            close_reason="TP",
            decision_id=None,
            restored_evidence_gaps=[],
        )
    )

    doc = _build(sim)
    realized = _by_field(doc, "performance", "realized_pnl")
    fees = _by_field(doc, "accounting", "fees_paid")
    assert realized["classification"] == "PARTIAL"
    assert realized["delta_ppl_minus_legacy"] is None
    assert fees["classification"] == "UNRESOLVED"
    assert fees["legacy"]["value"] is None



def _stable_test_legacy(cash: float):
    return {
        "free_cash": cash,
        "initial_capital": 100.0,
        "positions": [],
        "closed_session": [],
    }


def _stable_test_ppl_off():
    return {
        "status": "OFF",
        "paper_epoch_id": None,
        "last_error": None,
        "projection": None,
        "events": [],
    }


def test_source_pair_capture_retries_until_two_consecutive_reads_match(monkeypatch):
    legacy_reads = iter(
        [
            _stable_test_legacy(99.0),
            _stable_test_legacy(100.0),
            _stable_test_legacy(100.0),
        ]
    )
    monkeypatch.setattr(
        ppl_comparison,
        "_snapshot_legacy",
        lambda _sim: next(legacy_reads),
    )
    monkeypatch.setattr(
        ppl_comparison,
        "_snapshot_ppl",
        lambda _sim: _stable_test_ppl_off(),
    )
    monkeypatch.setattr(ppl_comparison.time, "sleep", lambda _seconds: None)

    legacy, ppl = ppl_comparison._snapshot_sources_consistently(object())

    assert legacy["free_cash"] == 100.0
    assert ppl["status"] == "OFF"


def test_source_pair_capture_withholds_continuously_moving_state(monkeypatch):
    counter = {"value": 0}

    def moving_legacy(_sim):
        counter["value"] += 1
        return _stable_test_legacy(float(counter["value"]))

    monkeypatch.setattr(ppl_comparison, "_snapshot_legacy", moving_legacy)
    monkeypatch.setattr(
        ppl_comparison,
        "_snapshot_ppl",
        lambda _sim: _stable_test_ppl_off(),
    )
    monkeypatch.setattr(ppl_comparison.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="bounded coherent capture"):
        ppl_comparison._snapshot_sources_consistently(object())


# ---------------------------------------------------------------------------
# WEB-02 causal-coherence gate — generation-based, on top of byte stability.
# ---------------------------------------------------------------------------


def test_generation_open_then_ppl_observation_admits_comparison(monkeypatch, tmp_path):
    """(1) Legacy OPEN generation observed by PPL -> comparison admitted."""
    _patch_recorder_to_tmp(monkeypatch, tmp_path)
    shadow = _active_shadow(tmp_path)
    sim = MexcSimulator(mexc_reader=_reader(), shadow_observer=shadow)
    sim._capital = 100.0
    sim._initial_capital = 100.0

    order = sim.place_market_order(
        symbol="BTC/USDT", side="BUY", qty_usd=10.0, current_price=100.0
    )
    assert order.status.value == "FILLED"
    assert sim._legacy_generation == 1
    assert shadow.consistent_view().observed_legacy_generation == 1

    doc = _build(sim)
    assert doc["comparison_available"] is True


def test_unacknowledged_legacy_generation_withholds_artifact(tmp_path):
    """(2) Legacy generation not yet acknowledged by PPL -> artifact retained."""
    shadow = _active_shadow(tmp_path)
    sim = _Sim(shadow)
    # Legacy claims to be at generation 1 but never sent PPL a fact for it
    # (PPL's own ack, from a fresh bind with zero observations, stays 0).
    sim._legacy_generation = 1

    with pytest.raises(RuntimeError, match="generation mismatch"):
        _build(sim)


def test_close_transition_withholds_artifact(tmp_path):
    """(3) Legacy CLOSE in transition -> artifact retained."""
    shadow = _active_shadow(tmp_path)
    sim = _Sim(shadow)
    sim._legacy_transitions_in_flight = 1

    with pytest.raises(RuntimeError, match="CLOSE mutation in progress"):
        _build(sim)


def test_close_transition_clears_after_full_mutation(monkeypatch, tmp_path):
    """A completed CLOSE never leaves the transition marker set."""
    _patch_recorder_to_tmp(monkeypatch, tmp_path)
    shadow = _active_shadow(tmp_path)
    sim = MexcSimulator(mexc_reader=_reader(), shadow_observer=shadow)
    sim._capital = 100.0
    sim._initial_capital = 100.0

    sim.place_market_order(
        symbol="BTC/USDT", side="BUY", qty_usd=10.0, current_price=100.0
    )
    sim._close_position("BTC/USDT", 110.0, "TP")

    assert sim._legacy_transitions_in_flight == 0
    assert sim._legacy_generation == 2
    assert shadow.consistent_view().observed_legacy_generation == 2

    doc = _build(sim)
    assert doc["comparison_available"] is True


def test_ppl_failure_leaves_legacy_authoritative_and_ppl_honest(monkeypatch, tmp_path):
    """(5) A PPL append failure never blocks Legacy and is reported honestly."""
    _patch_recorder_to_tmp(monkeypatch, tmp_path)
    shadow = _active_shadow(tmp_path)

    def boom(*_args, **_kwargs):
        raise OSError("disk failure")

    monkeypatch.setattr(shadow.store, "append", boom)

    sim = MexcSimulator(mexc_reader=_reader(), shadow_observer=shadow)
    sim._capital = 100.0
    sim._initial_capital = 100.0

    order = sim.place_market_order(
        symbol="BTC/USDT", side="BUY", qty_usd=10.0, current_price=100.0
    )
    assert order.status.value == "FILLED"
    assert "BTC/USDT" in sim._positions
    assert sim._legacy_generation == 1

    doc = _build(sim)
    assert doc["shadow_status"] == "DEGRADED"
    assert doc["comparison_available"] is False


def test_legacy_admission_freeze_is_observable_and_blocks_all_new_order_types(
    monkeypatch, tmp_path
):
    """A boundary freeze blocks every new Legacy admission and leaves audit pairs."""
    from paper_trading.admission_ledger import (
        get_admission_ledger,
        reset_admission_ledger_singleton,
    )

    monkeypatch.setenv("PAPER_LEGACY_ADMISSIONS_FROZEN", "true")
    monkeypatch.setenv("PAPER_ADMISSION_LEDGER", str(tmp_path / "admission.jsonl"))
    reset_admission_ledger_singleton()

    sim = MexcSimulator(mexc_reader=_reader())
    sim._capital = 100.0
    sim._initial_capital = 100.0

    market = sim.place_market_order(
        symbol="BTC/USDT", side="BUY", qty_usd=10.0, current_price=100.0
    )
    limit = sim.place_limit_order(
        symbol="ETH/USDT", side="BUY", qty_usd=10.0, limit_price=100.0
    )
    stop_limit = sim.place_stop_limit_order(
        symbol="SOL/USDT",
        side="BUY",
        qty_usd=10.0,
        stop_price=101.0,
        limit_price=100.0,
    )

    assert [market.status.value, limit.status.value, stop_limit.status.value] == [
        "REJECTED",
        "REJECTED",
        "REJECTED",
    ]
    assert sim._positions == {}
    assert sim._orders == {}
    assert sim._legacy_admissions_state == "FROZEN"

    events = get_admission_ledger().events()
    outcomes = [row for row in events if row["event"] == "ADMISSION_OUTCOME"]
    assert len(outcomes) == 3
    assert {row["write_result"] for row in outcomes} == {"REJECTED_FROZEN"}
    assert {row["anomaly"] for row in outcomes} == {
        "order_type=MARKET",
        "order_type=LIMIT",
        "order_type=STOP_LIMIT",
    }

    legacy = ppl_comparison._snapshot_legacy(sim)
    quiescence = ppl_comparison._legacy_quiescence(legacy)
    assert quiescence["admissions_state"] == {
        "value": "FROZEN",
        "status": "PRESENT",
        "provenance": "PAPER_LEGACY_ADMISSIONS_FROZEN=true at process bootstrap",
    }


def test_legacy_admission_freeze_rejects_invalid_configuration(monkeypatch):
    monkeypatch.setenv("PAPER_LEGACY_ADMISSIONS_FROZEN", "perhaps")
    with pytest.raises(ValueError, match="must be an explicit boolean"):
        MexcSimulator(mexc_reader=_reader())
