"""Validité historique et snapshot.

Le test le plus important du paquet est `test_le_ledger_reel_reste_lisible` :
il relit les journaux **réellement commités** dans le dépôt, pas des fixtures.
Toute évolution du code qui rendrait un enregistrement passé illisible fera
échouer la suite — c'est la forme exécutable du critère d'acceptation
« les données écrites aujourd'hui seront-elles encore interprétables demain ? »
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scios import history, snapshot
from scios.ledger import EventLedger
from scios.objects import ObjectStore, Observation, measurement

REPO = Path(__file__).resolve().parents[2]
REAL_KNOWLEDGE = REPO / "knowledge"


@pytest.fixture()
def prov():
    return measurement(
        tool="tests",
        method="fixture de test",
        limitations="données synthétiques, aucune portée scientifique",
    )


# ── Le contrôle porte sur les données réelles ────────────────────────────────


@pytest.mark.skipif(
    not (REAL_KNOWLEDGE / "objects.jsonl").exists(),
    reason="aucun journal commité dans ce checkout",
)
def test_le_ledger_reel_reste_lisible():
    """Garantie de non-régression sur la totalité de ce qui a été écrit."""
    report = history.check(REAL_KNOWLEDGE)
    assert report.records_read > 0
    assert report.violations == [], report.render()


@pytest.mark.skipif(
    not (REAL_KNOWLEDGE / "objects.jsonl").exists(),
    reason="aucun journal commité dans ce checkout",
)
def test_le_ledger_reel_declare_des_regles_connues():
    report = history.check(REAL_KNOWLEDGE)
    assert set(report.by_schema) <= set(history.RULESETS)


# ── Validité historique : le mécanisme ───────────────────────────────────────


def test_un_enregistrement_sans_schema_est_une_violation(tmp_path):
    root = tmp_path / "knowledge"
    root.mkdir()
    (root / "objects.jsonl").write_text(
        json.dumps({"kind": "Observation", "id": "OBS-2026-001"}) + "\n",
        encoding="utf-8",
    )
    report = history.check(root)
    assert any("aucun schema_version" in v for v in report.violations)


def test_un_schema_hors_registre_est_une_violation(tmp_path, prov):
    root = tmp_path / "knowledge"
    store = ObjectStore(root)
    obs = Observation(
        id=store.ids.allocate("Observation", 2026),
        created_at="2026-08-02T00:00:00+00:00",
        provenance=prov,
        schema_version="9.9.9",
        statement="ecrit sous des regles inconnues.",
    )
    store.append(obs)
    report = history.check(root)
    assert any("absent du registre RULESETS" in v for v in report.violations)


def test_tout_jeu_de_regles_reste_inscrit():
    """Une version retirée du registre rendrait son époque ininterprétable."""
    assert "1.0.0" in history.RULESETS
    assert "1.1.0" in history.RULESETS


def test_check_ne_migre_rien(tmp_path, prov):
    """Constater qu'un enregistrement est illisible n'autorise pas à le réécrire."""
    root = tmp_path / "knowledge"
    store = ObjectStore(root)
    store.create(Observation, 2026, provenance=prov, statement="fait mesure.")
    avant = (root / "objects.jsonl").read_bytes()
    history.check(root)
    assert (root / "objects.jsonl").read_bytes() == avant


# ── Snapshot : le lien vérifiable ledger <-> dépôt ───────────────────────────


def _peupler(root, prov, n_events=5):
    ledger, store = EventLedger(root), ObjectStore(root)
    from scios.ledger import Event, EventSource

    ids = ledger.ids.allocate_many("Event", 2026, n_events)
    ledger.append_many(
        [
            Event(
                id=i,
                created_at="2026-08-02T12:00:00+00:00",
                provenance=prov,
                ts_utc="2026-07-18T04:12:00Z",
                event_kind="TRADE_OPEN",
                source=EventSource.IMPORT.value,
                payload_data={"seq": k},
            )
            for k, i in enumerate(ids)
        ]
    )
    store.create(Observation, 2026, provenance=prov, statement="fait mesure.")
    return ids


def test_snapshot_reproductible(tmp_path, prov):
    root = tmp_path / "knowledge"
    _peupler(root, prov)
    a = snapshot.build(root, "2026-08-02T00:00:00+00:00").to_dict()
    b = snapshot.build(root, "2026-08-02T00:00:00+00:00").to_dict()
    assert a == b, "un manifeste doit être reproductible à partir des mêmes fichiers"


def test_snapshot_detecte_une_derive_du_ledger(tmp_path, prov):
    root = tmp_path / "knowledge"
    _peupler(root, prov)
    snapshot.write(root, "2026-08-02T00:00:00+00:00")
    assert snapshot.verify(root) == []

    with (root / "events.jsonl").open("a", encoding="utf-8") as fh:
        fh.write('{"kind": "Event", "id": "EVT-2026-999"}\n')

    problemes = snapshot.verify(root)
    assert any("events.jsonl" in p and "sha256" in p for p in problemes)


def test_snapshot_detecte_son_propre_falsification(tmp_path, prov):
    root = tmp_path / "knowledge"
    _peupler(root, prov)
    path = snapshot.write(root, "2026-08-02T00:00:00+00:00")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["files"]["events.jsonl"]["lines"] = 999
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    problemes = snapshot.verify(root)
    assert any("manifeste lui-même a été altéré" in p for p in problemes)


def test_snapshot_absent_est_signale(tmp_path, prov):
    root = tmp_path / "knowledge"
    _peupler(root, prov)
    assert any("absent" in p for p in snapshot.verify(root))


def test_le_manifeste_reste_petit_quel_que_soit_le_ledger(tmp_path, prov):
    """C'est la propriété qui permettra des millions d'événements hors dépôt."""
    root = tmp_path / "knowledge"
    _peupler(root, prov, n_events=500)
    path = snapshot.write(root, "2026-08-02T00:00:00+00:00")
    assert path.stat().st_size < 2000
    assert (root / "events.jsonl").stat().st_size > path.stat().st_size * 10
