from __future__ import annotations

import json

import pytest

import infra.wallet_sync as wallet_sync
from paper_trading.durable_event_store import DurableEventStore
from paper_trading.ledger_events import (
    make_epoch_created_event,
    make_position_closed_event,
    make_position_opened_event,
)
from paper_trading.ppl_capital import ScientificCapitalUnavailableError
from scripts import burnin_calibration_v3
from scripts.data_quality import CLEAN_DATA_SINCE_ACTIVE
from tools.cri_calculator import (
    ScientificDatasetUnavailableError,
    compute_cri,
    coverage_score,
    drift_score,
    load_clean_regrets,
    load_clean_trades,
    trades_provenance,
)


EPOCH = "F00-EPOCH-01"
OTHER_EPOCH = "OTHER-EPOCH"
_AFTER = CLEAN_DATA_SINCE_ACTIVE.timestamp() + 3600
_BEFORE = CLEAN_DATA_SINCE_ACTIVE.timestamp() - 3600


def _close(
    trade_id: str,
    *,
    ts: float = _AFTER,
    price: float = 100.0,
    pnl_usd: float | None = 1.0,
    source_authority: str = "",
    paper_epoch_id: str = "",
    evidence_status: str = "",
    missing_evidence_fields: str = "",
    score: int = 0,
    regime: str = "unknown",
) -> dict:
    return {
        "event": "CLOSE",
        "trade_id": trade_id,
        "ts": ts,
        "symbol": "ALT/USDT",
        "price": price,
        "exit_price": price,
        "score": score,
        "regime": regime,
        "duration_s": 3600.0,
        "pnl_usd": pnl_usd,
        "pnl_pct": 0.01 if pnl_usd is not None else None,
        "source_authority": source_authority,
        "paper_epoch_id": paper_epoch_id,
        "evidence_status": evidence_status,
        "missing_evidence_fields": missing_evidence_fields,
    }


def _write_jsonl(path, rows):
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def _enable_ppl(monkeypatch, *, store_root=None, epoch_id=EPOCH):
    monkeypatch.setenv("PAPER_LIFECYCLE_AUTHORITY", "PPL_AUTHORITY")
    monkeypatch.setenv("PPL_AUTHORITY_EPOCH_ID", epoch_id)
    if store_root is not None:
        monkeypatch.setenv("PPL_AUTHORITY_STORE_ROOT", str(store_root))


def test_ppl_population_is_exact_epoch_and_low_price_trade_is_not_fixture(
    tmp_path, monkeypatch
):
    path = tmp_path / "paper_trades.jsonl"
    rows = [
        _close("legacy", ts=_AFTER, price=98_000.0, score=75, regime="bull_trend"),
        _close(
            "ppl-keep",
            ts=_BEFORE,
            price=0.42,
            source_authority="PPL",
            paper_epoch_id=EPOCH,
            evidence_status="PARTIAL_METADATA",
            missing_evidence_fields="score,regime,market_context",
        ),
        _close(
            "ppl-other",
            price=0.55,
            source_authority="PPL",
            paper_epoch_id=OTHER_EPOCH,
            evidence_status="PARTIAL_METADATA",
            missing_evidence_fields="score,regime",
        ),
        _close(
            "ppl-unresolved",
            price=0.77,
            pnl_usd=None,
            source_authority="PPL",
            paper_epoch_id=EPOCH,
            evidence_status="UNRESOLVED",
            missing_evidence_fields="exit_price,pnl_usd,pnl_pct",
        ),
    ]
    _write_jsonl(path, rows)
    _enable_ppl(monkeypatch)

    trades = load_clean_trades(path)
    assert [row["trade_id"] for row in trades] == ["ppl-keep"]

    provenance = trades_provenance(path)
    assert provenance["population_mode"] == "PPL_EPOCH"
    assert provenance["source_authority"] == "PPL"
    assert provenance["paper_epoch_id"] == EPOCH
    assert provenance["clean_data_since"] is None
    assert provenance["close_events_total"] == 4
    assert provenance["n_canonical"] == 1
    assert provenance["decision_metadata_complete"] == 0
    assert provenance["excluded_by_reason"] == {
        "legacy_outside_ppl_epoch": 1,
        "ppl_wrong_epoch": 1,
        "ppl_unresolved_outcome": 1,
    }


