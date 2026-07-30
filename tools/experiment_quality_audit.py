"""
tools/experiment_quality_audit.py — auditer les EXPÉRIENCES, pas le moteur.

Les deux incidents les plus coûteux de la campagne (AUDIT-EMP-001 et -002)
n'étaient pas des erreurs d'algorithme. C'étaient des erreurs de **méthodologie
de mesure** : une population non déclarée, une formule anonyme, une puissance
jamais publiée, une hypothèse d'indépendance jamais énoncée. Aucun test unitaire
ne pouvait les voir, parce qu'aucun code n'était faux.

Cet outil audite les **instruments de mesure** du dépôt selon quatre critères,
chacun issu d'un incident CONSTATÉ — jamais d'un principe général :

| Critère        | Question                              | Incident d'origine  |
|----------------|---------------------------------------|---------------------|
| POPULATION     | population issue du loader canonique ? | AUDIT-EMP-001      |
| POWER          | effet minimal détectable publié ?      | AUDIT-EMP-002      |
| TRANSFORMATION | artefact daté et situé ?               | AUDIT-EMP-001 gate D |
| INDEPENDENCE   | unité d'échantillonnage déclarée ?     | AUDIT-EMP-002 O6   |

Surface de garantie — À LIRE AVANT D'UTILISER LE VERDICT
--------------------------------------------------------
Ce que cet outil détecte : l'**absence de déclaration explicite**. Il cherche
une trace textuelle qu'une question a été posée dans le code.

| ✓ Détecte | ✗ Ne détecte **pas** |
|---|---|
| un instrument sans loader canonique | que le loader canonique soit *le bon* |
| un verdict sans mention de puissance | qu'une puissance soit *bien calculée* |
| un artefact sans marqueur de population | qu'un marqueur présent soit *exact* |
| une dispersion sans unité déclarée | qu'une unité déclarée soit *la bonne* |
| un lecteur du dataset hors registre | qu'un rôle déclaré soit *sincère* |

Limite mesurée sur cet outil lui-même (2026-07-29) : les motifs ignorent la
**polarité**. `tools/init_order_audit.py` a d'abord échoué au critère
INDEPENDENCE parce qu'il contenait la phrase « aucun intervalle de confiance
n'aurait de sens ici » — une négation, comptée comme une statistique de
dispersion. Un faux positif de ce type se lève en **déclarant** explicitement
l'unité d'échantillonnage, ce qui est le comportement souhaité ; mais la limite
est réelle et doit être connue : ces motifs détectent des mots, pas des
intentions.

Seconde limite de la même famille (2026-07-29) : les motifs ne distinguent pas
la **mention** de l'**usage**. `tools/chain_audit.py` nomme
`databases/paper_trades.jsonl` dans la déclaration d'une chaîne sans jamais
l'ouvrir ; le critère POPULATION l'accusait de lire le journal hors loader
canonique. Là encore la levée passe par une déclaration explicite
(« Population consommée : aucune »), et là encore une déclaration vérifiée par
mot-clé reste contournable par quiconque connaît le mot.

Autrement dit : il transforme une hypothèse implicite en **précondition
explicite**, et rien de plus. Un instrument qui déclare tout et se trompe
partout passe cet audit. C'est assumé — l'alternative serait de prétendre
vérifier la vérité d'un énoncé, ce que seul un humain fait ici.

Le registre est délibérément EXPLICITE : ajouter un instrument exige de déclarer
son rôle. Un fichier qui lit le dataset sans figurer au registre est signalé
comme `NON_DECLARE` — le registre ne peut donc pas devenir silencieusement
obsolète.

Usage :
    python tools/experiment_quality_audit.py
    python tools/experiment_quality_audit.py --json
    python tools/experiment_quality_audit.py --strict   # exit 1 si un critère échoue
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from system.provenance import (  # noqa: E402
    CEILING_FULL,
    CEILING_LOW,
    CEILING_MEDIUM,
    CEILING_NONE,
    Coverage,
    weakest_ceiling,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Rôles ─────────────────────────────────────────────────────────────────────

ROLE_INSTRUMENT = "INSTRUMENT"  # émet une conclusion statistique
ROLE_LOADER = "LOADER"  # accès canonique à une population
ROLE_PRODUCTEUR = "PRODUCTEUR"  # écrit le dataset
ROLE_MOTEUR = "MOTEUR"  # décide (seul autorisé à décider, ADR-0007)
ROLE_AFFICHAGE = "AFFICHAGE"  # restitue sans conclure
ROLE_COLLECTEUR = "COLLECTEUR"  # transporte / archive

#: Seuls les INSTRUMENT sont soumis aux quatre critères. Les autres rôles sont
#: déclarés pour que le détecteur de dérive ne les signale pas — et pour que la
#: frontière observation / décision (ADR-0007) reste écrite quelque part.
REGISTRY: dict[str, tuple[str, str]] = {
    # --- instruments : émettent une conclusion sur le système de trading ---
    "scripts/burnin_calibration_v3.py": (ROLE_INSTRUMENT, "verdict GO/DEGRADED/NO_GO"),
    "scripts/prelive_gate.py": (ROLE_INSTRUMENT, "6 gates, verdict GO/NO-GO"),
    "tools/cri_calculator.py": (
        ROLE_INSTRUMENT,
        "CRI + loader canonique (double rôle)",
    ),
    "tools/score_calibration_audit.py": (
        ROLE_INSTRUMENT,
        "pouvoir de classement du score",
    ),
    "tools/exit_audit.py": (ROLE_INSTRUMENT, "hypothèse H-exit, capture ratio"),
    "tools/exit_replay.py": (ROLE_INSTRUMENT, "rejeu du chemin depuis le pouls"),
    "scripts/data_quality.py": (
        ROLE_INSTRUMENT,
        "qualité des données + borne d'époque",
    ),
    "scripts/regret_audit.py": (ROLE_INSTRUMENT, "décomposition causale du regret"),
    "scripts/audit_r2.py": (ROLE_INSTRUMENT, "diagnostic quantitatif du burn-in"),
    "scripts/bear_trend_audit.py": (ROLE_INSTRUMENT, "H0 vs H1 sur bear_trend"),
    "scripts/burnin_v2_report.py": (
        ROLE_INSTRUMENT,
        "rapport burn-in v2 (époque morte)",
    ),
    "scripts/counterfactual_replay.py": (ROLE_INSTRUMENT, "replay sous max_positions"),
    "scripts/validate_trade_dataset.py": (ROLE_INSTRUMENT, "certification du corpus"),
    "paper_trading/dataset_validator.py": (ROLE_INSTRUMENT, "invariants du corpus"),
    "scripts/toxicity_report.py": (ROLE_INSTRUMENT, "toxicité de l'univers perp"),
    "scripts/shadow_execution.py": (ROLE_INSTRUMENT, "trades refusés par la gate"),
    # --- autres rôles ---
    "system/performance_metrics.py": (
        ROLE_LOADER,
        "bibliothèque de formules, INV-METRIC-001",
    ),
    "tools/regret_repository.py": (ROLE_LOADER, "accès canonique regret (MC-001)"),
    "paper_trading/mexc_simulator.py": (
        ROLE_PRODUCTEUR,
        "écrivain de paper_trades (INV-3)",
    ),
    "paper_trading/recorder.py": (ROLE_PRODUCTEUR, "écrivain de paper_trades (INV-3)"),
    "core/advisor_loop.py": (ROLE_MOTEUR, "seul composant qui décide (ADR-0007)"),
    "observability/regret_scheduler.py": (
        ROLE_COLLECTEUR,
        "évaluation asynchrone des horizons",
    ),
    "observability/rejection_store.py": (ROLE_COLLECTEUR, "journal des rejets"),
    "scripts/vps_burn_in_collector.py": (ROLE_COLLECTEUR, "transport VPS"),
    "scripts/dashboard.py": (ROLE_AFFICHAGE, "restitution"),
    "scripts/test_intel_report.py": (ROLE_AFFICHAGE, "restitution Telegram"),
    "scripts/runtime_validator.py": (ROLE_AFFICHAGE, "état système instantané"),
    "scripts/preflight.py": (ROLE_AFFICHAGE, "contrôle de démarrage"),
    "infra/wallet_sync.py": (ROLE_LOADER, "base de capital (ADR-0007)"),
    "tools/throughput_probe.py": (ROLE_INSTRUMENT, "débit du pipeline"),
    "tools/experiment_quality_audit.py": (
        ROLE_INSTRUMENT,
        "cet outil — audité par lui-même",
    ),
    "tools/init_order_audit.py": (
        ROLE_INSTRUMENT,
        "INIT-ORDER, verdicts déterministes",
    ),
    "tools/chain_audit.py": (
        ROLE_INSTRUMENT,
        "chaîne artefact → décision, verdicts déterministes",
    ),
    "system/provenance.py": (
        ROLE_LOADER,
        "preuve de transformation + couverture normative",
    ),
}

#: Répertoires balayés par le détecteur de dérive.
SCAN_DIRS = [
    "scripts",
    "tools",
    "system",
    "paper_trading",
    "core",
    "infra",
    "observability",
]

# ── Motifs — chacun cherche une DÉCLARATION, pas une correction ───────────────

_RE_CONCLUSION = re.compile(
    r"NO_GO|NO-GO|DEGRADED|verdict|VERDICT|significat|est_significa|"
    r"STATUS_GO|STATUS_NOGO|blockers|PASS\b|FAIL\b",
)
_RE_DISPERSION = re.compile(
    r"\bstdev\b|\bpstdev\b|\bstd\b|variance|sharpe|Sharpe|spearman|pearson|"
    r"p_value|t_statistic|\bt_stat|correl|z_score|confidence|intervalle",
)
#: Deux façons de satisfaire POPULATION : passer par un chemin canonique, OU
#: déclarer explicitement qu'aucune population de trades n'est consommée. La
#: seconde existe parce que les motifs ne distinguent pas la MENTION de l'USAGE :
#: `tools/chain_audit.py` nomme `databases/paper_trades.jsonl` dans la
#: déclaration d'une chaîne sans jamais l'ouvrir. Troisième faux positif de la
#: même famille après la polarité — voir la limite documentée plus haut.
_RE_POPULATION_OK = re.compile(
    r"load_clean_trades|trades_provenance|RegretRepository|regret_repository|"
    r"CLEAN_DATA_SINCE|Population consommée : aucune",
)
_RE_POPULATION_BAD = re.compile(
    r"paper_trades\.jsonl|PAPER_TRADE_LOG",
)
#: Effet minimal DÉTECTABLE — la seule chose qui réponde à « aurais-je pu voir
#: cet effet ? ». Un seuil de volume n'y répond pas : N=500 ne dit rien de la
#: taille d'effet visible si la variance est grande ou le domaine écrasé.
#: Deux façons de satisfaire le critère : publier un effet minimal détectable,
#: OU déclarer que le verdict est déterministe (aucune inférence, donc aucune
#: puissance à publier). La seconde n'est pas une échappatoire : elle est
#: falsifiable — un verdict déclaré déterministe qui repose en fait sur un
#: échantillon est une fausse déclaration, visible en relisant l'outil.
_RE_POWER_OK = re.compile(
    r"min_detectable|MIN_DETECTABLE|puissance|POWER\b|power\b|resolution|"
    r"_Z_POWER|effect_size|taille d'effet|MDE\b|déterministe|deterministe|"
    r"aucune inférence statistique",
)

#: Exigence de VOLUME. Souvent confondue avec la puissance — d'où un motif
#: séparé, et un message de défaillance qui nomme explicitement la confusion.
_RE_SAMPLE_SIZE = re.compile(
    r"N_TARGET|BURNIN_N|_BURNIN_N|min_n_required|MIN_N|n_required|MIN_CELL|"
    r"MIN_PSI_SAMPLE|min_trades|N >= |n >= ",
)
#: Artefact = contenu PERSISTÉ, susceptible d'être relu plus tard par un autre
#: outil. Écrire du JSON sur la sortie standard n'en est pas un : personne ne
#: peut le consommer six jours plus tard en croyant qu'il est frais, ce qui est
#: exactement le défaut de la gate D que ce critère cherche.
#:
#: FAUX POSITIF CORRIGÉ (2026-07-29) : le motif `json\.dump` sans parenthèse
#: capturait aussi `json.dumps(...)`. Trois instruments sur quatre signalés en
#: TRANSFORMATION n'écrivaient rien — ils imprimaient. Le critère accusait à
#: tort, et la famille "à traiter en priorité" était surévaluée de 300 %.
_RE_ARTIFACT = re.compile(
    r"json\.dump\(|write_text\(|\.to_json\(|\.to_csv\(|csv\.writer|"
    r"open\([^)]*['\"][wa]",
)
_RE_ARTIFACT_STAMP = re.compile(
    r"generated_at|generated|clean_data_since|provenance|n_canonical|"
    r"schema_version|measured_at",
)
#: Insensible à la casse : ces déclarations sont des phrases de documentation
#: française, et « Unité d'échantillonnage » en début de ligne est la même
#: déclaration que « unité d'échantillonnage » au fil du texte. La casse a
#: silencieusement produit un faux positif lors de la première exécution.
_RE_SAMPLING_UNIT = re.compile(
    r"sampling_unit|unité d'échantillonnage|par trade|per_trade|per-trade|"
    r"blocs de jours|block_ci|block_iterations|independan|indépendan|"
    r"observations recouvrantes|N effectif|n_effectif",
    re.IGNORECASE,
)

CRITERIA = ["POPULATION", "POWER", "TRANSFORMATION", "INDEPENDENCE"]

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_NA = "N/A"

#: Statut PROPAGÉ : le critère n'a pas été évalué sur ses propres mérites, il est
#: invalidé par l'échec d'un critère amont. Distinct de FAIL (l'instrument a
#: manqué quelque chose) et de N/A (la question ne se pose pas).
STATUS_INVALID = "INVALIDE"

#: Propagation du maillon faible ENTRE critères (§ 3 du protocole, généralisé aux
#: audits eux-mêmes). Les quatre familles ne sont pas indépendantes : une
#: puissance calculée sur une population contaminée n'est pas « correcte », elle
#: est sans objet. Une transformation exacte appliquée à une donnée invalide
#: produit un résultat invalide avec une traçabilité impeccable.
#:
#: POPULATION est la seule racine : c'est la seule dimension dont l'échec prive
#: les autres de leur référent. Un artefact non horodaté (TRANSFORMATION=FAIL)
#: n'invalide pas la puissance de l'analyse qui l'a produit ; il invalide ce que
#: son CONSOMMATEUR en fera — et cela relève de l'audit de chaîne, pas d'ici.
PROPAGATION = {"POPULATION": ["POWER", "TRANSFORMATION", "INDEPENDENCE"]}


# ── Structures ────────────────────────────────────────────────────────────────


@dataclass
class Check:
    criterion: str
    status: str
    binds_because: str = ""
    evidence: list[str] = field(default_factory=list)


@dataclass
class InstrumentReport:
    path: str
    role: str
    note: str
    exists: bool
    lines: int
    checks: list[Check] = field(default_factory=list)

    @property
    def failures(self) -> list[str]:
        return [c.criterion for c in self.checks if c.status == STATUS_FAIL]

    @property
    def invalidated(self) -> list[str]:
        return [c.criterion for c in self.checks if c.status == STATUS_INVALID]

    @property
    def confidence_ceiling(self) -> str:
        """Plafond de confiance de CET instrument, mécaniquement.

        Un critère invalidé par propagation plafonne plus bas qu'un simple
        échec : dans le premier cas on ne sait même pas ce qu'on mesurait.
        """
        if self.role != ROLE_INSTRUMENT:
            return CEILING_FULL
        if self.invalidated:
            return CEILING_NONE
        if self.failures:
            return CEILING_LOW
        binding = [c for c in self.checks if c.status != STATUS_NA]
        if not binding:
            return CEILING_MEDIUM
        return CEILING_FULL


@dataclass
class QualityReport:
    generated_at: str
    n_registered: int
    n_instruments: int
    instruments: list[InstrumentReport]
    undeclared_readers: list[str]
    missing_from_disk: list[str]
    totals: dict = field(default_factory=dict)
    coverage: dict = field(default_factory=dict)
    confidence_ceiling: str = CEILING_NONE


# ── Inspection ────────────────────────────────────────────────────────────────


def _matches(pattern: re.Pattern, source: str, *, limit: int = 3) -> list[str]:
    """Lignes correspondantes, format `numéro: extrait` — la preuve est citable."""
    out: list[str] = []
    for i, line in enumerate(source.splitlines(), start=1):
        if pattern.search(line):
            out.append(f"{i}: {line.strip()[:88]}")
            if len(out) >= limit:
                break
    return out


def audit_source(path: str, role: str, note: str, source: str) -> InstrumentReport:
    """Applique les quatre critères. Un critère qui ne LIE PAS rend `N/A`.

    Le statut `N/A` est un résultat, pas une absence de résultat : il dit que la
    question ne se pose pas pour cet instrument, et pourquoi.
    """
    report = InstrumentReport(
        path=path,
        role=role,
        note=note,
        exists=True,
        lines=len(source.splitlines()),
    )
    if role != ROLE_INSTRUMENT:
        return report

    # --- POPULATION : lit-il une population de trades, et via quoi ? ---
    reads_dataset = bool(_RE_POPULATION_BAD.search(source)) or bool(
        _RE_POPULATION_OK.search(source)
    )
    if not reads_dataset:
        report.checks.append(
            Check(
                "POPULATION",
                STATUS_NA,
                "n'accède à aucune population de trades ou de regret",
            )
        )
    elif _RE_POPULATION_OK.search(source):
        report.checks.append(
            Check(
                "POPULATION",
                STATUS_PASS,
                "accède à la population par un chemin canonique",
                _matches(_RE_POPULATION_OK, source),
            )
        )
    else:
        report.checks.append(
            Check(
                "POPULATION",
                STATUS_FAIL,
                "lit le journal directement, sans loader canonique (INV-DATASET-001)",
                _matches(_RE_POPULATION_BAD, source),
            )
        )

    # --- POWER : émet-il une conclusion, et publie-t-il sa résolution ? ---
    conclusion = _matches(_RE_CONCLUSION, source, limit=2)
    if not conclusion:
        report.checks.append(
            Check("POWER", STATUS_NA, "n'émet aucun verdict ni test de significativité")
        )
    elif _RE_POWER_OK.search(source):
        report.checks.append(
            Check(
                "POWER",
                STATUS_PASS,
                "publie un effet minimal détectable",
                _matches(_RE_POWER_OK, source),
            )
        )
    elif _RE_SAMPLE_SIZE.search(source):
        report.checks.append(
            Check(
                "POWER",
                STATUS_FAIL,
                "publie une exigence de VOLUME mais aucun effet minimal détectable "
                "— un seuil de N n'est pas une puissance (INV-POWER-001)",
                _matches(_RE_SAMPLE_SIZE, source) + conclusion,
            )
        )
    else:
        report.checks.append(
            Check(
                "POWER",
                STATUS_FAIL,
                "conclut sans publier ce qu'il pourrait détecter (INV-POWER-001)",
                conclusion,
            )
        )

    # --- TRANSFORMATION : l'artefact produit est-il daté et situé ? ---
    artifact = _matches(_RE_ARTIFACT, source, limit=2)
    if not artifact:
        report.checks.append(
            Check("TRANSFORMATION", STATUS_NA, "n'écrit aucun artefact consommable")
        )
    elif _RE_ARTIFACT_STAMP.search(source):
        report.checks.append(
            Check(
                "TRANSFORMATION",
                STATUS_PASS,
                "l'artefact porte une date et/ou un marqueur de population",
                _matches(_RE_ARTIFACT_STAMP, source),
            )
        )
    else:
        report.checks.append(
            Check(
                "TRANSFORMATION",
                STATUS_FAIL,
                "écrit un artefact sans date ni population — un consommateur ne "
                "peut pas savoir ce qu'il lit (cf. gate D, rapport de 559.8 h)",
                artifact,
            )
        )

    # --- INDEPENDENCE : statistique de dispersion sans unité déclarée ? ---
    dispersion = _matches(_RE_DISPERSION, source, limit=2)
    if not dispersion:
        report.checks.append(
            Check("INDEPENDENCE", STATUS_NA, "aucune statistique de dispersion")
        )
    elif _RE_SAMPLING_UNIT.search(source):
        report.checks.append(
            Check(
                "INDEPENDENCE",
                STATUS_PASS,
                "déclare son unité d'échantillonnage",
                _matches(_RE_SAMPLING_UNIT, source),
            )
        )
    else:
        report.checks.append(
            Check(
                "INDEPENDENCE",
                STATUS_FAIL,
                "statistique de dispersion sans unité d'échantillonnage déclarée",
                dispersion,
            )
        )
    return _propagate(report)


def _propagate(report: InstrumentReport) -> InstrumentReport:
    """Applique le maillon faible ENTRE critères — POPULATION contamine l'aval.

    Un rapport qui affiche `POPULATION: FAIL` et `POWER: ok` laisse croire que le
    test de puissance renseigne sur quelque chose. Il renseigne sur une
    population dont on vient de dire qu'elle n'est pas la bonne. Le statut devient
    `INVALIDE` : ni réussi, ni raté — sans objet.

    La propagation ne DÉTRUIT jamais le constat d'origine : `evidence` et
    `binds_because` du critère aval sont conservés, préfixés de la raison de
    l'invalidation. Rétracter n'est pas nier (§ 2 du protocole).
    """
    by_criterion = {c.criterion: c for c in report.checks}
    for root_criterion, downstream in PROPAGATION.items():
        root_check = by_criterion.get(root_criterion)
        if root_check is None or root_check.status != STATUS_FAIL:
            continue
        for name in downstream:
            check = by_criterion.get(name)
            if check is None or check.status == STATUS_NA:
                continue
            check.binds_because = (
                f"INVALIDE par propagation depuis {root_criterion}=FAIL — "
                f"constat initial conservé : {check.binds_because}"
            )
            check.status = STATUS_INVALID
    return report


def find_undeclared_readers(root: Path = REPO_ROOT) -> list[str]:
    """Fichiers qui accèdent au dataset sans figurer au registre.

    Empêche le registre de devenir un inventaire mort : tout nouvel accès au
    dataset doit être classé, ne serait-ce que comme AFFICHAGE.
    """
    out: list[str] = []
    for folder in SCAN_DIRS:
        base = root / folder
        if not base.exists():
            continue
        for f in sorted(base.rglob("*.py")):
            rel = f.relative_to(root).as_posix()
            if rel in REGISTRY or "test" in f.name:
                continue
            try:
                source = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if _RE_POPULATION_OK.search(source) or _RE_POPULATION_BAD.search(source):
                out.append(rel)
    return out


def build_report(root: Path = REPO_ROOT) -> QualityReport:
    instruments: list[InstrumentReport] = []
    missing: list[str] = []
    for rel, (role, note) in sorted(REGISTRY.items()):
        path = root / rel
        if not path.exists():
            missing.append(rel)
            instruments.append(
                InstrumentReport(path=rel, role=role, note=note, exists=False, lines=0)
            )
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        instruments.append(audit_source(rel, role, note, source))

    only_instruments = [i for i in instruments if i.role == ROLE_INSTRUMENT]
    totals: dict[str, dict[str, int]] = {}
    for criterion in CRITERIA:
        counts = {
            STATUS_PASS: 0,
            STATUS_FAIL: 0,
            STATUS_NA: 0,
            STATUS_INVALID: 0,
        }
        for inst in only_instruments:
            for check in inst.checks:
                if check.criterion == criterion:
                    counts[check.status] += 1
        totals[criterion] = counts

    # Couverture normative : combien d'instruments sont AUDITÉS SANS RÉSERVE, sur
    # le total déclaré. Un dépôt dont 3 instruments sur 19 passent les quatre
    # critères ne peut pas prétendre à une confiance élevée dans ses conclusions,
    # et le plafond le dit sans que le lecteur ait à faire la division.
    clean = [i for i in only_instruments if not i.failures and not i.invalidated]
    coverage = Coverage(
        measured=len(clean),
        total=len(only_instruments),
        subject="instruments sans defaillance ni invalidation",
    )

    return QualityReport(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        n_registered=len(REGISTRY),
        n_instruments=len(only_instruments),
        instruments=instruments,
        undeclared_readers=find_undeclared_readers(root),
        missing_from_disk=missing,
        totals=totals,
        coverage=coverage.to_dict(),
        confidence_ceiling=weakest_ceiling(
            [coverage.confidence_ceiling]
            + [i.confidence_ceiling for i in only_instruments]
        ),
    )


# ── Restitution ───────────────────────────────────────────────────────────────


def render_text(report: QualityReport) -> str:
    lines: list[str] = []
    add = lines.append
    add("=" * 78)
    add("  EXPERIMENT QUALITY AUDIT — la mesure est-elle déclarée ?")
    add("=" * 78)
    add(f"  Généré     : {report.generated_at}")
    add(
        f"  Registre   : {report.n_registered} fichiers, "
        f"{report.n_instruments} instruments"
    )
    add("")
    add("  Cet outil détecte l'ABSENCE DE DÉCLARATION, jamais l'inexactitude.")
    add("  Un instrument qui déclare tout et se trompe partout passe cet audit.")
    add("")

    add("-" * 78)
    add("  INSTRUMENTS      (INV = invalide par propagation, pas evalue)")
    add("-" * 78)
    add("    fichier                              POP  PWR  TRA  IND   plafond")
    for inst in report.instruments:
        if inst.role != ROLE_INSTRUMENT:
            continue
        cells = []
        for criterion in CRITERIA:
            status = next(
                (c.status for c in inst.checks if c.criterion == criterion), "?"
            )
            cells.append(
                {
                    STATUS_PASS: " ok ",
                    STATUS_FAIL: "FAIL",
                    STATUS_NA: " -  ",
                    STATUS_INVALID: "INV ",
                }[status]
            )
        add(f"    {inst.path:<36} {' '.join(cells)}  {inst.confidence_ceiling}")
    add("")

    add("-" * 78)
    add("  SYNTHÈSE PAR CRITÈRE")
    add("-" * 78)
    for criterion in CRITERIA:
        t = report.totals[criterion]
        add(
            f"    {criterion:<16} ok={t[STATUS_PASS]:>3}   FAIL={t[STATUS_FAIL]:>3}   "
            f"INVALIDE={t[STATUS_INVALID]:>3}   non liant={t[STATUS_NA]:>3}"
        )
    add("")

    add("-" * 78)
    add("  COUVERTURE NORMATIVE")
    add("-" * 78)
    cov = report.coverage
    add(
        f"    instruments sans défaillance ni invalidation : "
        f"{cov['measured']}/{cov['total']} ({cov['ratio']:.2%})"
    )
    add("    plafond de couverture             : " f"{cov['confidence_ceiling']}")
    add("    PLAFOND DE CONFIANCE DU RAPPORT  : " f"{report.confidence_ceiling}")
    add("")
    add("    Le plafond est le MAILLON FAIBLE de la couverture et de tous les")
    add("    instruments. Une conclusion plus affirmative que ce plafond contredit")
    add("    les données de ce rapport — ce n'est pas au lecteur de faire le calcul.")
    add("")

    add("-" * 78)
    add("  DÉFAILLANCES, AVEC LEUR PREUVE")
    add("-" * 78)
    any_fail = False
    for inst in report.instruments:
        fails = [c for c in inst.checks if c.status == STATUS_FAIL]
        if not fails:
            continue
        any_fail = True
        add(f"    {inst.path}  ({inst.note})")
        for check in fails:
            add(f"      {check.criterion} — {check.binds_because}")
            for ev in check.evidence:
                add(f"        {ev}")
        add("")
    if not any_fail:
        add("    aucune")
        add("")

    if report.undeclared_readers:
        add("-" * 78)
        add("  ACCÈS AU DATASET NON DÉCLARÉS AU REGISTRE")
        add("-" * 78)
        for rel in report.undeclared_readers:
            add(f"    {rel}")
        add("")
    if report.missing_from_disk:
        add("-" * 78)
        add("  AU REGISTRE MAIS ABSENTS DU DISQUE")
        add("-" * 78)
        for rel in report.missing_from_disk:
            add(f"    {rel}")
        add("")
    add("=" * 78)
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit de la qualité des expériences (outil de mesure passif)"
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 si un critère échoue ou si un lecteur n'est pas déclaré",
    )
    args = parser.parse_args(argv)

    report = build_report()
    if args.json:
        print(json.dumps(asdict(report), indent=2, default=str, ensure_ascii=False))
    else:
        print(render_text(report))

    if args.strict:
        failed = any(
            c.status == STATUS_FAIL for inst in report.instruments for c in inst.checks
        )
        if failed or report.undeclared_readers or report.missing_from_disk:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
