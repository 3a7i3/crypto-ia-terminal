"""
system/provenance.py — preuve de transformation et couverture normative.

Deux primitives, nées de deux limites constatées du protocole (2026-07-29).

**1. Une transformation déclarée n'est pas une transformation prouvée.**
Le § 20 du protocole demande à chaque étape de déclarer son opération, sa perte
d'information et ses hypothèses. Ce sont des phrases. Rien ne permettait de
vérifier qu'un artefact a bien été produit par le script annoncé, à partir des
entrées annoncées. `Provenance` transforme la déclaration en **empreinte
vérifiable** : hash de l'entrée, hash du script, hash de la sortie, population.
Même saut que « les tests passent » → « voici l'observation qui le montre ».

**2. Une couverture citée en remarque n'engage personne.**
« 3 constantes mesurées sur 234 » était une note de bas de page ; le lecteur
devait faire le calcul et en tirer lui-même les conséquences. `Coverage` rend le
ratio normatif : il porte un **plafond de confiance** mécanique, et un rapport
qui affirme plus que son plafond est en contradiction avec ses propres données.

Ce module ne lit aucune configuration et ne décide rien. Il ne sait pas ce qui
est « assez couvert » — il applique une grille écrite ici, discutable, et la
rend visible.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

__all__ = [
    "sha256_text",
    "sha256_file",
    "sha256_json",
    "PROVENANCE_SCHEMA_VERSION",
    "InputRef",
    "Provenance",
    "build_provenance",
    "verify_provenance",
    "CEILING_ORDER",
    "CEILING_NONE",
    "CEILING_LOW",
    "CEILING_MEDIUM",
    "CEILING_HIGH",
    "CEILING_FULL",
    "Coverage",
    "weakest_ceiling",
]

#: Version du schéma de provenance. Un consommateur qui lit une provenance dont
#: la version lui est inconnue doit refuser de conclure, pas deviner — c'est la
#: leçon de la gate D, qui lisait une clé qu'aucun producteur n'écrivait.
PROVENANCE_SCHEMA_VERSION = 1

_CHUNK = 1 << 20


# ── Empreintes ────────────────────────────────────────────────────────────────


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> Optional[str]:
    """SHA-256 d'un fichier, ou None s'il est absent/illisible.

    None est un résultat, pas une erreur : un artefact dont l'entrée a disparu
    est précisément ce qu'on veut pouvoir constater.
    """
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            while chunk := handle.read(_CHUNK):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def sha256_json(payload: object) -> str:
    """Empreinte d'une structure, indépendante de l'ordre des clés.

    `sort_keys=True` : deux rapports identiques au réordonnancement près ont la
    même empreinte. Sans cela, un simple changement de version de bibliothèque
    ferait croire à une modification de contenu.
    """
    return sha256_text(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    )


# ── Provenance ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class InputRef:
    """Une entrée d'une transformation, avec son empreinte au moment de la lecture."""

    path: str
    sha256: Optional[str]
    n_records: Optional[int] = None


@dataclass
class Provenance:
    """Preuve reproductible d'une transformation observation → artefact.

    `output_sha256` est renseigné APRÈS sérialisation du corps du rapport : la
    provenance décrit un contenu, elle n'en fait pas partie. C'est ce qui permet
    à un consommateur de recalculer l'empreinte et de détecter une édition
    manuelle de l'artefact.
    """

    schema_version: int
    generated_at: str
    tool: str
    tool_sha256: Optional[str]
    inputs: list[InputRef] = field(default_factory=list)
    population: dict = field(default_factory=dict)
    output_sha256: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "tool": self.tool,
            "tool_sha256": self.tool_sha256,
            "inputs": [
                {"path": i.path, "sha256": i.sha256, "n_records": i.n_records}
                for i in self.inputs
            ],
            "population": self.population,
            "output_sha256": self.output_sha256,
            "notes": self.notes,
        }


def build_provenance(
    *,
    tool_path: Path,
    inputs: Sequence[InputRef] = (),
    population: Optional[Mapping] = None,
    notes: str = "",
    generated_at: Optional[str] = None,
) -> Provenance:
    """Provenance d'un artefact en cours de production.

    `tool_path` est haché : deux artefacts produits par deux versions du même
    script portent des empreintes d'outil différentes, ce qui rend visible le cas
    « le rapport a été produit par un code qui n'existe plus » — invisible
    aujourd'hui, et à l'origine de la traçabilité rompue de la gate D.
    """
    stamp = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return Provenance(
        schema_version=PROVENANCE_SCHEMA_VERSION,
        generated_at=stamp,
        tool=tool_path.name,
        tool_sha256=sha256_file(tool_path),
        inputs=list(inputs),
        population=dict(population or {}),
        notes=notes,
    )


