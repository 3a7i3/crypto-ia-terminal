"""Ligne capital des panneaux — compte papier en tête, registre nommé.

Demande opérateur 2026-07-19 : le bot affichait en permanence les 10.00 USD
alloués Phase F-01 au lieu du wallet paper (~677 USD) qui trade réellement.

Étiquetage 2026-08-06 : « Wallet virtuel » et « Alloc F-01 » ne disaient pas
que le premier est de l'argent simulé et le second une enveloppe de capital
réel. Le numéro de phase était en dur — F-01 s'affichait même en F-02.
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

    lines = _capital_lines(p, _throttle(), "F-01")

    assert lines[0] == "Compte papier *677.83 USD* — Jour 2.5 / 7"
    assert lines[1] == "Enveloppe réelle F-01: 10.00 USD"


def test_fallback_to_throttle_without_paper_equity():
    p = CommandDataProvider()

    lines = _capital_lines(p, _throttle(), "F-01")

    assert lines == ["Enveloppe réelle F-01 *10.00 USD* — Jour 2.5 / 7"]


def test_paper_equity_alone_without_throttle():
    p = CommandDataProvider(get_paper_equity=lambda: 500.0)

    assert _capital_lines(p, None) == ["Compte papier *500.00 USD*"]


def test_broken_paper_equity_falls_back():
    def _boom():
        raise RuntimeError("wallet indisponible")

    p = CommandDataProvider(get_paper_equity=_boom)

    lines = _capital_lines(p, _throttle(), "F-01")

    assert lines[0].startswith("Enveloppe réelle F-01 *10.00 USD*")


class TestLeRegistreEstNomme:
    """Les deux montants voisins appartiennent a deux mondes differents."""

    def test_les_deux_lignes_se_distinguent(self):
        p = CommandDataProvider(get_paper_equity=lambda: 677.83)

        lines = _capital_lines(p, _throttle(), "F-01")

        assert "papier" in lines[0], "le capital simule doit se dire simule"
        assert "réelle" in lines[1], "l'enveloppe de phase est du capital reel"
        assert "Wallet virtuel" not in "\n".join(lines)

    def test_la_phase_n_est_plus_ecrite_en_dur(self):
        p = CommandDataProvider(get_paper_equity=lambda: 677.83)

        lines = _capital_lines(p, _throttle(), "F-02")

        assert lines[1] == "Enveloppe réelle F-02: 10.00 USD"
        assert "F-01" not in lines[1]

    def test_phase_inconnue_n_invente_pas_de_numero(self):
        p = CommandDataProvider(get_paper_equity=lambda: 677.83)

        lines = _capital_lines(p, _throttle())

        assert lines[1] == "Enveloppe réelle: 10.00 USD"
