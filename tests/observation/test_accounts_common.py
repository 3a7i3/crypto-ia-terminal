"""Primitives techniques des collecteurs de comptes réels (ADR-0019, T2).

Aucun client réel, aucun réseau : ces fonctions sont pures ou ne lisent que
l'environnement.
"""

from __future__ import annotations

from observation.accounts import _common as C


# ── Seuil de poussière (piège mesuré n°4) ───────────────────────────────────


def test_dust_thresholds_relus_a_chaque_appel(monkeypatch):
    monkeypatch.delenv("OBS_ACCOUNTS_DUST_QTY", raising=False)
    monkeypatch.delenv("OBS_ACCOUNTS_DUST_USD", raising=False)
    assert C.dust_thresholds() == (1e-6, 0.01)
    monkeypatch.setenv("OBS_ACCOUNTS_DUST_QTY", "0.5")
    assert C.dust_thresholds()[0] == 0.5  # DS-001 : aucune constante figée


def test_is_dust_cas_mesure_doge_5e_9():
    # 5.2e-9 DOGE, equity 0 → ni position ni collatéral.
    assert C.is_dust(5.2e-9, 0.0, 1e-6, 0.01) is True


def test_is_dust_position_reelle_conservee():
    assert C.is_dust(120.0, 12.5, 1e-6, 0.01) is False


def test_is_dust_notionnel_inconnu_ne_suffit_pas():
    assert C.is_dust(120.0, None, 1e-6, 0.01) is False


def test_is_dust_notionnel_sous_seuil_avec_quantite_forte():
    assert C.is_dust(1e6, 0.001, 1e-6, 0.01) is True


# ── Conversions tolérantes ──────────────────────────────────────────────────


def test_safe_float_tolerant():
    assert C.safe_float("1.5") == 1.5
    assert C.safe_float(None) is None
    assert C.safe_float("abc") is None
    assert C.safe_float(True) is None  # un booléen n'est pas une mesure


def test_iso_from_ms():
    assert C.iso_from_ms(1_753_920_000_000).startswith("2025-")
    assert C.iso_from_ms(None) is None
    assert C.iso_from_ms("abc") is None
    assert C.iso_from_ms(1e30) is None  # hors domaine → None, jamais d'exception


def test_utc_now_iso_est_horodate_utc():
    assert C.utc_now_iso().endswith("+00:00")


# ── Échec de source : visible et typé ───────────────────────────────────────


def test_source_error_conserve_le_type():
    class AuthenticationError(Exception):
        pass

    assert C.source_error(AuthenticationError("bad key")).startswith(
        "AuthenticationError: bad key"
    )


def test_source_error_distingue_permission_denied():
    class PermissionDenied(Exception):
        pass

    assert "PermissionDenied" in C.source_error(PermissionDenied("scope"))


def test_source_error_borne_la_longueur():
    assert len(C.source_error(RuntimeError("x" * 500))) < 200
