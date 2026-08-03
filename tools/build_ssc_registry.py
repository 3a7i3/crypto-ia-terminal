# -*- coding: utf-8 -*-
"""Assemble le registre d'invariants du SSC depuis la sortie du workflow."""
import json
import re
from collections import Counter
from pathlib import Path

OUT = Path(
    r"C:\Users\WINDOWS\AppData\Local\Temp\claude\C--Users-WINDOWS-crypto-ai-terminal\5b963306-be6b-4c67-922d-86de20df7171\tasks\wgz3sct60.output"
)
DEST = Path(
    r"C:\Users\WINDOWS\crypto_ai_terminal\docs\v5\SCIENTIFIC_SAFETY_CONTRACT.md"
)

raw = OUT.read_text(encoding="utf-8", errors="replace")
i = raw.find('{"survivors"')
if i < 0:
    i = raw.find('"survivors"')
    i = raw.rfind("{", 0, i)
dec = json.JSONDecoder()
data, _ = dec.raw_decode(raw[i:])

survivors = data["survivors"]
stats = data.get("stats", {})

DOMAIN_LABEL = {
    "D1-autorite-decision": ("D1", "Autorité d'exécution et décision"),
    "D2-etat-arret-securite": ("D2", "État runtime, arrêt d'urgence, sécurité"),
    "D3-deployment": ("D3", "Deployment"),
    "D4-epoch-dataset": ("D4", "Research Epoch et Dataset"),
    "D5-experiment-replay": ("D5", "Experiment, Replay, Ablation"),
    "D6-evidence-calibration-policy": ("D6", "Evidence, Calibration, Policy"),
    "D7-provenance-graph-memoire": ("D7", "Provenance, Graphe, Mémoire, Conseil"),
}

# --- Corrections d'autorité (jugement du Chief Scientist, tracées) -----------
# SSC-R4 : ENFORCED_ALL interdit si l'invariant est actuellement VIOLÉ.
DEMOTE = {
    "Systemd ExecStart Path Exists": (
        "OBSERVED",
        "violé aujourd'hui (ExecStart=advisor_loop.py inexistant) — SSC-R4 interdit ENFORCED_ALL",
    ),
    "Single Instantiated Kill Switch": (
        "OBSERVED",
        "clause d'import violée (2 modules kill switch exécutés) — SSC-R4",
    ),
    "No Online Learning In Decision Path": (
        "OBSERVED",
        "clause large non adossée à une mesure — SSC-R4",
    ),
    "Audit Tag Truthfulness": (
        "OBSERVED",
        "rouge à perpétuité si universel sur l'historique — portée à restreindre au neuf avant promotion",
    ),
    "Epoch Boundary Requires Existing ADR": (
        "OBSERVED",
        "clause auto-bloquante signalée par le critique",
    ),
    "Human Merge Only": (
        "OBSERVED",
        "clause historique rouge au premier balayage — scinder avant promotion",
    ),
    "Single Clean Boundary Source": (
        "OBSERVED",
        "proxy à fort taux de faux positifs signalé par le critique",
    ),
}
# Doublons signalés par le critique : on conserve le premier, on note la fusion.
MERGE = {
    ("D6", "Hard Veto Cap"): "D1/Hard Veto Cap",
    ("D3", "Service Unit Truthfulness"): "D2/Systemd ExecStart Path Exists",
    ("D3", "Single Decision Engine Host"): "D2/Single Live Engine Instance",
}

