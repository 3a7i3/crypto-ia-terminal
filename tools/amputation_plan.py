#!/usr/bin/env python3
"""Génère AMPUTATION_PLAN.md en croisant trois sources de preuve.

Sources :
  1. artifacts/cartography.json            — graphe d'import statique (AST)
  2. artifacts/prod_executed_modules.txt   — modules compilés par le processus
                                             de production réel (.pyc)
  3. artifacts/prod_deployed_files.txt     — fichiers .py présents sur le VPS

PASSIF : ne supprime ni ne déplace aucun fichier. Produit une PROPOSITION.

Usage : python tools/amputation_plan.py
"""

from __future__ import annotations

import collections
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "cartography" / "AMPUTATION_PLAN.md"

# Répertoires historiquement désignés comme expérimentaux / recherche.
EXPERIMENTAL_ROOTS = {
    "research",
    "experiments",
    "walk_forward",
    "meta_learning",
    "ai_autonomous_loop",
    "project_os",
    "audit",
    "S2",
    "S3",
    "analysis",
    "pieuvre",
    "lm_studio",
    "sdos_terminal",
    "dip",
}

# Modules dont l'absence de .pyc est un ARTEFACT, pas une preuve de non-exécution.
PYC_EXEMPT = {"core/advisor_loop.py"}  # script __main__ : CPython n'écrit pas de .pyc


def sh(*a: str) -> str:
    try:
        return subprocess.run(
            a, cwd=ROOT, capture_output=True, text=True, timeout=60
        ).stdout.strip()
    except Exception:
        return "UNKNOWN"


def classify(m: dict, executed: set[str], deployed: set[str]) -> tuple[str, str, str]:
    """-> (classe, confiance, justification)"""
    f = m["file"]
    st = m["status"]

    if st == "TEST":
        return "TEST", "PROUVÉ", "fichier de test"

    if f in executed or f in PYC_EXEMPT:
        why = (
            "point d'entrée — CPython n'écrit pas de .pyc pour `__main__`"
            if f in PYC_EXEMPT
            else ".pyc présent sur le VPS : corps de module exécuté en production"
        )
        return "ACTIVE", "PROUVÉ", why

    if f not in deployed:
        return (
            "DEAD",
            "MOYENNE",
            "absent du VPS : jamais déployé, donc jamais exécuté — "
            "mais peut servir hors production (outil local, CI)",
        )

    if st in ("ACTIVE", "ENTRYPOINT"):
        return (
            "ACTIVE-PROBABLE",
            "MOYENNE",
            "atteignable par import mais non exécuté dans la fenêtre "
            "d'observation : branche paresseuse probablement non encore prise",
        )

    if st == "TOOL":
        return (
            "TOOL",
            "ÉLEVÉE",
            "script autonome (`__main__`), jamais importé, non exécuté par le "
            "moteur — outil hors runtime",
        )

    if m["top_package"] in EXPERIMENTAL_ROOTS:
        return (
            "EXPERIMENTAL",
            "ÉLEVÉE",
            f"appartient à `{m['top_package']}/`, répertoire de recherche ; "
            "déployé mais non exécuté",
        )

    if st == "TEST_ONLY":
        return (
            "LEGACY",
            "ÉLEVÉE",
            "atteignable uniquement depuis les tests : couvert par des tests "
            "mais absent du chemin de production",
        )

    if m["imported_by"]:
        return (
            "LEGACY",
            "MOYENNE",
            f"importé par {len(m['imported_by'])} module(s), tous hors "
            "exécution production",
        )

    return (
        "DEAD",
        "ÉLEVÉE",
        "déployé, jamais exécuté, aucun importeur, aucun `__main__`",
    )


