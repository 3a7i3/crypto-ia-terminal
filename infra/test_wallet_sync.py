"""Tests WalletSync — continuité du grand livre à travers les redémarrages.

Régression : une revue (2026-07) a trouvé qu'une version antérieure de
get_balance() (mode paper) soustrayait une baseline capturée à l'__init__,
ce qui remettait le capital de sizing à zéro à chaque redémarrage du process.
Ces tests verrouillent le comportement correct : get_balance() est un grand
livre continu (source du sizing), session_pnl_since_restart() est un compteur
de confort qui, lui, repart bien de zéro à chaque nouvelle instance.
"""

from __future__ import annotations

import json

import infra.wallet_sync as ws


def _write_close(path, pnl_usd: float) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"event": "CLOSE", "pnl_usd": pnl_usd}) + "\n")


class TestGetBalanceContinuousAcrossRestarts:
    def test_new_instance_does_not_reset_balance(self, tmp_path, monkeypatch):
        trades_path = tmp_path / "paper_trades.jsonl"
        monkeypatch.setattr(ws, "_TRADES_LOG", trades_path)
        monkeypatch.setattr(ws, "_PAPER_CAPITAL", 1000.0)

        _write_close(trades_path, -50.0)
        _write_close(trades_path, 20.0)

        wallet_before_restart = ws.WalletSync(mode="paper")
        assert wallet_before_restart.get_balance() == 1000.0 - 50.0 + 20.0

        # "Redémarrage" : nouvelle instance, même ledger persistant sur disque.
        wallet_after_restart = ws.WalletSync(mode="paper")
        assert wallet_after_restart.get_balance() == wallet_before_restart.get_balance()

    def test_balance_keeps_growing_with_new_trades_post_restart(
        self, tmp_path, monkeypatch
    ):
        trades_path = tmp_path / "paper_trades.jsonl"
        monkeypatch.setattr(ws, "_TRADES_LOG", trades_path)
        monkeypatch.setattr(ws, "_PAPER_CAPITAL", 1000.0)

        _write_close(trades_path, 100.0)
        wallet = ws.WalletSync(mode="paper")  # instance "post-restart"
        assert wallet.get_balance() == 1100.0

        _write_close(trades_path, 30.0)  # nouveau trade après le restart
        assert wallet.get_balance() == 1130.0  # cumul continu, pas de reset


class TestSessionPnlSinceRestart:
    def test_zero_right_after_init_even_with_prior_history(self, tmp_path, monkeypatch):
        trades_path = tmp_path / "paper_trades.jsonl"
        monkeypatch.setattr(ws, "_TRADES_LOG", trades_path)
        monkeypatch.setattr(ws, "_PAPER_CAPITAL", 1000.0)

        _write_close(trades_path, -200.0)  # historique pré-existant
        wallet = ws.WalletSync(mode="paper")
        assert wallet.session_pnl_since_restart() == 0.0

    def test_reflects_only_trades_after_this_instance_started(
        self, tmp_path, monkeypatch
    ):
        trades_path = tmp_path / "paper_trades.jsonl"
        monkeypatch.setattr(ws, "_TRADES_LOG", trades_path)
        monkeypatch.setattr(ws, "_PAPER_CAPITAL", 1000.0)

        _write_close(trades_path, -200.0)  # avant le "redémarrage"
        wallet = ws.WalletSync(mode="paper")

        _write_close(trades_path, 15.0)  # après
        _write_close(trades_path, -5.0)  # après
        assert wallet.session_pnl_since_restart() == 10.0
        # get_balance() reste le grand livre complet, jamais affecté par la session
        assert wallet.get_balance() == 1000.0 - 200.0 + 15.0 - 5.0
