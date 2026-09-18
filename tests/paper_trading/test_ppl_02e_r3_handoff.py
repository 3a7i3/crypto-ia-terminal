from __future__ import annotations

import json

import pytest

import infra.wallet_sync as wallet_sync
from paper_trading.durable_event_store import DurableEventStore
from paper_trading.ledger_events import (
    make_epoch_created_event,
    make_position_closed_event,
    make_position_opened_event,
    make_position_unresolved_event,
)
from paper_trading.mexc_simulator import MexcSimulator
from paper_trading.paper_authority import PaperLifecycleAuthority
from paper_trading.ppl_authority_gate import validate_ppl_authority_dataset
from paper_trading.ppl_capital import (
    ScientificCapitalUnavailableError,
    scientific_capital_from_ppl,
)
from paper_trading.ppl_compatibility import (
    build_compatibility_rows,
    project_ppl_to_legacy_jsonl,
)
from paper_trading.recorder import PaperTradeRecorder


EPOCH = "pe-r3-v2"


def epoch_event(epoch_id=EPOCH, schema_version=2):
    return make_epoch_created_event(
        event_id=f"evt-{epoch_id}-epoch",
        paper_epoch_id=epoch_id,
        sequence=1,
        timestamp=1.0,
        initial_virtual_capital=100.0,
        code_sha="sha-r3",
        config_snapshot_hash="cfg-r3",
        schema_version=schema_version,
    )


def open_event(epoch_id=EPOCH, schema_version=2):
    kwargs = {}
    if schema_version == 2:
        kwargs.update(
            tp_price=104.0,
            sl_price=98.0,
            timeout_at=20.0,
            recovery_eligible_until=30.0,
        )
    return make_position_opened_event(
        event_id=f"evt-{epoch_id}-open",
        paper_epoch_id=epoch_id,
        sequence=2,
        timestamp=10.0,
        trade_id="trade-r3",
        symbol="BTCUSDT",
        side="BUY",
        principal=10.0,
        entry_price=100.0,
        entry_fee=0.01,
        decision_id="decision-r3",
        schema_version=schema_version,
        **kwargs,
    )


def close_event(epoch_id=EPOCH, schema_version=2):
    return make_position_closed_event(
        event_id=f"evt-{epoch_id}-close",
        paper_epoch_id=epoch_id,
        sequence=3,
        timestamp=15.0,
        trade_id="trade-r3",
        exit_price=110.0,
        exit_fee=0.01,
        decision_id="decision-r3",
        schema_version=schema_version,
    )


def unresolved_event(epoch_id=EPOCH):
    return make_position_unresolved_event(
        event_id=f"evt-{epoch_id}-unresolved",
        paper_epoch_id=epoch_id,
        sequence=3,
        timestamp=31.0,
        trade_id="trade-r3",
        reason="recovery_window_expired",
        schema_version=2,
    )


def persist(store_root, events):
    store = DurableEventStore(store_root)
    for event in events:
        store.append(event.paper_epoch_id, event)


def test_r3_ppl_scientific_capital_uses_epoch_plus_realized_pnl(tmp_path):
    store_root = tmp_path / "ppl"
    persist(store_root, (epoch_event(), open_event(), close_event()))

    value = scientific_capital_from_ppl(store_root, EPOCH)

    # gross +1.0; entry/exit fees 0.02 => realized +0.98
    assert value == pytest.approx(100.98)


def test_r3_ppl_scientific_capital_refuses_unresolved(tmp_path):
    store_root = tmp_path / "ppl"
    persist(store_root, (epoch_event(), open_event(), unresolved_event()))

    with pytest.raises(ScientificCapitalUnavailableError, match="UNRESOLVED|unresolved"):
        scientific_capital_from_ppl(store_root, EPOCH)