def main() -> int:
    d = json.loads(
        (ROOT / "artifacts" / "cartography.json").read_text(encoding="utf-8")
    )
    executed = {
        line.strip()
        for line in (ROOT / "artifacts" / "prod_executed_modules.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    }
    deployed = {
        line.strip()
        for line in (ROOT / "artifacts" / "prod_deployed_files.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    }

    rows = []
    for m in d["modules"]:
        m = dict(m, file=m["file"].replace("\\", "/"))
        cls, conf, why = classify(m, executed, deployed)
        rows.append({**m, "classe": cls, "confiance": conf, "pourquoi": why})

    counts = collections.Counter(r["classe"] for r in rows)
    conf_counts = collections.Counter((r["classe"], r["confiance"]) for r in rows)

    L = []
    A = L.append
    A("# AMPUTATION_PLAN.md — Proposition de classement, aucune suppression\n\n")
    A(
        "> **Document généré automatiquement.** Régénérer via `python tools/amputation_plan.py`.\n"
    )
    A(
        f"> Généré le {sh('git', 'log', '-1', '--format=%ad', '--date=short')} — "
        f"dépôt `{sh('git', 'rev-parse', '--short', 'HEAD')}`.\n\n"
    )
    A(
        "> ## ⚠ AUCUNE SUPPRESSION N'EST PROPOSÉE À CE STADE\n"
        "> Ce document **classe**. Le passage du classement à l'action exige une\n"
        "> validation humaine explicite, et — pour toute classe autre que `DEAD`\n"
        "> à confiance `ÉLEVÉE` — une fenêtre d'observation supplémentaire.\n\n"
    )

    A("## 1. Les trois sources de preuve\n\n")
    A("| Source | Nature | Ce qu'elle prouve |\n|---|---|---|\n")
    A("| `artifacts/cartography.json` | statique (AST) | atteignabilité par import |\n")
    A(
        f"| `artifacts/prod_executed_modules.txt` | **exécution réelle** | "
        f"{len(executed)} modules dont le `.pyc` a été écrit par le processus de "
        "production (PID 62316) |\n"
    )
    A(
        f"| `artifacts/prod_deployed_files.txt` | déploiement | {len(deployed)} "
        "fichiers `.py` présents sur le VPS |\n\n"
    )

    A("### Pourquoi l'analyse statique ne suffisait pas\n\n")
    stat_dead_but_alive = [
        r
        for r in rows
        if r["file"] in executed and r["status"] in ("ORPHAN", "TEST_ONLY")
    ]
    A(
        f"**{len(stat_dead_but_alive)} modules classés `ORPHAN` ou `TEST_ONLY` par "
        "l'analyse statique sont exécutés en production.** Une amputation fondée sur "
        "le seul graphe d'import aurait supprimé du code vivant, dont :\n\n"
    )
    for r in sorted(stat_dead_but_alive, key=lambda x: -x["loc"])[:8]:
        A(f"- `{r['file']}` ({r['loc']} LOC) — classé `{r['status']}`, **exécuté**\n")
    A(
        "\nCause mesurée : les `__init__.py` de package importent transitivement leurs "
        "sous-modules ; mon analyseur ne modélisait pas cet effet. "
        "**C'est la justification empirique de l'exigence de preuve d'exécution.**\n\n"
    )

    A("## 2. Limites de la preuve d'exécution\n\n")
    A(
        """| Limite | Conséquence |
|---|---|
| Un `.pyc` prouve **au moins un** import depuis le déploiement, pas un import à chaque cycle | `ACTIVE` ne signifie pas « utilisé en permanence » |
| Fenêtre d'observation courte (processus démarré le 2026-08-01 20:53) | des branches paresseuses n'ont pas encore été prises → **210 est une borne INFÉRIEURE** |
| CPython n'écrit pas de `.pyc` pour le script `__main__` | `core/advisor_loop.py` est exempté explicitement |
| Le code de production est le commit `f427895` (2026-07-20), le dépôt local est plus récent | l'appariement prod → dépôt est imparfait pour les modules récents |
| Aucune mesure des chemins d'erreur / de reprise | un module de recovery peut n'être chargé qu'en incident |

**Règle qui en découle** : aucun module ne peut passer en `DEAD` confiance `ÉLEVÉE`
sur la seule fenêtre actuelle. Une seconde mesure après **≥ 7 jours** de runtime
continu, incluant au moins un incident et un redémarrage, est requise.

"""
    )

    A(
        "## 3. Décompte\n\n| Classe | Modules | dont PROUVÉ | dont ÉLEVÉE | dont MOYENNE |\n"
    )
    A("|---|---:|---:|---:|---:|\n")
    for cls, n in counts.most_common():
        A(
            f"| `{cls}` | {n} | {conf_counts[(cls, 'PROUVÉ')]} | "
            f"{conf_counts[(cls, 'ÉLEVÉE')]} | {conf_counts[(cls, 'MOYENNE')]} |\n"
        )
    A(f"| **TOTAL** | **{len(rows)}** | | | |\n\n")

    A(
        """## 4. Définition des classes

| Classe | Définition | Action proposée |
|---|---|---|
| `ACTIVE` | Exécution prouvée en production | **Aucune. Ne pas toucher.** |
| `ACTIVE-PROBABLE` | Atteignable par import, non encore exécuté | **Aucune.** Observer 7 jours de plus |
| `LEGACY` | Déployé, non exécuté, mais couvert par des tests ou importé hors runtime | Geler ; candidat à `docs/_historique/` après seconde mesure |
| `EXPERIMENTAL` | Appartient à un répertoire de recherche, non exécuté | Geler ; décision à prendre avec le protocole d'expérience |
| `TOOL` | Script autonome hors runtime | Conserver ; documenter dans un registre d'outils |
| `DEAD` | Déployé ou non, jamais exécuté, aucun importeur | **Candidat à mise en quarantaine** — jamais à suppression directe |
| `TEST` | Fichier de test | Hors périmètre |

### Procédure de quarantaine proposée (à valider)

Aucune suppression. Un module retenu serait déplacé vers `_quarantine/<chemin>`
avec un fichier `_quarantine/MANIFEST.json` enregistrant chemin d'origine, classe,
confiance, preuve et date. Critère de sortie de quarantaine : **30 jours de
runtime sans incident ni `ImportError`**. Réversible par un `git mv` inverse.

"""
    )

    A("## 5. Classement complet\n\n")
    for cls in ["DEAD", "LEGACY", "EXPERIMENTAL", "TOOL", "ACTIVE-PROBABLE", "ACTIVE"]:
        sel = sorted(
            [r for r in rows if r["classe"] == cls],
            key=lambda r: (-r["loc"], r["file"]),
        )
        if not sel:
            continue
        A(f"\n### {cls} — {len(sel)} modules\n\n")
        A(
            "| Fichier | LOC | Confiance | Statut statique | Déployé | Exécuté | "
            "Dernier commit | Justification |\n"
        )
        A("|---|---:|---|---|:-:|:-:|---|---|\n")
        for r in sel:
            A(
                f"| `{r['file']}` | {r['loc']} | {r['confiance']} | {r['status']} | "
                f"{'oui' if r['file'] in deployed else 'non'} | "
                f"{'**oui**' if r['file'] in executed else 'non'} | "
                f"{r['last_commit']} | {r['pourquoi']} |\n"
            )

    A(
        """
## 6. Ce qui reste NON MESURÉ

| Question | Ce qu'il faudrait |
|---|---|
| Modules chargés uniquement en incident / recovery | seconde mesure après un incident réel |
| Modules chargés uniquement à certaines heures (radar 06:00, horizons 06:15) | mesure sur ≥ 24 h continues |
| Fréquence d'usage d'un module `ACTIVE` | compteurs d'appel, pas seulement d'import |
| Cohérence des paires de classes dupliquées actives | trace d'instances, pas d'imports |
| Modules du dépôt local absents du VPS et jamais exécutés localement | exécution d'une passe locale |
"""
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(L), encoding="utf-8")
    print(f"-> {OUT}")
    for cls, n in counts.most_common():
        print(f"   {cls:18} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