# --- Invariants manquants identifiés par le critique de complétude ----------
# Chacun comble un fait mesuré que la campagne de rédaction n'avait couvert
# par aucun invariant. Domaine D8 : intégrité de l'instrument de mesure.
EXTRA = [
    {
        "domain": "D8-meta-instrument",
        "invariants": [
            {
                "name": "Executed Module Inventory Is A Versioned Artifact",
                "objet": "Inventaire des modules réellement exécutés en production (mesure .pyc)",
                "enonce": "L'inventaire des modules exécutés en production est un artefact versionné du dépôt, portant sa date de mesure, l'hôte mesuré et le commit exécuté, produit par une procédure rejouable. Tout contrôle du contrat dont le périmètre est « les modules exécutés en production » cite l'identifiant de cet artefact et échoue si l'artefact est absent ou antérieur au dernier déploiement. Aucun contrôle ne substitue une approximation statique à cet artefact.",
                "etat": "OBSERVED",
                "justification_etat": "Le contrôle (présence, datation, fraîcheur) est exécutable aujourd'hui et échoue immédiatement : la mesure des 210 modules existe, l'artefact versionné non.",
                "preuve_actuelle": "210 modules exécutés mesurés sur 1115 ; borne statique 102-170 ; 52 modules classés ORPHAN/TEST_ONLY par le statique sont exécutés en prod. Rejouabilité de la mesure : NON MESURÉE.",
                "test_futur": "Contrôle de présence et de fraîcheur de l'artefact ; contrôle de reproductibilité (seconde mesure sur le même hôte redonnant le même ensemble) ; analyse statique du contrat vérifiant que tout invariant à périmètre « modules exécutés » référence l'artefact.",
                "portee_blocage": "deploiement",
                "depend_de": ["Production Code Fingerprint"],
                "_verdict": "AJOUT_CRITIQUE",
            },
            {
                "name": "No Import Cycle In Decision Closure",
                "objet": "Graphe d'import des modules exécutés en production",
                "enonce": "La fermeture d'import du point d'entrée core/advisor_loop.py ne contient aucune composante fortement connexe de taille supérieure à un.",
                "etat": "OBSERVED",
                "justification_etat": "Détection exécutable aujourd'hui, et violée : l'un des 3 cycles mesurés relie core.decision_packet, module des révocations :5734 et :5808. Casser ce cycle exige une refonte non décidée.",
                "preuve_actuelle": "3 cycles d'import mesurés, dont core.decision_packet <-> core.lifecycle ; core.decision_packet écrit le verdict à core/advisor_loop.py:5734 et :5808. Effet sur l'ordre d'initialisation : NON MESURÉ.",
                "test_futur": "Extraction des composantes fortement connexes du graphe d'import, intersection avec la fermeture du point d'entrée. Cliquet complémentaire : le compte total de cycles ne peut dépasser 3.",
                "portee_blocage": "merge",
                "depend_de": ["Executed Module Inventory Is A Versioned Artifact"],
                "_verdict": "AJOUT_CRITIQUE",
            },
            {
                "name": "No sys.path Dependent Internal Import",
                "objet": "Clauses d'import des modules exécutés en production",
                "enonce": "Aucun module exécuté en production n'importe un autre module du dépôt par nom nu : toute importation interne est qualifiée par son paquet, de sorte que l'ensemble des modules chargés soit fonction du seul contenu des fichiers et non du répertoire de lancement.",
                "etat": "OBSERVED",
                "justification_etat": "Analyse statique exécutable aujourd'hui, violée par au moins une occurrence mesurée. Le nombre total d'occurrences n'est pas encore connu.",
                "preuve_actuelle": "core/advisor_loop.py:33 fait « from advisor_runtime_adapters import ... », nom nu résolu par sys.path. Nombre total d'occurrences dans les 210 modules exécutés : NON MESURÉ.",
                "test_futur": "Analyse statique des clauses d'import des modules de l'inventaire d'exécution ; échec pour tout nom importé correspondant à un fichier du dépôt sans être qualifié par son paquet.",
                "portee_blocage": "merge",
                "depend_de": ["Executed Module Inventory Is A Versioned Artifact"],
                "_verdict": "AJOUT_CRITIQUE",
            },
            {
                "name": "Single Definition For Executed Record Types",
                "objet": "Types de données du chemin d'enregistrement (TradeRecord, Position, PortfolioSnapshot, MarketSnapshot, Alert, ValidationResult)",
                "enonce": "Aucun nom de la liste fermée et versionnée des types d'enregistrement n'est défini par deux modules simultanément exécutés en production ; tous les enregistrements d'une même époque partagent le même ensemble de champs.",
                "etat": "OBSERVED",
                "justification_etat": "Mesurable aujourd'hui et violé : 6 des 8 paires doublement exécutées sont des types d'enregistrement. La déduplication impose des renommages dans le chemin d'exécution.",
                "preuve_actuelle": "8 paires dont les DEUX définitions sont exécutées en prod, dont TradeRecord, Position, PortfolioSnapshot, MarketSnapshot, Alert, ValidationResult ; 69 noms dupliqués hors tests. Laquelle des deux définitions de TradeRecord a écrit chacun des 139 trades V4 : NON MESURÉ.",
                "test_futur": "Index des définitions croisé avec l'inventaire d'exécution ; échec si un nom de la liste fermée a plus d'une définition exécutée. Cliquet : le compte de noms dupliqués hors tests ne peut dépasser 69.",
                "portee_blocage": "merge",
                "depend_de": ["Executed Module Inventory Is A Versioned Artifact"],
                "_verdict": "AJOUT_CRITIQUE",
            },
            {
                "name": "Evaluation Horizon Covered By Realized Holding",
                "objet": "Horizon d'évaluation de la spec scellée et distribution de détention réalisée du corpus",
                "enonce": "La spec scellée déclare, avant exécution, l'horizon d'évaluation et le critère de couverture par la distribution de détention réalisée du corpus. Tout verdict dont l'horizon d'évaluation ne satisfait pas le critère déclaré est INCONCLUSIVE et porte l'entrée de limitation « horizon d'information ».",
                "etat": "DESIGNED",
                "justification_etat": "Ni ExperimentSpec exécutable, ni Corpus, ni Verdict n'existent : les deux termes de la comparaison sont absents. Le fait mesuré montre que la propriété est aujourd'hui fausse, mais aucun objet ne permet de l'évaluer.",
                "preuve_actuelle": "Le score ne classe rien à <=1h et classe faiblement à 12-24h (rho=0.16, AUC=0.60) alors que la détention réalisée est de 5.92h ; N=139 époque V4, 0 verdict. Aucun artefact ne rapproche ces deux horizons.",
                "test_futur": "Comparaison numérique, à l'agrégation du verdict, entre l'horizon déclaré dans la spec scellée et les quantiles de détention du corpus référencé ; dégradation automatique et journalisée en INCONCLUSIVE hors critère.",
                "portee_blocage": "experience",
                "depend_de": ["Single Primary Metric", "Frozen Corpus Content Hash"],
                "_verdict": "AJOUT_CRITIQUE",
            },
            {
                "name": "Single Fingerprint Canonicalization Spec",
                "objet": "Règle de calcul d'empreinte utilisée par tous les contrôles de hachage",
                "enonce": "Il existe une seule spécification versionnée de canonicalisation d'empreinte (encodage, fins de ligne, ordre de parcours, exclusions) ; tout contrôle du contrat qui hache un fichier ou un ensemble de fichiers la référence et n'en définit pas une autre.",
                "etat": "OBSERVED",
                "justification_etat": "Huit invariants du contrat hachent, aucun ne possède la règle. Mesurable immédiatement par lecture du contrat lui-même ; violé dès aujourd'hui.",
                "preuve_actuelle": "Le commit de production f427895 n'a pu être identifié que par md5 NORMALISÉ LF — l'identité octet à octet ne survit pas au chemin de déploiement (taille locale 345307 contre 342959 en production).",
                "test_futur": "Analyse statique du registre d'invariants : tout contrôle de hachage référence l'identifiant de la spécification de canonicalisation ; échec sinon.",
                "portee_blocage": "commit",
                "depend_de": [],
                "_verdict": "AJOUT_CRITIQUE",
            },
            {
                "name": "Safe Mode Halt Proof",
                "objet": "Effet de SAFE_MODE sur l'ouverture de position",
                "enonce": "Lorsque SAFE_MODE est actif, aucune ouverture de position n'est émise : l'ensemble des verdicts d'exécution produits pendant une fenêtre SAFE_MODE est vide.",
                "etat": "OBSERVED",
                "justification_etat": "Un pendant existe pour le kill switch mais pas pour SAFE_MODE, alors que SAFE_MODE est écrit dans 18 fichiers de production dont 8 atteignables. L'effet réel n'a jamais été mesuré.",
                "preuve_actuelle": "SAFE_MODE présent dans 18 fichiers de production, 8 atteignables par le runtime ; 2 machines d'état simultanément exécutées en portent chacune une notion. Effet sur l'émission d'ordres : NON MESURÉ.",
                "test_futur": "Vérification d'intégrité sur le journal de décisions : intersection entre les fenêtres SAFE_MODE et les verdicts d'ouverture émis ; échec si non vide.",
                "portee_blocage": "experience",
                "depend_de": ["Single Runtime State Machine"],
                "_verdict": "AJOUT_CRITIQUE",
            },
        ],
    }
]

