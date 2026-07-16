"""Radar de marché R1 (ADR-0016) — fonctions pures, aucun appel réseau."""

import json

from observation.market_observer import append_records, day_file
from observation.market_radar import (
    aggregate_pairs,
    is_eligible_symbol,
    rank_universe,
    render_digest,
    run_radar,
    score_liquidity,
    score_spread,
    split_symbol,
)

_TS = 1_784_100_000.0  # 2026-07-15 ~07:20 UTC


def _rec(ts, sym, mkt="spot", last=1.0, sp=0.05, qv=5_000_000.0, chg=1.0):
    return {
        "ts": ts,
        "sym": sym,
        "mkt": mkt,
        "last": last,
        "bid": last * 0.999,
        "ask": last * 1.001,
        "sp": sp,
        "qv": qv,
        "chg": chg,
    }


def test_split_symbol_handles_swap_suffix():
    assert split_symbol("BTC/USDT") == ("BTC", "USDT")
    assert split_symbol("BTC/USDT:USDT") == ("BTC", "USDT")


def test_eligibility_filters(monkeypatch):
    monkeypatch.setenv("SYMBOL_BLACKLIST", "USDC/USDT,SCAM/USDT")

    assert is_eligible_symbol("BTC/USDT") is True
    assert is_eligible_symbol("BTC/USDT:USDT") is True
    assert is_eligible_symbol("BTC3L/USDT") is False  # token à levier
    assert is_eligible_symbol("ETH5S/USDT") is False
    assert is_eligible_symbol("BTC/EUR") is False  # quote hors liste
    assert is_eligible_symbol("SCAM/USDT") is False  # blacklist


def test_scores_monotonic():
    assert score_liquidity(400_000) == 0.0  # sous le plancher
    assert score_liquidity(5_000_000) < score_liquidity(50_000_000)
    assert score_spread(0.005) == 100.0
    assert score_spread(0.5) == 0.0
    assert score_spread(None) == 0.0


def test_aggregate_pairs_medians_and_presence():
    records = [
        _rec(_TS, "BTC/USDT", last=100.0, qv=1e6),
        _rec(_TS + 900, "BTC/USDT", last=110.0, qv=3e6),
        _rec(_TS + 1800, "BTC/USDT", last=105.0, qv=2e6),
        _rec(_TS, "GHOST/USDT", last=1.0),  # présent 1 tick sur 3
    ]

    agg = aggregate_pairs(records)
    btc = agg[("BTC/USDT", "spot")]

    assert btc["qv_med"] == 2e6
    assert abs(btc["range_pct"] - (10.0 / 105.0 * 100)) < 1e-3  # arrondi 4 déc.
    assert btc["presence"] == 1.0
    assert agg[("GHOST/USDT", "spot")]["presence"] < 0.5


def test_rank_universe_filters_and_sorts():
    agg = {
        ("BTC/USDT", "spot"): {
            "qv_med": 100e6,
            "sp_med": 0.02,
            "range_pct": 2.0,
            "chg_24h": 1.0,
            "presence": 1.0,
        },
        ("MICRO/USDT", "spot"): {  # volume sous plancher → exclu
            "qv_med": 100_000,
            "sp_med": 0.02,
            "range_pct": 5.0,
            "chg_24h": 9.0,
            "presence": 1.0,
        },
        ("WIDE/USDT", "spot"): {  # spread > max → exclu
            "qv_med": 10e6,
            "sp_med": 1.2,
            "range_pct": 5.0,
            "chg_24h": 9.0,
            "presence": 1.0,
        },
        ("ALT/USDT", "swap"): {
            "qv_med": 20e6,
            "sp_med": 0.05,
            "range_pct": 4.0,
            "chg_24h": -3.0,
            "presence": 0.9,
        },
    }

    ranked = rank_universe(agg, top_n=10)

    syms = [e["sym"] for e in ranked]
    assert "MICRO/USDT" not in syms
    assert "WIDE/USDT" not in syms
    assert set(syms) == {"BTC/USDT", "ALT/USDT"}
    assert ranked[0]["score"] >= ranked[1]["score"]


def test_run_radar_end_to_end_with_diff(tmp_path):
    """Pouls sur disque → shortlist stockée + entrées/sorties vs la veille."""
    # Shortlist de la veille : contient OLD/USDT (sortira) — 2026-07-14
    prev = {"shortlist": [{"sym": "OLD/USDT"}, {"sym": "BTC/USDT"}]}
    (tmp_path / "radar_shortlist_2026-07-14.json").write_text(
        json.dumps(prev), encoding="utf-8"
    )
    # Pouls du jour : BTC (reste) + NEW (entre), 2 ticks chacun
    records = [
        _rec(_TS, "BTC/USDT", last=100.0, qv=50e6),
        _rec(_TS + 900, "BTC/USDT", last=101.0, qv=50e6),
        _rec(_TS, "NEW/USDT", mkt="swap", last=2.0, qv=8e6),
        _rec(_TS + 900, "NEW/USDT", mkt="swap", last=2.1, qv=8e6),
    ]
    append_records(day_file(tmp_path, _TS), records)

    payload = run_radar(tmp_path, now=_TS + 1000)

    assert {e["sym"] for e in payload["shortlist"]} == {"BTC/USDT", "NEW/USDT"}
    assert payload["entries"] == ["NEW/USDT"]
    assert payload["exits"] == ["OLD/USDT"]
    assert (tmp_path / "radar_shortlist_2026-07-15.json").exists()

    digest = render_digest(payload)
    assert "2 paires retenues" in digest
    assert "ADR-0015" in digest  # rappel : sélection tradée = univers épinglé


def test_telegram_digest_disabled_by_default(monkeypatch):
    from observation.market_radar import send_telegram_digest

    monkeypatch.delenv("RADAR_TELEGRAM_DIGEST", raising=False)

    assert send_telegram_digest("test") is False