def verify_provenance(
    stamp: Mapping, *, body: object = None, repo_root: Optional[Path] = None
) -> list[str]:
    """Écarts entre ce qu'une provenance affirme et ce qui est vérifiable.

    Retourne une liste de constats, vide si tout concorde. Ne lève jamais : un
    outil de vérification qui meurt sur un artefact malformé laisse le
    consommateur sans information, ce qui est le pire des cas.

    Ce qui est vérifié : version de schéma connue, présence de la date, empreinte
    de l'outil recalculable et identique, empreintes d'entrées identiques,
    empreinte de sortie identique au corps fourni.
    Ce qui n'est PAS vérifié : que la transformation annoncée soit celle qui a
    réellement eu lieu. Une empreinte prouve l'identité des octets, pas la
    justesse de l'opération.
    """
    issues: list[str] = []
    if not isinstance(stamp, Mapping):
        return ["provenance absente ou de type inattendu"]

    version = stamp.get("schema_version")
    if version is None:
        issues.append(
            "schema_version absent — le consommateur ne peut pas savoir quoi lire"
        )
    elif version != PROVENANCE_SCHEMA_VERSION:
        issues.append(
            f"schema_version {version} inconnu (attendu {PROVENANCE_SCHEMA_VERSION})"
        )

    if not stamp.get("generated_at"):
        issues.append("generated_at absent — fraîcheur non évaluable")

    root = repo_root or Path.cwd()
    tool = stamp.get("tool")
    declared_tool_hash = stamp.get("tool_sha256")
    if tool and declared_tool_hash:
        for candidate in (root / "tools" / tool, root / "scripts" / tool, root / tool):
            if candidate.exists():
                actual = sha256_file(candidate)
                if actual != declared_tool_hash:
                    issues.append(
                        f"empreinte de l'outil {tool} différente : l'artefact a été "
                        f"produit par une autre version du script"
                    )
                break
        else:
            issues.append(f"outil {tool} introuvable — provenance non recalculable")

    for ref in stamp.get("inputs") or []:
        if not isinstance(ref, Mapping):
            issues.append("entrée de provenance malformée")
            continue
        path = ref.get("path")
        declared = ref.get("sha256")
        if not path or not declared:
            issues.append(f"entrée sans chemin ou sans empreinte : {ref}")
            continue
        actual = sha256_file(Path(path))
        if actual is None:
            issues.append(f"entrée disparue depuis la production : {path}")
        elif actual != declared:
            issues.append(f"entrée modifiée depuis la production : {path}")

    if body is not None and stamp.get("output_sha256"):
        if sha256_json(body) != stamp["output_sha256"]:
            issues.append("corps de l'artefact modifié après production")

    return issues


# ── Couverture normative ──────────────────────────────────────────────────────

CEILING_NONE = "AUCUNE"
CEILING_LOW = "FAIBLE"
CEILING_MEDIUM = "MOYENNE"
CEILING_HIGH = "ELEVEE"
CEILING_FULL = "COMPLETE"

#: Du plus contraignant au moins contraignant. Sert au maillon faible : une
#: chaîne ne vaut jamais mieux que son plafond le plus bas.
CEILING_ORDER = [
    CEILING_NONE,
    CEILING_LOW,
    CEILING_MEDIUM,
    CEILING_HIGH,
    CEILING_FULL,
]

#: Grille de plafonnement. Volontairement grossière et exposée : le seul intérêt
#: d'un seuil est qu'il soit discutable en un coup d'œil. Ces bornes ne sont PAS
#: des seuils du moteur de trading — elles ne gouvernent qu'un niveau de langage
#: admissible dans un rapport.
_CEILING_THRESHOLDS = [
    (0.90, CEILING_FULL),
    (0.50, CEILING_HIGH),
    (0.10, CEILING_MEDIUM),
    (0.0, CEILING_LOW),
]


@dataclass(frozen=True)
class Coverage:
    """Couverture d'une mesure, avec son plafond de confiance MÉCANIQUE.

    Exemple réel : INV-INIT-001 est énoncé sur 234 constantes et mesuré sur 3.
    `Coverage(measured=3, total=234)` rend `ratio=0.0128` et
    `confidence_ceiling=FAIBLE`. Le rapport n'a plus le droit d'écrire
    « vérifié » : son propre objet de couverture le contredit.
    """

    measured: int
    total: int
    subject: str = ""

    @property
    def ratio(self) -> float:
        if self.total <= 0:
            return 0.0
        return self.measured / self.total

    @property
    def confidence_ceiling(self) -> str:
        if self.total <= 0 or self.measured <= 0:
            return CEILING_NONE
        for threshold, ceiling in _CEILING_THRESHOLDS:
            if self.ratio >= threshold:
                return ceiling
        return CEILING_LOW

    @property
    def unmeasured(self) -> int:
        return max(0, self.total - self.measured)

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "measured": self.measured,
            "total": self.total,
            "unmeasured": self.unmeasured,
            "ratio": round(self.ratio, 6),
            "confidence_ceiling": self.confidence_ceiling,
        }

    def sentence(self) -> str:
        """Phrase à recopier dans un rapport — le plafond y est inséparable du ratio."""
        return (
            f"{self.subject or 'couverture'} : {self.measured}/{self.total} "
            f"({self.ratio:.2%}) — plafond de confiance {self.confidence_ceiling}"
        )


def weakest_ceiling(ceilings: Iterable[str]) -> str:
    """Plafond le plus contraignant d'un ensemble — maillon faible (§ 3).

    Une chaîne dont une étape est plafonnée à FAIBLE est plafonnée à FAIBLE,
    quel que soit le soin apporté aux autres étapes.
    """
    worst = CEILING_FULL
    for ceiling in ceilings:
        if ceiling not in CEILING_ORDER:
            return CEILING_NONE
        if CEILING_ORDER.index(ceiling) < CEILING_ORDER.index(worst):
            worst = ceiling
    return worst
