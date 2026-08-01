"""TradeCollector — historique réel via fetch_positions_history (ADR-0019, T2).

Faux client ccxt INJECTÉ ; l'échantillon réel est celui mesuré le 2026-07-31
(`positionId 1398747550`, DOGE_USDT).
"""

from __future__ import annotations

from observation.accounts.trade_collector import collect_real_trades


class FakeSwap:
    def __init__(self, history=None, fail=None):
        self.history = history if history is not None else []
        self.fail = fail
        self.calls: list[tuple] = []

    def fetch_positions_history(self, symbols=None, since=None, limit=None):
        self.calls.append((symbols, since, limit))
        if self.fail:
            raise self.fail
        return self.history

    def fetch_orders(self, *a, **kw):  # ne doit JAMAIS être appelée ici
        raise AssertionError("l'historique ne s'apparie pas depuis les ordres")


def _closed_position(**overrides):
    """Échantillon mesuré : positionId 1398747550, DOGE_USDT."""
    info = {
        "positionId": "1398747550",
        "openAvgPrice": "0.10049",
        "closeAvgPrice": "0.09935",
        "closeVol": "1200",
        "realised": "-1.4978",
        "profitRatio": "-2.293",
        "leverage": "200",
        "liquidatePrice": "0.0995",
        "holdFee": "-0.0021",
        "totalFee": "0",
        "createTime": 1_753_920_000_000,
        "updateTime": 1_753_920_397_000,  # 6 min 37 s plus tard
        "positionShowStatus": "CLOSED",
    }
    info.update(overrides.pop("info", {}))
    raw = {"symbol": "DOGE/USDT:USDT", "side": "long", "info": info}
    raw.update(overrides)
    return raw


# ── Historique réel : fetch_positions_history, un seul appel ────────────────


def test_historique_reel_en_un_appel_sans_appariement_dordres():
    swap = FakeSwap([_closed_position()])
    hist = collect_real_trades(swap, since=1_753_000_000_000, limit=50)

    assert swap.calls == [(None, 1_753_000_000_000, 50)]  # un seul appel
    assert len(hist.trades) == 1  # fetch_orders lèverait si appelée


def test_tous_les_champs_de_la_position_fermee_mesuree():
    (trade,) = collect_real_trades(FakeSwap([_closed_position()])).trades

    assert trade.source == "real"
    assert trade.symbol == "DOGE/USDT:USDT"
    assert trade.direction == "long"
    assert trade.entry == 0.10049
    assert trade.exit == 0.09935
    assert trade.qty == 1200.0
    assert trade.profit == -1.4978
    assert trade.roi == -2.293
    assert trade.leverage == 200.0
    assert trade.liquidation_price == 0.0995
    assert trade.funding_fee == -0.0021  # holdFee
    assert trade.position_id == "1398747550"


def test_duree_calculee_par_update_moins_create():
    (trade,) = collect_real_trades(FakeSwap([_closed_position()])).trades
    assert trade.duration_s == 397.0  # 6 min 37 s, le trade réel mesuré


def test_origin_manual_quand_le_moteur_ne_peut_pas_emettre():
    (trade,) = collect_real_trades(
        FakeSwap([_closed_position()]), engine_live=False
    ).trades
    assert trade.origin == "manual"


def test_origin_unknown_si_le_moteur_devenait_capable():
    (trade,) = collect_real_trades(
        FakeSwap([_closed_position()]), engine_live=True
    ).trades
    assert trade.origin == "unknown"


def test_sens_inconnu_jamais_devine():
    (trade,) = collect_real_trades(FakeSwap([_closed_position(side="9")])).trades
    assert trade.direction == "unknown"


def test_event_id_non_attribue_ici_ticket_t3():
    (trade,) = collect_real_trades(FakeSwap([_closed_position()])).trades
    assert trade.event_id is None


def test_panne_visible_et_typee():
    class AuthenticationError(Exception):
        pass

    hist = collect_real_trades(FakeSwap(fail=AuthenticationError("bad key")))
    assert hist.ok is False and "AuthenticationError" in hist.error
    assert hist.trades == ()


def test_client_absent_ne_leve_pas():
    hist = collect_real_trades(None)
    assert hist.ok is False and "NoClient" in hist.error


def test_historique_spot_jamais_declare_exhaustif():
    hist = collect_real_trades(FakeSwap([]))
    assert hist.spot_history_exhaustive is False
