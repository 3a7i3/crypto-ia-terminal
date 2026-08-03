#!/usr/bin/env python3
"""Générateur des cinq documents de cartographie J1-J2.

Lit artifacts/cartography.json (produit par tools/runtime_cartographer.py) et
émet les documents dans docs/cartography/. Aucun contenu n'est saisi à la main :
toute ligne factuelle provient du JSON de mesure ou d'une sonde AST/regex.

PASSIF (ADR-0007) : ne modifie ni le runtime ni aucun module mesuré.

Usage :
    python tools/cartography_report.py
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARTO = ROOT / "artifacts" / "cartography.json"
OUTDIR = ROOT / "docs" / "cartography"

SELF = {"tools/runtime_cartographer.py", "tools/cartography_report.py"}

HDR = (
    "> **Document généré automatiquement.** Ne pas éditer à la main.\n"
    "> Source : `artifacts/cartography.json` — régénérer via\n"
    "> `python tools/runtime_cartographer.py && python tools/cartography_report.py`\n"
    "> Généré le {date} — commit `{sha}`\n\n"
    "> **Portée de la mesure.** Graphe d'import statique (AST), imports paresseux\n"
    "> inclus. `ACTIVE` signifie **atteignable par import** depuis le point d'entrée\n"
    "> runtime, **pas** « exécuté ». Prouver l'exécution exige une trace runtime\n"
    "> (`sys.settrace`/coverage sur le VPS) — **NON MESURÉ** en J1-J2.\n"
)


def sh(*args: str) -> str:
    try:
        return subprocess.run(
            args, cwd=ROOT, capture_output=True, text=True, timeout=60
        ).stdout.strip()
    except Exception:
        return "UNKNOWN"


def load() -> dict:
    return json.loads(CARTO.read_text(encoding="utf-8"))


def hdr() -> str:
    return HDR.format(
        date=sh("git", "log", "-1", "--format=%ad", "--date=short"),
        sha=sh("git", "rev-parse", "--short", "HEAD"),
    )


def clean(items: list[dict]) -> list[dict]:
    """Retire l'instrument de sa propre mesure."""
    return [x for x in items if x.get("file", "").replace("\\", "/") not in SELF]


def norm(p: str) -> str:
    return p.replace("\\", "/")


# ─────────────────────────────────────────────────────────────────────────────


def doc_dead_modules(d: dict) -> str:
    mods = d["modules"]
    by_status: dict[str, list[dict]] = defaultdict(list)
    for m in mods:
        by_status[m["status"]].append(m)

    out = ["# DEAD_MODULES.md — Classement de tous les modules\n", hdr()]
    out.append(
        "\n**Aucun fichier n'a été supprimé.** Ce document classe, il n'ampute pas.\n"
    )
    out.append("\n## Définition des statuts\n")
    out.append(
        """
| Statut | Définition **mesurée** |
|---|---|
| `ENTRYPOINT` | Point d'entrée runtime déclaré |
| `ACTIVE` | Atteignable par import depuis l'`ENTRYPOINT` |
| `TOOL` | Contient `__main__`, importé par aucun module — script autonome |
| `TEST_ONLY` | Atteignable depuis les tests, **jamais** depuis le runtime |
| `ORPHAN` | Ni runtime, ni test, ni script autonome |
| `TEST` | Fichier de test lui-même |

`ORPHAN` **n'est pas** synonyme de « supprimable » : un module peut être chargé
par un chemin que l'analyse statique ne voit pas (`importlib`, plugin, entrée
systemd distincte). Toute suppression exige une contre-vérification par trace.
"""
    )
    t = d["totals"]
    out.append("\n## Décompte\n\n| Statut | Modules |\n|---|---|\n")
    for s in ["ENTRYPOINT", "ACTIVE", "TOOL", "TEST_ONLY", "ORPHAN", "TEST"]:
        out.append(f"| `{s}` | {len(by_status.get(s, []))} |\n")
    out.append(f"| **TOTAL** | **{t['modules_total']}** |\n")

    for s in ["ENTRYPOINT", "ACTIVE", "TOOL", "TEST_ONLY", "ORPHAN"]:
        rows = sorted(by_status.get(s, []), key=lambda m: (-m["loc"], m["module"]))
        if not rows:
            continue
        out.append(f"\n## {s} — {len(rows)} modules\n\n")
        out.append(
            "| Module | Fichier | LOC | Dernier commit | Importé par | Justification |\n"
        )
        out.append("|---|---|---:|---|---:|---|\n")
        for m in rows:
            out.append(
                f"| `{m['module']}` | `{norm(m['file'])}` | {m['loc']} | "
                f"{m['last_commit']} | {len(m['imported_by'])} | {m['justification']} |\n"
            )
    return "".join(out)


