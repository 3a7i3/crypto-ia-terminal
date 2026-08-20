"""
tests/paper_trading/test_execution_capture.py

Preuve du chantier A (capture d'exécution — observabilité pure) :
  1. execution_capture extrait fill/slippage/fee/order_type/is_maker d'un
     résultat d'ordre ccxt, tolérant aux champs manquants.
  2. recorder schema v4 persiste ces champs SANS casser la rétrocompatibilité :
     les lignes anciennes (schema v1/v3, sans champs d'exécution) restent
     lisibles, et les nouveaux trades portent les champs.
  3. Le PnL et les décisions ne changent pas — ce sont des champs additifs None
     par défaut (ADR-0007 : les observers ne modifient rien).
"""

from __future__ import annotations

import json

import pytest

from paper_trading import execution_capture as ec


# ── 1. Extracteur ccxt ────────────────────────────────────────────────────────


class TestFeeExtraction:
    def test_single_fee_cost(self):
        assert ec.fee_usd_from_order({"fee": {"cost": 0.03, "currency": "USDT"}}) == 0.03

    def test_multiple_fees_summed(self):
        order = {"fees": [{"cost": 0.01}, {"cost": 0.02}, {"cost": None}]}
        assert ec.fee_usd_from_order(order) == 0.03

    def test_no_fee_returns_none(self):
        assert ec.fee_usd_from_order({"price": 100.0}) is None

    def test_non_dict_returns_none(self):
        assert ec.fee_usd_from_order(None) is None
        assert ec.fee_usd_from_order("nope") is None


class TestOrderType:
    def test_reads_type(self):
        assert ec.order_type_from_order({"type": "LIMIT"}) == "limit"
        assert ec.order_type_from_order({"type": "market"}) == "market"

    def test_missing_type_returns_empty(self):
        assert ec.order_type_from_order({}) == ""


class TestIsMaker:
    def test_taker_or_maker_direct(self):
        assert ec.is_maker_from_order({"takerOrMaker": "maker"}) is True
        assert ec.is_maker_from_order({"takerOrMaker": "taker"}) is False

    def test_info_is_maker(self):
        assert ec.is_maker_from_order({"info": {"isMaker": True}}) is True
        assert ec.is_maker_from_order({"info": {"isMaker": False}}) is False

    def test_derive_from_type(self):
        assert ec.is_maker_from_order({"type": "limit"}) is True
        assert ec.is_maker_from_order({"type": "market"}) is False

    def test_indeterminate_returns_none(self):
        assert ec.is_maker_from_order({}) is None


class TestSlippage:
    def test_positive_slippage(self):
        # fill au-dessus du prix visé (BUY défavorable)
        assert ec.slippage_pct(100.0, 100.05) == pytest.approx(0.05)

    def test_negative_slippage(self):
        assert ec.slippage_pct(100.0, 99.95) == pytest.approx(-0.05)

    def test_missing_price_returns_none(self):
        assert ec.slippage_pct(None, 100.0) is None
        assert ec.slippage_pct(100.0, None) is None
        assert ec.slippage_pct(0.0, 100.0) is None


class TestCaptureBundle:
    def test_full_ccxt_order(self):
        order = {
            "type": "limit",
            "takerOrMaker": "maker",
            "fee": {"cost": 0.0, "currency": "USDT"},
        }
        out = ec.capture_from_ccxt(order, intended_price=100.0, fill_price=100.0)
        assert out == {
            "intended_price": 100.0,
            "fill_price": 100.0,
            "slippage_pct": 0.0,
            "fee_usd": 0.0,
            "order_type": "limit",
            "is_maker": True,
        }

    def test_paper_synthetic_order_degrades_gracefully(self):
        # dict paper synthétique sans fee/type → None partout sauf prix fournis
        out = ec.capture_from_ccxt({}, intended_price=50.0, fill_price=50.1)
        assert out["fill_price"] == 50.1
        assert out["slippage_pct"] == pytest.approx(0.2)
        assert out["fee_usd"] is None
        assert out["order_type"] == ""
        assert out["is_maker"] is None


# ── 2. Recorder schema v4 + rétrocompatibilité ────────────────────────────────


