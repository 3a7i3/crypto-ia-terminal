from __future__ import annotations

import csv
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
from paper_trading.ppl_capital import ScientificCapitalUnavailableError
from scripts.burnin_calibration_v3 import _initial_capital, _load_gate_funnel
from scripts.prelive_gate import STATUS_GO, gate_c_dataset
from tools.cri_calculator import (
    ScientificDatasetUnavailableError,
    compute_cri,
    coverage_score,
    drift_score,
    load_clean_regrets,
    load_clean_trades,
    trades_provenance,
)


EPOCH = "F00-TEST-EPOCH"
CREATED_AT = 1_800_000_000.0


def _epoch():
    return make_epoch_created_event(
        event_id="evt-epoch",
        paper_epoch_id=EPOCH,
        sequence=1,
        timestamp=CREATED_AT,
        initial_virtual_capital=100.0,
        code_sha="sha-f00",
        config_snapshot_hash="cfg-f00",
        schema_version=2,
    )


def _open():
    return make_position_opened_event(
        event_id="evt-open",
        paper_epoch_id=EPOCH,
        sequence=2,
        timestamp=CREATED_AT + 10,
        trade_id="low-price-ppl",
        symbol="ALTUSDT",
        side="BUY",
        principal=10.0,
        entry_price=10.0,
        entry_fee=0.01,
        decision_id="dp-low",
        schema_version=2,
        tp_price=11.0,
        sl_price=9.0,
        timeout_at=CREATED_AT + 3600,
        recovery_eligible_until=CREATED_AT + 7200,
    )


def _close():
    return make_position_closed_event(
        event_id="evt-close",
        paper_epoch_id=EPOCH,
        sequence=3,
        timestamp=CREATED_AT + 20,
        trade_id="low-price-ppl",
        exit_price=11.0,
        exit_fee=0.01,
        decision_id="dp-low",
        schema_version=2,
    )


def _unresolved():
    return make_position_unresolved_event(
        event_id="evt-unresolved",
        paper_epoch_id=EPOCH,
        sequence=3,
        timestamp=CREATED_AT + 3700,
        trade_id="low-price-ppl",
        reason="recovery_window_expired",
        schema_version=2,
    )


def _persist(root, events):
    store = DurableEventStore(root)
    for event in events:
        store.append(EPOCH, event)


def _select_ppl(monkeypatch, root):
    monkeypatch.setenv("PAPER_LIFECYCLE_AUTHORITY", "PPL_AUTHORITY")
    monkeypatch.setenv("PPL_AUTHORITY_STORE_ROOT", str(root))
    monkeypatch.setenv("PPL_AUTHORITY_EPOCH_ID", EPOCH)
    monkeypatch.setattr(wallet_sync, "_singleton", None)


