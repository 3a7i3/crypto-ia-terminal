"""
tools/protocol_efficacy_audit.py — le protocole mérite-t-il son propre coût ?

Le facteur limitant n'est plus la **conception** du protocole mais son
**épreuve**. Après six audits en dix jours, la question utile n'est plus « quelle
règle ajouter ? » mais :

> Quelles règles ont réellement trouvé des défauts, et lesquelles n'ont jamais
> rien produit d'autre que du travail ?

Cet outil ne juge pas la beauté d'une règle. Il additionne ce qu'elle a détecté,
ce qu'elle a coûté en faux positifs, et si elle a seulement eu l'occasion de se
déclencher.

**Il ne mesure qu'une valeur HISTORIQUE, jamais une valeur OPTIONNELLE.** Une
règle peut rester inactive très longtemps puis empêcher un incident majeur une
seule fois — c'est le cas classique du garde-fou de sûreté. La retirer parce
qu'elle n'a jamais servi confondrait « inutile » et « pas encore rencontré ».
D'où trois situations et non deux : `INACTIVE`, `EPROUVEE`, `ASSURANCE` (aucun
cas rencontré, mais conséquence d'une absence de protection assez grave pour
justifier le maintien — exceptionnelle, et exigeant une justification écrite).

**Ce registre est DESCRIPTIF, il n'est pas une cible.** Supprimer les règles peu
sollicitées ferait monter le pourcentage de « productives » sans améliorer d'un
iota la qualité des audits : mesurer l'activité et la lire comme de la valeur est
précisément la dérive que ce protocole reproche ailleurs aux indicateurs. Une
baisse du nombre de règles sans nouvelle détection est signalée comme un
**élagage suspect**, jamais comme un progrès.

Quatre verdicts, et un seul est positif
---------------------------------------
| Verdict            | Sens                                                     |
|--------------------|----------------------------------------------------------|
| `PRODUCTIVE`       | a détecté au moins un défaut réel, coût en FP acceptable |
| `COUTEUSE`         | autant ou plus de faux positifs que de détections        |
| `NON_DETECTRICE`   | liante, mais n'a jamais rien trouvé — effet d'expression |
| `JAMAIS_LIEE`      | n'a jamais eu l'occasion de se déclencher                |

`NON_DETECTRICE` n'est **pas** une condamnation : une règle peut agir en
plafonnant ce qu'un rapport a le droit d'affirmer (INV-COVERAGE-001) ou en
interdisant une classe de travail (INV-FRICTION-001). L'outil le distingue mais
ne tranche pas — c'est une décision d'opérateur.

Surface de garantie
-------------------
| ✓ Mesure | ✗ Ne mesure **pas** |
|---|---|
| ce qu'une règle a détecté, tel que consigné | si le registre est sincère ou complet |
| le coût en faux positifs consignés | les faux NÉGATIFS — non estimés à ce jour |
| l'effort ORDINAL et sa base déclarée | le temps réel passé, jamais chronométré |
| les décisions réellement changées | la valeur de ces décisions |
| si une règle a déjà eu l'occasion de mordre | si une règle non liée est inutile |
| l'éligibilité au retrait (3 conditions) | la valeur d'assurance d'un garde-fou |
| l'absence d'une règle au registre | si un compte a été gonflé par optimisme |

**Le trou principal est déclaré : les faux négatifs sont NON ESTIMÉS.** Un
défaut qu'aucune règle n'a cherché ne laisse aucune trace dans ce registre. Non
estimé n'est pas inobservable : plusieurs méthodes pourraient en borner le taux —
injections contrôlées de défauts connus, jeux de cas synthétiques, audits
indépendants ciblés, campagne adversariale. Une seule a produit quelque chose à
ce jour (12 défauts qu'aucune règle n'avait vus) ; aucune n'est instrumentée.
L'espace des méthodes reste **ouvert**, et le fermer prématurément serait la
faute que ce protocole cherche à empêcher.

**Dimension économique (INV-ROI-001).** Compter les détections ne suffit pas :
deux règles à deux détections ne se valent pas si l'une a évité une erreur
mineure et l'autre une décision qui aurait contaminé une campagne. Le registre
porte donc aussi `decisions_changed`, `effort` (ordinal, base mesurable
déclarée) et `severity_avoided`. Aucun ratio n'est calculé : diviser deux
ordinaux ne produit pas un nombre, seulement l'apparence d'un.

**Population consommée : aucune.** Cet outil lit le manifeste et le code, jamais
un dataset de trades. Verdicts **déterministes** : aucune inférence statistique,
unité d'échantillonnage sans objet.

Usage :
    python tools/protocol_efficacy_audit.py
    python tools/protocol_efficacy_audit.py --json
    python tools/protocol_efficacy_audit.py --strict   # exit 1 si le registre dérive
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from system.provenance import (  # noqa: E402
    CEILING_NONE,
    CeilingBreakdown,
    Coverage,
    weakest_ceiling,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / ".claude" / "manifest.yaml"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

VERDICT_PRODUCTIVE = "PRODUCTIVE"
VERDICT_COSTLY = "COUTEUSE"
VERDICT_NON_DETECTING = "NON_DETECTRICE"
VERDICT_NEVER_BOUND = "JAMAIS_LIEE"


#: Echelle ORDINALE d'effort, du moins cher au plus cher. Aucun temps n'a ete
#: chronometre : publier des heures serait inventer un chiffre. La BASE de chaque
#: classement est en revanche mesurable (outils construits, tests ecrits).
EFFORT_ORDER = ["NUL", "FAIBLE", "MOYEN", "ELEVE"]

#: Gravite de ce qui a ete EVITE, pas de ce qui a ete trouve. Deux regles a deux
#: detections ne se valent pas si l'une a evite une erreur mineure et l'autre une
#: decision qui aurait contamine une campagne entiere.
SEVERITY_ORDER = ["NULLE", "MINEURE", "MAJEURE", "CRITIQUE"]

#: CYCLE DE VIE — le registre mesure une valeur HISTORIQUE, jamais une valeur
#: OPTIONNELLE. Une règle peut rester inactive longtemps puis empêcher un
#: incident majeur une seule fois : c'est le cas classique du garde-fou de
#: sûreté. Trois situations, et non deux.
LIFECYCLE_INACTIVE = "INACTIVE"
LIFECYCLE_TESTED = "EPROUVEE"
LIFECYCLE_INSURANCE = "ASSURANCE"

#: `ASSURANCE` doit rester EXCEPTIONNELLE et porter une justification écrite :
#: sans cette exigence, toute règle inactive se déclarerait « assurance » et le
#: registre cesserait de trier quoi que ce soit.
LIFECYCLES = (LIFECYCLE_INACTIVE, LIFECYCLE_TESTED, LIFECYCLE_INSURANCE)

#: SOURCE DE LEGITIMITE — les trois statuts ne sont pas seulement statistiques,
#: ce sont des statuts de GOUVERNANCE : ils repondent a « pourquoi cette regle
#: existe-t-elle encore ? ». Deux formes de justification tres differentes ne
#: doivent pas etre confondues.
LEGITIMACY_OBSERVED = "OBSERVATION_REELLE"
LEGITIMACY_RISK = "ANALYSE_DE_RISQUE"
LEGITIMACY_NONE = "AUCUNE"

#: Correspondance EXIGEE. Une ASSURANCE dont la legitimite serait une observation
#: reelle est en fait une EPROUVEE ; une ASSURANCE sans analyse citable n'est
#: qu'une INACTIVE qui se protege.
LEGITIMACY_OF_LIFECYCLE = {
    LIFECYCLE_TESTED: LEGITIMACY_OBSERVED,
    LIFECYCLE_INSURANCE: LEGITIMACY_RISK,
    LIFECYCLE_INACTIVE: LEGITIMACY_NONE,
}

#: Justifications RECEVABLES d'un retrait. Une diminution du nombre de regles
#: n'est pas suspecte en soi : c'est le resultat ATTENDU d'une campagne arrivee a
#: maturite. Ce qui est suspect, c'est une diminution SANS justification observee.
REMOVAL_KINDS = (
    "FUSION",
    "GENERALISATION",
    "INVALIDATION_EXPERIMENTALE",
    "RISQUE_DISPARU",
)


@dataclass
class RuleEfficacy:
    id: str
    title: str
    detected: int
    false_positives: int
    prevented: int
    never_bound: bool
    verdict: str
    decisions_changed: int = 0
    effort: str = "?"
    severity_avoided: str = "NULLE"
    economics: str = ""
    lifecycle: str = LIFECYCLE_INACTIVE
    assurance_justification: str = ""
    legitimacy_source: str = LEGITIMACY_NONE
    legitimacy_basis: str = ""
    note: str = ""
    detections: list[str] = field(default_factory=list)

    @property
    def lifecycle_valid(self) -> bool:
        """Statut cohérent avec sa SOURCE DE LÉGITIMITÉ, et justifié si assurance.

        Trois statuts de gouvernance, trois sources distinctes : une observation
        réelle, une analyse de risque documentée, ou rien. Les confondre
        permettrait à une règle sans fondement de se déclarer garde-fou.
        """
        if self.lifecycle not in LIFECYCLES:
            return False
        attendu = LEGITIMACY_OF_LIFECYCLE.get(self.lifecycle)
        if self.legitimacy_source != attendu:
            return False
        if self.lifecycle == LIFECYCLE_INSURANCE:
            return bool(self.assurance_justification.strip()) and bool(
                self.legitimacy_basis.strip()
            )
        return True

    @property
    def retirement_eligible(self) -> bool:
        """Éligible au retrait — les TROIS conditions, jamais une seule.

        (1) aucun cas réel rencontré ; (2) aucune injection contrôlée ne montre
        qu'elle protège un scénario plausible ; (3) aucune analyse de risque ne
        justifie son maintien comme garde-fou.

        L'absence de déclenchement seule ne suffit JAMAIS — et naître d'une
        extrapolation n'est pas un argument contre une règle : c'est un argument
        pour l'éprouver. Les conditions (2) et (3) ne sont pas mesurables
        aujourd'hui : aucune injection n'a été tentée, aucune analyse de risque
        n'a été écrite. Cette propriété rend donc `False` pour toutes les règles,
        et c'est le résultat correct : personne n'est éligible tant que les deux
        épreuves manquantes n'ont pas eu lieu.
        """
        aucun_cas = self.lifecycle == LIFECYCLE_INACTIVE and self.detected == 0
        injection_tentee = False  # aucune méthode d'injection instrumentée
        analyse_de_risque = self.lifecycle == LIFECYCLE_INSURANCE
        return aucun_cas and injection_tentee and not analyse_de_risque

    @property
    def yield_reading(self) -> str:
        """Lecture ECONOMIQUE — INV-ROI-001. Jamais un score, toujours une phrase.

        Un ratio « detections / effort » serait un faux chiffre : l'effort est
        ordinal, la gravite aussi, et diviser deux ordinaux ne produit rien. On
        rend donc un classement en clair, dont chaque terme renvoie a une
        observation consignee.
        """
        cher = self.effort in ("ELEVE", "MOYEN")
        grave = self.severity_avoided in ("MAJEURE", "CRITIQUE")
        if self.decisions_changed > 0 and self.effort in ("NUL", "FAIBLE"):
            return "RENDEMENT ELEVE — cout faible, decision(s) changee(s)"
        if self.decisions_changed > 0:
            return "JUSTIFIEE — cout reel, mais a change une decision"
        if grave and cher:
            return "COUTEUSE MAIS COUVRANTE — rien change, gravite evitee elevee"
        if cher and self.detected == 0:
            return "A INSTRUIRE — cout engage, aucun resultat a ce jour"
        if cher and self.detected > 0:
            # Distinction qui manquait : une regle chere QUI TROUVE mais dont
            # rien n'a decoule n'est pas « a laisser courir ». Elle est en
            # attente de son premier effet.
            return "TROUVE SANS EFFET — cout reel, aucune decision changee"
        return "COUT FAIBLE — a laisser courir"


@dataclass
class AxisEfficacy:
    id: str
    binding: int
    passed: int
    failed: int
    discriminant: bool
    note: str = ""


@dataclass
class EfficacyReport:
    generated_at: str
    measured_at: str
    caveat: str
    effort_caveat: str
    severity_scale: str
    lifecycle_scale: str
    retirement_rule: str
    anti_optimisation: str
    pruning_alert: str
    rules: list[RuleEfficacy]
    axes: list[AxisEfficacy]
    unregistered_rules: list[str]
    totals: dict
    coverage: dict
    ceilings: dict
    confidence_ceiling: str


def _verdict(detected: int, false_positives: int, never_bound: bool) -> str:
    """Quatre cas, dans cet ordre — l'occasion de mordre passe avant le score.

    Une règle jamais liée n'est ni bonne ni mauvaise : elle n'a pas été mise à
    l'épreuve. La classer « non détectrice » lui reprocherait un silence dont
    elle n'est pas responsable.
    """
    if never_bound:
        return VERDICT_NEVER_BOUND
    if detected == 0:
        return VERDICT_NON_DETECTING
    if false_positives >= detected:
        return VERDICT_COSTLY
    return VERDICT_PRODUCTIVE


def _pruning_alert(ledger: dict, rules: list) -> str:
    """Détecteur d'ÉLAGAGE — garde-fou anti-Goodhart, version raffinée.

    **Une diminution n'est PAS suspecte en soi.** Elle est même le résultat
    ATTENDU d'une campagne empirique arrivée à maturité : le critère de sortie
    du gel prévoit explicitement que le protocole puisse être simplifié. Signaler
    « diminution = suspect » contredirait ce critère.

    Ce qui est suspect est une diminution **sans justification observée**. Quatre
    justifications sont recevables (`REMOVAL_KINDS`), chacune exigeant sa preuve.
    Un retrait déclaré avec une justification valide n'est pas une alerte : c'est
    la campagne qui fait son travail.
    """
    precedent = ledger.get("previous_measurement") or {}
    avant_ids = set(precedent.get("rule_ids") or [])
    if not avant_ids:
        return ""
    presentes = {r.id for r in rules}
    retirees = avant_ids - presentes
    if not retirees:
        return ""

    declares = {}
    for entry in ledger.get("removals") or []:
        if isinstance(entry, dict) and entry.get("id"):
            declares[entry["id"]] = entry

    injustifies = []
    for rid in sorted(retirees):
        entree = declares.get(rid)
        if entree is None:
            injustifies.append(f"{rid} (aucun retrait déclaré)")
        elif entree.get("kind") not in REMOVAL_KINDS:
            injustifies.append(f"{rid} (motif « {entree.get('kind')} » non recevable)")
        elif not str(entree.get("evidence") or "").strip():
            injustifies.append(f"{rid} (motif recevable, mais AUCUNE preuve citée)")

    if not injustifies:
        return ""
    return (
        f"ÉLAGAGE SUSPECT : {len(retirees)} règle(s) retirée(s), dont "
        f"{len(injustifies)} sans justification observée — "
        + " ; ".join(injustifies)
        + ". Le taux de règles productives monte mécaniquement ; la qualité des "
        "audits, elle, n'a pas bougé."
    )


def load_manifest(path: Path = MANIFEST) -> dict:
    """Lit le manifeste. Aucune analyse de prose : uniquement des champs typés."""
    import yaml

    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}


def build_report(manifest_path: Path = MANIFEST) -> EfficacyReport:
    data = load_manifest(manifest_path)
    ledger = data.get("protocol_efficacy") or {}
    declared = {r.get("id") for r in (data.get("invariants") or [])}

    rules: list[RuleEfficacy] = []
    for entry in ledger.get("rules") or []:
        detected = int(entry.get("detected") or 0)
        fp = int(entry.get("false_positives") or 0)
        never = bool(entry.get("never_bound"))
        rules.append(
            RuleEfficacy(
                id=entry.get("id", "?"),
                title=entry.get("title", ""),
                detected=detected,
                false_positives=fp,
                prevented=int(entry.get("prevented") or 0),
                never_bound=never,
                verdict=_verdict(detected, fp, never),
                decisions_changed=int(entry.get("decisions_changed") or 0),
                effort=str(entry.get("effort") or "?"),
                severity_avoided=str(entry.get("severity_avoided") or "NULLE"),
                economics=(entry.get("economics") or "").strip(),
                lifecycle=str(entry.get("lifecycle") or LIFECYCLE_INACTIVE),
                assurance_justification=(
                    entry.get("assurance_justification") or ""
                ).strip(),
                legitimacy_source=str(
                    entry.get("legitimacy_source") or LEGITIMACY_NONE
                ),
                legitimacy_basis=(entry.get("legitimacy_basis") or "").strip(),
                note=(entry.get("note") or "").strip(),
                detections=list(entry.get("detections") or []),
            )
        )

    axes: list[AxisEfficacy] = []
    for entry in ledger.get("axes") or []:
        binding = int(entry.get("binding") or 0)
        failed = int(entry.get("fail") or 0)
        axes.append(
            AxisEfficacy(
                id=entry.get("id", "?"),
                binding=binding,
                passed=int(entry.get("pass") or 0),
                failed=failed,
                # Un critère qui ne rend jamais FAIL ne sépare rien : il ne
                # distingue pas un dépôt sain d'un critère qui ne mord pas.
                discriminant=failed > 0,
                note=(entry.get("note") or "").strip(),
            )
        )

    # Dérive du registre : une règle déclarée invariant mais absente du registre
    # échappe à toute mesure d'efficacité — et c'est exactement ainsi qu'un
    # protocole grossit sans qu'on sache ce qui sert.
    inscrites = {r.id for r in rules}
    manquantes = sorted(declared - inscrites)

    totals = {
        "rules": len(rules),
        LIFECYCLE_INACTIVE: sum(1 for r in rules if r.lifecycle == LIFECYCLE_INACTIVE),
        LIFECYCLE_TESTED: sum(1 for r in rules if r.lifecycle == LIFECYCLE_TESTED),
        LIFECYCLE_INSURANCE: sum(
            1 for r in rules if r.lifecycle == LIFECYCLE_INSURANCE
        ),
        "lifecycle_invalid": sum(1 for r in rules if not r.lifecycle_valid),
        "retirement_eligible": sum(1 for r in rules if r.retirement_eligible),
        "detections": sum(r.detected for r in rules),
        "decisions_changed": sum(r.decisions_changed for r in rules),
        "rules_changing_a_decision": sum(1 for r in rules if r.decisions_changed),
        "costly_without_result": sum(
            1
            for r in rules
            if r.effort in ("MOYEN", "ELEVE")
            and r.detected == 0
            and r.decisions_changed == 0
        ),
        "false_positives": sum(r.false_positives for r in rules),
        "prevented": sum(r.prevented for r in rules),
        VERDICT_PRODUCTIVE: sum(1 for r in rules if r.verdict == VERDICT_PRODUCTIVE),
        VERDICT_COSTLY: sum(1 for r in rules if r.verdict == VERDICT_COSTLY),
        VERDICT_NON_DETECTING: sum(
            1 for r in rules if r.verdict == VERDICT_NON_DETECTING
        ),
        VERDICT_NEVER_BOUND: sum(1 for r in rules if r.verdict == VERDICT_NEVER_BOUND),
        "axes_discriminants": sum(1 for a in axes if a.discriminant),
        "axes": len(axes),
    }

    couverture = Coverage(
        measured=len(rules),
        total=len(declared) if declared else len(rules),
        subject="regles inscrites au registre d'efficacite",
    )
    epreuve = Coverage(
        measured=sum(1 for r in rules if not r.never_bound),
        total=len(rules) if rules else 0,
        subject="regles ayant eu l'occasion de mordre",
    )
    breakdown = CeilingBreakdown(
        coverage_ceiling=couverture.confidence_ceiling,
        adoption_ceiling=epreuve.confidence_ceiling,
        weakest_link_ceiling=CEILING_NONE if manquantes else epreuve.confidence_ceiling,
    )

    return EfficacyReport(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        measured_at=str(ledger.get("measured_at") or "inconnu"),
        caveat=(ledger.get("caveat") or "").strip(),
        effort_caveat=(ledger.get("effort_caveat") or "").strip(),
        severity_scale=(ledger.get("severity_scale") or "").strip(),
        lifecycle_scale=(ledger.get("lifecycle_scale") or "").strip(),
        retirement_rule=(ledger.get("retirement_rule") or "").strip(),
        anti_optimisation=(ledger.get("anti_optimisation") or "").strip(),
        pruning_alert=_pruning_alert(ledger, rules),
        rules=rules,
        axes=axes,
        unregistered_rules=manquantes,
        totals=totals,
        coverage=couverture.to_dict(),
        ceilings=breakdown.to_dict(),
        confidence_ceiling=weakest_ceiling(
            [breakdown.final, epreuve.confidence_ceiling]
        ),
    )


def render_text(report: EfficacyReport) -> str:
    lines: list[str] = []
    add = lines.append
    add("=" * 78)
    add("  PROTOCOL EFFICACY AUDIT — quelles règles ont réellement trouvé ?")
    add("=" * 78)
    add(f"  Généré  : {report.generated_at}")
    add(f"  Registre: {report.measured_at}")
    add("")
    if report.caveat:
        for ligne in report.caveat.splitlines():
            add(f"  ⚠ {ligne.strip()}")
        add("")

    add("-" * 78)
    add("  RÈGLES")
    add("-" * 78)
    add("    règle                 détect.  déc.  effort  gravité   cycle      verdict")
    for rule in sorted(
        report.rules, key=lambda r: (-r.decisions_changed, -r.detected, r.id)
    ):
        add(
            f"    {rule.id:<20} {rule.detected:>6}  {rule.decisions_changed:>4}"
            f"  {rule.effort:<6}  {rule.severity_avoided:<8}  "
            f"{rule.lifecycle:<9}  {rule.verdict}"
        )
    add("")
    if report.effort_caveat:
        for phrase in report.effort_caveat.split(". "):
            if phrase.strip():
                add("    " + " ".join(phrase.split())[:200])
        add("")

    add("-" * 78)
    add("  SYNTHÈSE")
    add("-" * 78)
    t = report.totals
    add(f"    détections réelles          {t['detections']}")
    add(
        f"    DÉCISIONS changées          {t['decisions_changed']}"
        f"  (par {t['rules_changing_a_decision']} règles)"
    )
    add(f"    coûteuses sans résultat     {t['costly_without_result']}")
    add("")
    add(f"    ÉPROUVÉES (≥ 1 cas réel)    {t[LIFECYCLE_TESTED]}")
    add(f"    ASSURANCE (justifiée)       {t[LIFECYCLE_INSURANCE]}")
    add(f"    INACTIVES                   {t[LIFECYCLE_INACTIVE]}")
    add(f"    éligibles au RETRAIT        {t['retirement_eligible']}")
    if t["lifecycle_invalid"]:
        add(f"    ⚠ ASSURANCE sans justification : {t['lifecycle_invalid']}")
    add(f"    faux positifs consignés     {t['false_positives']}")
    add(f"    familles de FP empêchées    {t['prevented']}")
    add("")
    add(f"    PRODUCTIVE                  {t[VERDICT_PRODUCTIVE]}")
    add(f"    COUTEUSE                    {t[VERDICT_COSTLY]}")
    add(f"    NON_DETECTRICE              {t[VERDICT_NON_DETECTING]}")
    add(f"    JAMAIS_LIEE                 {t[VERDICT_NEVER_BOUND]}")
    add("")

    add("-" * 78)
    add("  AXES — un critère qui ne rend jamais FAIL ne sépare rien")
    add("-" * 78)
    add("    axe                         liants  ok  FAIL  discriminant")
    for axis in report.axes:
        marque = "oui" if axis.discriminant else "NON"
        add(
            f"    {axis.id:<26} {axis.binding:>6} {axis.passed:>3} {axis.failed:>5}"
            f"   {marque}"
        )
    add("")

    if report.pruning_alert:
        add("-" * 78)
        add("  ⚠ " + report.pruning_alert)
        add("-" * 78)
        add("")

    add("-" * 78)
    add("  CYCLE DE VIE — valeur historique ≠ valeur optionnelle")
    add("-" * 78)
    add("    Une règle peut rester inactive longtemps puis empêcher un incident")
    add("    majeur une seule fois. Retirer un garde-fou parce qu'il n'a jamais")
    add("    servi confond « inutile » et « pas encore rencontré ».")
    add("")
    for rule in report.rules:
        if rule.lifecycle == LIFECYCLE_TESTED:
            continue
        add(f"    [{rule.lifecycle}] {rule.id}  ← {rule.legitimacy_source}")
        if rule.legitimacy_basis:
            add("        base : " + " ".join(rule.legitimacy_basis.split())[:150])
        if rule.assurance_justification:
            add("        " + " ".join(rule.assurance_justification.split())[:150])
    add("")
    if report.retirement_rule:
        add("    RETRAIT — les TROIS conditions, jamais une seule :")
        for phrase in report.retirement_rule.split(";"):
            if phrase.strip():
                add("      " + " ".join(phrase.split())[:170])
        add("")

    add("-" * 78)
    add("  LECTURE ÉCONOMIQUE — INV-ROI-001")
    add("-" * 78)
    add("    Deux règles à deux détections ne se valent pas : ce qui compte est")
    add("    ce qu'elles ont COÛTÉ et ce qu'elles ont ÉVITÉ.")
    add("")
    for rule in sorted(
        report.rules,
        key=lambda r: (
            -r.decisions_changed,
            -(
                SEVERITY_ORDER.index(r.severity_avoided)
                if r.severity_avoided in SEVERITY_ORDER
                else 0
            ),
        ),
    ):
        if rule.effort == "NUL" and rule.decisions_changed == 0:
            continue
        add(f"    {rule.id:<20} {rule.yield_reading}")
        if rule.economics:
            add("        " + " ".join(rule.economics.split())[:160])
    add("")

    candidats = [r for r in report.rules if r.verdict != VERDICT_PRODUCTIVE]
    if candidats:
        add("-" * 78)
        add("  À INSTRUIRE — ni condamnation, ni acquittement")
        add("-" * 78)
        for rule in candidats:
            add(f"    [{rule.verdict}] {rule.id} — {rule.title}")
            if rule.note:
                add(f"        {rule.note.splitlines()[0]}")
        add("")

    if report.unregistered_rules:
        add("-" * 78)
        add("  RÈGLES DÉCLARÉES MAIS ABSENTES DU REGISTRE")
        add("-" * 78)
        for rid in report.unregistered_rules:
            add(f"    {rid}")
        add("    → leur efficacité n'est mesurée par personne.")
        add("")

    add("-" * 78)
    add("  PLAFONDS")
    add("-" * 78)
    cov = report.coverage
    add(
        f"    règles inscrites            {cov['measured']}/{cov['total']}"
        f" ({cov['ratio']:.0%})"
    )
    add(f"    plafond de COUVERTURE       {report.ceilings['coverage_ceiling']}")
    add(f"    plafond d'ÉPREUVE           {report.ceilings['adoption_ceiling']}")
    add(f"    PLAFOND FINAL               {report.confidence_ceiling}")
    add(f"    → {report.ceilings['binding_reason']}")
    add("")
    if report.anti_optimisation:
        add("    GARDE-FOU ANTI-OPTIMISATION :")
        for phrase in report.anti_optimisation.split(". "):
            if phrase.strip():
                add("      " + " ".join(phrase.split())[:180])
        add("")
    add("    Ce que ce rapport ne mesure pas : les faux NÉGATIFS. Un défaut")
    add("    qu'aucune règle n'a cherché ne laisse aucune trace ici. Ils sont")
    add("    NON ESTIMÉS — pas inobservables. Plusieurs méthodes pourraient en")
    add("    borner le taux : injections contrôlées, jeux de cas synthétiques,")
    add("    audits indépendants ciblés, campagne adversariale. Aucune n'est")
    add("    instrumentée à ce jour ; l'espace des méthodes reste ouvert.")
    add("=" * 78)
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Efficacité mesurée du protocole (outil de mesure passif)"
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 si une règle déclarée est absente du registre",
    )
    args = parser.parse_args(argv)

    report = build_report()
    if args.json:
        print(json.dumps(asdict(report), indent=2, default=str, ensure_ascii=False))
    else:
        print(render_text(report))

    if args.strict and report.unregistered_rules:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
