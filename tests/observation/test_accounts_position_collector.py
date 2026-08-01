"""PositionCollector — positions ouvertes (ADR-0019, T2).

Faux client ccxt INJECTÉ : aucun appel réseau n'est possible depuis ces tests.
"""

from __future__ import annotations

from observation.accounts.position_collector import collect_positions


class FakeSwap:
    def __init__(self, positions=None, fail=None):
        self.positions = positions if positions is not None else []
        self.fail = fail

    def fetch_positions(self):
        if self.fail:
            raise self.fail
        return self.positions


def _position(**overrides):
    raw = {
        "symbol": "DOGE/USDT:USDT",
        "side": "long",
        "contracts": 120.0,
        "notional": 12.06,
        "entryPrice": 0.10049,
        "markPrice": 0.09935,
        "unrealizedPnl": -1.4978,
        "percentage": -2.293,
        "leverage": 200.0,
        "liquidationPrice": 0.0995,
        "initialMargin": 0.06,
        "timestamp": 1_753_920_000_000,
        "info": {"positionId": "1398747550"},
    }
    raw.update(overrides)
    return raw


def test_position_ouverte_rendue_avec_tous_ses_champs():
    (pos,) = collect_positions(FakeSwap([_position()])).positions

    assert pos.symbol == "DOGE/USDT:USDT"
    assert pos.side == "long"
    assert pos.contracts == 120.0
    assert pos.entry_price == 0.10049
    assert pos.mark_price == 0.09935
    assert pos.unrealized_pnl == -1.4978
    assert pos.roi == -2.293
    assert pos.liquidation_price == 0.0995
    assert pos.margin_usd == 0.06
    assert pos.position_id == "1398747550"
    assert pos.opened_at_utc.startswith("2025-")


def test_levier_eleve_collecte_tel_quel():
    # 143 et 200 mesurés sur le compte réel : jamais supposé, jamais omis.
    for lev in (143.0, 200.0):
        (pos,) = collect_positions(FakeSwap([_position(leverage=lev)])).positions
        assert pos.leverage == lev


def test_poussiere_ecartee_cas_mesure_doge_5e_9():
    rec = collect_positions(
        FakeSwap([_position(contracts=5.2e-9, notional=0.0), _position()])
    )
    assert len(rec.positions) == 1  # la fausse position n'est pas signalée
    assert rec.dust_filtered == 1


def test_poussiere_comptee_jamais_effacee_en_silence():
    rec = collect_positions(FakeSwap([_position(contracts=5.2e-9, notional=0.0)]))
    assert rec.positions == ()
    assert rec.dust_filtered == 1
    assert rec.dust_min_contracts == 1e-6
    assert rec.dust_min_notional_usd == 0.01


def test_seuil_de_poussiere_injectable(monkeypatch):
    monkeypatch.setenv("OBS_ACCOUNTS_DUST_QTY", "500")  # DS-001 : relu à l'appel
    rec = collect_positions(FakeSwap([_position()]))
    assert rec.positions == ()
    assert rec.dust_filtered == 1


def test_notionnel_inconnu_ne_fait_pas_disparaitre_une_position():
    rec = collect_positions(FakeSwap([_position(notional=None)]))
    assert len(rec.positions) == 1
    assert rec.positions[0].notional_usd is None


def test_code_de_sens_brut_mappe():
    # Un side brut '3' (open short) reste directionnellement lisible.
    (pos,) = collect_positions(FakeSwap([_position(side="3")])).positions
    assert pos.side == "short"


def test_sens_inconnu_jamais_devine():
    (pos,) = collect_positions(FakeSwap([_position(side="9")])).positions
    assert pos.side == "unknown"


def test_roi_et_liquidation_replis_sur_les_champs_bruts():
    raw = _position(percentage=None, liquidationPrice=None, initialMargin=None)
    raw["info"] = {
        "positionId": "1398747550",
        "profitRatio": -2.293,
        "liquidatePrice": 0.0995,
        "positionMargin": 0.06,
    }
    (pos,) = collect_positions(FakeSwap([raw])).positions
    assert pos.roi == -2.293
    assert pos.liquidation_price == 0.0995
    assert pos.margin_usd == 0.06


def test_aucune_position_ouverte():
    rec = collect_positions(FakeSwap([]))
    assert rec.positions == ()
    assert rec.ok is True  # zéro position n'est pas une erreur


def test_panne_visible_et_typee():
    class PermissionDenied(Exception):
        pass

    rec = collect_positions(FakeSwap(fail=PermissionDenied("scope")))
    assert rec.ok is False
    assert "PermissionDenied" in rec.error
    assert rec.positions == ()


def test_client_absent_ne_leve_pas():
    rec = collect_positions(None)
    assert rec.ok is False and "NoClient" in rec.error


def test_entrees_malformees_ignorees():
    rec = collect_positions(FakeSwap([None, "x", _position()]))
    assert len(rec.positions) == 1


def test_enregistrement_horodate_et_versionne():
    rec = collect_positions(FakeSwap([]), exchange="mexc")
    assert rec.exchange == "mexc" and rec.schema_version == 1
    assert rec.ts_utc.endswith("+00:00")