def test_ppl_loader_reads_authority_store_not_legacy_projection(tmp_path, monkeypatch):
    store_root = tmp_path / "ppl"
    _persist(store_root, (_epoch(), _open(), _close()))
    _select_ppl(monkeypatch, store_root)

    legacy = tmp_path / "paper_trades.jsonl"
    legacy.write_text(
        json.dumps(
            {
                "event": "CLOSE",
                "trade_id": "legacy-fake",
                "ts": CREATED_AT + 20,
                "price": 99_000,
                "score": 99,
                "regime": "bull_trend",
                "pnl_usd": 999_999,
                "pnl_pct": 9.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    trades = load_clean_trades(legacy)

    assert [trade["trade_id"] for trade in trades] == ["low-price-ppl"]
    assert trades[0]["source_authority"] == "PPL"
    assert trades[0]["paper_epoch_id"] == EPOCH
    assert trades[0]["exit_price"] == 11.0
    assert trades[0]["pnl_usd"] != 999_999


def test_low_price_ppl_trade_is_not_misclassified_as_test_fixture(tmp_path, monkeypatch):
    store_root = tmp_path / "ppl"
    _persist(store_root, (_epoch(), _open(), _close()))
    _select_ppl(monkeypatch, store_root)

    trades = load_clean_trades(tmp_path / "ignored.jsonl")

    assert len(trades) == 1
    assert trades[0]["price"] == 11.0
    assert trades[0]["score"] == 0


def test_unresolved_ppl_outcome_is_not_a_zero_pnl_trade(tmp_path, monkeypatch):
    store_root = tmp_path / "ppl"
    _persist(store_root, (_epoch(), _open(), _unresolved()))
    _select_ppl(monkeypatch, store_root)

    assert load_clean_trades() == []
    provenance = trades_provenance()
    assert provenance["n_canonical"] == 0
    assert provenance["excluded_by_reason"] == {"unresolved_outcome": 1}


def test_ppl_placeholder_score_regime_never_feed_coverage_or_drift(tmp_path, monkeypatch):
    store_root = tmp_path / "ppl"
    _persist(store_root, (_epoch(), _open(), _close()))
    _select_ppl(monkeypatch, store_root)
    trade = load_clean_trades()[0]
    repeated = [dict(trade) for _ in range(40)]

    assert coverage_score(repeated, []) == 0.0
    assert drift_score(repeated) == 0.0


def test_cri_marks_ppl_trade_metadata_as_partial_not_empirical(tmp_path, monkeypatch):
    store_root = tmp_path / "ppl"
    _persist(store_root, (_epoch(), _open(), _close()))
    _select_ppl(monkeypatch, store_root)
    regrets = tmp_path / "regrets.jsonl"
    regrets.write_text("", encoding="utf-8")

    result = compute_cri(tmp_path / "ignored.jsonl", regrets)

    assert result["n_clean"] == 1
    assert result["trade_decision_metadata_unavailable"] == 1
    assert result["validity"] == "PARTIAL"
    assert result["sub_scores"]["drift_score"] == 0.0
    assert result["gate_ready"] is False


def test_ppl_wallet_initial_capital_comes_from_epoch_not_env(tmp_path, monkeypatch):
    store_root = tmp_path / "ppl"
    _persist(store_root, (_epoch(), _open(), _close()))
    _select_ppl(monkeypatch, store_root)
    monkeypatch.setattr(wallet_sync, "_PAPER_CAPITAL", 1000.0)

    wallet = wallet_sync.WalletSync(mode="paper")

    assert wallet.initial_capital() == pytest.approx(100.0)


def test_burnin_initial_capital_has_no_numeric_fallback_under_ppl(monkeypatch):
    monkeypatch.setenv("PAPER_LIFECYCLE_AUTHORITY", "PPL_AUTHORITY")
    monkeypatch.delenv("PPL_AUTHORITY_STORE_ROOT", raising=False)
    monkeypatch.delenv("PPL_AUTHORITY_EPOCH_ID", raising=False)
    monkeypatch.setattr(wallet_sync, "_singleton", None)

    with pytest.raises(ScientificCapitalUnavailableError):
        _initial_capital()


def test_ppl_regrets_are_bounded_by_epoch_creation(tmp_path, monkeypatch):
    store_root = tmp_path / "ppl"
    _persist(store_root, (_epoch(),))
    _select_ppl(monkeypatch, store_root)
    path = tmp_path / "regrets.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts_signal": CREATED_AT - 1,
                        "score": 70,
                        "regime": "sideways",
                    }
                ),
                json.dumps(
                    {
                        "ts_signal": CREATED_AT + 1,
                        "score": 71,
                        "regime": "sideways",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    regrets = load_clean_regrets(path)

    assert len(regrets) == 1
    assert regrets[0]["score"] == 71


def test_ppl_gate_funnel_is_bounded_by_epoch_creation(tmp_path, monkeypatch):
    store_root = tmp_path / "ppl"
    _persist(store_root, (_epoch(),))
    _select_ppl(monkeypatch, store_root)
    path = tmp_path / "gate.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "ts",
                "symbol",
                "regime",
                "score",
                "effective_min",
                "allowed",
                "failed",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "ts": CREATED_AT - 1,
                "symbol": "OLD/USDT",
                "regime": "sideways",
                "score": "80",
                "effective_min": "60",
                "allowed": "True",
                "failed": "[]",
            }
        )
        writer.writerow(
            {
                "ts": CREATED_AT + 1,
                "symbol": "NEW/USDT",
                "regime": "sideways",
                "score": "81",
                "effective_min": "60",
                "allowed": "True",
                "failed": "[]",
            }
        )

    funnel = _load_gate_funnel(path)

    assert funnel.total == 1
    assert funnel.allowed == 1
    assert funnel.score_avg == 81


def test_prelive_gate_c_uses_ppl_store_not_legacy_jsonl(tmp_path, monkeypatch):
    store_root = tmp_path / "ppl"
    _persist(store_root, (_epoch(), _open(), _close()))
    _select_ppl(monkeypatch, store_root)
    corrupt_legacy = tmp_path / "paper_trades.jsonl"
    corrupt_legacy.write_text("{this is not json\n", encoding="utf-8")
    monkeypatch.setenv("PAPER_TRADE_LOG", str(corrupt_legacy))

    result = gate_c_dataset()

    assert result.status == STATUS_GO
    assert EPOCH in result.detail


def test_ppl_scientific_dataset_fails_closed_when_epoch_config_missing(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PAPER_LIFECYCLE_AUTHORITY", "PPL_AUTHORITY")
    monkeypatch.delenv("PPL_AUTHORITY_STORE_ROOT", raising=False)
    monkeypatch.delenv("PPL_AUTHORITY_EPOCH_ID", raising=False)

    with pytest.raises(ScientificDatasetUnavailableError):
        load_clean_trades(tmp_path / "legacy.jsonl")
