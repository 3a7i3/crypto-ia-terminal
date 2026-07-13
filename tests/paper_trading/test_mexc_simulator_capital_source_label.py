"""
test_mexc_simulator_capital_source_label.py — Régression label "Source" du
panneau MEXC SIM (réconciliation Telegram 2026-07-13).

Avant ce correctif, le panneau "MEXC SIM — Compte actif" affichait
"Source : Solde reel MEXC" en dur, même quand le capital provenait en
réalité de WalletSync en mode paper (le cas de tous les déploiements
observés en production, cf. log "[SIM] Capital via WalletSync (paper)").
"""

from __future__ import annotations

from unittest.mock import MagicMock

from paper_trading.mexc_simulator import MexcSimulator


class _FakeWallet:
    def __init__(self, mode: str, balance: float):
        self.mode = mode
        self._balance = balance

    def get_balance(self, force_refresh: bool = False) -> float:
        return self._balance


def _start_and_capture(monkeypatch, wallet, mexc_reader=None):
    messages: list[str] = []
    # get_wallet_sync est importé localement dans start() — patcher le module
    # source (infra.wallet_sync) pour que l'import local le résolve.
    import infra.wallet_sync as wallet_sync_module

    monkeypatch.setattr(wallet_sync_module, "get_wallet_sync", lambda: wallet)

    sim = MexcSimulator(mexc_reader=mexc_reader, telegram_fn=messages.append)
    sim.start()
    sim._running = False  # stoppe la boucle de monitoring en arrière-plan
    return messages


def test_paper_mode_shows_walletsync_source(monkeypatch):
    wallet = _FakeWallet(mode="paper", balance=676.28)

    messages = _start_and_capture(monkeypatch, wallet)

    assert any("WalletSync (paper)" in m for m in messages)
    assert not any("Solde reel MEXC" in m for m in messages)


def test_real_balance_mode_shows_real_mexc_source(monkeypatch):
    wallet = _FakeWallet(mode="live", balance=0.0)  # get_balance() fallback only
    reader = MagicMock()
    reader.spot.fetch_balance.return_value = {"free": {"USDT": 12.5}}
    reader.futures.fetch_balance.return_value = {"free": {"USDT": 0.0}}

    messages = _start_and_capture(monkeypatch, wallet, mexc_reader=reader)

    assert any("Solde reel MEXC" in m for m in messages)


def test_forced_env_capital_shows_forced_source(monkeypatch):
    monkeypatch.setenv("MEXC_SIM_CAPITAL", "50")
    wallet = _FakeWallet(mode="live", balance=0.0)
    reader = MagicMock()
    reader.spot.fetch_balance.return_value = {"free": {"USDT": 10.0}}
    reader.futures.fetch_balance.return_value = {"free": {"USDT": 0.0}}

    messages = _start_and_capture(monkeypatch, wallet, mexc_reader=reader)

    assert any("Forcé via env (MEXC_SIM_CAPITAL)" in m for m in messages)
