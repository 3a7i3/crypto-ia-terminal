"""Ordres futures et recoupement par positionId (ADR-0019, T2).

Faux client ccxt INJECTÉ. L'échantillon reproduit les faits mesurés le
2026-07-31 : `side` brut en '1'..'4', `clientOrderId` nul, `externalOid`
préfixé `_m_`, et une position référencée par un ordre mais absente de
l'historique.
"""

from __future__ import annotations

from observation.accounts.order_reader import collect_orders, reconcile_position_ids


class FakeSwap:
    def __init__(self, orders=None, fail=None):
        self.orders = orders if orders is not None else []
        self.fail = fail
        self.calls: list[tuple] = []

    def fetch_orders(self, symbol=None, since=None, limit=None):
        self.calls.append((symbol, since, limit))
        if self.fail:
            raise self.fail
        return self.orders


def _order(order_id="o1", side="4", position_id="1398747550", oid="_m_d86b7bca91"):
    return {
        "id": order_id,
        "clientOrderId": None,  # ccxt rend null sur MEXC
        "symbol": "DOGE/USDT:USDT",
        "side": side,
        "amount": 1200.0,
        "price": 0.09935,
        "status": "closed",
        "timestamp": 1_753_920_397_000,
        "info": {"externalOid": oid, "positionId": position_id, "vol": "1200"},
    }


class _Trade:
    """Substitut minimal d'un TradeRecord — seul positionId compte ici."""

    def __init__(self, position_id):
        self.position_id = position_id


# ── Lecture des ordres ──────────────────────────────────────────────────────


def test_fetch_orders_sans_symbole_et_incremental():
    swap = FakeSwap([_order()])
    collect_orders(swap, since=1_753_000_000_000, limit=50)
    assert swap.calls == [(None, 1_753_000_000_000, 50)]


def test_code_de_sens_brut_mappe_et_conserve():
    (order,) = collect_orders(FakeSwap([_order(side="4")])).orders
    assert order.raw_side == "4"  # brut conservé, jamais réécrit
    assert order.side == "close_long"
    assert order.direction == "long"


def test_les_quatre_codes_mesures():
    swap = FakeSwap([_order(order_id=str(i), side=str(i)) for i in (1, 2, 3, 4)])
    sides = [o.side for o in collect_orders(swap).orders]
    assert sides == ["open_long", "close_short", "open_short", "close_long"]


def test_sens_inconnu_jamais_devine():
    (order,) = collect_orders(FakeSwap([_order(side="9")])).orders
    assert order.side == "unknown" and order.direction == "unknown"


def test_external_oid_lu_dans_info_et_indice_trace():
    (order,) = collect_orders(FakeSwap([_order()])).orders
    assert order.external_oid == "_m_d86b7bca91"
    assert order.manual_oid_hint is True


def test_indice_absent_nempeche_pas_la_lecture():
    (order,) = collect_orders(FakeSwap([_order(oid="autre")])).orders
    assert order.external_oid == "autre" and order.manual_oid_hint is False


def test_origin_manual_sans_dependre_du_prefixe():
    swap = FakeSwap([_order(oid="autre")])
    (order,) = collect_orders(swap, engine_live=False).orders
    assert order.origin == "manual"  # certain : le moteur ne peut pas émettre


def test_origin_unknown_si_le_moteur_devenait_capable():
    (order,) = collect_orders(FakeSwap([_order()]), engine_live=True).orders
    assert order.origin == "unknown"


def test_panne_visible_et_typee():
    class AuthenticationError(Exception):
        pass

    rec = collect_orders(FakeSwap(fail=AuthenticationError("bad key")))
    assert rec.ok is False and "AuthenticationError" in rec.error


def test_client_absent_ne_leve_pas():
    assert collect_orders(None).ok is False


# ── Recoupement par positionId (fait mesuré n°7) ────────────────────────────


def test_position_referencee_par_un_ordre_mais_absente_de_lhistorique():
    orders = collect_orders(
        FakeSwap([_order("o1", position_id="A"), _order("o2", position_id="B")])
    ).orders
    rec = reconcile_position_ids(orders, [_Trade("A")])

    assert rec.position_ids_in_orders == 2
    assert rec.position_ids_in_history == 1
    assert rec.ids_absent_from_history == ("B",)  # l'orpheline est NOMMÉE
    assert rec.ids_absent_from_orders == ()


def test_recoupement_sans_ecart():
    orders = collect_orders(FakeSwap([_order("o1", position_id="A")])).orders
    rec = reconcile_position_ids(orders, [_Trade("A")])
    assert rec.ids_absent_from_history == () and rec.ids_absent_from_orders == ()


def test_historique_plus_riche_que_les_ordres():
    orders = collect_orders(FakeSwap([_order("o1", position_id="A")])).orders
    rec = reconcile_position_ids(orders, [_Trade("A"), _Trade("C")])
    assert rec.ids_absent_from_orders == ("C",)


def test_position_id_absent_ignore():
    orders = collect_orders(FakeSwap([_order(position_id=None)])).orders
    rec = reconcile_position_ids(orders, [])
    assert rec.position_ids_in_orders == 0


def test_recoupement_ne_rend_aucun_verdict():
    # OBS-I : la structure ne porte que des comptes et des identifiants.
    rec = reconcile_position_ids([], [])
    champs = set(vars(rec))
    assert champs == {
        "position_ids_in_orders",
        "position_ids_in_history",
        "ids_absent_from_history",
        "ids_absent_from_orders",
    }