def test_ppl_partial_decision_metadata_never_fabricates_cri_coverage(tmp_path, monkeypatch):
    path = tmp_path / "paper_trades.jsonl"
    rows = [
        _close(
            f"ppl-{i}",
            price=1.0 + i / 100,
            source_authority="PPL",
            paper_epoch_id=EPOCH,
            evidence_status="PARTIAL_METADATA",
            missing_evidence_fields="score,regime",
        )
        for i in range(25)
    ]
    _write_jsonl(path, rows)
    _enable_ppl(monkeypatch)

    trades = load_clean_trades(path)
    assert len(trades) == 25
    assert coverage_score(trades, []) == 0.0
    assert drift_score(trades) == 0.0

    result = compute_cri(path, tmp_path / "empty_regrets.jsonl")
    assert result["n_clean"] == 25
    assert result["paper_epoch_id"] == EPOCH
    assert result["dataset_population_mode"] == "PPL_EPOCH"
    assert result["decision_metadata_complete"] == 0
    assert result["sub_scores"]["coverage_score"] == 0.0
    assert result["sub_scores"]["drift_score"] == 0.0


def test_ppl_scientific_population_requires_explicit_authority_epoch(
    tmp_path, monkeypatch
):
    path = tmp_path / "paper_trades.jsonl"
    _write_jsonl(path, [])
    monkeypatch.setenv("PAPER_LIFECYCLE_AUTHORITY", "PPL_AUTHORITY")
    monkeypatch.delenv("PPL_AUTHORITY_EPOCH_ID", raising=False)

    with pytest.raises(ScientificDatasetUnavailableError, match="PPL_AUTHORITY_EPOCH_ID"):
        load_clean_trades(path)


def test_regrets_are_epoch_filtered_in_ppl_authority(tmp_path, monkeypatch):
    path = tmp_path / "regrets.jsonl"
    rows = [
        {
            "ts_signal": _AFTER,
            "score": 70,
            "regime": "bull_trend",
            "source_authority": "PPL",
            "paper_epoch_id": EPOCH,
        },
        {
            "ts_signal": _AFTER,
            "score": 80,
            "regime": "sideways",
            "source_authority": "PPL",
            "paper_epoch_id": OTHER_EPOCH,
        },
        {
            "ts_signal": _AFTER,
            "score": 90,
            "regime": "bear_trend",
        },
    ]
    _write_jsonl(path, rows)
    _enable_ppl(monkeypatch)

    regrets = load_clean_regrets(path)
    assert len(regrets) == 1
    assert regrets[0]["paper_epoch_id"] == EPOCH
    assert regrets[0]["source_authority"] == "PPL"


def _persist_epoch_with_realized_pnl(store_root):
    store = DurableEventStore(store_root)
    store.append(
        EPOCH,
        make_epoch_created_event(
            event_id="evt-epoch",
            paper_epoch_id=EPOCH,
            sequence=1,
            timestamp=1.0,
            initial_virtual_capital=123.45,
            code_sha="sha-f00",
            config_snapshot_hash="cfg-f00",
            schema_version=2,
        ),
    )
    store.append(
        EPOCH,
        make_position_opened_event(
            event_id="evt-open",
            paper_epoch_id=EPOCH,
            sequence=2,
            timestamp=2.0,
            trade_id="trade-1",
            symbol="BTCUSDT",
            side="BUY",
            principal=10.0,
            entry_price=100.0,
            entry_fee=0.1,
            decision_id="dp-1",
            schema_version=2,
            tp_price=110.0,
            sl_price=95.0,
            timeout_at=20.0,
            recovery_eligible_until=30.0,
        ),
    )
    store.append(
        EPOCH,
        make_position_closed_event(
            event_id="evt-close",
            paper_epoch_id=EPOCH,
            sequence=3,
            timestamp=3.0,
            trade_id="trade-1",
            exit_price=110.0,
            exit_fee=0.1,
            decision_id="dp-1",
            schema_version=2,
        ),
    )


def test_wallet_initial_capital_comes_from_epoch_and_is_restart_stable(
    tmp_path, monkeypatch
):
    store_root = tmp_path / "ppl"
    _persist_epoch_with_realized_pnl(store_root)
    _enable_ppl(monkeypatch, store_root=store_root)
    monkeypatch.setattr(wallet_sync, "_PAPER_CAPITAL", 999.0)

    first = wallet_sync.WalletSync(mode="paper")
    restarted = wallet_sync.WalletSync(mode="paper")

    assert first.initial_capital() == pytest.approx(123.45)
    assert restarted.initial_capital() == pytest.approx(123.45)
    assert first.get_balance() == pytest.approx(124.25)


def test_ppl_initial_capital_missing_store_fails_closed_without_numeric_fallback(
    tmp_path, monkeypatch
):
    _enable_ppl(monkeypatch, store_root=tmp_path / "missing")
    monkeypatch.setattr(wallet_sync, "_PAPER_CAPITAL", 1000.0)
    monkeypatch.setattr(wallet_sync, "_singleton", None)

    wallet = wallet_sync.WalletSync(mode="paper")
    with pytest.raises(ScientificCapitalUnavailableError):
        wallet.initial_capital()

    with pytest.raises(ScientificCapitalUnavailableError):
        burnin_calibration_v3._initial_capital()
