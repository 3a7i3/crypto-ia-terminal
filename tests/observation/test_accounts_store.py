"""Store des observations de comptes réels — ADR-0019, ticket T3."""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from observation.accounts import store

TS = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc).timestamp()


@dataclass(frozen=True)
class _Rec:
    sym: str
    valeur: float


# ── Résolution du chemin (DS-001) ─────────────────────────────────────────────


def test_repertoire_resolu_a_l_execution(tmp_path: Path, monkeypatch) -> None:
    """Le chemin doit suivre l'environnement, sinon il n'est pas injectable.

    Une constante de module ferait échouer toute session pytest via le
    Scientific Data Guard, qui surveille databases/.
    """
    monkeypatch.setenv("OBS_ACCOUNTS_DIR", str(tmp_path / "ailleurs"))
    assert store.accounts_dir() == tmp_path / "ailleurs"

    monkeypatch.setenv("OBS_ACCOUNTS_DIR", str(tmp_path / "encore-ailleurs"))
    assert store.accounts_dir() == tmp_path / "encore-ailleurs"


def test_flux_inconnu_refuse() -> None:
    """Un flux invente au point d'appel produirait un fichier orphelin."""
    with pytest.raises(ValueError, match="flux inconnu"):
        store.day_file("inconnu", TS)


def test_un_fichier_par_flux_et_par_jour(tmp_path: Path) -> None:
    a = store.day_file("balances", TS, tmp_path)
    b = store.day_file("events", TS, tmp_path)
    lendemain = store.day_file("balances", TS + 86_400, tmp_path)

    assert a.name == "balances_2026-07-31.jsonl.gz"
    assert b.name == "events_2026-07-31.jsonl.gz"
    assert lendemain.name == "balances_2026-08-01.jsonl.gz"
    assert a != b != lendemain


# ── Écriture ──────────────────────────────────────────────────────────────────


def test_append_ecrit_et_horodate_le_schema(tmp_path: Path) -> None:
    r = store.append("balances", [_Rec("BTC", 1.5), _Rec("ETH", 2.0)], TS, tmp_path)

    assert r["ok"] is True
    assert r["n"] == 2
    lignes = store.read_day("balances", TS, tmp_path)
    assert [x["sym"] for x in lignes] == ["BTC", "ETH"]
    assert all(x["schema_version"] == store.SCHEMA_VERSION for x in lignes)


def test_append_accepte_dataclass_et_dict(tmp_path: Path) -> None:
    store.append(
        "positions", [_Rec("SOL", 1.0), {"sym": "DOGE", "valeur": 2.0}], TS, tmp_path
    )
    lignes = store.read_day("positions", TS, tmp_path)
    assert {x["sym"] for x in lignes} == {"SOL", "DOGE"}


def test_append_est_cumulatif_entre_deux_appels(tmp_path: Path) -> None:
    """gzip en append cree des membres successifs, relus comme un flux unique."""
    store.append("orders", [_Rec("A", 1.0)], TS, tmp_path)
    store.append("orders", [_Rec("B", 2.0)], TS, tmp_path)

    assert [x["sym"] for x in store.read_day("orders", TS, tmp_path)] == ["A", "B"]


def test_append_ne_leve_jamais_sur_objet_non_serialisable(tmp_path: Path) -> None:
    """Une collecte ne doit pas mourir parce qu'une ecriture echoue."""
    r = store.append("trades", [object()], TS, tmp_path)

    assert r["ok"] is False
    assert "serialisation" in r["motif"]


def test_liste_vide_est_un_succes_explicite(tmp_path: Path) -> None:
    r = store.append("events", [], TS, tmp_path)
    assert r["ok"] is True
    assert r["motif"] == "rien_a_ecrire"


# ── Garde-fou disque ──────────────────────────────────────────────────────────


def test_disque_insuffisant_saute_l_ecriture(tmp_path: Path, monkeypatch) -> None:
    """Saturer le disque du VPS arreterait le moteur, etranger a l'observation."""
    monkeypatch.setattr(store, "free_disk_gb", lambda _p: 0.1)
    r = store.append("balances", [_Rec("BTC", 1.0)], TS, tmp_path)

    assert r["ok"] is False
    assert "disque_insuffisant" in r["motif"]
    assert not store.day_file("balances", TS, tmp_path).exists()


# ── Lecture ───────────────────────────────────────────────────────────────────


def test_read_day_absent_rend_liste_vide(tmp_path: Path) -> None:
    assert store.read_day("balances", TS, tmp_path) == []


def test_ligne_corrompue_n_invalide_pas_la_journee(tmp_path: Path) -> None:
    """Une ecriture interrompue ne doit pas faire perdre le reste du jour."""
    path = store.day_file("events", TS, tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.write(json.dumps({"sym": "OK1"}) + "\n")
        fh.write("{ceci n'est pas du json\n")
        fh.write(json.dumps({"sym": "OK2"}) + "\n")

    assert [x["sym"] for x in store.read_day("events", TS, tmp_path)] == ["OK1", "OK2"]


# ── Rétention ─────────────────────────────────────────────────────────────────


def test_prune_supprime_au_dela_de_la_retention(tmp_path: Path) -> None:
    recent = datetime.now(timezone.utc).timestamp()
    vieux = (datetime.now(timezone.utc) - timedelta(days=90)).timestamp()
    store.append("balances", [_Rec("NEUF", 1.0)], recent, tmp_path)
    store.append("balances", [_Rec("VIEUX", 1.0)], vieux, tmp_path)

    r = store.prune(tmp_path, jours=45)

    assert r["supprimes"] == 1
    assert r["conserves"] == 1
    assert store.day_file("balances", recent, tmp_path).exists()
    assert not store.day_file("balances", vieux, tmp_path).exists()


def test_prune_ne_touche_pas_un_fichier_etranger(tmp_path: Path) -> None:
    """Ne supprimer que ce que ce module a ecrit."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    intrus = tmp_path / "sauvegarde_2020-01-01.jsonl.gz"
    intrus.write_bytes(b"peu importe")

    store.prune(tmp_path, jours=1)

    assert intrus.exists()


def test_prune_repertoire_absent_ne_leve_pas(tmp_path: Path) -> None:
    assert store.prune(tmp_path / "jamais-cree", jours=1)["supprimes"] == 0
