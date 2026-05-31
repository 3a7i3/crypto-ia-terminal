#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_miniature.py — Genere une "miniature" du projet crypto_ai_terminal
dans UN SEUL fichier Markdown (PROJET_MINIATURE.md), destine a etre lu/analyse
par un LLM externe (GPT) qui ne peut pas ingerer les 800+ fichiers du depot.

Principe : on n'exporte QUE le squelette d'API
  - docstring (1re ligne) de chaque module
  - chaque classe : nom, bases, docstring, signatures de methodes
  - chaque fonction top-level : signature + docstring
Jamais le corps des fonctions  ->  le fichier reste lisible par un humain ET un LLM.

Mode "ecrasement" : relancer ce script ecrase le fichier de sortie a neuf.

Deux modes :
  - compact (defaut) : detail COMPLET pour les modules [COEUR] (cerveau,
    execution, securite, donnees) ; index compact (noms seuls) pour le reste.
    Sortie : PROJET_MINIATURE.md  -> tient dans une fenetre GPT.
  - full (--full)    : detail complet pour TOUS les modules.
    Sortie : PROJET_MINIATURE_FULL.md  -> exhaustif mais tres gros.

Usage :
    python tools/generate_miniature.py            # compact
    python tools/generate_miniature.py --full     # exhaustif
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # tools/ -> racine projet

# Dossiers de DONNEES / SORTIES / ARCHIVES -> jamais du code source a analyser.
EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cursor",
    ".vscode",
    ".github",
    ".idea",
    "node_modules",
    "frontend",
    "site-packages",
    "archives",
    "_ARCHIVE_2026",
    "archive_results",
    "artifacts",
    "logs",
    "cache",
    "databases",
    "checkpoints",
    "data",
    "results",
    "reports",
    "errors",
    "sim_summaries",
    "reality_checks",
    "feedback_logs",
    "anara_context",
    "tickets",
    "k8s",
    "install",
    "deploy",
    "docs",
}

# Methodes "dunder" trop bruyantes : on ne garde que celles qui portent du sens.
KEEP_DUNDERS = {
    "__init__",
    "__call__",
    "__enter__",
    "__exit__",
    "__aenter__",
    "__aexit__",
    "__post_init__",
}

# Sous-chaines qui signalent un module "coeur" (cerveau / execution / securite /
# donnees). Sert juste a poser un repere visuel pour l'analyste.
CORE_HINTS = (
    "advisor_loop",
    "execution",
    "order",
    "risk",
    "kill",
    "circuit_breaker",
    "reconcil",
    "exchange",
    "feed",
    "stream_bus",
    "data_verifier",
    "position",
    "portfolio",
    "decision",
    "safety",
    "watchdog",
    "audit",
    "invariant",
    "burn_in",
    "burnin",
    "emergency",
    "gate",
    "kill_switch",
    "killswitch",
)


def is_excluded_dir(name: str) -> bool:
    if name in EXCLUDE_DIRS:
        return True
    # artefact de chemin malforme observe dans le depot
    if name.startswith("c:Users") or "crypto_ai_terminalcapital" in name:
        return True
    return False


def is_core(relpath: str) -> bool:
    low = relpath.lower()
    return any(h in low for h in CORE_HINTS)


def first_doc_line(node) -> str:
    doc = ast.get_docstring(node)
    if not doc:
        return ""
    return doc.strip().splitlines()[0].strip()[:160]


def safe_unparse(node) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return "..."


def func_sig(node) -> str:
    kw = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    args = safe_unparse(node.args)
    ret = f" -> {safe_unparse(node.returns)}" if node.returns is not None else ""
    return f"{kw} {node.name}({args}){ret}"


def keep_method(name: str) -> bool:
    if name.startswith("__") and name.endswith("__"):
        return name in KEEP_DUNDERS
    return True


def summarize_module(path: Path) -> dict:
    src = path.read_text(encoding="utf-8", errors="replace")
    info = {
        "loc": src.count("\n") + 1,
        "doc": "",
        "classes": [],
        "functions": [],
        "error": None,
    }
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        info["error"] = f"SyntaxError L{e.lineno}: {e.msg}"
        return info
    except Exception as e:  # noqa: BLE001
        info["error"] = f"{type(e).__name__}: {e}"
        return info

    info["doc"] = first_doc_line(tree)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info["functions"].append(
                {"sig": func_sig(node), "doc": first_doc_line(node)}
            )
        elif isinstance(node, ast.ClassDef):
            bases = [safe_unparse(b) for b in node.bases]
            methods = []
            for sub in node.body:
                if isinstance(
                    sub, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) and keep_method(sub.name):
                    methods.append({"sig": func_sig(sub), "doc": first_doc_line(sub)})
            info["classes"].append(
                {
                    "name": node.name,
                    "bases": bases,
                    "doc": first_doc_line(node),
                    "methods": methods,
                }
            )
    return info