DOMAIN_LABEL["D8-meta-instrument"] = (
    "D8",
    "Intégrité de l'instrument de mesure (manques comblés)",
)

rows = []
seen_names = {}
for d in survivors + EXTRA:
    code, label = DOMAIN_LABEL.get(d["domain"], (d["domain"], d["domain"]))
    for inv in d["invariants"]:
        name = inv["name"]
        key = (code, name)
        merged_into = MERGE.get(key)
        etat = inv["etat"]
        note = ""
        if name in DEMOTE:
            etat, note = DEMOTE[name]
        rows.append(
            {
                "domain_code": code,
                "domain_label": label,
                "name": name,
                "objet": inv.get("objet", ""),
                "enonce": re.sub(r"\s+", " ", inv.get("enonce", "")).strip(),
                "etat": etat,
                "etat_origine": inv["etat"],
                "correction": note,
                "justification_etat": re.sub(
                    r"\s+", " ", inv.get("justification_etat", "")
                ).strip(),
                "preuve": re.sub(r"\s+", " ", inv.get("preuve_actuelle", "")).strip(),
                "test": re.sub(r"\s+", " ", inv.get("test_futur", "")).strip(),
                "portee": inv.get("portee_blocage", ""),
                "depend": inv.get("depend_de") or [],
                "verdict": inv.get("_verdict", "NON_VERIFIE"),
                "preuve_suspecte": bool(inv.get("_preuve_suspecte")),
                "merged_into": merged_into,
            }
        )
        seen_names.setdefault(name, []).append(code)

