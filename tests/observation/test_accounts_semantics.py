"""Sémantique mesurée du compte réel MEXC (ADR-0019, T2).

Ces tests verrouillent des faits relevés le 2026-07-31, pas des conventions
supposées. La règle testée partout : jamais un sens ni une origine devinés.
"""

from __future__ import annotations

import pytest

from observation.accounts import _semantics as S


# ── Codes de sens des contrats MEXC (piège mesuré n°1) ──────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1", "open_long"),
        ("2", "close_short"),
        ("3", "open_short"),
        ("4", "close_long"),  # le code le plus fréquent de l'échantillon
        (4, "close_long"),  # remonté en entier
        (" 4 ", "close_long"),
        ("long", "long"),  # déjà mappé par fetch_positions_history
        ("SHORT", "short"),
    ],
)
def test_map_contract_side_codes_mesures(raw, expected):
    assert S.map_contract_side(raw) == expected


@pytest.mark.parametrize(
    "raw", [None, "", "0", "5", "buy", "sell", {}, [], True, "unknown"]
)
def test_map_contract_side_inconnu_jamais_devine(raw):
    assert S.map_contract_side(raw) == "unknown"


def test_table_des_codes_est_celle_mesuree():
    assert S.CONTRACT_SIDE_CODES == {
        "1": "open_long",
        "2": "close_short",
        "3": "open_short",
        "4": "close_long",
    }


@pytest.mark.parametrize(
    "side,expected",
    [
        ("open_long", "long"),
        ("close_long", "long"),
        ("open_short", "short"),
        ("close_short", "short"),
        ("long", "long"),
        ("short", "short"),
        ("unknown", "unknown"),
        ("", "unknown"),
    ],
)
def test_direction_of_side(side, expected):
    assert S.direction_of_side(side) == expected


# ── externalOid (piège mesuré n°2) ──────────────────────────────────────────


def test_read_external_oid_depuis_info_car_ccxt_rend_null():
    order = {"clientOrderId": None, "info": {"externalOid": "_m_d86b7bca91"}}
    assert S.read_external_oid(order) == "_m_d86b7bca91"


def test_read_external_oid_repli_sur_client_order_id():
    assert S.read_external_oid({"clientOrderId": "abc", "info": {}}) == "abc"


@pytest.mark.parametrize("order", [{"clientOrderId": None, "info": {}}, {}, None, "x"])
def test_read_external_oid_absent(order):
    assert S.read_external_oid(order) is None


def test_indice_m_est_un_indice_pas_un_classement():
    assert S.has_manual_oid_hint("_m_abc") is True
    assert S.has_manual_oid_hint("x_abc") is False
    assert S.has_manual_oid_hint(None) is False


# ── origin (ADR-0019 §origin) ───────────────────────────────────────────────


def test_origin_manual_certain_quand_le_moteur_ne_peut_pas_emettre(monkeypatch):
    monkeypatch.delenv("LIVE_TRADING_CONFIRMED", raising=False)
    # Certain INDÉPENDAMMENT du préfixe : le préfixe n'est pas la règle.
    assert S.classify_origin("_m_abc") == "manual"
    assert S.classify_origin(None) == "manual"
    assert S.classify_origin("autre_prefixe") == "manual"


def test_origin_unknown_si_le_moteur_devient_capable_demettre(monkeypatch):
    monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "1")
    assert S.live_engine_enabled() is True
    # Aucun classement deviné : distinguer future_live_bot exige un ADR.
    assert S.classify_origin("_m_abc") == "unknown"
    assert S.classify_origin("_m_abc", engine_live=False) == "manual"


def test_live_engine_enabled_relu_a_chaque_appel(monkeypatch):
    monkeypatch.delenv("LIVE_TRADING_CONFIRMED", raising=False)
    assert S.live_engine_enabled() is False
    monkeypatch.setenv("LIVE_TRADING_CONFIRMED", "  ")  # blanc = non confirmé
    assert S.live_engine_enabled() is False


def test_origines_autorisees_fermees():
    assert set(S.ORIGINS) == {"manual", "paper_bot", "future_live_bot", "unknown"}
