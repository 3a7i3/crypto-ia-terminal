from __future__ import annotations

import json
from pathlib import Path

import pytest

import infra.wallet_sync as wallet_sync
from paper_trading.durable_event_store import DurableEventStore
from paper_trading.ledger_events import make_epoch_created_event


EPOCH_ID = "obs-wallet-ppl-01"


def _persist_epoch(store_root: Path, *, initial_capital: float) -> None:
    event = make_epoch_created_event(
        event_id="evt-obs-wallet-ppl-01",
        paper_epoch_id=EPOCH_ID,
        sequence=1,
        timestamp=1.0,
        initial_virtual_capital=initial_capital,
        code_sha="sha-obs-wallet-ppl-01",
        config_snapshot_hash="cfg-obs-wallet-ppl-01",
        schema_version=2,
    )
    DurableEventStore(store_root).append(EPOCH_ID, event)


def test_obs_wallet_ppl_01_startup_wording_declares_ppl_replay_provenance() -> None:
    source = Path("core/advisor_loop.py").read_text(encoding="utf-8")

    assert "paper fallback WALLET_PAPER_CAPITAL" not in source
    assert "provenance=PPL_REPLAY" in source
    assert "legacy_fallback=disabled" in source
    assert 'os.getenv("PPL_AUTHORITY_EPOCH_ID", "")' in source
    assert "provenance=WALLET_PAPER_CAPITAL_PLUS_LEGACY" in source


def test_obs_wallet_ppl_01_ppl_capital_remains_epoch_derived(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_root = tmp_path / "ppl"
    legacy = tmp_path / "legacy.jsonl"
    legacy.write_text(
        json.dumps({"event": "CLOSE", "pnl_usd": 999999.0}) + "\n",
        encoding="utf-8",
    )
    _persist_epoch(store_root, initial_capital=321.25)

    monkeypatch.setenv("PAPER_LIFECYCLE_AUTHORITY", "PPL_AUTHORITY")
    monkeypatch.setenv("PPL_AUTHORITY_STORE_ROOT", str(store_root))
    monkeypatch.setenv("PPL_AUTHORITY_EPOCH_ID", EPOCH_ID)
    monkeypatch.setenv("PAPER_TRADE_LOG", str(legacy))
    monkeypatch.setattr(wallet_sync, "_PAPER_CAPITAL", 888.0)

    wallet = wallet_sync.WalletSync(mode="paper")

    assert wallet_sync.get_scientific_capital() == pytest.approx(321.25)
    assert wallet.get_balance() == pytest.approx(321.25)
    assert wallet.initial_capital() == pytest.approx(321.25)


@pytest.mark.parametrize("authority", ["LEGACY_AUTHORITY", "PPL_SHADOW"])
def test_obs_wallet_ppl_01_legacy_shadow_semantics_are_unchanged(
    authority: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = tmp_path / "legacy.jsonl"
    legacy.write_text(
        json.dumps({"event": "CLOSE", "pnl_usd": 2.5}) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("PAPER_LIFECYCLE_AUTHORITY", authority)
    monkeypatch.setenv("PAPER_TRADE_LOG", str(legacy))
    monkeypatch.setattr(wallet_sync, "_PAPER_CAPITAL", 100.0)

    assert wallet_sync.get_scientific_capital() == pytest.approx(102.5)
