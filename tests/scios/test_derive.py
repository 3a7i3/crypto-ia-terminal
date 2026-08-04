"""Le lien Event -> Observation, rendu exécutable.

Un lien exécutable se teste sur quatre propriétés : il produit, il enregistre
sa source, il se reproduit, et il **cesse** de se reproduire quand la source
change. La quatrième est la seule qui prouve que les trois autres valent
quelque chose.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scios import derive
from scios.ledger import Event, EventLedger, EventSource
from scios.objects import ObjectStore, Observation, measurement

REPO = Path(__file__).resolve().parents[2]
REAL_KNOWLEDGE = REPO / "knowledge"


@pytest.fixture()
def prov():
    return measurement(
        tool="tests",
        method="fixture",
        limitations="données synthétiques, aucune portée scientifique",
    )


@pytest.fixture()
def peuple(tmp_path, prov):
    """5 clôtures synthétiques : 3 gagnantes, 2 perdantes."""
    root = tmp_path / "knowledge"
    ledger = EventLedger(root)
    pnls = [10.0, 5.0, 2.0, -4.0, -6.0]
    ids = ledger.ids.allocate_many("Event", 2026, len(pnls))
    ledger.append_many(
        [
            Event(
                id=i,
                created_at="2026-08-02T12:00:00+00:00",
                provenance=prov,
                epoch_id="EPO-004",
                ts_utc="2026-07-18T04:12:00Z",
                event_kind="TRADE_CLOSE",
                source=EventSource.IMPORT.value,
                payload_data={"pnl_usd": p, "duration_s": 3600.0, "reason": "TP"},
            )
            for i, p in zip(ids, pnls)
        ]
    )
    return root


# ── Le lien produit et enregistre sa source ──────────────────────────────────


def test_derivation_produit_une_observation_tracee(peuple):
    obs = derive.derive(peuple, "close_pnl_distribution", epoch_id="EPO-004")
    assert obs.source_event_count == 5
    assert obs.source_event_digest
    assert obs.source_selector["derivation"] == "close_pnl_distribution"
    assert obs.source_selector["derivation_version"] == "1.0.0"
    assert obs.provenance.actor_id == "derivation:close_pnl_distribution"
    assert obs.metrics["n_positives"] == 3
    assert obs.metrics["n_negatives"] == 2


def test_enonce_derive_reste_descriptif(peuple):
    """Une dérivation ne doit jamais produire un énoncé causal."""
    for name in derive.DERIVATIONS:
        obs = derive.derive(peuple, name, epoch_id="EPO-004")
        assert Observation._causal_markers(obs.statement) == []


def test_derivation_sans_evenement_echoue(peuple):
    with pytest.raises(derive.DerivationError, match="aucun evenement"):
        derive.derive(peuple, "close_pnl_distribution", epoch_id="EPO-999")


def test_derivation_inconnue_echoue(peuple):
    with pytest.raises(derive.DerivationError, match="inconnue"):
        derive.derive(peuple, "invention_du_jour")


# ── Le lien se reproduit ─────────────────────────────────────────────────────


def test_observation_derivee_se_reproduit(peuple):
    derive.derive(peuple, "close_pnl_distribution", epoch_id="EPO-004")
    assert derive.reproduce_all(peuple) == []


def test_deux_derivations_identiques_donnent_le_meme_resultat(peuple):
    a = derive.derive(peuple, "holding_duration", epoch_id="EPO-004")
    b = derive.derive(peuple, "holding_duration", epoch_id="EPO-004")
    assert a.id != b.id, "chaque exécution est un objet distinct"
    assert a.statement == b.statement
    assert a.metrics == b.metrics
    assert a.source_event_digest == b.source_event_digest


# ── Le lien CESSE de se reproduire quand la source change ────────────────────


def test_reproduction_echoue_si_un_evenement_est_ajoute(peuple, prov):
    derive.derive(peuple, "close_pnl_distribution", epoch_id="EPO-004")
    ledger = EventLedger(peuple)
    ledger.append(
        Event(
            id=ledger.ids.allocate("Event", 2026),
            created_at="2026-08-02T12:00:00+00:00",
            provenance=prov,
            epoch_id="EPO-004",
            ts_utc="2026-07-19T04:12:00Z",
            event_kind="TRADE_CLOSE",
            source=EventSource.IMPORT.value,
            payload_data={"pnl_usd": 999.0, "duration_s": 60.0, "reason": "TP"},
        )
    )
    problemes = derive.reproduce_all(peuple)
    assert problemes
    assert any("evenements selectionnes" in p for p in problemes)


def test_reproduction_signale_un_changement_de_version(peuple, monkeypatch):
    obs = derive.derive(peuple, "holding_duration", epoch_id="EPO-004")
    ancienne = derive.DERIVATIONS["holding_duration"]
    monkeypatch.setitem(
        derive.DERIVATIONS,
        "holding_duration",
        derive.Derivation(
            name=ancienne.name,
            version="2.0.0",
            description=ancienne.description,
            limitations=ancienne.limitations,
            event_kinds=ancienne.event_kinds,
            compute=ancienne.compute,
        ),
    )
    problemes = derive.reproduce(peuple, obs)
    assert any("registre en v2.0.0" in p for p in problemes)


def test_observation_non_derivee_n_a_rien_a_reproduire(tmp_path, prov):
    root = tmp_path / "knowledge"
    store = ObjectStore(root)
    obs = store.create(
        Observation, 2026, provenance=prov, statement="fait saisi a la main."
    )
    assert derive.reproduce(root, obs) == []


# ── Sur les données réelles ──────────────────────────────────────────────────


@pytest.mark.skipif(
    not (REAL_KNOWLEDGE / "events.jsonl").exists(),
    reason="aucun ledger commité dans ce checkout",
)
def test_les_observations_derivees_reelles_se_reproduisent():
    """Non-régression sur le lien réellement exécuté et commité."""
    problemes = derive.reproduce_all(REAL_KNOWLEDGE)
    assert problemes == [], "\n".join(problemes)


# ── Séparation Research Memory / Research Runtime ────────────────────────────


def test_la_memoire_se_lit_sans_le_runtime():
    """La mémoire doit survivre au remplacement complet du runtime.

    Les modules de mémoire (ledger, identité, provenance, socle, validité
    historique, snapshot) n'importent aucun module de runtime (dérivation,
    indicateurs). L'inverse est permis : le runtime lit la mémoire.

    C'est la forme exécutable de la séparation : on peut réécrire entièrement
    le runtime — langage compris — sans qu'un seul enregistrement devienne
    illisible.
    """
    memoire = [
        REPO / "scios" / "ledger" / "event.py",
        REPO / "scios" / "ledger" / "store.py",
        REPO / "scios" / "objects" / "base.py",
        REPO / "scios" / "objects" / "identity.py",
        REPO / "scios" / "objects" / "provenance.py",
        REPO / "scios" / "objects" / "store.py",
        REPO / "scios" / "history.py",
        REPO / "scios" / "snapshot.py",
    ]
    runtime = ("scios.derive", "scios.indicators")
    for module in memoire:
        for ligne in module.read_text(encoding="utf-8").splitlines():
            nu = ligne.strip()
            if nu.startswith(("import ", "from ")):
                assert not any(
                    r in nu for r in runtime
                ), f"{module.name} importe du runtime : {nu}"


@pytest.mark.skipif(
    not (REAL_KNOWLEDGE / "events.jsonl").exists(),
    reason="aucun ledger commité dans ce checkout",
)
def test_la_memoire_reelle_se_lit_en_json_pur():
    """Dernier recours : lisible sans SciOS du tout."""
    with (REAL_KNOWLEDGE / "events.jsonl").open(encoding="utf-8") as fh:
        premier = json.loads(fh.readline())
    assert premier["kind"] == "Event"
    assert premier["schema_version"]
    assert premier["provenance"]["actor_id"]
    assert premier["ts_utc"]
