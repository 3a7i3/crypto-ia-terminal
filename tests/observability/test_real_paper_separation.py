"""
tests/observability/test_real_paper_separation.py — ADR-0019, ticket T1.

Verrouille la séparation entre le COMPTE RÉEL (API) et le PAPER ENGINE
(moteur simulé).

Défaut corrigé (2026-07-31) : `render_real_account_block` juxtaposait trois
champs API (`api_equity_usdt`, `api_free_cash_usdt`, `api_positions`) et deux
champs paper (`paper_equity`, `session_pnl_usd`) dans un seul bloc, sans
séparateur ni marquage de source. C'est ce mélange — et non la troncature au
Top-6 — qui a produit la croyance « le bot perd réellement 330 $ ».

Ces tests échouent si le mélange revient.
"""

from __future__ import annotations

import pytest

from observability.system_snapshot_renderers import (
    render_paper_engine_block,
    render_real_account_block,
)


def _snapshot(**api_kwargs):
    """Snapshot minimal, avec des grandeurs réelles et paper DISCERNABLES."""
    from observability.system_snapshot import APIAccountSnapshot

    class _Meta:
        cycle = 42

    class _Portfolio:
        # Valeurs choisies pour être introuvables ailleurs : si elles
        # apparaissent dans le bloc réel, c'est qu'il y a fuite.
        paper_equity = 987.65
        session_pnl_usd = -330.0

    class _Snap:
        meta = _Meta()
        portfolio = _Portfolio()
        api_account = APIAccountSnapshot(
            api_equity_usdt=api_kwargs.pop("equity", 4.81),
            api_free_cash_usdt=api_kwargs.pop("free", 1.29),
            api_positions=api_kwargs.pop("positions", 0),
            api_assets=api_kwargs.pop("assets", (("USDT", 1.29),)),
            **api_kwargs,
        )

    return _Snap()


# ── Étanchéité ────────────────────────────────────────────────────────────────


def test_bloc_reel_ne_contient_aucune_grandeur_paper() -> None:
    """Le bloc réel ne doit exposer AUCUN chiffre du moteur."""
    out = render_real_account_block(_snapshot(source="compte1_agrege"), "OBS")

    assert "987.65" not in out, "paper_equity a fuité dans le bloc réel"
    assert "-330" not in out, "session_pnl_usd a fuité dans le bloc réel"
    assert "Paper" not in out, "le mot Paper n'a rien à faire dans le bloc réel"


def test_bloc_paper_ne_contient_aucune_grandeur_api() -> None:
    """Symétrie : le bloc paper n'expose aucun chiffre d'exchange."""
    out = render_paper_engine_block(_snapshot(equity=4.81, source="compte1_agrege"))

    assert "4.81" not in out
    assert "987.65" in out, "le bloc paper doit porter l'equity paper"


def test_chaque_bloc_declare_sa_source() -> None:
    """Un lecteur doit pouvoir dire d'où vient chaque chiffre."""
    reel = render_real_account_block(_snapshot(source="compte1_agrege"), "OBS")
    paper = render_paper_engine_block(_snapshot())

    assert "source" in reel.lower()
    assert "spot" in reel.lower(), "la source agrégée est spot — le dire"
    assert "moteur" in paper.lower()
    assert "aucun exchange" in paper.lower()


# ── Honnêteté de l'equity ─────────────────────────────────────────────────────


def test_equity_annoncee_comme_borne_inferieure_si_actifs_sans_prix() -> None:
    """`api_equity_usdt` exclut les non valorisés : ne jamais le taire."""
    out = render_real_account_block(
        _snapshot(source="compte1_agrege", unpriced_count=3), "OBS"
    )

    assert "borne inf" in out.lower()
    assert "3" in out
    assert "sans prix" in out.lower()


def test_pas_de_mention_borne_si_tout_est_valorise() -> None:
    out = render_real_account_block(
        _snapshot(source="compte1_agrege", unpriced_count=0), "OBS"
    )
    assert "borne inf" not in out.lower()


def test_troncature_annoncee_jamais_muette() -> None:
    """« 2 sur 17 » — le lecteur doit savoir qu'il ne voit pas tout."""
    out = render_real_account_block(
        _snapshot(
            source="compte1_agrege",
            assets=(("USDT", 1.29), ("XRP", 4.0)),
            assets_total=17,
        ),
        "OBS",
    )
    assert "2 sur 17" in out


# ── Futures : non collecté ≠ zéro ─────────────────────────────────────────────


def test_futures_non_collecte_est_dit_et_non_affiche_a_zero() -> None:
    """None = non collecté. Afficher 0.00 serait un mensonge."""
    out = render_real_account_block(
        _snapshot(source="compte1_agrege", futures_usd=None), "OBS"
    )

    assert "non collecté" in out.lower()
    assert "Futures : <b>$0.0000" not in out


def test_futures_collecte_affiche_marge_et_pnl_latent() -> None:
    out = render_real_account_block(
        _snapshot(
            source="compte1_agrege",
            futures_usd=6.03,
            futures_margin_used_usd=1.5,
            futures_unrealized_usd=0.38,
        ),
        "OBS",
    )

    assert "6.03" in out
    assert "1.5" in out
    assert "+0.38" in out
    assert "non collecté" not in out.lower()


# ── Le remplissage du heartbeat ───────────────────────────────────────────────


def test_snapshot_non_collecte_n_affiche_aucun_chiffre() -> None:
    """Régression : le heartbeat construit un snapshot API entièrement à zéro.

    Sans marqueur, un lecteur — ou un futur détecteur d'anomalie — verrait
    l'equity tomber à 0 à chaque heartbeat. Le bloc doit refuser d'afficher.
    """
    out = render_real_account_block(_snapshot(source="non_collecte"), "OBS")

    assert "non collecté" in out.lower()
    assert "0.0000" not in out
    assert "4.81" not in out


@pytest.mark.parametrize("source", ["exchange_execution", "compte1_agrege", "inconnue"])
def test_sources_collectees_affichent_les_chiffres(source: str) -> None:
    out = render_real_account_block(_snapshot(source=source), "OBS")
    assert "4.81" in out


# ── Le modèle lui-même ────────────────────────────────────────────────────────


def test_proprietes_du_snapshot() -> None:
    from observability.system_snapshot import APIAccountSnapshot

    vide = APIAccountSnapshot(0.0, 0.0, 0, source="non_collecte")
    assert vide.collected is False
    assert vide.equity_is_lower_bound is False

    partiel = APIAccountSnapshot(
        4.81, 1.29, 0, source="compte1_agrege", unpriced_count=2
    )
    assert partiel.collected is True
    assert partiel.equity_is_lower_bound is True


def test_defauts_retrocompatibles() -> None:
    """Les appelants existants (4 arguments) ne doivent pas casser."""
    from observability.system_snapshot import APIAccountSnapshot

    a = APIAccountSnapshot(1.0, 2.0, 3, (("USDT", 1.0),))
    assert a.source == "inconnue"
    assert a.futures_usd is None
    assert a.unpriced_count == 0
