"""Panneaux SIGNAUX agrégés (ADR-0017 T5) — anti-spam Telegram aux paliers."""

from capital_deployment.command_center_bot import _SIGNALS_DETAIL_MAX, _signals_lines


def _items(n: int) -> list:
    return [
        (
            f"S{i}/USDT",
            {
                "score": i % 100,
                "action": "BUY",
                "regime": "sideways" if i % 2 else "bull_trend",
            },
        )
        for i in range(n)
    ]


def test_signals_detailed_below_threshold():
    lines = _signals_lines(_items(5))

    assert len(lines) == 5
    assert lines[0].startswith("  S0/USDT")


def test_signals_aggregated_beyond_threshold():
    n = _SIGNALS_DETAIL_MAX + 120  # simule un palier 150 paires
    lines = _signals_lines(_items(n), top=10)

    # jamais une ligne par symbole : en-tête + "Top 10:" + 10 + compteur
    assert len(lines) == 13
    assert f"{n} paires" in lines[0]
    assert "sideways" in lines[0] and "bull_trend" in lines[0]
    assert lines[1].strip() == "Top 10:"
    assert lines[-1].strip().startswith("…")
    assert f"+{n - 10} autres" in lines[-1]


def test_signals_aggregated_top_sorted_by_score():
    items = _items(_SIGNALS_DETAIL_MAX + 10)
    items.append(("BEST/USDT", {"score": 99, "action": "SELL", "regime": "bull_trend"}))

    lines = _signals_lines(items, top=3)

    assert "BEST/USDT" in lines[2]  # 1re ligne du top


def test_signals_ignores_non_dict_entries():
    items = _items(3) + [("RAW/USDT", "texte brut")]

    lines = _signals_lines(items)

    assert len(lines) == 3