active = [r for r in rows if not r["merged_into"]]
# numérotation par domaine
counters = Counter()
for r in active:
    counters[r["domain_code"]] += 1
    r["id"] = f"SSC-{r['domain_code']}-{counters[r['domain_code']]:02d}"

by_state = Counter(r["etat"] for r in active)
by_verdict = Counter(r["verdict"] for r in active)
suspect = [r for r in active if r["preuve_suspecte"]]
demoted = [r for r in active if r["correction"]]
merged = [r for r in rows if r["merged_into"]]
dup_names = {n: c for n, c in seen_names.items() if len(c) > 1}

L = []
A = L.append
A("\n---\n\n## 4. Registre des invariants\n\n")
A(
    f"**{len(active)} invariants**, produits par une campagne en trois passes : rédaction par domaine, "
    "vérification adverse invariant par invariant, puis critique de complétude et de doublons.\n\n"
)

A("### 4.1 Traçabilité de la production\n\n| Étape | Résultat |\n|---|---:|\n")
A(f"| Invariants rédigés | {stats.get('totalWritten', '?')} |\n")
A(f"| Rejetés par la vérification adverse | {stats.get('rejected', '?')} |\n")
A(f"| Signalés avec preuve suspecte | {stats.get('fabricated', '?')} |\n")
A(f"| Fusionnés comme doublons | {len(merged)} |\n")
A(f"| **Retenus au registre** | **{len(active)}** |\n\n")