def walk_py_files():
    files = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if not is_excluded_dir(d)]
        for fn in filenames:
            if fn.endswith(".py"):
                files.append(Path(dirpath) / fn)
    return sorted(files, key=lambda p: str(p.relative_to(ROOT)).lower())


def build_tree(files) -> str:
    """Arbre des dossiers contenant du .py, avec compte direct."""
    counts: dict[str, int] = {}
    for f in files:
        rel = f.relative_to(ROOT).parent
        key = str(rel).replace("\\", "/")
        counts[key] = counts.get(key, 0) + 1
    lines = []
    for key in sorted(counts):
        depth = 0 if key == "." else key.count("/") + 1
        name = "<racine>" if key == "." else key.split("/")[-1]
        indent = "  " * depth
        lines.append(f"{indent}{name}/  ({counts[key]} .py)")
    return "\n".join(lines)


def git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--oneline"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        return out.stdout.strip() or "(git indisponible)"
    except Exception:  # noqa: BLE001
        return "(git indisponible)"


def count_tests(files) -> int:
    n = 0
    for f in files:
        rel = str(f.relative_to(ROOT)).lower()
        if "test" not in rel:
            continue
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        n += txt.count("def test_")
    return n


PREAMBLE = """\
## 0. A LIRE EN PREMIER  (cadre pour l'analyste GPT)

Ce fichier est une **miniature** (squelette d'API) d'un bot de trading crypto
autonome : `crypto_ai_terminal`. Le depot reel fait 800+ fichiers Python ; ici
on ne montre que les signatures (classes, methodes, fonctions) + docstrings,
jamais le corps du code. Objectif : que tu puisses raisonner sur l'ARCHITECTURE
COMPLETE en une seule lecture.

### Etat du systeme
- Phase atteinte : **P12-D** (Paper Trading Burn-In termine). Le bot n'est PAS
  encore sur capital reel. Prochaine etape : ~1 mois de burn-in d'observation,
  puis decision P13 (capital reel progressif).
- **Gel d'architecture** en vigueur pendant le burn-in : pas de nouvelle
  fonctionnalite, pas de gros refactoring, pas de nouvelle strategie. Autorise
  uniquement : corrections critiques, securite, bugs bloquants.

### Ce que le proprietaire veut faire verifier
1. Le code est-il propre / coherent (pas de modules morts, pas d'enums
   dupliquees, pas de mismatch de types entre couches) ?
2. Toutes les fonctions sont-elles couvertes par des tests ?
3. Le telechargement des donnees (feeds exchange, market data) est-il fiable ?
4. Le systeme prend-il de bonnes decisions ET enregistre-t-il ses erreurs
   (memoire des erreurs, audit, alertes) ?
5. Le "cerveau" (couches de decision) envoie-t-il bien les ordres au module
   d'execution dedie, sans court-circuit ?
6. La machine peut-elle s'arreter sur N'IMPORTE quelle alerte d'urgence OU sur
   un arret brusque demande par l'utilisateur (kill switch / circuit breaker) ?

### Bugs connus a garder en tete (source : BUGS.md)
- BUG-007 (HAUT) : la `.venv` locale pointe vers un Python311 absent -> pytest
  local casse. Verifier d'abord qu'on peut faire tourner la suite de tests.
- BUG-003 (HAUT) : noms de regime incoherents entre certains modules et le
  format `MarketRegime` -> mappings fragiles.
- BUG-005 (MOYEN) : deux enums de "conviction" coexistent avec des valeurs
  incompatibles.
- BUG-006 (MOYEN) : quelques `test_*.py` racine a fiabiliser/reclasser.

### Ou regarder en priorite (chaine cerveau -> execution -> securite)
- `advisor_loop.py` : la boucle "cerveau" principale (tres gros fichier).
- `risk_limits.py`, `circuit_breaker.py` : garde-fous de risque.
- `exchange_factory.py`, `multi_exchange_feed.py`, `stream_bus.py` : connexion
  exchange + flux de donnees.
- `data_verifier.py` : verification d'integrite des donnees telechargees.
- modules contenant `execution`, `order`, `reconcil`, `position`, `kill`,
  `watchdog`, `invariant`, `burn_in` : execution, reconciliation, arret d'urgence.
Les modules "coeur" sont marques **[COEUR]** ci-dessous.
"""