def test_r3_wallet_ppl_authority_ignores_legacy_jsonl(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy.jsonl"
    legacy.write_text(
        json.dumps({"event": "CLOSE", "pnl_usd": 999999.0}) + "\n",
        encoding="utf-8",
    )
    store_root = tmp_path / "ppl"
    persist(store_root, (epoch_event(), open_event(), close_event()))

    monkeypatch.setenv("PAPER_LIFECYCLE_AUTHORITY", "PPL_AUTHORITY")
    monkeypatch.setenv("PPL_AUTHORITY_STORE_ROOT", str(store_root))
    monkeypatch.setenv("PPL_AUTHORITY_EPOCH_ID", EPOCH)
    monkeypatch.setenv("PAPER_TRADE_LOG", str(legacy))
    monkeypatch.setattr(wallet_sync, "_PAPER_CAPITAL", 777.0)

    assert wallet_sync.get_scientific_capital() == pytest.approx(100.98)


def test_r3_wallet_ppl_authority_has_no_legacy_fallback(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy.jsonl"
    legacy.write_text(
        json.dumps({"event": "CLOSE", "pnl_usd": 12.0}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PAPER_LIFECYCLE_AUTHORITY", "PPL_AUTHORITY")
    monkeypatch.delenv("PPL_AUTHORITY_STORE_ROOT", raising=False)
    monkeypatch.delenv("PPL_AUTHORITY_EPOCH_ID", raising=False)
    monkeypatch.setenv("PAPER_TRADE_LOG", str(legacy))

    with pytest.raises(ScientificCapitalUnavailableError):
        wallet_sync.get_scientific_capital()


def test_r3_wallet_legacy_and_shadow_preserve_existing_semantics(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy.jsonl"
    legacy.write_text(
        "\n".join(
            [
                json.dumps({"event": "CLOSE", "pnl_usd": 2.5}),
                json.dumps({"event": "CLOSE", "pnl_usd": -1.0}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PAPER_TRADE_LOG", str(legacy))
    monkeypatch.setattr(wallet_sync, "_PAPER_CAPITAL", 100.0)

    for authority in ("LEGACY_AUTHORITY", "PPL_SHADOW"):
        monkeypatch.setenv("PAPER_LIFECYCLE_AUTHORITY", authority)
        assert wallet_sync.get_scientific_capital() == pytest.approx(101.5)


def test_r3_walletsync_paper_balance_uses_same_authority_accessor(tmp_path, monkeypatch):
    store_root = tmp_path / "ppl"
    persist(store_root, (epoch_event(), open_event(), close_event()))
    monkeypatch.setenv("PAPER_LIFECYCLE_AUTHORITY", "PPL_AUTHORITY")
    monkeypatch.setenv("PPL_AUTHORITY_STORE_ROOT", str(store_root))
    monkeypatch.setenv("PPL_AUTHORITY_EPOCH_ID", EPOCH)

    wallet = wallet_sync.WalletSync(mode="paper")
    assert wallet.get_balance() == pytest.approx(wallet_sync.get_scientific_capital())


def test_r3_legacy_restore_is_disabled_under_ppl_authority(monkeypatch):
    import paper_trading.recorder as recorder

    monkeypatch.setattr(
        recorder,
        "get_recorder",
        lambda: (_ for _ in ()).throw(AssertionError("legacy recorder read")),
    )
    sim = MexcSimulator(
        lifecycle_authority=PaperLifecycleAuthority.PPL_AUTHORITY,
        authority_runtime=object(),
    )

    assert sim._restore_positions() == 0


def test_r3_authority_gate_accepts_clean_v2_epoch(tmp_path):
    store_root = tmp_path / "ppl"
    persist(store_root, (epoch_event(), open_event()))

    report = validate_ppl_authority_dataset(store_root, EPOCH)

    assert report.ready_for_mutation is True
    assert report.reason == "READY"
    assert report.open_positions == 1


def test_r3_authority_gate_rejects_v1_epoch(tmp_path):
    epoch_id = "pe-r3-v1"
    store_root = tmp_path / "ppl"
    persist(
        store_root,
        (
            epoch_event(epoch_id, schema_version=1),
            open_event(epoch_id, schema_version=1),
        ),
    )

    report = validate_ppl_authority_dataset(store_root, epoch_id)

    assert report.ready_for_mutation is False
    assert report.reason == "SCHEMA_NOT_REPLAY_COMPLETE"


def test_r3_authority_gate_rejects_unresolved_capital(tmp_path):
    store_root = tmp_path / "ppl"
    persist(store_root, (epoch_event(), open_event(), unresolved_event()))

    report = validate_ppl_authority_dataset(store_root, EPOCH)

    assert report.ready_for_mutation is False
    assert report.reason == "UNRESOLVED_CAPITAL"


def test_r3_compatibility_projection_preserves_legacy_prefix_and_is_idempotent(
    tmp_path,
):
    target = tmp_path / "paper_trades.jsonl"
    legacy_prefix = b'{"legacy_original":true}\n'
    target.write_bytes(legacy_prefix)
    events = (epoch_event(), open_event(), close_event())

    appended_first = project_ppl_to_legacy_jsonl(events, target)
    after_first = target.read_bytes()
    appended_second = project_ppl_to_legacy_jsonl(events, target)
    after_second = target.read_bytes()

    assert appended_first == 2
    assert appended_second == 0
    assert after_first.startswith(legacy_prefix)
    assert after_second == after_first


def test_r3_compatibility_rows_have_exact_ppl_provenance_and_pnl():
    rows = build_compatibility_rows((epoch_event(), open_event(), close_event()))

    assert len(rows) == 2
    opened, closed = rows
    assert opened["source_authority"] == "PPL"
    assert opened["paper_epoch_id"] == EPOCH
    assert opened["ppl_event_id"] == open_event().event_id
    assert opened["projection_id"]
    assert opened["evidence_status"] == "PARTIAL_METADATA"
    assert "score" in opened["missing_evidence_fields"]
    assert opened["fee_entry_usd"] == pytest.approx(0.01)
    assert closed["pnl_usd"] == pytest.approx(0.98)
    assert closed["pnl_pct"] == pytest.approx(0.1)
    assert "reason" in closed["missing_evidence_fields"]


def test_r3_compatibility_unresolved_never_becomes_zero_pnl():
    rows = build_compatibility_rows(
        (epoch_event(), open_event(), unresolved_event())
    )
    close_row = rows[-1]

    assert close_row["evidence_status"] == "UNRESOLVED"
    assert close_row["exit_price"] is None
    assert close_row["pnl_usd"] is None
    assert close_row["pnl_pct"] is None
    assert close_row["reason"] == "ppl_unresolved:recovery_window_expired"


def test_r3_recorder_preserves_projection_provenance(tmp_path):
    target = tmp_path / "paper_trades.jsonl"
    project_ppl_to_legacy_jsonl(
        (epoch_event(), open_event(), close_event()),
        target,
    )

    events = PaperTradeRecorder(str(target)).events()
    trades = PaperTradeRecorder(str(target)).trades()

    assert len(events) == 2
    assert events[0].source_authority == "PPL"
    assert events[0].paper_epoch_id == EPOCH
    assert events[0].ppl_event_id == open_event().event_id
    assert events[0].projection_id
    assert len(trades) == 1
    assert trades[0].source_authority == "PPL"
    assert trades[0].paper_epoch_id == EPOCH
    assert trades[0].open_ppl_event_id == open_event().event_id
    assert trades[0].close_ppl_event_id == close_event().event_id
