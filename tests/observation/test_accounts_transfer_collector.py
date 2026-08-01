"""TransferCollector — mouvements de fonds (ADR-0019, T2).

Faux client ccxt INJECTÉ. Les montants sont ceux relevés le 2026-07-31 :
SPOT→FUTURES 5.609 USDT, FUTURES→SPOT 1.29 USDT.
"""

from __future__ import annotations

from observation.accounts.transfer_collector import collect_transfers


class FakeClient:
    """Faux client exigeant fromAccountType ET toAccountType, comme MEXC."""

    def __init__(self, transfers=None, deposits=None, withdrawals=None, fail=None):
        self.transfers = transfers or {}
        self.deposits = deposits or []
        self.withdrawals = withdrawals or []
        self.fail = fail or {}
        self.calls: list[tuple] = []

    def fetch_transfers(self, code=None, since=None, limit=None, params=None):
        params = params or {}
        src, dst = params.get("fromAccountType"), params.get("toAccountType")
        if not src or not dst:
            raise ArgumentsRequired("fromAccountType and toAccountType are required")
        self.calls.append(("fetch_transfers", src, dst, since, limit))
        if "fetch_transfers" in self.fail:
            raise self.fail["fetch_transfers"]
        return self.transfers.get((src, dst), [])

    def fetch_deposits(self, code=None, since=None, limit=None):
        self.calls.append(("fetch_deposits", since, limit))
        if "fetch_deposits" in self.fail:
            raise self.fail["fetch_deposits"]
        return self.deposits

    def fetch_withdrawals(self, code=None, since=None, limit=None):
        self.calls.append(("fetch_withdrawals", since, limit))
        if "fetch_withdrawals" in self.fail:
            raise self.fail["fetch_withdrawals"]
        return self.withdrawals


class ArgumentsRequired(Exception):
    """Réplique de ccxt.ArgumentsRequired — le piège mesuré n°3."""


def _movement(mid, amount, src, dst):
    return {
        "id": mid,
        "timestamp": 1_753_840_000_000,
        "currency": "USDT",
        "amount": amount,
        "fromAccount": src,
        "toAccount": dst,
        "status": "ok",
    }


def _client(**kw):
    return FakeClient(
        transfers={
            ("SPOT", "FUTURES"): [_movement("tr1", 5.609, "SPOT", "FUTURES")],
            ("FUTURES", "SPOT"): [_movement("tr2", 1.29, "FUTURES", "SPOT")],
        },
        deposits=[
            dict(_movement("d1", 10.0, None, None), txid="0xabc"),
        ],
        withdrawals=[],
        **kw,
    )


def test_deux_appels_un_par_sens_car_les_deux_champs_sont_obligatoires():
    client = _client()
    collect_transfers(client, since=1_753_000_000_000, limit=20)

    transfer_calls = [c for c in client.calls if c[0] == "fetch_transfers"]
    assert [(c[1], c[2]) for c in transfer_calls] == [
        ("SPOT", "FUTURES"),
        ("FUTURES", "SPOT"),
    ]
    assert transfer_calls[0][3:] == (1_753_000_000_000, 20)  # incrémental


def test_transferts_mesures_rendus_dans_les_deux_sens():
    rec = collect_transfers(_client())
    transfers = [m for m in rec.movements if m.kind == "transfer"]

    assert [(m.from_account, m.to_account, m.amount) for m in transfers] == [
        ("SPOT", "FUTURES", 5.609),
        ("FUTURES", "SPOT", 1.29),
    ]
    assert transfers[0].currency == "USDT"
    assert transfers[0].ts_utc.startswith("2025-")


def test_depots_et_retraits_collectes():
    rec = collect_transfers(_client())
    kinds = [m.kind for m in rec.movements]

    assert kinds.count("deposit") == 1
    assert kinds.count("withdrawal") == 0  # aucun retrait dans les sources lues
    deposit = next(m for m in rec.movements if m.kind == "deposit")
    assert deposit.amount == 10.0 and deposit.tx_id == "0xabc"


def test_quatre_sources_toutes_listees():
    rec = collect_transfers(_client())
    assert rec.sources_ok == (
        "fetch_transfers[SPOT->FUTURES]",
        "fetch_transfers[FUTURES->SPOT]",
        "fetch_deposits",
        "fetch_withdrawals",
    )
    assert rec.sources_failed == ()


def test_un_sens_en_panne_naffecte_pas_lautre():
    client = _client(fail={"fetch_deposits": RuntimeError("boom")})
    rec = collect_transfers(client)

    assert len([m for m in rec.movements if m.kind == "transfer"]) == 2
    assert ("fetch_deposits", "RuntimeError: boom") in rec.sources_failed
    assert "fetch_withdrawals" in rec.sources_ok


def test_echec_type_et_visible():
    class PermissionDenied(Exception):
        pass

    rec = collect_transfers(_client(fail={"fetch_transfers": PermissionDenied("scope")}))
    failed = dict(rec.sources_failed)
    assert "PermissionDenied" in failed["fetch_transfers[SPOT->FUTURES]"]
    assert "PermissionDenied" in failed["fetch_transfers[FUTURES->SPOT]"]
    assert rec.movements  # dépôts encore lisibles


def test_client_absent_ne_leve_pas():
    rec = collect_transfers(None)
    assert rec.movements == ()
    assert len(rec.sources_failed) == 4 and rec.sources_ok == ()


def test_entrees_malformees_ignorees():
    client = _client()
    client.deposits = [None, "x", {"id": "d2", "currency": "USDT", "amount": 1.0}]
    rec = collect_transfers(client)
    assert len([m for m in rec.movements if m.kind == "deposit"]) == 1


def test_enregistrement_horodate_et_versionne():
    rec = collect_transfers(_client(), exchange="mexc")
    assert rec.exchange == "mexc" and rec.schema_version == 1
    assert rec.ts_utc.endswith("+00:00")
