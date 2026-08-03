"""Identité scientifique — allocation d'identifiants permanents.

Applique KNOWLEDGE_MODEL §1 : `<TYPE>-<YYYY>-<NNN>`, **jamais réattribué**,
même après suppression logique de l'objet.

Le registre est un journal append-only. Un identifiant retiré du registre des
objets vivants reste inscrit ici pour toujours — c'est ce qui garantit la
non-réattribution, condition de l'invariant `Permanent Object Identifier`.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path

ID_PATTERN = re.compile(r"^(?P<type>[A-Z]{2,4})-(?P<year>\d{4})-(?P<seq>\d{3,})$")

# Préfixes canoniques. Fermé volontairement : un objet hors de cette liste
# n'appartient pas au modèle gelé et doit passer par un ADR (FOUNDATION_FREEZE §6.1).
PREFIXES: dict[str, str] = {
    # L1 — le ledger. Seul objet non reconstructible du système.
    "Event": "EVT",
    # L2 et au-dessus — dérivables.
    "Observation": "OBS",
    "Question": "QST",
    "Hypothesis": "HYP",
    "Corpus": "COR",
    "Baseline": "BSL",
    "Experiment": "EXP",
    "RunManifest": "RUN",
    "Verdict": "VRD",
    "Publication": "PUB",
    "Policy": "POL",
    "Calibration": "CAL",
    "ADR": "ADR",
    "Deployment": "DEP",
    "ResearchEpoch": "EPO",
    "Knowledge": "KNW",
    "Contribution": "CTB",
}


class IdentityError(RuntimeError):
    """Violation d'un invariant d'identité."""


@dataclass(frozen=True)
class AllocatedId:
    value: str
    kind: str
    year: int
    seq: int


def parse(identifier: str) -> AllocatedId:
    m = ID_PATTERN.match(identifier)
    if not m:
        raise IdentityError(
            f"identifiant malformé: {identifier!r} — attendu <TYPE>-<YYYY>-<NNN>"
        )
    prefix = m.group("type")
    kind = next((k for k, v in PREFIXES.items() if v == prefix), None)
    if kind is None:
        raise IdentityError(
            f"préfixe inconnu: {prefix!r} — hors du modèle gelé. "
            "Ajouter un type exige un ADR (FOUNDATION_FREEZE §6.1)."
        )
    return AllocatedId(identifier, kind, int(m.group("year")), int(m.group("seq")))


class IdRegistry:
    """Journal append-only des identifiants alloués.

    Un identifiant présent dans le journal n'est jamais réalloué, y compris si
    l'objet correspondant a été retiré. La lecture reconstruit l'état complet :
    le fichier est la source de vérité, l'index en mémoire n'est qu'un cache.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._allocated: set[str] = set()
        self._max_seq: dict[tuple[str, int], int] = {}
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> None:
        if not self._path.exists():
            return
        for line_no, raw in enumerate(
            self._path.read_text(encoding="utf-8").splitlines(), 1
        ):
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise IdentityError(
                    f"{self._path}:{line_no} journal d'identité corrompu: {exc}"
                ) from exc
            self._register(rec["id"])

    def _register(self, identifier: str) -> None:
        parsed = parse(identifier)
        self._allocated.add(identifier)
        key = (parsed.kind, parsed.year)
        self._max_seq[key] = max(self._max_seq.get(key, 0), parsed.seq)

    def is_allocated(self, identifier: str) -> bool:
        return identifier in self._allocated

    def allocate(self, kind: str, year: int) -> str:
        """Alloue le prochain identifiant pour (type, année) et le journalise."""
        if kind not in PREFIXES:
            raise IdentityError(
                f"type hors du modèle gelé: {kind!r}. "
                "Ajouter un type exige un ADR (FOUNDATION_FREEZE §6.1)."
            )
        with self._lock:
            key = (kind, year)
            seq = self._max_seq.get(key, 0) + 1
            identifier = f"{PREFIXES[kind]}-{year}-{seq:03d}"
            if identifier in self._allocated:  # défense: ne doit jamais arriver
                raise IdentityError(f"collision d'identifiant: {identifier}")
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"id": identifier, "kind": kind}) + "\n")
            self._register(identifier)
            return identifier

    def allocate_many(self, kind: str, year: int, count: int) -> list[str]:
        """Alloue `count` identifiants consécutifs en une seule écriture.

        Même sémantique qu'`allocate`, sans rouvrir le journal à chaque unité :
        l'ingestion d'un ledger de plusieurs milliers d'événements ne doit pas
        coûter autant d'ouvertures de fichier.
        """
        if kind not in PREFIXES:
            raise IdentityError(
                f"type hors du modèle gelé: {kind!r}. "
                "Ajouter un type exige un ADR (FOUNDATION_FREEZE §6.1)."
            )
        if count < 0:
            raise IdentityError("count ne peut pas être négatif")
        with self._lock:
            key = (kind, year)
            start = self._max_seq.get(key, 0) + 1
            ids = [
                f"{PREFIXES[kind]}-{year}-{n:03d}" for n in range(start, start + count)
            ]
            collision = next((i for i in ids if i in self._allocated), None)
            if collision is not None:  # défense: ne doit jamais arriver
                raise IdentityError(f"collision d'identifiant: {collision}")
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                for identifier in ids:
                    fh.write(json.dumps({"id": identifier, "kind": kind}) + "\n")
            for identifier in ids:
                self._register(identifier)
            return ids

    def reserve(self, identifier: str) -> str:
        """Journalise un identifiant imposé de l'extérieur (import, migration).

        Échoue si l'identifiant est déjà alloué — la réattribution est interdite.
        """
        parsed = parse(identifier)
        with self._lock:
            if identifier in self._allocated:
                raise IdentityError(
                    f"identifiant déjà alloué, réattribution interdite: {identifier}"
                )
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"id": identifier, "kind": parsed.kind}) + "\n")
            self._register(identifier)
            return identifier
