"""Tests pour selection, observatory (store) et adaptateurs LMI."""

import json
import os
from pathlib import Path

from trade_analysis.integrations import dashboard_adapter as da
from trade_analysis.integrations.radar_adapter import (
    format_lmi_message,
    format_lmi_overview,
)
from trade_analysis.observatory import LiveStateStore
from trade_analysis.selection import SymbolSelector, normalize_symbol


# ---------------------------------------------------------------------------
# Fixtures : produit un radar_shortlist + paper_trades minimalistes
# ---------------------------------------------------------------------------


def _write_radar(obs_dir: Path, entries):
    obs_dir.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": "2026-08-25T00:00:00Z", "shortlist": entries}
    (obs_dir / "radar_shortlist_2026-08-25.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _write_paper(path: Path, closes):
    lines = []
    for sym, is_win in closes:
        lines.append(
            json.dumps(
                {"event": "CLOSE", "symbol": sym, "is_win": is_win, "pnl_usd": 1.0}
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# SymbolSelector
# ---------------------------------------------------------------------------


class TestSymbolSelector:
    def test_normalize(self):
        assert normalize_symbol("BTC/USDT") == "BTCUSDT"
        assert normalize_symbol("BTC_USDT") == "BTCUSDT"
        assert normalize_symbol("btcusdt") == "BTCUSDT"
        # Suffixe settle des swaps CCXT — doit etre retire (sinon doublons)
        assert normalize_symbol("BTCUSDT:USDT") == "BTCUSDT"
        assert normalize_symbol("BTC/USDT:USDT") == "BTCUSDT"

    def test_dedup_swap_and_spot(self, tmp_path):
        obs = tmp_path / "obs"
        _write_radar(
            obs,
            [
                {"sym": "BTCUSDT:USDT", "qv_med": 5e8, "range_pct": 2.0, "score": 90},
                {"sym": "BTCUSDT", "qv_med": 4e8, "range_pct": 2.0, "score": 88},
            ],
        )
        sel = SymbolSelector(obs_dir=obs, paper_trade_log=tmp_path / "none.jsonl")
        cands = sel.load_candidates()
        # Les deux entrees collapsent sur une seule cle normalisee
        assert [c.symbol for c in cands] == ["BTCUSDT"]

    def test_load_and_merge(self, tmp_path):
        obs = tmp_path / "obs"
        _write_radar(
            obs,
            [
                {"sym": "BTCUSDT", "qv_med": 5e8, "range_pct": 2.1, "score": 90},
                {"sym": "SOLUSDT", "qv_med": 1e8, "range_pct": 6.0, "score": 75},
            ],
        )
        paper = tmp_path / "paper.jsonl"
        _write_paper(paper, [("BTC/USDT", True), ("BTC/USDT", False), ("BTC/USDT", True)])

        sel = SymbolSelector(obs_dir=obs, paper_trade_log=paper)
        cands = {c.symbol: c for c in sel.load_candidates()}

        assert cands["BTCUSDT"].market_cap_proxy == 5e8
        assert cands["BTCUSDT"].n_trades == 3
        assert cands["BTCUSDT"].wins == 2
        assert cands["BTCUSDT"].losses == 1
        assert abs(cands["BTCUSDT"].win_rate - 2 / 3) < 1e-9
        assert cands["SOLUSDT"].win_rate is None

    def test_sort_by_market_cap(self, tmp_path):
        obs = tmp_path / "obs"
        _write_radar(
            obs,
            [
                {"sym": "BTCUSDT", "qv_med": 5e8, "range_pct": 2.0, "score": 90},
                {"sym": "SOLUSDT", "qv_med": 1e8, "range_pct": 6.0, "score": 75},
            ],
        )
        sel = SymbolSelector(obs_dir=obs, paper_trade_log=tmp_path / "none.jsonl")
        res = sel.select(sort_by="market_cap", limit=10)
        assert [c.symbol for c in res] == ["BTCUSDT", "SOLUSDT"]

    def test_filter_by_volatility(self, tmp_path):
        obs = tmp_path / "obs"
        _write_radar(
            obs,
            [
                {"sym": "BTCUSDT", "qv_med": 5e8, "range_pct": 2.0, "score": 90},
                {"sym": "SOLUSDT", "qv_med": 1e8, "range_pct": 6.0, "score": 75},
            ],
        )
        sel = SymbolSelector(obs_dir=obs, paper_trade_log=tmp_path / "none.jsonl")
        res = sel.select(min_volatility=4.0, limit=10)
        assert [c.symbol for c in res] == ["SOLUSDT"]

    def test_filter_by_win_rate(self, tmp_path):
        obs = tmp_path / "obs"
        _write_radar(
            obs,
            [
                {"sym": "BTCUSDT", "qv_med": 5e8, "range_pct": 2.0, "score": 90},
                {"sym": "SOLUSDT", "qv_med": 1e8, "range_pct": 6.0, "score": 75},
            ],
        )
        paper = tmp_path / "paper.jsonl"
        _write_paper(
            paper,
            [("BTC/USDT", True), ("BTC/USDT", True), ("SOL/USDT", False), ("SOL/USDT", False)],
        )
        sel = SymbolSelector(obs_dir=obs, paper_trade_log=paper)
        res = sel.select(min_win_rate=0.5, min_trades=1, limit=10)
        assert [c.symbol for c in res] == ["BTCUSDT"]

    def test_missing_files_graceful(self, tmp_path):
        sel = SymbolSelector(
            obs_dir=tmp_path / "nope", paper_trade_log=tmp_path / "nope.jsonl"
        )
        assert sel.load_candidates() == []
        assert sel.select() == []

    def test_pinned_universe_restricts(self, tmp_path):
        obs = tmp_path / "obs"
        _write_radar(
            obs,
            [
                {"sym": "BTCUSDT", "qv_med": 5e8, "range_pct": 2.0, "score": 90},
                {"sym": "XAUUSDT", "qv_med": 9e8, "range_pct": 1.0, "score": 95},
                {"sym": "MUSTOCKUSDT", "qv_med": 8e8, "range_pct": 1.0, "score": 92},
                {"sym": "ETHUSDT", "qv_med": 3e8, "range_pct": 2.0, "score": 80},
            ],
        )
        sel = SymbolSelector(obs_dir=obs, paper_trade_log=tmp_path / "none.jsonl")
        pinned = {"BTCUSDT", "ETHUSDT"}
        res = sel.select(restrict_to_pinned=True, pinned_universe=pinned, limit=10)
        # XAU (or) et MUSTOCK (action) exclus, meme s'ils ont plus de volume
        assert [c.symbol for c in res] == ["BTCUSDT", "ETHUSDT"]

    def test_pinned_universe_empty_is_noop(self, tmp_path):
        obs = tmp_path / "obs"
        _write_radar(
            obs,
            [
                {"sym": "BTCUSDT", "qv_med": 5e8, "range_pct": 2.0, "score": 90},
                {"sym": "XAUUSDT", "qv_med": 9e8, "range_pct": 1.0, "score": 95},
            ],
        )
        sel = SymbolSelector(obs_dir=obs, paper_trade_log=tmp_path / "none.jsonl")
        # Univers epingle vide -> aucun filtre (dev, hors VPS)
        res = sel.select(restrict_to_pinned=True, pinned_universe=set(), limit=10)
        assert {c.symbol for c in res} == {"BTCUSDT", "XAUUSDT"}

    def test_load_pinned_universe_from_env(self, monkeypatch):
        from trade_analysis.selection import load_pinned_universe

        monkeypatch.setenv("UNIVERSE_PINNED_SYMBOLS", "  BTC/USDT ETH/USDT  SOL/USDT ")
        assert load_pinned_universe() == {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
        monkeypatch.delenv("UNIVERSE_PINNED_SYMBOLS", raising=False)
        assert load_pinned_universe() == set()


# ---------------------------------------------------------------------------
# LiveStateStore
# ---------------------------------------------------------------------------


def _make_pf(symbol="BTCUSDT", state="accumulation"):
    import time as _t

    from trade_analysis.models import (
        AggressiveFlow,
        LiquidityDynamics,
        MarketResistance,
        MarketStateLabel,
        PressureField,
    )

    now_ms = int(_t.time() * 1000)
    flow = AggressiveFlow(
        timestamp_ms=1_000_000, window_ms=10_000, buy_volume_usd=4_000_000,
        sell_volume_usd=1_000_000, buy_count=100, sell_count=30,
        buy_avg_size_usd=40_000, sell_avg_size_usd=33_000, large_buy_count=5,
        large_sell_count=1, buy_acceleration=100, sell_acceleration=-50,
        dominant_side="buy", pressure_ratio=0.8,
    )
    liq = LiquidityDynamics(
        timestamp_ms=1_000_000, bid_added_usd=1000, bid_removed_usd=500,
        ask_added_usd=800, ask_removed_usd=2000, bid_consumed_usd=300,
        ask_consumed_usd=3400, cancellation_rate_bid=0.2, cancellation_rate_ask=0.4,
        net_liquidity_change_usd=-700,
    )
    res = MarketResistance(
        timestamp_ms=1_000_000, volume_applied_usd=5_000_000,
        price_displacement_bps=2.0, resistance_score=71, fragility_score=0.2,
        absorption_ratio=0.6,
    )
    return PressureField(
        timestamp_ms=now_ms, symbol=symbol, price=65000.0, price_change_bps=1.5,
        flow=flow, liquidity=liq, resistance=res,
        state=MarketStateLabel(state), state_confidence=0.76, state_components={},
    )


class TestLiveStateStore:
    def test_update_and_flush(self, tmp_path):
        store = LiveStateStore(path=tmp_path / "state.json", exchange="mexc")
        store.set_watchlist(["BTCUSDT", "ETHUSDT"])
        store.update(_make_pf("BTCUSDT"))
        store.flush()

        data = json.loads((tmp_path / "state.json").read_text())
        assert data["exchange"] == "mexc"
        assert data["watchlist"] == ["BTCUSDT", "ETHUSDT"]
        assert "BTCUSDT" in data["symbols"]
        assert data["stats"]["symbols_active"] == 1
        assert "age_ms" in data["symbols"]["BTCUSDT"]

    def test_atomic_write(self, tmp_path):
        store = LiveStateStore(path=tmp_path / "state.json")
        store.update(_make_pf())
        store.flush()
        store.update(_make_pf(state="conflict"))
        store.flush()
        data = json.loads((tmp_path / "state.json").read_text())
        assert data["symbols"]["BTCUSDT"]["state"] == "conflict"
        assert not list(tmp_path.glob("*.tmp"))


# ---------------------------------------------------------------------------
# Dashboard adapter
# ---------------------------------------------------------------------------


class TestDashboardAdapter:
    def _prep(self, tmp_path):
        store = LiveStateStore(path=tmp_path / "state.json", exchange="mexc")
        store.set_watchlist(["BTCUSDT"])
        store.update(_make_pf("BTCUSDT", "accumulation"))
        store.flush()
        return tmp_path / "state.json"

    def test_status(self, tmp_path):
        p = self._prep(tmp_path)
        st = da.lmi_status(p)
        assert st["running"] is True
        assert st["exchange"] == "mexc"
        assert st["symbols_active"] == 1

    def test_table(self, tmp_path):
        p = self._prep(tmp_path)
        t = da.lmi_table(p)
        assert t["count"] == 1
        row = t["data"][0]
        assert row["symbol"] == "BTCUSDT"
        assert row["state"] == "accumulation"
        assert row["buy_pressure"] == 80

    def test_symbol(self, tmp_path):
        p = self._prep(tmp_path)
        d = da.lmi_symbol("BTC", p)
        assert d is not None
        assert d["symbol"] == "BTCUSDT"
        assert d["liquidity"]["consumed_usd"] == 3700  # 300 + 3400

    def test_symbol_missing(self, tmp_path):
        p = self._prep(tmp_path)
        assert da.lmi_symbol("XXXUSDT", p) is None

    def test_events(self, tmp_path):
        p = self._prep(tmp_path)
        ev = da.lmi_events(p, min_confidence=0.6)
        assert ev["count"] == 1
        assert ev["data"][0]["state"] == "accumulation"

    def test_missing_file(self, tmp_path):
        st = da.lmi_status(tmp_path / "nope.json")
        assert st["running"] is False


# ---------------------------------------------------------------------------
# Radar adapter
# ---------------------------------------------------------------------------


class TestRadarAdapter:
    def _prep(self, tmp_path):
        store = LiveStateStore(path=tmp_path / "state.json")
        store.set_watchlist(["BTCUSDT"])
        store.update(_make_pf("BTCUSDT", "accumulation"))
        store.flush()
        return tmp_path / "state.json"

    def test_message(self, tmp_path):
        p = self._prep(tmp_path)
        msg = format_lmi_message("BTC", p)
        assert "BTC" in msg
        assert "ACCUMULATION" in msg
        assert "Not a trading signal" in msg

    def test_message_absent(self, tmp_path):
        p = self._prep(tmp_path)
        msg = format_lmi_message("XXXUSDT", p)
        assert "Aucune donnee live" in msg

    def test_overview(self, tmp_path):
        p = self._prep(tmp_path)
        msg = format_lmi_overview(p)
        assert "LMI OBSERVATORY" in msg
        assert "BTCUSDT" in msg


# ---------------------------------------------------------------------------
# DS-001 — Non-regression : LMI_DIR honoré après import (writer + reader)
# ---------------------------------------------------------------------------


class TestDS001LateEnvHonored:
    """Vérifie que LMI_DIR posé après import est honoré (ADR-0008 / DS-001).

    Ces tests reproduisent les deux violations HIGH signalées par l'auditeur
    DS-001 :
      - late_env_honored_writer : LiveStateStore() sans path explicite doit
        utiliser le LMI_DIR courant de l'environnement, pas celui figé à
        l'import d'observatory.py.
      - late_env_honored_reader : lmi_status() sans path explicite doit lire
        dans le LMI_DIR courant de l'environnement, pas celui figé à
        l'import de dashboard_adapter.py.
    """

    def test_late_env_honored_writer(self, monkeypatch, tmp_path):
        """LMI_DIR posé après import est honoré par LiveStateStore()."""
        import trade_analysis.observatory as obs_mod

        new_dir = tmp_path / "lmi_writer"
        monkeypatch.setenv("LMI_DIR", str(new_dir))

        store = LiveStateStore()
        assert store.path == new_dir / "lmi_live_state.json", (
            f"Attendu {new_dir / 'lmi_live_state.json'}, obtenu {store.path}"
        )

    def test_late_env_honored_reader(self, monkeypatch, tmp_path):
        """LMI_DIR posé après import est honoré par lmi_status() sans path."""
        import trade_analysis.integrations.dashboard_adapter as da_mod

        new_dir = tmp_path / "lmi_reader"
        monkeypatch.setenv("LMI_DIR", str(new_dir))

        # Écrire un sidecar temporaire dans ce répertoire
        new_dir.mkdir(parents=True, exist_ok=True)
        sidecar = new_dir / "lmi_live_state.json"
        sidecar.write_text(
            json.dumps({
                "exchange": "mexc",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "watchlist": ["BTCUSDT"],
                "contract_meta": {},
                "symbols": {"BTCUSDT": {"state": "accumulation", "state_confidence": 0.8,
                                        "age_ms": 100, "flow": {}, "resistance": {}}},
                "stats": {"events": 1, "symbols_active": 1, "symbols_watched": 1},
            }),
            encoding="utf-8",
        )

        status = da_mod.lmi_status()
        assert status["running"] is True, (
            "lmi_status() devrait lire le sidecar dans LMI_DIR posé après import"
        )
        assert status["exchange"] == "mexc"