class TestRecorderSchemaV4:
    @pytest.fixture
    def recorder(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PAPER_TRADE_LOG", str(tmp_path / "trades.jsonl"))
        from paper_trading.recorder import PaperTradeRecorder

        return PaperTradeRecorder(log_path=str(tmp_path / "trades.jsonl"))

    def test_exec_fields_persisted(self, recorder):
        recorder.record_open(
            trade_id="t1",
            symbol="BTC/USDT",
            side="buy",
            price=100.0,
            size_usd=30.0,
            regime="bull_trend",
            score=72,
            intended_price=100.0,
            fill_price=100.05,
            slippage_pct=0.05,
            fee_usd=0.0,
            order_type="limit",
            is_maker=True,
        )
        line = recorder._path.read_text().strip()
        rec = json.loads(line)
        assert rec["order_type"] == "limit"
        assert rec["is_maker"] is True
        assert rec["fee_usd"] == 0.0
        assert rec["fill_price"] == 100.05
        assert rec["schema_version"] == 4

    def test_close_exec_fields_persisted(self, recorder):
        recorder.record_close(
            trade_id="t1",
            exit_price=101.0,
            pnl_usd=0.3,
            pnl_pct=0.003,
            reason="TP",
            fill_price=100.95,
            fee_usd=0.03,
            order_type="market",
            is_maker=False,
        )
        rec = json.loads(recorder._path.read_text().strip())
        assert rec["reason"] == "TP"
        assert rec["fee_usd"] == 0.03
        assert rec["is_maker"] is False

    def test_backward_compat_old_schema_line(self, recorder):
        """Une ligne schema v1 (sans champs d'exécution) reste lisible."""
        old_open = {
            "event": "OPEN",
            "trade_id": "legacy1",
            "ts": 1779100899.0,
            "ts_iso": "2026-05-18T10:41:39Z",
            "symbol": "INJ/USDT",
            "side": "buy",
            "price": 4.5,
            "size_usd": 30.0,
            "mode": "paper",
            "regime": "sideways",
            "score": 70,
        }
        old_close = {
            "event": "CLOSE",
            "trade_id": "legacy1",
            "ts": 1779104499.0,
            "ts_iso": "2026-05-18T11:41:39Z",
            "symbol": "INJ/USDT",
            "side": "buy",
            "price": 4.6,
            "size_usd": 30.0,
            "mode": "paper",
            "exit_price": 4.6,
            "pnl_usd": 0.66,
            "pnl_pct": 0.022,
            "reason": "TP",
        }
        with recorder._path.open("w", encoding="utf-8") as f:
            f.write(json.dumps(old_open) + "\n")
            f.write(json.dumps(old_close) + "\n")

        events = recorder.events()
        assert len(events) == 2
        # Les nouveaux champs valent None sur les vieux enregistrements
        assert events[0].fill_price is None
        assert events[0].order_type == ""
        assert events[0].is_maker is None

        trades = recorder.trades()
        assert len(trades) == 1
        t = trades[0]
        assert not t.is_open
        assert t.pnl_usd == 0.66
        # vue fusionnée : champs d'exécution None mais pas d'erreur
        assert t.entry_fill_price is None
        assert t.total_fee_usd is None

    def test_merged_view_surfaces_exec_fields(self, recorder):
        recorder.record_open(
            trade_id="t2",
            symbol="ETH/USDT",
            side="buy",
            price=2000.0,
            size_usd=30.0,
            fill_price=2000.5,
            fee_usd=0.0,
            order_type="limit",
            is_maker=True,
        )
        recorder.record_close(
            trade_id="t2",
            exit_price=2020.0,
            pnl_usd=0.3,
            pnl_pct=0.01,
            reason="TP",
            fill_price=2019.5,
            fee_usd=0.02,
            order_type="market",
            is_maker=False,
        )
        t = recorder.trades()[0]
        assert t.entry_is_maker is True
        assert t.exit_is_maker is False
        assert t.entry_fee_usd == 0.0
        assert t.exit_fee_usd == 0.02
        assert t.total_fee_usd == 0.02
