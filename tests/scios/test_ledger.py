"""Tests de la couche L1 — ledger d'événements.

Deux tests portent sur des défauts réellement rencontrés pendant la
construction, pas sur des hypothèses : `test_empreinte_atteste_des_octets_ecrits`
et `test_durcir_une_regle_ne_rend_pas_le_passe_illisible`.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from scios.ledger import Event, EventLedger, EventSource, LedgerError
from scios.objects import ObjectError, ObjectStore, Observation, measurement
from scios.objects.base import fingerprint_dict


@pytest.fixture()
def prov():
    return measurement(
        tool="tools/ingest_trade_events.py",
        method="une ligne du journal de production devient un Event, sans agrégation",
        limitations="aucun deployment_id : l'objet Deployment n'existe pas encore",
    )


@pytest.fixture()
def ledger(tmp_path) -> EventLedger:
    return EventLedger(tmp_path / "knowledge")


def _event(ledger, prov, **kw) -> Event:
    defaults = dict(
        id=ledger.ids.allocate("Event", 2026),
        created_at="2026-08-02T12:00:00+00:00",
        provenance=prov,
        ts_utc="2026-07-18T04:12:00Z",
        event_kind="TRADE_OPEN",
        source=EventSource.IMPORT.value,
        payload_data={"symbol": "BTC/USDT", "price": 61234.5},
    )
    defaults.update(kw)
    return Event(**defaults)


# ── Event : un atome, jamais révisable ───────────────────────────────────────


def test_event_n_a_aucune_machinerie_de_succession(ledger, prov):
    """RECORDED -> jamais autre chose. Le champ n'existe même pas."""
    evt = _event(ledger, prov)
    assert not hasattr(evt, "supersedes")
    assert not hasattr(evt, "superseded_by")
    assert not hasattr(evt, "succeed")


def test_event_immuable(ledger, prov):
    evt = _event(ledger, prov)
    with pytest.raises(dataclasses.FrozenInstanceError):
        evt.ts_utc = "2026-01-01T00:00:00Z"


def test_event_exige_un_instant(ledger, prov):
    with pytest.raises(ObjectError, match="ts_utc"):
        _event(ledger, prov, ts_utc="")


def test_event_refuse_une_source_inconnue(ledger, prov):
    with pytest.raises(ObjectError, match="source inconnue"):
        _event(ledger, prov, source="rumeur")


# ── Ledger : append-only, refuse les objets dérivés ──────────────────────────


def test_ledger_refuse_un_objet_derive(ledger, prov):
    obs = Observation(
        id=ledger.ids.allocate("Observation", 2026),
        created_at="2026-08-02T12:00:00+00:00",
        provenance=prov,
        statement="fait mesure.",
    )
    with pytest.raises(LedgerError, match="que des Event"):
        ledger.append(obs)


def test_ledger_refuse_un_id_non_alloue(ledger, prov):
    evt = _event(ledger, prov)
    orphelin = dataclasses.replace(evt, id="EVT-2026-999")
    with pytest.raises(LedgerError, match="registre d'identité"):
        ledger.append(orphelin)


def test_ingestion_en_lot_et_relecture(ledger, prov):
    ids = ledger.ids.allocate_many("Event", 2026, 50)
    lot = [
        _event(ledger, prov, id=i, payload_data={"seq": n}) for n, i in enumerate(ids)
    ]
    assert ledger.append_many(lot) == 50
    assert ledger.count() == 50
    assert ledger.verify() == []
    relu = ledger.by_id()[ids[7]]
    assert relu.payload_data["seq"] == 7


def test_ledger_detecte_un_doublon(ledger, prov):
    evt = _event(ledger, prov)
    ledger.append(evt)
    with ledger.journal.open("a", encoding="utf-8") as fh:
        rec = {"_fingerprint": evt.fingerprint(), **evt.to_dict()}
        fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    problemes = ledger.verify()
    assert any("deux fois" in p for p in problemes)


# ── Leçons apprises pendant la construction ──────────────────────────────────


def test_empreinte_atteste_des_octets_ecrits(ledger, prov):
    """L'empreinte porte sur l'enregistrement, pas sur l'objet reconstruit.

    Défaut rencontré : l'ajout du champ `source_artifacts` à la sérialisation
    invalidait rétroactivement l'empreinte de TOUS les enregistrements déjà
    journalisés, parce que la vérification re-sérialisait l'objet avec le code
    courant au lieu de re-hacher ce qui avait été écrit.
    """
    evt = _event(ledger, prov)
    ledger.append(evt)
    rec = json.loads(ledger.journal.read_text(encoding="utf-8").strip())

    assert fingerprint_dict(rec) == rec["_fingerprint"]

    # Une clé de métadonnée d'écriture n'entre pas dans l'empreinte.
    rec_bis = dict(rec, _written_at="1999-01-01T00:00:00+00:00")
    assert fingerprint_dict(rec_bis) == rec["_fingerprint"]

    # Un champ de contenu, si.
    rec_ter = dict(rec, ts_utc="1999-01-01T00:00:00Z")
    assert fingerprint_dict(rec_ter) != rec["_fingerprint"]


def test_durcir_une_regle_ne_rend_pas_le_passe_illisible(tmp_path, prov):
    """Schéma 1.1.0 : `source_events` n'accepte plus que des identifiants Event.

    Un enregistrement écrit en 1.0.0 avec un chemin de fichier reste lisible.
    Un journal append-only ne se réécrit pas.
    """
    store = ObjectStore(tmp_path / "knowledge")
    legacy_id = store.ids.allocate("Observation", 2026)
    legacy = Observation(
        id=legacy_id,
        created_at="2026-08-02T00:00:00+00:00",
        provenance=prov,
        schema_version="1.0.0",
        statement="210 modules executes sur 1115.",
        source_events=("artifacts/prod_executed_modules.txt",),
    )
    store.append(legacy)
    assert store.get(legacy_id).source_events == (
        "artifacts/prod_executed_modules.txt",
    )
    assert store.verify() == []

    with pytest.raises(ObjectError, match="que des identifiants Event"):
        Observation(
            id=store.ids.allocate("Observation", 2026),
            created_at="2026-08-02T00:00:00+00:00",
            provenance=prov,
            statement="meme fait, schema courant.",
            source_events=("artifacts/prod_executed_modules.txt",),
        )


def test_observation_relie_a_de_vrais_evenements(tmp_path, prov):
    """La chaîne de provenance descend jusqu'à l'atome."""
    root = tmp_path / "knowledge"
    ledger, store = EventLedger(root), ObjectStore(root)
    ids = ledger.ids.allocate_many("Event", 2026, 3)
    ledger.append_many([_event(ledger, prov, id=i) for i in ids])

    obs = store.create(
        Observation,
        2026,
        provenance=prov,
        statement="3 ouvertures enregistrees sur la periode.",
        n=3,
        source_events=tuple(ids),
        source_artifacts=("databases/paper_trades.jsonl",),
    )
    connus = set(ledger.by_id())
    assert set(obs.source_events) <= connus
    assert store.verify() == []
