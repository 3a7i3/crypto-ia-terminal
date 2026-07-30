"""
tools/init_order_audit.py — INIT-ORDER : la configuration précède-t-elle les imports ?

Catégorie de défaut distincte du dataset et des KPI. L'ordre attendu est :

    .env  ──►  load_dotenv()  ──►  imports des modules dépendants

Or une constante écrite à la racine d'un module est évaluée **au moment de
l'import**. Si l'import précède `load_dotenv()`, la constante prend son défaut
codé en dur et le reste pour toute la durée du process — silencieusement, sans
erreur, sans trace.

Instance CONSTATÉE (2026-07-29) :

    infra/wallet_sync.py:48
        _PAPER_CAPITAL = float(os.getenv("WALLET_PAPER_CAPITAL", "100"))

`.env` porte 1000. Sur un harnais important `wallet_sync` avant `load_dotenv`,
le drawdown des 121 trades canoniques passe de **0.95 % à 9.42 %** — face à un
seuil de gate à 10 %. Le verdict d'une gate dépend donc d'un ordre d'import.

Ce que cet outil fait
---------------------
1. **Inventaire statique (AST)** de toutes les constantes de module lues via
   `os.getenv`, avec classement par criticité (capital, risque, exécution,
   seuil, autre). Un chiffre, pas une impression.
2. **Différentiel empirique** sur un registre de constantes déclarées
   critiques : la valeur est lue dans deux sous-processus — l'un **sans** `.env`,
   l'autre **avec** — et comparée. Un écart prouve la dépendance à l'ordre ; une
   égalité la réfute pour cette constante.

Le point 2 est une mesure, pas une inspection : c'est ce qui distingue
« ce code pourrait dépendre de l'ordre » de « cette constante en dépend ».

**Nature des verdicts : déterministe.** Deux lectures de la même constante dans
deux sous-processus ne constituent pas un échantillon — il n'y a ici aucune
inférence statistique, donc aucune puissance à publier (INV-POWER-001 ne lie pas
cet outil). Une égalité réfute la dépendance à l'ordre pour cette constante ; un
écart la prouve. Unité d'échantillonnage : **aucune** — la comparaison est
exacte, pas estimée, et aucun intervalle de confiance n'aurait de sens ici.

Ce que cet outil ne fait pas
----------------------------
Il ne corrige rien. Rendre `_PAPER_CAPITAL` paresseux changerait la valeur lue
par une gate dans le scénario ci-dessus (9.42 % → 0.95 %) : c'est un
déplacement de KPI face à un seuil, donc une décision d'opérateur sous ADR, pas
un nettoyage. Voir DEC-INIT-001.

Usage :
    python tools/init_order_audit.py
    python tools/init_order_audit.py --json
    python tools/init_order_audit.py --no-runtime   # inventaire statique seul
    python tools/init_order_audit.py --strict       # exit 1 si une critique dérive
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_SKIP_PARTS = (
    "_ARCHIVE",
    "/tests/",
    "test_",
    ".venv",
    "site-packages",
    "frontend",
    "node_modules",
)

#: Criticité par mot-clé du nom de constante ou de variable d'environnement.
#: L'ordre compte : la première catégorie qui correspond gagne.
_CRITICALITY = [
    ("CAPITAL", ("CAPITAL", "EQUITY", "BALANCE", "WALLET")),
    ("RISQUE", ("RISK", "EXPOSURE", "MAX_TOTAL", "DRAWDOWN", "LOSS", "KELLY")),
    ("EXECUTION", ("MAX_ORDER", "SIZE", "LEVERAGE", "SLIPPAGE", "QTY", "POSITION")),
    ("SEUIL", ("MIN_", "MAX_", "THRESHOLD", "SEUIL", "SCORE")),
]
_CRITICALITY_OTHER = "AUTRE"

#: Constantes déclarées critiques et testées EMPIRIQUEMENT. Chaque entrée est un
#: import sans effet de bord connu — un module qui démarre une boucle, ouvre un
#: socket ou écrit un fichier à l'import n'a pas sa place ici.
RUNTIME_REGISTRY: list[tuple[str, str, str]] = [
    ("infra.wallet_sync", "_PAPER_CAPITAL", "WALLET_PAPER_CAPITAL"),
    ("quant_hedge_ai.agents.intelligence.black_box", "_BB_MAX_SIZE", "BB_MAX"),
    ("runtime.system_state_bus", "_MAX_QUEUE_SIZE", "P10_BUS_MAX_QUEUE"),
]

VERDICT_STABLE = "STABLE"
VERDICT_ORDER_DEPENDENT = "DEPENDANT_DE_L_ORDRE"
VERDICT_UNMEASURABLE = "NON_MESURABLE"

#: Égalité des deux lectures alors que la variable n'est PAS définie dans `.env`.
#: L'égalité ne réfute alors rien : elle constate qu'il n'y a rien à écraser
#: aujourd'hui. Ajouter la variable à `.env` suffirait à rendre la constante
#: dépendante de l'ordre. Distinguer ce cas de STABLE évite de lire une absence
#: de configuration comme une preuve de robustesse.
VERDICT_UNCONSTRAINED = "NON_CONTRAINT"


# ── Inventaire statique ───────────────────────────────────────────────────────


@dataclass
class EnvConstant:
    path: str
    line: int
    source: str
    criticality: str


def _criticality(snippet: str) -> str:
    upper = snippet.upper()
    for label, keywords in _CRITICALITY:
        if any(k in upper for k in keywords):
            return label
    return _CRITICALITY_OTHER


def scan_module_level_env(root: Path = REPO_ROOT) -> list[EnvConstant]:
    """Constantes de module lues via `os.getenv` — donc figées à l'import.

    Seul `tree.body` est parcouru : une lecture d'environnement à l'intérieur
    d'une fonction est évaluée à l'appel, pas à l'import, et ne relève donc pas
    de cette catégorie de défaut.
    """
    found: list[EnvConstant] = []
    for f in sorted(root.rglob("*.py")):
        rel = f.relative_to(root).as_posix()
        if any(part in rel for part in _SKIP_PARTS):
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError, ValueError):
            continue
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            for sub in ast.walk(node):
                func = getattr(sub, "func", None)
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(func, ast.Attribute)
                    and func.attr == "getenv"
                ):
                    snippet = ast.unparse(node)[:120]
                    found.append(
                        EnvConstant(
                            path=rel,
                            line=node.lineno,
                            source=snippet,
                            criticality=_criticality(snippet),
                        )
                    )
                    break
    return found


# ── Différentiel empirique ────────────────────────────────────────────────────


_PROBE = (
    "import importlib, os, sys, json\n"
    "sys.path.insert(0, {root!r})\n"
    "{dotenv}\n"
    "defined = {var!r} in os.environ\n"
    "m = importlib.import_module({module!r})\n"
    "print(json.dumps({{'value': repr(getattr(m, {attr!r}, None)), "
    "'defined': defined}}))\n"
)


def _probe(
    module: str, attr: str, var: str, *, with_dotenv: bool
) -> tuple[Optional[str], bool]:
    """Lit la constante dans un sous-processus neuf, avec ou sans `.env` chargé.

    Sous-processus obligatoire : une fois le module importé dans CE process, sa
    constante est figée — mesurer les deux ordres dans un seul interpréteur est
    impossible par construction.
    """
    dotenv = "from dotenv import load_dotenv; load_dotenv()" if with_dotenv else "pass"
    code = _PROBE.format(
        root=str(REPO_ROOT), dotenv=dotenv, module=module, attr=attr, var=var
    )
    env = dict(os.environ)
    # L'environnement du shell peut déjà porter la variable : on le nettoie pour
    # que « sans .env » signifie réellement « sans configuration ».
    for _, _, var in RUNTIME_REGISTRY:
        env.pop(var, None)
    try:
        out = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(REPO_ROOT),
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, False
    if out.returncode != 0:
        return None, False
    for line in reversed(out.stdout.strip().splitlines()):
        try:
            payload = json.loads(line)
            return payload["value"], bool(payload.get("defined"))
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return None, False


@dataclass
class RuntimeCheck:
    module: str
    attribute: str
    env_var: str
    value_without_dotenv: Optional[str]
    value_with_dotenv: Optional[str]
    defined_in_env: bool
    verdict: str


def check_runtime(registry: Sequence[tuple[str, str, str]]) -> list[RuntimeCheck]:
    results: list[RuntimeCheck] = []
    for module, attr, var in registry:
        without, _ = _probe(module, attr, var, with_dotenv=False)
        with_, defined = _probe(module, attr, var, with_dotenv=True)
        if without is None or with_ is None:
            verdict = VERDICT_UNMEASURABLE
        elif without != with_:
            verdict = VERDICT_ORDER_DEPENDENT
        elif defined:
            verdict = VERDICT_STABLE
        else:
            verdict = VERDICT_UNCONSTRAINED
        results.append(
            RuntimeCheck(
                module=module,
                attribute=attr,
                env_var=var,
                value_without_dotenv=without,
                value_with_dotenv=with_,
                defined_in_env=defined,
                verdict=verdict,
            )
        )
    return results


# ── Rapport ───────────────────────────────────────────────────────────────────


@dataclass
class InitOrderReport:
    generated_at: str
    total_module_level_env_reads: int
    files_concerned: int
    by_criticality: dict
    critical_constants: list[EnvConstant]
    runtime_checks: list[RuntimeCheck] = field(default_factory=list)

    @property
    def order_dependent(self) -> list[RuntimeCheck]:
        return [c for c in self.runtime_checks if c.verdict == VERDICT_ORDER_DEPENDENT]


def build_report(*, with_runtime: bool = True) -> InitOrderReport:
    constants = scan_module_level_env()
    by_crit: dict[str, int] = {}
    for c in constants:
        by_crit[c.criticality] = by_crit.get(c.criticality, 0) + 1
    critical = [c for c in constants if c.criticality != _CRITICALITY_OTHER]
    return InitOrderReport(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        total_module_level_env_reads=len(constants),
        files_concerned=len({c.path for c in constants}),
        by_criticality=dict(sorted(by_crit.items(), key=lambda kv: -kv[1])),
        critical_constants=sorted(critical, key=lambda c: (c.criticality, c.path)),
        runtime_checks=check_runtime(RUNTIME_REGISTRY) if with_runtime else [],
    )


def render_text(report: InitOrderReport) -> str:
    lines: list[str] = []
    add = lines.append
    add("=" * 78)
    add("  INIT-ORDER AUDIT — la configuration précède-t-elle les imports ?")
    add("=" * 78)
    add(f"  Généré : {report.generated_at}")
    add("")
    add("-" * 78)
    add("  INVENTAIRE STATIQUE (constantes figées à l'import)")
    add("-" * 78)
    add(
        f"    lectures d'environnement au niveau module : "
        f"{report.total_module_level_env_reads}"
    )
    add(f"    fichiers concernés                        : {report.files_concerned}")
    for label, count in report.by_criticality.items():
        add(f"      {label:<12} {count:>4}")
    add("")
    add("-" * 78)
    add("  CONSTANTES CRITIQUES (capital / risque / exécution / seuil)")
    add("-" * 78)
    for c in report.critical_constants:
        add(f"    [{c.criticality}] {c.path}:{c.line}")
        add(f"        {c.source}")
    add("")
    if report.runtime_checks:
        add("-" * 78)
        add("  DIFFÉRENTIEL EMPIRIQUE (sous-processus sans .env vs avec .env)")
        add("-" * 78)
        for c in report.runtime_checks:
            add(f"    {c.module}.{c.attribute}  ({c.env_var})")
            add(f"        sans .env : {c.value_without_dotenv}")
            add(f"        avec .env : {c.value_with_dotenv}")
            add(f"        définie dans l'env : {'oui' if c.defined_in_env else 'non'}")
            add(f"        verdict   : {c.verdict}")
            if c.verdict == VERDICT_UNCONSTRAINED:
                add(
                    "                    (égalité par ABSENCE de configuration — "
                    "définir la variable rendrait la constante dépendante)"
                )
        add("")
        n = len(report.order_dependent)
        n_latent = sum(
            1 for c in report.runtime_checks if c.verdict == VERDICT_UNCONSTRAINED
        )
        add(f"    constantes prouvées dépendantes de l'ordre : {n}")
        add(f"    constantes non contraintes (latentes)      : " f"{n_latent}")
        add("")
    add("  Cet outil NE CORRIGE RIEN : rendre une de ces constantes paresseuse")
    add("  déplacerait un KPI face à un seuil de gate. Voir DEC-INIT-001.")
    add("=" * 78)
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit de l'ordre d'initialisation (outil de mesure passif)"
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-runtime", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 si une constante critique est prouvée dépendante de l'ordre",
    )
    args = parser.parse_args(argv)

    report = build_report(with_runtime=not args.no_runtime)
    if args.json:
        print(json.dumps(asdict(report), indent=2, default=str, ensure_ascii=False))
    else:
        print(render_text(report))

    if args.strict and report.order_dependent:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
