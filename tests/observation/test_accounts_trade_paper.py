"""Historique paper au MÊME schéma que le réel (ADR-0019, T2).

Fonction pure : aucun client, aucun chemin, aucune lecture disque. Les
enregistrements sont ceux de `paper_trading/recorder.py` (OPEN + CLOSE liés
par `trade_id`).
"""

from __future__ import annotations

from dataclasses import fields

from observation.accounts.trade_collector import (
    TradeRecord,
    collect_paper_trades,
    collect_real_trades,
)


class FakeSwap:
    def fetch_positions_history(self, symbols=None, since=None, limit=None):
        return [
            {
                "symbol": "DOGE/USDT:USDT",
                "side": "long",
                "info": {
                    "positionId": "1398747550",
                    "openAvgPrice": "0.10049",
                    "closeAvgPrice": "0.09935",
                    "closeVol": "1200",
                    "realised": "-1.4978",
                    "profitRatio": "-2.293",
                    "leverage": "200",
                    "createTime": 1_753_920_000_000,
                    "updateTime": 1_753_920_397_000,
                },
            }
        ]


def _paper_pair(trade_id="t1", side="buy"):
    return [
        {
            "event": "OPEN",
            "trade_id": trade_id,
            "symbol": "BTC/USDT",
            "side": side,
            "price": 100.0,
            "size_usd": 50.0,
            "ts": 1_753_920_000.0,
        },
        {
            "event": "CLOSE",
            "trade_id": trade_id,
            "symbol": "BTC/USDT",
            "side": side,
            "exit_price": 110.0,
            "size_usd": 50.0,
            "pnl_usd": 5.0,
            "pnl_pct": 0.10,
            "duration_s": 397.0,
            "ts": 1_753_920_397.0,
            "ts_iso": "2026-07-31T02:06:37+00:00",
        },
    ]


def test_paper_et_reel_portent_le_meme_schema():
    (real,) = collect_real_trades(FakeSwap()).trades
    (paper,) = collect_paper_trades(_paper_pair()).trades

    assert type(real) is TradeRecord and type(paper) is TradeRecord
    assert {f.name for f in fields(real)} == {f.name for f in fields(paper)}
    assert (real.source, paper.source) == ("real", "paper")


def test_paper_apparie_open_et_close_par_trade_id():
    (trade,) = collect_paper_trades(_paper_pair()).trades

    assert trade.symbol == "BTC/USDT"
    assert trade.direction == "long"
    assert trade.entry == 100.0
    assert trade.exit == 110.0
    assert trade.qty == 0.5  # 50 USD / 100 — une division, pas une inférence
    assert trade.profit == 5.0
    assert trade.roi == 0.10
    assert trade.duration_s == 397.0
    assert trade.origin == "paper_bot"
    assert trade.position_id == "t1"


def test_paper_sell_devient_short():
    (trade,) = collect_paper_trades(_paper_pair(side="sell")).trades
    assert trade.direction == "short"


def test_paper_sens_inconnu_jamais_devine():
    (trade,) = collect_paper_trades(_paper_pair(side="???")).trades
    assert trade.direction == "unknown"


def test_paper_sans_open_apparie_ne_devine_pas_lentree():
    close = _paper_pair()[1]
    (trade,) = collect_paper_trades([close]).trades
    assert trade.entry is None and trade.qty is None


def test_paper_aucun_frais_implicite():
    (trade,) = collect_paper_trades(_paper_pair()).trades
    assert trade.fee is None  # None ≠ 0 : aucun frais inventé
    assert trade.funding_fee is None


def test_paper_event_id_non_attribue_ici_ticket_t3():
    (trade,) = collect_paper_trades(_paper_pair()).trades
    assert trade.event_id is None


def test_paper_ignore_les_evenements_non_close_et_le_bruit():
    events = _paper_pair() + [{"event": "OPEN", "trade_id": "t2"}, "bruit", None]
    assert len(collect_paper_trades(events).trades) == 1


def test_plusieurs_trades_apparies_independamment():
    events = _paper_pair("a") + _paper_pair("b", side="sell")
    trades = collect_paper_trades(events).trades
    assert {t.position_id: t.direction for t in trades} == {"a": "long", "b": "short"}


def test_paper_ne_lit_aucun_fichier(tmp_path, monkeypatch):
    # Fonction pure : aucun chemin résolu, aucun accès disque.
    monkeypatch.chdir(tmp_path)
    assert collect_paper_trades([]).trades == ()
