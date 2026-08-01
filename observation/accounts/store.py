"""Persistance des observations de comptes réels (ADR-0019, ticket T3).

Un fichier par flux, une rotation par jour, gzip append-only. Écrit ce que les
collecteurs de T2 rendent, sans jamais l'interpréter.

**Invariant single-writer (OBS-D)** : un seul processus écrit ce répertoire —
le service d'observation, en ``Type=oneshot``. ``advisor_loop`` ne doit
**jamais** y écrire ; il peut le lire pour l'affichage (T4). Le contre-modèle
est documenté dans le dépôt : ``databases/paper_trades.jsonl`` a trois points
d'écriture sur un append sans verrou.

**Invariant OBS-B** : ce store n'est jamais lu par le chemin de décision.
Aucun module de ``core/``, ``src/engine/`` ou ``risk/`` ne doit l'importer.

**DS-001** : le répertoire est résolu à CHAQUE appel, jamais figé dans une
constante de module — sans quoi le Scientific Data Guard fait échouer toute
session pytest, et le chemin ne serait pas injectable en test.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import shutil
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# Un flux = un fichier. Les nommer ici et nulle part ailleurs : un flux
# inventé au point d'appel produirait un fichier que personne ne relit.
FLUX: tuple[str, ...] = (
    "balances",
    "positions",
    "orders",
    "trades",
    "transfers",
    "events",
)


def accounts_dir() -> Path:
    """Répertoire du store, résolu à l'exécution (DS-001)."""
    return Path(os.getenv("OBS_ACCOUNTS_DIR", "databases/observation/accounts"))


def min_free_disk_gb() -> float:
    """Seuil sous lequel on cesse d'écrire (aligné sur ADR-0016)."""
    return float(os.getenv("OBS_MIN_FREE_DISK_GB", "1.5"))


def retention_days() -> int:
    return int(os.getenv("OBS_ACCOUNTS_RETENTION_DAYS", "45"))


def free_disk_gb(path: Path) -> float:
    probe = (
        path if path.exists() else path.parent if path.parent.exists() else Path(".")
    )
    return shutil.disk_usage(probe).free / 1e9


def day_file(flux: str, ts: float, directory: Path | None = None) -> Path:
    """Chemin du fichier du jour pour un flux donné."""
    if flux not in FLUX:
        raise ValueError(f"flux inconnu : {flux!r} (attendus : {', '.join(FLUX)})")
    day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    return (directory or accounts_dir()) / f"{flux}_{day}.jsonl.gz"


def _plain(obj: Any) -> Any:
    """Rend un objet sérialisable, quelle que soit sa forme."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "_asdict"):  # namedtuple
        return obj._asdict()
    raise TypeError(f"enregistrement non sérialisable : {type(obj).__name__}")


def append(
    flux: str,
    records: Iterable[Any],
    ts: float | None = None,
    directory: Path | None = None,
) -> dict:
    """Ajoute des enregistrements au fichier du jour. Ne lève jamais.

    Une écriture qui échoue ne doit pas tuer la collecte : le compte rendu
    porte le motif, et l'appelant peut le journaliser. Un échec silencieux
    serait pire — d'où ``ok`` et ``motif`` toujours renseignés.
    """
    now = ts if ts is not None else datetime.now(timezone.utc).timestamp()
    target_dir = directory or accounts_dir()
    rendu = {
        "flux": flux,
        "ok": False,
        "n": 0,
        "octets": 0,
        "motif": "",
        "fichier": None,
    }

    try:
        path = day_file(flux, now, target_dir)
    except ValueError as exc:
        rendu["motif"] = str(exc)
        return rendu

    # Garde-fou disque AVANT toute écriture : saturer le disque du VPS
    # arrêterait le moteur, qui n'a rien à voir avec l'observation.
    libre = free_disk_gb(target_dir)
    if libre < min_free_disk_gb():
        rendu["motif"] = (
            f"disque_insuffisant ({libre:.2f} Go < {min_free_disk_gb()} Go)"
        )
        log.warning("[store] écriture sautée — %s", rendu["motif"])
        return rendu

    try:
        lignes = []
        for rec in records:
            payload = dict(_plain(rec))
            payload.setdefault("schema_version", SCHEMA_VERSION)
            lignes.append(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            )
    except TypeError as exc:
        rendu["motif"] = f"serialisation: {exc}"
        log.warning("[store] %s", rendu["motif"])
        return rendu

    if not lignes:
        rendu.update(ok=True, motif="rien_a_ecrire", fichier=str(path))
        return rendu

    blob = ("\n".join(lignes) + "\n").encode("utf-8")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # gzip en append crée des membres successifs ; le module gzip les
        # relit de façon transparente comme un flux unique. Motif repris de
        # observation/market_observer.py, éprouvé en production.
        with gzip.open(path, "ab") as fh:
            fh.write(blob)
    except OSError as exc:
        rendu["motif"] = f"ecriture: {exc}"
        log.warning("[store] %s", rendu["motif"])
        return rendu

    rendu.update(ok=True, n=len(lignes), octets=len(blob), fichier=str(path))
    return rendu


def read_day(flux: str, ts: float, directory: Path | None = None) -> list[dict]:
    """Relit un fichier de flux. Rend [] si absent — jamais d'exception."""
    try:
        path = day_file(flux, ts, directory)
    except ValueError:
        return []
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    # Une ligne corrompue (écriture interrompue) ne doit pas
                    # invalider la journée entière.
                    continue
    except OSError as exc:
        log.warning("[store] lecture impossible %s: %s", path, exc)
    return out


def prune(directory: Path | None = None, jours: int | None = None) -> dict:
    """Supprime les fichiers de flux plus vieux que la rétention.

    Ne touche QUE les fichiers ``{flux}_{date}.jsonl.gz`` de ce répertoire :
    un fichier étranger déposé là n'est jamais supprimé.
    """
    target_dir = directory or accounts_dir()
    limite_j = jours if jours is not None else retention_days()
    rendu = {"supprimes": 0, "octets_liberes": 0, "conserves": 0}
    if not target_dir.exists():
        return rendu

    seuil = (datetime.now(timezone.utc) - timedelta(days=limite_j)).date()
    for f in target_dir.glob("*.jsonl.gz"):
        prefixe, _, jour = f.name[: -len(".jsonl.gz")].rpartition("_")
        if prefixe not in FLUX:
            continue
        try:
            jour_date = datetime.strptime(jour, "%Y-%m-%d").date()
        except ValueError:
            continue
        if jour_date < seuil:
            try:
                taille = f.stat().st_size
                f.unlink()
                rendu["supprimes"] += 1
                rendu["octets_liberes"] += taille
            except OSError as exc:
                log.warning("[store] suppression impossible %s: %s", f, exc)
        else:
            rendu["conserves"] += 1
    return rendu
