"""AccountCollector — soldes, marge, equity (ADR-0019, T2).

Faux client ccxt INJECTÉ, motif de `tests/observability/test_real_accounts.py` :
aucun appel réseau n'est possible depuis ces tests.
"""

from __future__ import annotations

from observation.accounts.account_collector import collect_account


class FakeClient:
    """Faux client ccxt — ne porte AUCUNE méthode d'ordre, par construction."""

    def __init__(self, balance=None, tickers=None, fail=None):
        self.balance = balance or {"total": {}, "free": {}, "used": {}}
        self.tickers = tickers or {}
        self.fail = fail or {}
        self.calls: list[str] = []

    def fetch_balance(self):
        self.calls.append("fetch_balance")
        if "fetch_balance" in self.fail:
            raise self.fail["fetch_balance"]
        return self.balance

    def fetch_tickers(self):
        self.calls.append("fetch_tickers")
        if "fetch_tickers" in self.fail:
            raise self.fail["fetch_tickers"]
        return self.tickers


def _spot(**kw):
    return FakeClient(
        balance={
            "total": {"USDT": 4.0, "DOGE": 100.0, "info": {}},
            "free": {"USDT": 4.0, "DOGE": 100.0},
            "used": {},
        },
        tickers={"DOGE/USDT": {"last": 0.10}, "BTC/USDT": {"last": 50_000.0}},
        **kw,
    )


def _swap(**kw):
    return FakeClient(
        balance={
            "total": {"USDT": 6.0},
            "free": {"USDT": 2.0},
            "used": {"USDT": 4.0},
        },
        **kw,
    )


def test_soldes_spot_et_futures_ne_partagent_jamais_une_ligne():
    rec = collect_account(_spot(), _swap())

    assert {a.asset for a in rec.spot_assets} == {"USDT", "DOGE"}
    assert all(a.wallet == "spot" for a in rec.spot_assets)
    assert [a.wallet for a in rec.futures_assets] == ["futures"]
    assert rec.equity_spot_usd == 4.0  # DOGE non valorisable sans prix
    assert rec.equity_futures_usd == 6.0
    assert rec.equity_total_usd == 10.0


def test_marge_utilisee_et_libre_lues_sur_le_wallet_futures():
    rec = collect_account(_spot(), _swap())
    assert rec.margin_used_usd == 4.0
    assert rec.margin_free_usd == 2.0


def test_actif_sans_prix_exclu_du_total_et_equity_dite_borne_inferieure():
    rec = collect_account(_spot(), _swap())

    by_asset = {a.asset: a for a in rec.spot_assets}
    assert by_asset["DOGE"].usd_value is None
    assert rec.unpriced == ("DOGE",)
    assert rec.equity_is_lower_bound is True
    assert rec.assets_total == 3  # aucune troncature : tout est rendu


def test_equity_exacte_quand_tout_est_valorise():
    spot = FakeClient(balance={"total": {"USDT": 4.0}, "free": {"USDT": 4.0}})
    rec = collect_account(spot, _swap())
    assert rec.unpriced == ()
    assert rec.equity_is_lower_bound is False
    assert rec.equity_total_usd == 10.0


def test_aucune_troncature_le_top_6_est_supprime():
    spot = _spot()
    for i in range(12):
        spot.balance["total"][f"USD{i}"] = 1.0
    rec = collect_account(spot, _swap())
    assert len(rec.spot_assets) == 14  # 12 + USDT + DOGE, rien de coupé


def test_panne_dune_source_isolee_et_visible():
    spot = _spot(fail={"fetch_balance": RuntimeError("boom")})
    rec = collect_account(spot, _swap())

    assert rec.spot_assets == ()
    assert rec.equity_futures_usd == 6.0  # le futures reste lisible
    assert ("spot.fetch_balance", "RuntimeError: boom") in rec.sources_failed
    assert "swap.fetch_balance" in rec.sources_ok
    assert rec.equity_is_lower_bound is True  # une source manque → borne basse


def test_echec_dauthentification_type_et_visible():
    class AuthenticationError(Exception):
        pass

    swap = _swap(fail={"fetch_balance": AuthenticationError("bad key")})
    rec = collect_account(_spot(), swap)
    assert "AuthenticationError" in dict(rec.sources_failed)["swap.fetch_balance"]


def test_client_absent_ne_leve_pas():
    rec = collect_account(None, None)
    assert rec.equity_total_usd == 0.0
    assert len(rec.sources_failed) == 2
    assert rec.sources_ok == ()


def test_soldes_nuls_et_champ_info_ignores():
    spot = FakeClient(balance={"total": {"USDT": 0.0, "info": {"x": 1}}, "free": {}})
    rec = collect_account(spot, None)
    assert rec.spot_assets == ()


def test_enregistrement_horodate_et_versionne():
    rec = collect_account(_spot(), _swap(), exchange="mexc")
    assert rec.exchange == "mexc"
    assert rec.schema_version == 1
    assert rec.ts_utc.endswith("+00:00")