A(
    "Verdicts de la passe adverse sur les invariants retenus :\n\n| Verdict | Nombre |\n|---|---:|\n"
)
for v, n in by_verdict.most_common():
    A(f"| `{v}` | {n} |\n")
A(
    "\n`CORRIGER` signifie que l'énoncé ou l'état a été amendé par le vérificateur, pas que "
    "l'invariant est douteux. Les corrections sont intégrées ci-dessous.\n\n"
)

A("### 4.2 Répartition par état\n\n| État | Nombre | Part |\n|---|---:|---:|\n")
tot = len(active)
for s in ["DESIGNED", "OBSERVED", "ENFORCED_NEW", "ENFORCED_ALL"]:
    n = by_state.get(s, 0)
    A(f"| `{s}` | {n} | {100*n/tot:.0f} % |\n")
A(f"| **Total** | **{tot}** | |\n\n")

A("### 4.3 Corrections d'autorité appliquées après la campagne\n\n")
A(
    "Le critique a établi que plusieurs invariants étaient placés en `ENFORCED_*` alors qu'ils sont "
    "**actuellement violés** — ce que SSC-R4 interdit, sous peine d'une CI rouge dès le premier jour "
    "et d'un contrat désactivé dans la semaine. Rétrogradations appliquées :\n\n"
)
A("| Invariant | État proposé | État retenu | Motif |\n|---|---|---|---|\n")
for r in demoted:
    A(
        f"| `{r['name']}` | {r['etat_origine']} | **{r['etat']}** | {r['correction']} |\n"
    )
A("\n")

if merged:
    A("Doublons fusionnés :\n\n| Invariant retiré | Fusionné dans |\n|---|---|\n")
    for r in merged:
        A(f"| `{r['domain_code']}/{r['name']}` | `{r['merged_into']}` |\n")
    A("\n")

if suspect:
    A(f"### 4.4 Preuves à revérifier — {len(suspect)} invariants\n\n")
    A(
        "Le vérificateur adverse a signalé que la preuve citée mentionne un fichier, une ligne ou un "
        "chiffre **absent du corpus de faits mesurés**. Ces invariants sont conservés — leur énoncé "
        "reste valable — mais leur champ *preuve* doit être re-mesuré avant toute promotion d'état. "
        "**Aucun d'eux ne peut passer en `ENFORCED_*` en l'état.**\n\n"
    )
    A("| ID | Invariant | État |\n|---|---|---|\n")
    for r in suspect:
        A(f"| `{r['id']}` | {r['name']} | {r['etat']} |\n")
    A("\n")

A("### 4.5 Table de synthèse\n\n")
A("| ID | Nom | Objet | État | Portée |\n|---|---|---|---|---|\n")
for r in active:
    flag = " ⚠" if r["preuve_suspecte"] else ""
    A(
        f"| `{r['id']}` | {r['name']}{flag} | {r['objet'][:60]} | `{r['etat']}` | {r['portee']} |\n"
    )
A("\n⚠ = preuve à revérifier (§4.4)\n\n---\n\n## 5. Registre détaillé\n")

cur = None
for r in active:
    if r["domain_code"] != cur:
        cur = r["domain_code"]
        A(f"\n### {cur} — {r['domain_label']}\n")
    A(f"\n#### `{r['id']}` — {r['name']}\n\n")
    A(f"| | |\n|---|---|\n")
    A(f"| **Objet** | {r['objet']} |\n")
    A(
        f"| **État** | `{r['etat']}`{' *(rétrogradé depuis ' + r['etat_origine'] + ')*' if r['correction'] else ''} |\n"
    )
    A(f"| **Portée du blocage** | {r['portee']} |\n")
    if r["depend"]:
        A(f"| **Dépend de** | {', '.join('`' + x + '`' for x in r['depend'])} |\n")
    A(f"\n**Énoncé.** {r['enonce']}\n\n")
    A(f"**Justification de l'état.** {r['justification_etat']}\n\n")
    pv = r["preuve"]
    if r["preuve_suspecte"]:
        pv = "⚠ **À REVÉRIFIER** — " + pv
    A(f"**Preuve actuelle.** {pv}\n\n")
    A(f"**Contrôle futur.** {r['test']}\n")

