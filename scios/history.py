"""Validité historique — un objet se lit sous les règles de sa création.

Troisième propriété fondamentale du modèle, au même rang que l'immuabilité et
la provenance.

    La question posée à un objet est :
        « sous quelles règles as-tu été créé ? »
    Jamais :
        « es-tu valide selon les règles d'aujourd'hui ? »

C'est le fonctionnement des publications scientifiques : un article de 2012 ne
devient pas invalide parce que la méthode de 2026 a changé. Il reste
interprétable dans le contexte où il a été produit.

Ce module ne définit pas la règle — il la **vérifie**. Le contrôle
`check(root)` relit l'intégralité des journaux réellement écrits et échoue si
un seul enregistrement est devenu illisible. Branché en test, il transforme la
promesse en garantie : toute évolution du code qui casserait la relecture du
passé fait échouer la suite.

Deux défauts réels l'ont motivé, tous deux rencontrés en construisant le ledger
et tous deux détectables par ce contrôle :

  1. l'ajout d'un champ à la sérialisation a invalidé rétroactivement
     l'empreinte de tous les enregistrements déjà écrits ;
  2. le durcissement d'une règle de validation a rendu les enregistrements
     antérieurs impossibles à relire.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scios.ledger.store import EventLedger
from scios.objects.store import ObjectStore

# Registre des jeux de règles. Une version décrit ce qui a changé et RESTE
# inscrite pour toujours : c'est le contexte sous lequel les enregistrements
# de cette époque doivent être interprétés.
RULESETS: dict[str, str] = {
    "1.0.0": (
        "Socle initial : identité permanente, provenance obligatoire, "
        "immuabilité par succession, magasin append-only. `source_events` "
        "acceptait n'importe quelle chaîne, y compris un chemin de fichier. "
        "Les 7 premières observations et les 1421 premiers événements portent "
        "cette version — le ledger L1 a été peuplé AVANT le durcissement de "
        "1.1.0, et ses enregistrements le déclarent honnêtement."
    ),
    "1.1.0": (
        "`source_events` n'accepte plus que des identifiants Event ; les "
        "références de fichier, d'outil ou de rapport passent par "
        "`source_artifacts`. L'empreinte porte désormais sur l'enregistrement "
        "écrit et non sur l'objet reconstruit."
    ),
    "1.2.0": (
        "Le lien Event -> Observation devient exécutable. Une observation "
        "dérivée porte `source_selector` (comment re-choisir le même ensemble "
        "d'événements), `source_event_count` et `source_event_digest` — la "
        "provenance reste vérifiable à coût constant quel que soit le volume "
        "du ledger, là où l'inscription des identifiants un à un ne passe pas "
        "l'échelle."
    ),
}


@dataclass
class ValidityReport:
    records_read: int = 0
    by_schema: dict[str, int] = field(default_factory=dict)
    violations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def to_dict(self) -> dict[str, Any]:
        return {
            "records_read": self.records_read,
            "by_schema": self.by_schema,
            "violations": self.violations,
            "ok": self.ok,
        }

    def render(self) -> str:
        lines = ["VALIDITÉ HISTORIQUE", ""]
        lines.append(f"enregistrements relus : {self.records_read}")
        for version in sorted(self.by_schema):
            known = "" if version in RULESETS else "   ⚠ jeu de règles inconnu"
            lines.append(f"  schéma {version:<8} {self.by_schema[version]:>6}{known}")
        lines.append("")
        if self.ok:
            lines.append(
                "Aucune violation. Tout enregistrement écrit reste lisible et "
                "vérifiable sous les règles de sa création."
            )
        else:
            lines.append(f"{len(self.violations)} violation(s) :")
            lines.extend(f"  - {v}" for v in self.violations)
        return "\n".join(lines)


def _scan(path: Path, report: ValidityReport) -> None:
    """Relève les versions de schéma déclarées, sans interpréter le contenu."""
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError as exc:
                report.violations.append(f"{path.name}:{line_no} illisible — {exc}")
                continue
            report.records_read += 1
            version = rec.get("schema_version")
            if version is None:
                report.violations.append(
                    f"{path.name}:{line_no} aucun schema_version déclaré — "
                    "l'enregistrement ne dit pas sous quelles règles il a été écrit"
                )
                continue
            report.by_schema[version] = report.by_schema.get(version, 0) + 1
            if version not in RULESETS:
                report.violations.append(
                    f"{path.name}:{line_no} schéma {version!r} absent du registre "
                    "RULESETS — impossible de savoir comment l'interpréter"
                )


def check(root: Path) -> ValidityReport:
    """Relit tout ce qui a été écrit et vérifie que rien n'est devenu illisible.

    Lecture seule. N'écrit rien, ne migre rien : constater qu'un enregistrement
    est illisible n'autorise pas à le réécrire.
    """
    root = Path(root)
    report = ValidityReport()

    _scan(root / "events.jsonl", report)
    _scan(root / "objects.jsonl", report)

    # Le décodage effectif : un enregistrement doit non seulement se parser,
    # mais se reconstruire en objet et vérifier son empreinte.
    for store, label in ((EventLedger(root), "ledger"), (ObjectStore(root), "magasin")):
        try:
            problems = store.verify()
        except Exception as exc:  # décodage impossible = perte de lisibilité
            report.violations.append(
                f"{label} : relecture impossible — {type(exc).__name__}: {exc}"
            )
            continue
        report.violations.extend(f"{label} : {p}" for p in problems)

    return report