def main() -> int:
    full = "--full" in sys.argv[1:]
    out_path = ROOT / ("PROJET_MINIATURE_FULL.md" if full else "PROJET_MINIATURE.md")

    files = walk_py_files()
    summaries = [(f, summarize_module(f)) for f in files]

    n_files = len(summaries)
    n_core = sum(
        1 for f, _ in summaries if is_core(str(f.relative_to(ROOT)).replace("\\", "/"))
    )
    n_classes = sum(len(s["classes"]) for _, s in summaries)
    n_funcs = sum(len(s["functions"]) for _, s in summaries)
    n_methods = sum(len(c["methods"]) for _, s in summaries for c in s["classes"])
    n_loc = sum(s["loc"] for _, s in summaries)
    errors = [(f, s["error"]) for f, s in summaries if s["error"]]
    n_tests = count_tests(files)
    head = git_head()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    out = []
    w = out.append

    mode_label = (
        "FULL (detail complet, tous modules)"
        if full
        else "COMPACT (detail complet sur [COEUR], index pour le reste)"
    )
    regen_cmd = (
        "python tools/generate_miniature.py --full"
        if full
        else "python tools/generate_miniature.py"
    )

    w(f"# PROJET MINIATURE — crypto_ai_terminal")
    w(f"_Genere le {now} par `tools/generate_miniature.py` — mode **{mode_label}**._")
    w(f"_Squelette d'API : signatures uniquement, jamais le corps des fonctions._")
    w(f"_Regenerer (ecrase ce fichier) : `{regen_cmd}`_\n")

    w(PREAMBLE)

    w("\n## 1. Statistiques")
    w(f"- Git HEAD : `{head}`")
    w(f"- Fichiers .py analyses : **{n_files}**")
    w(f"- Lignes de code (approx) : **{n_loc:,}**")
    w(
        f"- Classes : **{n_classes}**  |  Fonctions : **{n_funcs}**"
        f"  |  Methodes : **{n_methods}**"
    )
    w(f"- Modules marques [COEUR] : **{n_core}** / {n_files}")
    w(f"- Fonctions de test (`def test_`) : **{n_tests}**")
    w(
        f"- Fichiers en ERREUR de parsing : **{len(errors)}**"
        + ("  ⚠️" if errors else "  ✅")
    )

    w("\n## 2. Fichiers qui ne PARSENT PAS (signal de sante code)")
    if errors:
        for f, err in errors:
            w(f"- `{f.relative_to(ROOT)}` — {err}")
    else:
        w("_Aucun — tous les fichiers .py parsent correctement._")

    w("\n## 3. Arborescence (dossiers contenant du .py)")
    w("```")
    w(build_tree(files))
    w("```")

    if not full:
        w(
            "\n> En mode COMPACT : les modules **[COEUR]** sont detailles (toutes "
            "signatures de methodes) ; les autres ne montrent que les NOMS de "
            "classes/fonctions. Pour le detail complet d'un module non-coeur, "
            "regenerer avec `--full` ou demander ce module precis."
        )

    w("\n## 4. Squelette d'API par module")
    for f, s in summaries:
        rel = str(f.relative_to(ROOT)).replace("\\", "/")
        core = is_core(rel)
        tag = " **[COEUR]**" if core else ""
        w(f"\n### `{rel}`  ({s['loc']} LOC){tag}")
        if s["error"]:
            w(f"> ⚠️ {s['error']}")
            continue
        if s["doc"]:
            w(f"> {s['doc']}")

        detailed = full or core
        if detailed:
            for c in s["classes"]:
                bases = f"({', '.join(c['bases'])})" if c["bases"] else ""
                doc = f" — {c['doc']}" if c["doc"] else ""
                w(f"- **class {c['name']}{bases}**{doc}")
                for m in c["methods"]:
                    mdoc = f" — {m['doc']}" if m["doc"] else ""
                    w(f"    - `{m['sig']}`{mdoc}")
            for fn in s["functions"]:
                fdoc = f" — {fn['doc']}" if fn["doc"] else ""
                w(f"- `{fn['sig']}`{fdoc}")
        else:
            # index compact : noms seulement
            if s["classes"]:
                parts = []
                for c in s["classes"]:
                    parts.append(f"{c['name']} ({len(c['methods'])}m)")
                w(f"- classes : {', '.join(parts)}")
            if s["functions"]:
                names = ", ".join(
                    fn["sig"].split("(")[0].replace("def ", "").replace("async ", "")
                    for fn in s["functions"]
                )
                w(f"- fonctions : {names}")

    text = "\n".join(out) + "\n"
    out_path.write_text(text, encoding="utf-8")

    size_kb = len(text.encode("utf-8")) / 1024
    approx_tokens = len(text) // 4
    print(f"OK -> {out_path.name}  (mode {'full' if full else 'compact'})")
    print(
        f"   {n_files} fichiers ({n_core} coeur), {n_loc:,} LOC, "
        f"{n_classes} classes, {n_funcs} fonctions, {n_methods} methodes"
    )
    print(f"   tests: {n_tests} | parse errors: {len(errors)} | HEAD: {head}")
    print(f"   taille: {size_kb:,.0f} Ko  (~{approx_tokens:,} tokens approx)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