A(
    """
---

## 6. Fusions restant à appliquer avant adoption

Le critique de complétude a identifié **13 fusions nettes** ; **3 seulement sont
appliquées** dans le registre ci-dessus, les autres exigeant un arbitrage sur
l'énoncé conservé. Le registre est donc à 117 invariants là où la cible est
d'environ 104. Ces fusions doivent être tranchées avant toute promotion d'état,
sous peine de faire échouer plusieurs contrôles pour un seul défaut.

| Famille | Invariants concernés | Décision attendue |
|---|---|---|
| Citation d'ADR | `Cited ADR Exists` (D4) + `Cited ADR Must Exist` (D6) + `Cited Norm Exists` (D7) | garder un seul propriétaire — 3 échecs CI pour le seul défaut ADR-0018 |
| `FORCE_TEST_EXECUTION` | 6 invariants dans 4 domaines pour un seul fait mesuré | 3 propriétaires : contrôle statique, refus de démarrage, marquage du trade |
| Sites d'écriture du verdict | `Single Decision Writer`, `Decision Write Site Ratchet`, `State Machine Never Writes Decision`, clause (a) de `Replay Authority Identity`, `No AI Decision Authority` | conserver la cible + le cliquet ; les trois autres sont impliqués |
| Auto-calibration | `No Online Learning In Decision Path` (D1) + `No Runtime Auto Calibration` (D6) | D6 disparaît, ses deux clauses sont déjà portées ailleurs |
| Fidélité du simulateur | `Simulator Fidelity Disclosure` (D5) + `Replay Verdict Declares Simulator Fidelity Gap` (D6) | états contradictoires (ENFORCED_ALL vs DESIGNED) à réconcilier |
| Source unique de la borne | `Single Clean Boundary Source` (D4) + `Experiment Corpus Bound Single Source` (D5) + clause (b) de `Epoch Boundary Requires Existing ADR` (D6) | D5 a un périmètre **vide** (`experiments/` = 0 module Python) |
| Identifiant permanent | `Unique Deployment Identity` (D3) + `Epoch Id Uniqueness` (D4) + `Permanent Object Identifier` (D7) | un seul propriétaire (D7) ; les deux autres gardent leur clause propre |
| Scellement de spec | `Verdict Immutability`, `Succession Not Mutation`, `Experiment Preregistration Precedence`, `Stopping Rule Preregistered`, `Ablation Groups Preregistered` | un invariant `Sealed Spec Immutability` cité par les autres |
| Limitations obligatoires | `Verdict Limitations Not Empty` (D6) ⊂ `Mandatory Provenance Block` (D7) ⊃ `Mandatory Limitations Field` (D7) | trois expressions de la même règle |
| Séparation des rôles | `Three Role Separation` (D6) ↔ `No Self Validation` (D7) | **ne pas fusionner** — délimiter : D6 = paramètres, D7 = chaîne scientifique |

Une **collision de nom** subsiste dans le registre lui-même : `Hard Veto Cap`
existe en D1 et en D6. C'est exactement le défaut que `Permanent Object
Identifier` prétend interdire — et l'homologue du doublon `0008` déjà mesuré
dans `docs/adr/`.

---

## 7. Lot de verrouillage jour 0

Ce qui est **gratuit aujourd'hui** et doit être verrouillé avant de devenir
coûteux (SSC-R4). Par coût croissant :

| # | Invariant | Coût | Pourquoi maintenant |
|---|---|---|---|
| 1 | `Deploy Script Stdin Safety` | un balayage | Garde exactement le vecteur de l'incident du 2026-07-09 (`ssh` sans `-n`, 55 fichiers sur 80 non déployés, 3 tags mensongers, SEC-01 inactif) |
| 2 | `Systemd ExecStart Path Exists` | une ligne de `scripts/crypto_advisor.service` | Le fichier versionné déclare un exécutable inexistant |
| 3 | `No Online Learning` réduit aux deux drapeaux mesurés | nul | Déjà satisfait (`config/feature_flags.py:47,50`, consommateur unique, delta nul) |
| 4 | `Human Merge Only`, clause branche uniquement | lecture d'une configuration | **Le coût de ce verrou croît strictement avec le temps** — aucun agent ne fusionne aujourd'hui |
| 5 | `Single Live Engine Instance` | écrire la sonde d'inventaire | Satisfait depuis la suppression de l'ancienne VM ; c'est la seule forme de contrôle qui aurait détecté le service `enabled` oublié |
| 6 | `No Environment Bypass` | retrait d'un bloc localisé (`:1943-1980`) | Ce seul geste rend verrouillables quatre invariants du quadruplet `FORCE_TEST_EXECUTION` |

### Deux anomalies de répartition à corriger

- **D7 ne bloque jamais rien** : 18 invariants, aucun `ENFORCED_*`. Le domaine
  de la provenance et de la mémoire — celui qui porte l'indépendance aux
  modèles — est intégralement déclaratif.
- **D3 non plus** : aucun `ENFORCED_ALL`, alors que c'est le seul domaine
  adossé à un incident aux dégâts matériels prouvés. **Le contrat est le plus
  mou exactement là où l'historique est le plus chargé.**

---

## 8. Ce que le contrat ne couvrira pas

**8.1 La véracité sémantique d'un commentaire.** Le fait mesuré
`core/advisor_loop.py:1962` — un commentaire affirmant que l'arbitrage
« remplace la logique dispersée » alors que le code à `:1996` l'**ajoute** au ET
— n'est pas décidable mécaniquement. Le seul contrôle honnête est le cliquet sur
le nombre de termes de la conjonction. Déclaré **hors périmètre**, explicitement,
plutôt que laissé en trou implicite.

**8.2 Le contournement d'un cliquet sans le violer.** Déplacer une révocation
dans une fonction auxiliaire, renommer la variable porteuse ou construire une
clé de dictionnaire dynamiquement laisse le compte à 5. Les cliquets sont des
garde-fous anti-régression, **jamais des preuves d'unicité**.

**8.3 L'antidatage d'un pré-enregistrement.** `submitted_at` est auto-déclaré
dans un fichier que l'auteur contrôle. Seul un horodatage externe (signature
git, ancrage tiers) le rendrait opposable — hors périmètre à ce stade.

**8.4 La qualité d'une question de recherche.** Aucun invariant ne distingue une
question féconde d'une question anodine.

---

## 9. Prochaine étape

La spécification est complète ; **aucun test n'est écrit**. L'étape suivante,
distincte et à valider séparément, est l'écriture des contrôles — en commençant
par le lot de verrouillage du §7, seul ensemble dont l'activation laisse la CI
verte au premier jour.

Prérequis avant écriture : trancher les fusions du §6, re-mesurer les preuves
signalées au §4.4, et produire l'artefact d'inventaire d'exécution
(`SSC-D8-01`), dont **douze invariants dépendent** pour définir leur périmètre.
"""
)

body = "".join(L)
existing = DEST.read_text(encoding="utf-8")
existing = existing.split("## 4. Registre des invariants")[0].rstrip()
existing = existing.replace(
    "*(Section produite par la campagne de rédaction — voir §5 et suivantes.)*", ""
).rstrip()
DEST.write_text(existing + body, encoding="utf-8")

print("invariants retenus :", len(active))
print("par etat :", dict(by_state))
print("par domaine :", dict(counters))
print("preuves suspectes :", len(suspect))
print("retrogrades :", len(demoted))
print("fusionnes :", len(merged))
print("noms dupliques inter-domaines :", {k: v for k, v in dup_names.items()})
print("-> ", DEST)
