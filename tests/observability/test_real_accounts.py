"""Tests du compte n°1 — soldes réels multi-exchange (observation passive).

Vérifie la règle de séparation des sources (héritée d'OBS_EXCHANGES) :
chaque compte porte son champ ``exchange``, une source en panne produit sa
propre ligne d'erreur et ne casse jamais la lecture des autres.
"""

from __future__ import annotations

import pytest

from observability.real_accounts import (
    RealAccountsObserver,
    configured_exchanges,
    render_compte1_block,
    render_real_accounts_detail,
)


class FakeClient:
    def __init__(self, balance=None, tickers=None, fail=False):
        self.balance = balance or {"total": {}, "free": {}}
        self.tickers = tickers or {}
        self.fail = fail
        self.balance_calls = 0

    def fetch_balance(self):
        self.balance_calls += 1
        if self.fail:
            raise RuntimeError(f"boom {id(self)}")
        return self.balance

    def fetch_ticker(self, symbol):
        if symbol in self.tickers:
            return {"last": self.tickers[symbol]}
        raise RuntimeError("no market")


@pytest.fixture()
def env_two_accounts(monkeypatch):
    for ex in ("MEXC", "BINANCE"):
        monkeypatch.setenv(f"{ex}_API_KEY", "k")
        monkeypatch.setenv(f"{ex}_API_SECRET", "s")
    for ex in ("KRAKEN", "GATEIO"):
        monkeypatch.delenv(f"{ex}_API_KEY", raising=False)
        monkeypatch.delenv(f"{ex}_API_SECRET", raising=False)
    monkeypatch.delenv("REAL_ACCOUNTS_EXCHANGES", raising=False)
    monkeypatch.delenv("REAL_ACCOUNTS_DUST_USD", raising=False)


def test_configured_exchanges_detecte_les_paires_completes(
    monkeypatch, env_two_accounts
):
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)  # clé sans secret
    assert configured_exchanges() == ["mexc"]


def test_configured_exchanges_override(monkeypatch, env_two_accounts):
    monkeypatch.setenv("REAL_ACCOUNTS_EXCHANGES", "binance")
    assert configured_exchanges() == ["binance"]


def test_sources_separees_panne_isolee(env_two_accounts):
    fakes = {
        "mexc": FakeClient(fail=True),
        "binance": FakeClient(
            balance={"total": {"USDT": 40.0, "BTC": 0.001}, "free": {"USDT": 40.0}},
            tickers={"BTC/USDT": 50_000.0},
        ),
    }
    obs = RealAccountsObserver(ttl_s=0, client_factory=lambda ex: fakes[ex])
    snaps = obs.snapshot()

    assert [s.exchange for s in snaps] == ["mexc", "binance"]
    mexc, binance = snaps
    # La panne MEXC est visible sur sa ligne, sans contaminer Binance.
    assert mexc.ok is False and "boom" in mexc.error and mexc.assets == ()
    assert binance.ok is True
    assert {a.asset for a in binance.assets} == {"USDT", "BTC"}


def test_valorisation_stables_tickers_et_sans_prix(env_two_accounts, monkeypatch):
    monkeypatch.setenv("REAL_ACCOUNTS_EXCHANGES", "binance")
    fake = FakeClient(
        balance={"total": {"USDT": 40.0, "BTC": 0.001, "XYZ": 5.0}, "free": {}},
        tickers={"BTC/USDT": 50_000.0},
    )
    obs = RealAccountsObserver(ttl_s=0, client_factory=lambda ex: fake)
    (snap,) = obs.snapshot()

    by_asset = {a.asset: a for a in snap.assets}
    assert by_asset["USDT"].usd_value == 40.0  # stable, valorisé sans ticker
    assert by_asset["BTC"].usd_value == 50.0
    assert by_asset["XYZ"].usd_value is None  # aucun marché — exclu du total
    assert snap.total_usd == 90.0
    assert snap.unpriced == 1
    # Tri par valeur décroissante, actifs sans prix en dernier.
    assert [a.asset for a in snap.assets] == ["BTC", "USDT", "XYZ"]


def test_cache_ttl(env_two_accounts, monkeypatch):
    monkeypatch.setenv("REAL_ACCOUNTS_EXCHANGES", "mexc")
    fake = FakeClient(balance={"total": {"USDT": 1.0}, "free": {}})
    obs = RealAccountsObserver(ttl_s=3600, client_factory=lambda ex: fake)
    obs.snapshot()
    obs.snapshot()
    assert fake.balance_calls == 1
    obs.snapshot(force=True)
    assert fake.balance_calls == 2


def test_render_compte1_block(env_two_accounts):
    fakes = {
        "mexc": FakeClient(fail=True),
        "binance": FakeClient(balance={"total": {"USDT": 90.0}, "free": {}}),
    }
    obs = RealAccountsObserver(ttl_s=0, client_factory=lambda ex: fakes[ex])
    block = render_compte1_block(obs.snapshot())

    assert "COMPTE N°1" in block
    assert "BINANCE" in block and "$90.00" in block and "✔" in block
    assert "MEXC" in block and "erreur" in block and "✘" in block
    assert render_compte1_block(()) == ""


def test_render_detail_html_escape_et_poussiere(env_two_accounts, monkeypatch):
    monkeypatch.setenv("REAL_ACCOUNTS_EXCHANGES", "mexc,binance")
    fakes = {
        "mexc": FakeClient(
            balance={"total": {"USDT": 10.0, "PEPE": 100.0}, "free": {}},
            tickers={"PEPE/USDT": 0.001},  # 0.10 $ → poussière
        ),
        "binance": FakeClient(fail=True),
    }
    fakes["binance"].fetch_balance = _raise_html  # erreur avec caractères HTML
    obs = RealAccountsObserver(ttl_s=0, client_factory=lambda ex: fakes[ex])
    detail = render_real_accounts_detail(obs.snapshot(), cycle=7)

    assert "Cycle #7" in detail
    assert "MEXC" in detail and "USDT : 10" in detail
    assert "+ 1 actif(s)" in detail  # PEPE agrégé en poussière
    assert "<b>hack</b>" not in detail  # HTML de l'erreur échappé
    assert "&lt;b&gt;hack&lt;/b&gt;" in detail


def _raise_html():
    raise RuntimeError("<b>hack</b>")
