"""Ligne capital des panneaux — wallet virtuel « compte n°2 » en tête.

Demande opérateur 2026-07-19 : le bot affichait en permanence les 10.00 USD
alloués Phase F-01 au lieu du wallet paper (~677 USD) qui trade réellement.
"""

from types import SimpleNamespace

from capital_deployment.command_center_bot import CommandDataProvider, _capital_lines


def _throttle(allocated: float = 10.0):
    return SimpleNamespace(
        allocated_capital=allocated,
        allocation=lambda: SimpleNamespace(
            days_elapsed=lambda: 2.5, min_duration_days=7
        ),
    )


def test_paper_equity_leads_when_available():
    p = CommandDataProvider(get_paper_equity=lambda: 677.83)

    lines = _capital_lines(p, _throttle())

    assert lines[0] == "Wallet virtuel *677.83 USD* — Jour 2.5 / 7"
    assert lines[1] == "Alloc F-01: 10.00 USD"


def test_fallback_to_throttle_without_paper_equity():
    p = CommandDataProvider()

    lines = _capital_lines(p, _throttle())

    assert lines == ["Capital *10.00 USD* — Jour 2.5 / 7"]


def test_paper_equity_alone_without_throttle():
    p = CommandDataProvider(get_paper_equity=lambda: 500.0)

    assert _capital_lines(p, None) == ["Wallet virtuel *500.00 USD*"]


def test_broken_paper_equity_falls_back():
    def _boom():
        raise RuntimeError("wallet indisponible")

    p = CommandDataProvider(get_paper_equity=_boom)

    lines = _capital_lines(p, _throttle())

    assert lines[0].startswith("Capital *10.00 USD*")