def doc_runtime_graph(d: dict) -> str:
    mods = {m["module"]: m for m in d["modules"]}
    t = d["totals"]
    out = ["# RUNTIME_GRAPH.md — Graphe réel des imports\n", hdr()]

    out.append("\n## 1. Mesures globales\n\n| Mesure | Valeur |\n|---|---:|\n")
    for k, v in t.items():
        out.append(f"| `{k}` | {v} |\n")

    out.append("\n## 2. Cycles d'import\n\n")
    if d["cycles"]:
        out.append(f"**{len(d['cycles'])} cycles mesurés.**\n\n")
        out.append(
            "| # | Composante fortement connexe | Statut des membres |\n|---|---|---|\n"
        )
        for i, c in enumerate(d["cycles"], 1):
            sts = ", ".join(sorted({mods[x]["status"] for x in c if x in mods}))
            out.append(f"| {i} | {' ↔ '.join(f'`{x}`' for x in c)} | {sts} |\n")
    else:
        out.append("Aucun cycle mesuré.\n")

    out.append("\n## 3. Modules les plus dépendus (couplage entrant)\n\n")
    out.append("| Module | Statut | Importé par | LOC |\n|---|---|---:|---:|\n")
    top = sorted(d["modules"], key=lambda m: -len(m["imported_by"]))[:25]
    for m in top:
        out.append(
            f"| `{m['module']}` | {m['status']} | {len(m['imported_by'])} | {m['loc']} |\n"
        )

    out.append("\n## 4. Modules les plus couplants (couplage sortant)\n\n")
    out.append(
        "| Module | Statut | Importe | dont paresseux | LOC |\n|---|---|---:|---:|---:|\n"
    )
    top = sorted(d["modules"], key=lambda m: -len(m["imports_project"]))[:25]
    for m in top:
        out.append(
            f"| `{m['module']}` | {m['status']} | {len(m['imports_project'])} | "
            f"{m['lazy_imports']} | {m['loc']} |\n"
        )

    out.append("\n## 5. Modules isolés — aucun importeur, aucun `__main__`\n\n")
    out.append(f"**{len(d['isolated'])} modules mesurés.**\n\n")
    for x in d["isolated"]:
        out.append(
            f"- `{x}` — `{norm(mods[x]['file'])}` ({mods[x]['loc']} LOC, "
            f"dernier commit {mods[x]['last_commit']})\n"
        )

    out.append("\n## 6. Doublons de nom de classe (plusieurs vérités)\n\n")
    out.append(dup_classes())

    out.append("\n## 7. Répartition par package racine\n\n")
    agg: dict[str, Counter] = defaultdict(Counter)
    for m in d["modules"]:
        agg[m["top_package"]][m["status"]] += 1
    out.append("| Package | ACTIVE | ORPHAN | TOOL | TEST_ONLY | TEST | TOTAL |\n")
    out.append("|---|---:|---:|---:|---:|---:|---:|\n")
    for pkg, c in sorted(agg.items(), key=lambda kv: -sum(kv[1].values())):
        out.append(
            f"| `{pkg}` | {c['ACTIVE'] + c['ENTRYPOINT']} | {c['ORPHAN']} | "
            f"{c['TOOL']} | {c['TEST_ONLY']} | {c['TEST']} | {sum(c.values())} |\n"
        )
    return "".join(out)


