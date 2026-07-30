"""
tools/chain_audit.py — la garantie survit-elle jusqu'à la décision ?

`experiment_quality_audit.py` audite les instruments **un par un**. Mais les
instruments consomment les artefacts les uns des autres :

    paper_trades.jsonl ─► load_clean_trades ─► burnin_v3.json ─► gate D ─► GO/NO-GO

Chaque flèche est un endroit où une garantie peut disparaître **sans qu'aucune
donnée ne disparaisse**. C'est l'idée centrale du § 20.1 du protocole, appliquée
ici de façon exécutable : une projection, une agrégation ou une simple relecture
d'artefact conserve les octets et détruit ce qui les rendait interprétables —
la population dont ils viennent, la date à laquelle ils valaient, l'unité dans
laquelle ils se lisent.

Précédent réel (AUDIT-EMP-001, gate D) : un rapport de burn-in vieux de 559.8 h,
calculé sur une population de 631 trades toutes époques confondues, était
consommé comme courant par une gate qui lisait en outre une clé
(`burnin_passed`) qu'aucun producteur n'écrivait. Les deux fichiers étaient
valides. Le verdict ne l'était pas.

Quatre contrôles par arête d'artefact
-------------------------------------
| Contrôle    | Question                                                    |
|-------------|-------------------------------------------------------------|
| PROVENANCE  | l'artefact dit-il par QUOI et QUAND il a été produit ?       |
| POPULATION  | dit-il SUR QUOI, et le consommateur le vérifie-t-il ?        |
| FRAICHEUR   | son âge est-il sous la limite que le consommateur déclare ?  |
| CONTRAT     | les clés lues par le consommateur existent-elles vraiment ?  |

Plafonnement
------------
Chaque étape porte un plafond de confiance ; la chaîne vaut son **maillon
faible** (`system.provenance.weakest_ceiling`). Une chaîne qui se termine sans
artefact persisté est signalée : une décision prise sur un rapport qui ne laisse
aucune trace n'est pas re-auditable, même si chacune de ses étapes était juste.

Ce que cet outil ne fait pas
----------------------------
Il ne relance aucun producteur et ne recalcule aucun KPI. Il lit les artefacts
tels qu'ils sont sur le disque et le code tel qu'il est. Un artefact absent est
un résultat — pas une erreur d'exécution. Verdicts **déterministes** : aucune
inférence statistique, unité d'échantillonnage sans objet.

**Population consommée : aucune.** Les chemins de datasets qui apparaissent
ci-dessous sont des *déclarations de chaîne*, jamais des lectures : cet outil
n'ouvre que des artefacts et des fichiers source.

Usage :
    python tools/chain_audit.py
    python tools/chain_audit.py --json
    python tools/chain_audit.py --strict     # exit 1 si une arête casse
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
    CEILING_FULL,
    CEILING_LOW,
    CEILING_MEDIUM,
    CEILING_NONE,
    Coverage,
    sha256_file,
    weakest_ceiling,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CHECK_PROVENANCE = "PROVENANCE"
CHECK_POPULATION = "POPULATION"
CHECK_FRESHNESS = "FRAICHEUR"
CHECK_CONTRACT = "CONTRAT"

STATUS_OK = "ok"
STATUS_BROKEN = "ROMPU"
STATUS_ABSENT = "ABSENT"
STATUS_NA = "-"

#: Clés qui, dans ce dépôt, portent une provenance de dataset. Déclarées ici et
#: nulle part ailleurs : un producteur qui inventerait un troisième nom serait
#: signalé plutôt que silencieusement accepté.
_POPULATION_KEYS = ("dataset_provenance", "population", "provenance")
_DATE_KEYS = ("generated_at", "measured_at", "ts_iso")


# ── Déclaration des chaînes ───────────────────────────────────────────────────


@dataclass(frozen=True)
class Edge:
    """Une arête artefact : un producteur écrit, un consommateur relit."""

    artifact: str
    producer: str
    consumer: str
    keys_consumed: tuple[str, ...]
    max_age_hours: Optional[float]
    unit_note: str = ""


@dataclass(frozen=True)
class Chain:
    """Un chemin observation → décision, déclaré explicitement.

    `terminal_persisted=False` signifie que la décision est prise sur une sortie
    non persistée (stdout, message Telegram) : rien ne permettra de rejouer
    l'enchaînement plus tard.
    """

    name: str
    source: str
    steps: tuple[str, ...]
    decision: str
    edges: tuple[Edge, ...] = ()
    terminal_persisted: bool = False
    note: str = ""


CHAINS: tuple[Chain, ...] = (
    Chain(
        name="CHAIN-BURNIN-PRELIVE",
        source="databases/paper_trades.jsonl",
        steps=(
            "tools/cri_calculator.py::load_clean_trades",
            "scripts/burnin_calibration_v3.py",
            "cache/burn_in_reports/burnin_v3.json",
            "scripts/prelive_gate.py::gate_d_calibration",
        ),
        decision="verdict prelive GO / NO-GO",
        edges=(
            Edge(
                artifact="cache/burn_in_reports/burnin_v3.json",
                producer="scripts/burnin_calibration_v3.py",
                consumer="scripts/prelive_gate.py",
                keys_consumed=("go_no_go", "generated_at", "dataset_provenance"),
                max_age_hours=24.0,
                unit_note="max_drawdown_pct en POURCENT, expectancy_pct en POURCENT",
            ),
        ),
        terminal_persisted=False,
        note=(
            "chaîne de l'incident AUDIT-EMP-001 — la seule à avoir "
            "produit un verdict faux"
        ),
    ),
    Chain(
        name="CHAIN-CRI",
        source="databases/paper_trades.jsonl",
        steps=(
            "tools/cri_calculator.py::load_clean_trades",
            "tools/cri_calculator.py::CRI",
        ),
        decision="autorisation de calibration (CRI >= 90)",
        edges=(),
        terminal_persisted=False,
        note="aucun artefact intermédiaire : le CRI est recalculé à chaque lecture",
    ),
    Chain(
        name="CHAIN-SCORE",
        source="databases/regret/regret_horizons_*.jsonl",
        steps=(
            "tools/score_calibration_audit.py::load_observed_records",
            "tools/score_calibration_audit.py::analyse_population",
        ),
        decision="DEC-HORIZON-001 (ouverte)",
        edges=(),
        terminal_persisted=False,
        note="projection entre populations déclarée (protocole § 20.1)",
    ),
    Chain(
        name="CHAIN-SHADOW",
        source="décisions refusées par la gate",
        steps=(
            "scripts/shadow_execution.py",
            "databases/shadow_s3_refused.jsonl",
        ),
        decision="aucune — observation seule (ADR-0007)",
        edges=(
            Edge(
                artifact="databases/shadow_s3_refused.jsonl",
                producer="scripts/shadow_execution.py",
                consumer="(aucun consommateur déclaré)",
                keys_consumed=(),
                max_age_hours=None,
            ),
        ),
        terminal_persisted=True,
    ),
)


# ── Résultats ─────────────────────────────────────────────────────────────────


@dataclass
class EdgeCheck:
    check: str
    status: str
    detail: str = ""


@dataclass
class EdgeReport:
    artifact: str
    producer: str
    consumer: str
    exists: bool
    sha256: Optional[str]
    age_hours: Optional[float]
    checks: list[EdgeCheck] = field(default_factory=list)

    @property
    def broken(self) -> list[str]:
        return [c.check for c in self.checks if c.status == STATUS_BROKEN]

    @property
    def confidence_ceiling(self) -> str:
        if not self.exists:
            return CEILING_NONE
        if self.broken:
            return CEILING_LOW
        return CEILING_FULL


@dataclass
class ChainReport:
    name: str
    source: str
    steps: list[str]
    decision: str
    note: str
    terminal_persisted: bool
    edges: list[EdgeReport] = field(default_factory=list)
    confidence_ceiling: str = CEILING_FULL
    remarks: list[str] = field(default_factory=list)


@dataclass
class ChainAuditReport:
    generated_at: str
    chains: list[ChainReport]
    coverage: dict
    confidence_ceiling: str


# ── Contrôles ─────────────────────────────────────────────────────────────────


def _age_hours(value: object) -> Optional[float]:
    if not isinstance(value, str) or not value:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - stamp).total_seconds() / 3600.0


def _load_artifact(path: Path) -> Optional[object]:
    """Charge un artefact JSON ou JSONL. None si absent ou illisible."""
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    text = text.strip()
    if not text:
        return {}
    if path.suffix == ".jsonl":
        for line in reversed(text.splitlines()):
            line = line.strip()
            if line:
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    return None
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def audit_edge(edge: Edge, root: Path = REPO_ROOT) -> EdgeReport:
    path = root / edge.artifact
    payload = _load_artifact(path)
    report = EdgeReport(
        artifact=edge.artifact,
        producer=edge.producer,
        consumer=edge.consumer,
        exists=path.exists(),
        sha256=sha256_file(path),
        age_hours=None,
    )
    if payload is None:
        report.checks.append(
            EdgeCheck(
                CHECK_PROVENANCE,
                STATUS_ABSENT,
                "artefact absent ou illisible — la chaîne est interrompue ici",
            )
        )
        for check in (CHECK_POPULATION, CHECK_FRESHNESS, CHECK_CONTRACT):
            report.checks.append(
                EdgeCheck(check, STATUS_ABSENT, "sans objet : artefact indisponible")
            )
        return report

    body = payload if isinstance(payload, dict) else {}

    # --- PROVENANCE ---
    date_key = next((k for k in _DATE_KEYS if body.get(k)), None)
    if date_key:
        report.age_hours = _age_hours(body.get(date_key))
        report.checks.append(
            EdgeCheck(CHECK_PROVENANCE, STATUS_OK, f"daté par `{date_key}`")
        )
    else:
        report.checks.append(
            EdgeCheck(
                CHECK_PROVENANCE,
                STATUS_BROKEN,
                "aucune date : un consommateur ne peut pas savoir si l'artefact "
                "décrit encore le système",
            )
        )

    # --- POPULATION : déclarée par le producteur ET vérifiée par le consommateur ---
    pop_key = next((k for k in _POPULATION_KEYS if body.get(k)), None)
    consumer_source = ""
    consumer_path = root / edge.consumer.split("::")[0]
    if consumer_path.exists():
        consumer_source = consumer_path.read_text(encoding="utf-8", errors="replace")
    if pop_key is None:
        report.checks.append(
            EdgeCheck(
                CHECK_POPULATION,
                STATUS_BROKEN,
                "l'artefact ne dit pas sur quelle population il a été calculé",
            )
        )
    elif consumer_source and pop_key not in consumer_source:
        report.checks.append(
            EdgeCheck(
                CHECK_POPULATION,
                STATUS_BROKEN,
                f"le producteur déclare `{pop_key}` mais le consommateur ne le lit "
                f"jamais : la population traverse l'arête sans être vérifiée",
            )
        )
    elif not consumer_source:
        report.checks.append(
            EdgeCheck(
                CHECK_POPULATION,
                STATUS_NA,
                f"`{pop_key}` déclaré ; aucun consommateur à inspecter",
            )
        )
    else:
        report.checks.append(
            EdgeCheck(
                CHECK_POPULATION,
                STATUS_OK,
                f"`{pop_key}` déclaré par le producteur et lu par le consommateur",
            )
        )

    # --- FRAICHEUR ---
    if edge.max_age_hours is None:
        report.checks.append(
            EdgeCheck(CHECK_FRESHNESS, STATUS_NA, "aucune limite d'âge déclarée")
        )
    elif report.age_hours is None:
        report.checks.append(
            EdgeCheck(CHECK_FRESHNESS, STATUS_BROKEN, "âge non calculable")
        )
    elif report.age_hours > edge.max_age_hours:
        report.checks.append(
            EdgeCheck(
                CHECK_FRESHNESS,
                STATUS_BROKEN,
                f"{report.age_hours:.1f} h > limite de {edge.max_age_hours:.0f} h — "
                f"l'artefact décrit un système qui a changé",
            )
        )
    else:
        report.checks.append(
            EdgeCheck(
                CHECK_FRESHNESS,
                STATUS_OK,
                f"{report.age_hours:.1f} h <= {edge.max_age_hours:.0f} h",
            )
        )

    # --- CONTRAT : les clés lues existent-elles réellement ? ---
    if not edge.keys_consumed:
        report.checks.append(
            EdgeCheck(CHECK_CONTRACT, STATUS_NA, "aucune clé consommée déclarée")
        )
    else:
        missing = [k for k in edge.keys_consumed if k not in body]
        if missing:
            report.checks.append(
                EdgeCheck(
                    CHECK_CONTRACT,
                    STATUS_BROKEN,
                    "clés lues par le consommateur et absentes de l'artefact : "
                    + ", ".join(missing)
                    + " (défaut exact de `burnin_passed`, gate D)",
                )
            )
        else:
            report.checks.append(
                EdgeCheck(
                    CHECK_CONTRACT,
                    STATUS_OK,
                    f"{len(edge.keys_consumed)} clé(s) présente(s) dans l'artefact",
                )
            )
    return report


def audit_chain(chain: Chain, root: Path = REPO_ROOT) -> ChainReport:
    edges = [audit_edge(e, root) for e in chain.edges]
    remarks: list[str] = []
    ceilings = [e.confidence_ceiling for e in edges]

    if not chain.terminal_persisted:
        remarks.append(
            "TERMINAISON NON PERSISTÉE : la décision est prise sur une sortie qui "
            "ne laisse aucune trace — l'enchaînement ne pourra pas être rejoué"
        )
        ceilings.append(CEILING_MEDIUM)

    if not chain.edges:
        remarks.append(
            "aucun artefact intermédiaire : rien ne peut périmer entre l'observation "
            "et la décision (c'est une propriété, pas un manque)"
        )

    return ChainReport(
        name=chain.name,
        source=chain.source,
        steps=list(chain.steps),
        decision=chain.decision,
        note=chain.note,
        terminal_persisted=chain.terminal_persisted,
        edges=edges,
        confidence_ceiling=weakest_ceiling(ceilings) if ceilings else CEILING_FULL,
        remarks=remarks,
    )


def build_report(root: Path = REPO_ROOT) -> ChainAuditReport:
    chains = [audit_chain(c, root) for c in CHAINS]
    total_edges = sum(len(c.edges) for c in chains)
    intact = sum(1 for c in chains for e in c.edges if e.exists and not e.broken)
    coverage = Coverage(
        measured=intact,
        total=total_edges,
        subject="aretes d'artefact intactes",
    )
    return ChainAuditReport(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        chains=chains,
        coverage=coverage.to_dict(),
        confidence_ceiling=weakest_ceiling(
            [coverage.confidence_ceiling] + [c.confidence_ceiling for c in chains]
        ),
    )


# ── Restitution ───────────────────────────────────────────────────────────────


def render_text(report: ChainAuditReport) -> str:
    lines: list[str] = []
    add = lines.append
    add("=" * 78)
    add("  CHAIN AUDIT — la garantie survit-elle jusqu'à la décision ?")
    add("=" * 78)
    add(f"  Généré : {report.generated_at}")
    add("")
    for chain in report.chains:
        add("-" * 78)
        add(f"  {chain.name}    plafond : {chain.confidence_ceiling}")
        add("-" * 78)
        add(f"    source   : {chain.source}")
        for i, step in enumerate(chain.steps):
            add(f"      {'└─►' if i == len(chain.steps) - 1 else '├─►'} {step}")
        add(f"    décision : {chain.decision}")
        if chain.note:
            add(f"    note     : {chain.note}")
        add("")
        for edge in chain.edges:
            add(f"    ARÊTE {edge.producer} ─► {edge.artifact} ─► {edge.consumer}")
            add(
                f"      présent : {'oui' if edge.exists else 'NON'}"
                + (f"   sha256 {edge.sha256[:12]}…" if edge.sha256 else "")
            )
            for check in edge.checks:
                add(f"      {check.check:<11} {check.status:<7} {check.detail}")
            add("")
        for remark in chain.remarks:
            add(f"    ⚠ {remark}")
        if chain.remarks:
            add("")

    add("-" * 78)
    add("  COUVERTURE NORMATIVE")
    add("-" * 78)
    cov = report.coverage
    add(
        f"    arêtes d'artefact intactes : {cov['measured']}/{cov['total']}"
        f" ({cov['ratio']:.2%})"
    )
    add(f"    plafond de couverture      : {cov['confidence_ceiling']}")
    add(f"    PLAFOND DE LA CHAÎNE       : {report.confidence_ceiling}")
    add("")
    add("    Une chaîne vaut son maillon faible. Aucune conclusion prise au bout")
    add("    d'une chaîne ne peut être plus assurée que ce plafond.")
    add("=" * 78)
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit de chaîne artefact → décision (outil de mesure passif)"
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--strict", action="store_true", help="exit 1 si une arête est rompue"
    )
    args = parser.parse_args(argv)

    report = build_report()
    if args.json:
        print(json.dumps(asdict(report), indent=2, default=str, ensure_ascii=False))
    else:
        print(render_text(report))

    if args.strict and any(e.broken for c in report.chains for e in c.edges):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