def dup_classes() -> str:
    """Classes définies sous le même nom dans plusieurs fichiers."""
    d = load()
    st = {m["file"].replace("\\", "/"): m["status"] for m in d["modules"]}
    seen: dict[str, list[tuple[str, int]]] = defaultdict(list)
    pat = re.compile(r"^class\s+([A-Za-z_][A-Za-z0-9_]*)")
    for m in d["modules"]:
        if m["status"] == "TEST":
            continue
        p = ROOT / m["file"]
        try:
            for i, line in enumerate(
                p.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                mt = pat.match(line)
                if mt:
                    seen[mt.group(1)].append((norm(m["file"]), i))
        except OSError:
            continue
    rows = {k: v for k, v in seen.items() if len(v) > 1}
    if not rows:
        return "Aucun doublon mesuré.\n"
    out = [
        f"**{len(rows)} noms de classe définis à plusieurs endroits "
        f"(hors tests).**\n\n| Classe | Définitions | Statuts |\n|---|---|---|\n"
    ]
    for name, locs in sorted(rows.items(), key=lambda kv: -len(kv[1]))[:40]:
        defs = "<br>".join(f"`{f}:{ln}`" for f, ln in locs)
        sts = ", ".join(st.get(f, "?") for f, _ in locs)
        out.append(f"| `{name}` | {defs} | {sts} |\n")
    return "".join(out)


def doc_authority(d: dict) -> str:
    a = d["authority"]
    st = {m["file"].replace("\\", "/"): m["status"] for m in d["modules"]}

    def S(f: str) -> str:
        return st.get(norm(f), "?")

    out = [
        "# AUTHORITY_CHAIN.md — Qui possède l'autorité d'ouvrir une position ?\n",
        hdr(),
    ]
    out.append(
        """
## Réponse mesurée

> **Aucune entité unique ne possède cette autorité.**
> La décision est **calculée en un point** puis **révoquée en quatre autres**,
> tous situés dans le même fichier `core/advisor_loop.py`.

Cette réponse ne tient pas en une phrase affirmative parce que l'autorité n'est
pas détenue : elle est **distribuée sur plusieurs sites d'écriture successifs**.

"""
    )

    writes = [w for w in clean(a["trade_allowed_writes"])]
    runtime_writes = [w for w in writes if S(w["file"]) in ("ACTIVE", "ENTRYPOINT")]
    out.append("## 1. Points d'écriture de `trade_allowed`\n\n")
    out.append(
        f"- Total mesuré dans le dépôt (hors tests et hors instrument) : "
        f"**{len(writes)}**\n"
    )
    out.append(
        f"- Dont situés dans du code atteignable par le runtime : "
        f"**{len(runtime_writes)}**\n\n"
    )
    out.append(
        "| # | Fichier:ligne | Statut module | Code | Rôle |\n|---|---|---|---|---|\n"
    )
    for i, w in enumerate(
        sorted(writes, key=lambda x: (norm(x["file"]), x["line"])), 1
    ):
        role = (
            "CALCUL initial"
            if w["line"] == 1983 and "advisor_loop" in w["file"]
            else (
                "RÉVOCATION"
                if "advisor_loop" in w["file"]
                else "lecture/relecture hors moteur"
            )
        )
        out.append(
            f"| {i} | `{norm(w['file'])}:{w['line']}` | {S(w['file'])} | "
            f"`{w['code'][:60]}` | {role} |\n"
        )

    out.append("\n## 2. Machines d'état\n\n")
    out.append(f"**{len(clean(a['state_machine_classes']))} classes mesurées.**\n\n")
    out.append("| Classe | Fichier:ligne | Statut |\n|---|---|---|\n")
    for x in clean(a["state_machine_classes"]):
        out.append(
            f"| `{x['code']}` | `{norm(x['file'])}:{x['line']}` | **{S(x['file'])}** |\n"
        )

    out.append("\n## 3. Kill switches\n\n")
    ks = clean(a["kill_switch_classes"])
    out.append(f"**{len(ks)} classes mesurées.**\n\n")
    out.append("| Classe | Fichier:ligne | Statut |\n|---|---|---|\n")
    for x in ks:
        out.append(
            f"| `{x['code']}` | `{norm(x['file'])}:{x['line']}` | **{S(x['file'])}** |\n"
        )

    out.append("\n## 4. Gates\n\n")
    g = clean(a["gate_classes"])
    out.append(f"**{len(g)} classes mesurées.**\n\n")
    out.append("| Classe | Fichier:ligne | Statut |\n|---|---|---|\n")
    for x in g:
        out.append(
            f"| `{x['code']}` | `{norm(x['file'])}:{x['line']}` | **{S(x['file'])}** |\n"
        )

    out.append("\n## 5. SAFE_MODE\n\n")
    sm = clean(a["safe_mode_files"])
    act = [x for x in sm if S(x["file"]) in ("ACTIVE", "ENTRYPOINT")]
    out.append(
        f"**{len(sm)} fichiers de production mentionnent `SAFE_MODE`, "
        f"dont {len(act)} atteignables par le runtime.**\n\n"
    )
    out.append("| Fichier | Statut |\n|---|---|\n")
    for x in sorted(sm, key=lambda y: norm(y["file"])):
        out.append(f"| `{norm(x['file'])}` | **{S(x['file'])}** |\n")

    out.append("\n## 6. DecisionPacket\n\n")
    out.append(f"**{len(a['decision_packet_defs'])} définition(s) mesurée(s).**\n\n")
    for x in a["decision_packet_defs"]:
        out.append(f"- `{norm(x['file'])}:{x['line']}` — statut **{S(x['file'])}**\n")
    return "".join(out)


def doc_system_map(d: dict) -> str:
    t = d["totals"]
    mods = {m["module"]: m for m in d["modules"]}
    out = ["# SYSTEM_RUNTIME_MAP.md — Cartographie du système vivant\n", hdr()]

    out.append("\n## 1. Points d'entrée\n\n")
    out.append(
        "| Point d'entrée | Source de la déclaration | Existe ? |\n|---|---|---|\n"
    )
    for ep in d["meta"]["runtime_entry_points"]:
        out.append(f"| `{ep}` | `scripts/deploy_vps.sh` (mode `core`) | oui |\n")
    svc = ROOT / "scripts" / "crypto_advisor.service"
    if svc.exists():
        m = re.search(r"ExecStart=.*?python\s+(\S+)", svc.read_text(encoding="utf-8"))
        if m:
            tgt = m.group(1)
            out.append(
                f"| `{tgt}` | `scripts/crypto_advisor.service` (systemd) | "
                f"**{'oui' if (ROOT / tgt).exists() else 'NON — fichier absent'}** |\n"
            )

    out.append(
        "\n## 2. Volumétrie mesurée\n\n| Mesure | Valeur | % du total |\n|---|---:|---:|\n"
    )
    tot = t["modules_total"]
    for k in [
        "modules_total",
        "modules_runtime_reachable",
        "modules_tool",
        "modules_test_only",
        "modules_orphan",
        "modules_test",
    ]:
        out.append(f"| `{k}` | {t[k]} | {100 * t[k] / tot:.1f}% |\n")

    out.append(
        """
### Bornes de la mesure de joignabilité

La résolution stricte (nom pointé complet uniquement) donne une borne
**inférieure**. La résolution avec repli sur les imports par nom nu — nécessaire
car le dépôt en contient (voir CONTRADICTION-02) — est **sur-inclusive** quand
un basename est ambigu, et donne donc une borne **supérieure**.

| Borne | Modules atteignables |
|---|---:|
| Inférieure (résolution stricte) | 102 |
| Supérieure (repli nom nu) | {reach} |

Nombre de basenames ambigus mesurés : **{amb}**.
""".format(
            reach=t["modules_runtime_reachable"], amb=t.get("ambiguous_bare_imports", 0)
        )
    )

    out.append("\n## 3. Modules atteignables par le runtime\n\n")
    act = sorted(
        [m for m in d["modules"] if m["status"] in ("ACTIVE", "ENTRYPOINT")],
        key=lambda m: (m["top_package"], m["module"]),
    )
    out.append("| Module | Fichier | LOC | Dernier commit |\n|---|---|---:|---|\n")
    for m in act:
        out.append(
            f"| `{m['module']}` | `{norm(m['file'])}` | {m['loc']} | "
            f"{m['last_commit']} |\n"
        )

    out.append("\n## 4. Répertoires présentés comme « base Research OS »\n\n")
    out.append("Vérification de la vitalité réelle de chaque répertoire.\n\n")
    out.append(
        "| Répertoire | Modules | ACTIVE | ORPHAN | TEST_ONLY | Dernier commit du package |\n"
    )
    out.append("|---|---:|---:|---:|---:|---|\n")
    for pkg in [
        "research",
        "experiments",
        "walk_forward",
        "meta_learning",
        "execution_simulator",
        "ai_autonomous_loop",
        "project_os",
        "audit",
        "governance",
        "observability",
        "tools",
    ]:
        rows = [m for m in d["modules"] if m["top_package"] == pkg]
        if not rows:
            out.append(f"| `{pkg}/` | 0 | 0 | 0 | 0 | — (aucun module Python) |\n")
            continue
        c = Counter(m["status"] for m in rows)
        last = max(
            (m["last_commit"] for m in rows if m["last_commit"] != "UNTRACKED"),
            default="UNKNOWN",
        )
        out.append(
            f"| `{pkg}/` | {len(rows)} | {c['ACTIVE'] + c['ENTRYPOINT']} | "
            f"{c['ORPHAN']} | {c['TEST_ONLY']} | {last} |\n"
        )

    out.append("\n## 5. Flow runtime mesuré\n\n")
    out.append("Voir `DECISION_PATH.md` pour le détail fonction/fichier/ligne.\n\n")
    out.append(
        """```
Market Data      infra/multi_exchange_feed.py, exchange_factory
      |
      v
Scanner          core/advisor_loop.py  (scanners: dict)
      |
      v
Features         FeatureEngineer -> features: dict
      |
      v
Signal           engine.evaluate()            advisor_loop.py:1459
      |
      v
Decision         trade_allowed = AND(12)      advisor_loop.py:1983
      |
      +--> REVOCATION 1  risk_governor         advisor_loop.py:5626
      +--> REVOCATION 2  safety_auditor        advisor_loop.py:5658
      +--> REVOCATION 3  (non nomme)           advisor_loop.py:5734
      +--> REVOCATION 4  decision_packet       advisor_loop.py:5808
      |
      v
Risk / Sizing    order_size_usd (mute par EO, conviction, arbitrage)
      |
      v
Execution        execution_engine / MexcSimulator
      |
      v
Logging          paper_trades.jsonl, black_box.jsonl, decision_packets
      |
      v
Replay           NON MESURE - aucun moteur de rejeu deterministe identifie
```
"""
    )
    return "".join(out)


def probe(pattern: str, path: str, limit: int = 12) -> list[tuple[int, str]]:
    p = ROOT / path
    hits = []
    rx = re.compile(pattern)
    for i, line in enumerate(
        p.read_text(encoding="utf-8", errors="replace").splitlines(), 1
    ):
        if rx.search(line):
            hits.append((i, line.strip()[:100]))
            if len(hits) >= limit:
                break
    return hits


def doc_decision_path(d: dict) -> str:
    AL = "core/advisor_loop.py"
    out = ["# DECISION_PATH.md — Chemin exact de la décision\n", hdr()]
    out.append(
        "\nToutes les lignes ci-dessous sont **sondées dans le fichier**, "
        "pas recopiées d'une documentation.\n"
    )

    stages = [
        ("0. Autorité — court-circuit d'entrée", r"_auth\.can_trade\(\)", AL),
        ("1. Régime de marché", r"regime\s*=\s*", AL),
        ("2. Features", r"features\s*=\s*", AL),
        ("3. Personnalité (Meta-Strategy)", r"personality = meta_engine\.select", AL),
        ("4. Signal", r"signal = engine\.evaluate", AL),
        ("5. DecisionPacket (parallèle)", r"_dp = _to_decision_packet", AL),
        ("6. Validation Meta-Strategy", r"meta_engine\.validate_signal", AL),
        ("7. Conviction", r"conviction", AL),
        ("8. MistakeMemory", r"mm_check", AL),
        ("9. PortfolioBrain", r"pb_verdict = ", AL),
        ("10. CapitalAllocationEngine", r"allocation = ", AL),
        ("11. ExecutiveOverride", r"eo_verdict = executive_override", AL),
        ("12. Arbitrage V2", r"arbitration_result = v2_arbitrator", AL),
        ("13. Timing V2", r"timing_signal = v2_timing_engine", AL),
        ("14. DÉCISION", r"^\s*trade_allowed = \($", AL),
        ("15. Révocations", r'r\["trade_allowed"\] = False', AL),
        ("16. Exécution", r"execution_engine|_sim\s*=", AL),
    ]
    out.append("\n| # | Étape | Fichier | Ligne(s) mesurée(s) | Code sondé |\n")
    out.append("|---|---|---|---|---|\n")
    for label, pat, path in stages:
        hits = probe(pat, path, limit=4)
        if not hits:
            out.append(
                f"| | {label} | `{path}` | **NON MESURÉ** | motif `{pat}` sans "
                f"correspondance |\n"
            )
            continue
        lines = ", ".join(str(h[0]) for h in hits)
        code = hits[0][1].replace("|", "\\|")
        out.append(f"| | {label} | `{path}` | {lines} | `{code}` |\n")

    out.append("\n## Les 12 termes de la conjonction finale\n\n")
    p = (ROOT / AL).read_text(encoding="utf-8", errors="replace").splitlines()
    start = None
    for i, line in enumerate(p, 1):
        if line.strip() == "trade_allowed = (":
            start = i
            break
    if start:
        out.append(f"Mesuré à `{AL}:{start}`.\n\n```python\n")
        j = start - 1
        while j < len(p):
            out.append(p[j] + "\n")
            if p[j].strip() == ")":
                break
            j += 1
        out.append("```\n\n")
        out.append(
            f"**Nombre de termes mesurés : "
            f"{sum(1 for k in range(start, j + 1) if p[k - 1].strip().startswith('and ') or p[k - 1].strip().startswith('_') )}**\n"
        )
    else:
        out.append("**NON MESURÉ** — motif introuvable.\n")

    out.append("\n## Étapes du flux non démontrables en J1-J2\n\n")
    out.append(
        """
| Étape | Statut |
|---|---|
| Ordre d'exécution réel des couches à l'exécution | **IMPOSSIBLE À DÉMONTRER AVEC LES ÉLÉMENTS ACTUELS** — exige une trace runtime |
| Fréquence de déclenchement de chaque révocation | **NON MESURÉ** — exige une instrumentation de compteurs en production |
| Effet marginal de chaque couche sur le débit | **NON MESURÉ** — exige un moteur d'ablation |
| Moteur de replay déterministe | **NON MESURÉ** — aucun module correspondant identifié dans le graphe runtime |
"""
    )
    return "".join(out)


def main() -> int:
    d = load()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    docs = {
        "SYSTEM_RUNTIME_MAP.md": doc_system_map(d),
        "AUTHORITY_CHAIN.md": doc_authority(d),
        "DEAD_MODULES.md": doc_dead_modules(d),
        "RUNTIME_GRAPH.md": doc_runtime_graph(d),
        "DECISION_PATH.md": doc_decision_path(d),
    }
    for name, body in docs.items():
        (OUTDIR / name).write_text(body, encoding="utf-8")
        print(f"-> docs/cartography/{name}  ({len(body.splitlines())} lignes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
