# AGENT-ECON A1 — Inventaire des profils `.github/agents/*.agent.md`

**Constitution :** [A0](AGENT_ECON_A0_FOREST_MAINTENANCE_CONTRACT.md) ·
[catalogue](AGENT_ECON_A1_CAPABILITY_CATALOG.md) ·
[A1](AGENT_ECON_A1_AGENT_REGISTRY_CONTRACT.md)
**Base source :** `c561fae406950bf7813102b5b3f59c32388566d0` (inspection de source, aucune observation runtime)
**Statut :** `DIAGNOSTIC ONLY — AUCUN FICHIER MODIFIÉ — AUCUN AGENT ENREGISTRÉ`

Les dix profils sont des artefacts historiques/candidats. Ils n'ont **aucune
autorité** et ne sont pas des agents au sens d'A0 : aucun n'est `REGISTERED`. Leur
contenu a été lu et évalué contre la nouvelle constitution ; il n'en dérive aucune
permission. Cette mission ne les modifie pas.

## 1. Constats communs

| Fait | Preuve |
|---|---|
| Aucun code, workflow ni document du dépôt ne référence `.github/agents` avant cette mission | `grep -rn "\.github/agents"` sur `*.py`, `*.yml`, `*.md` à `c561fae` : aucun résultat |
| Un seul commit a touché ce dossier (`b2a7d7d`, 2026-09-22) | `git log -- .github/agents` |
| Format `*.agent.md` avec front-matter (`tools`, `disable-model-invocation`, `user-invocable`) : convention de profils d'agents GitHub. Sémantique exacte des clés **non vérifiée ici** (inférée, non prouvée par le dépôt) | lecture des fichiers |
| Aucune de ces clés `tools:` ne correspond à une capability du catalogue fermé : le catalogue ne reprend pas les outils des profils | catalogue §1 |
| Trois profils ont un front-matter non fermé et aucun `tools:` déclaré : leurs droits effectifs sont `UNKNOWN`, pas « lecture seule » | voir lignes 7, 9 et 10 |

États de migration : `MIGRATION_CANDIDATE` (réécriture en `AgentSpec` plausible
après revue), `REVIEW_REQUIRED` (ambiguïté ou écart à lever avant), `BLOCKED_LEGACY_RECONCILIATION`
(incompatible avec A0 en l'état).

## 2. Inventaire

| # | Fichier / nom | Finalité actuelle | Pouvoirs déclarés | Écriture / exécution déclarée | Implication runtime | Compat. A0 | Classe future | Niveau | Statut | Remédiation requise |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `data-provenance-auditor` — Data Provenance Auditor | audit READ-ONLY des datasets, producteurs, consommateurs, fraîcheur, schémas | `tools: ["read","search"]` ; `disable-model-invocation: true` ; texte « Aucune modification… » | aucune | son texte cherche aussi des stores d'exécution (JSONL, SQLite, positions, portfolio) qui n'existent comme preuve qu'au runtime | partielle : lecture du dépôt compatible ; lecture de stores runtime hors catalogue | `DATA_STEWARD` | F2 | `MIGRATION_CANDIDATE` | limiter le scope au code et aux `artifact_domains` gouvernés ; exclure les stores runtime (mission VPS read-only distincte) ; expliciter UNKNOWN ≠ 0 dans les sorties |
| 2 | `decision-path-forensic` — Decision Path Forensic | investigation READ-ONLY de tout chemin influençant signal, gate, sizing, exécution | `tools: ["read","search"]` ; `disable-model-invocation: true` | aucune | cartographie de chemins d'exécution et de décision live, sans y agir | compatible en lecture | `FORENSIC` | F2 | `MIGRATION_CANDIDATE` | écrire le périmètre de lecture ; borner les sorties à `DIAGNOSTIC` ; aucune correction |
| 3 | `hedge-fund-architect` — AI Hedge Fund Architect (sans `name:`) | construire et étendre un système de trading : scanner, sniper, bot doctor, stratégies, Telegram, dashboard | `tools: [read, edit, search, execute, agent, todo]` ; `agents: [sniper-engine]` | **édition + exécution + délégation à un autre agent** ; instruit d'écrire l'implémentation, de scaffolder des modules de trading et d'exécuter un `execute_trade` | décrit deux arbres (`quant-hedge-ai`, `crypto_quant_v16`) **absents** à cette base ; modèle d'architecture périmé, prétend tester et exécuter | **incompatible** : édition+exécution sans isolation, domaine trading, délégation, absence de plafond | aucune (ne pas mapper) | — | `BLOCKED_LEGACY_RECONCILIATION` | réécrire entièrement comme nouveau spec (probablement `ENGINEER` F3, inscrit seulement après A6) ; ne lui accorder aucun droit hérité |
| 4 | `mission-preparation-researcher` — Mission Preparation Researcher | Evidence Pack READ-ONLY avant une mission : architecture, code, tests, risques | `tools: ["read","search","web"]` ; `disable-model-invocation: true` | aucune écriture ; **accès web en lecture** | contenu web externe = surface d'injection ; aucune capability `WEB_READ` dans le catalogue | partielle : le reste est de la lecture | `CURATOR` | F2 | `REVIEW_REQUIRED` | décider si une capability web doit être amendée au catalogue (A0 §10) ou si le profil renonce au web ; sinon rester sur dépôt, issues, artifacts gouvernés |
| 5 | `observability-cartographer` — Observability Cartographer | cartographie READ-ONLY des métriques, snapshots, dashboards, bots Telegram | `tools: ["read","search"]` ; `disable-model-invocation: true` | aucune | recense des surfaces d'observation | compatible en lecture | `SENSOR` | F0 | `MIGRATION_CANDIDATE` | rédiger le périmètre ; sorties = rapports d'observation seulement |
| 6 | `repository-cartographer` — Repository Cartographer | cartographie READ-ONLY du dépôt : modules, dépendances, call graphs | `tools: ["read","search"]` ; `disable-model-invocation: true` | aucune | analyse statique | compatible | `SENSOR` | F0 | `MIGRATION_CANDIDATE` | rédiger le périmètre ; ne pas exécuter le code analysé |
| 7 | `security-Guardian-agent` — Security Guardian | vérifier sécurité, invariants de gouvernance et frontières Research/Paper/Live | **aucun `tools:` déclaré** ; front-matter non fermé (`---` ouvert, pas de `---` de fin) ; se présente comme « dernier rempart » | non déclarée : droits effectifs `UNKNOWN` ; le texte interdit de désactiver une protection, d'utiliser ou publier un secret, de passer en LIVE | revue de diffs ; son verdict `PASS/BLOCK` ressemble à une porte | partielle : revue compatible ; formulation « dernier rempart » suggère une autorité qu'un F4 n'a pas | `SECURITY` | F4 | `REVIEW_REQUIRED` | corriger le front-matter et déclarer la liste d'outils ; retirer toute apparence de décision ; verdict = `REVIEW_REPORT` ; chemin d'exclusion des secrets |
| 8 | `sniper-engine` — Sniper Engine Agent (sans front-matter) | « exécution rapide » sur opportunités de trading (sniping) | aucun front-matter ; instructions : surveiller des pools, détecter des lancements, **exécuter des ordres d'achat/vente en quelques secondes** ; exemple « Achat instantané » | exécution d'ordres | écriture exchange : exactement `EXCHANGE_WRITE` (interdit) ; référencé par `hedge-fund-architect` | **incompatible** de façon constitutionnelle | aucune | — | `BLOCKED_LEGACY_RECONCILIATION` | ne pas migrer ; classification de nettoyage = `UNKNOWN` (consommateurs non prouvés, fichier non touché) avec recommandation `ARCHIVE` à décider par l'opérateur ; réécrire de zéro si un besoin légitime apparaît |
| 9 | `statistician-agent` — Statistician | vérifier la validité statistique et chercher biais et faux signaux | **aucun `tools:` déclaré** ; front-matter non fermé | non déclarée (droits effectifs `UNKNOWN`) ; contenu purement analytique | calculs de métriques sur des résultats | partielle : contenu compatible, formalisation absente | `REVIEWER` | F4 | `REVIEW_REQUIRED` | corriger le front-matter, déclarer l'accès ; `STATISTICAL_REVIEW` seulement ; ne recalcule pas PnL/equity comme vérité |
| 10 | `system-diagnostic` — System Diagnostician | diagnostic Linux, VPS, systemd, processus, ports, env, logs | **aucun `tools:` déclaré** ; front-matter non fermé ; règle « DIAGNOSE BEFORE MODIFYING » et escalade vers validation humaine | non déclarée ; demande d'inspecter systemd, processus, variables d'environnement, runtime | cible précisément les surfaces gelées par #286 (VPS, systemd, env) ; l'examen d'env peut exposer des secrets | partielle : seul le diagnostic sur dépôt/CI/artifacts est représentable ; le runtime/VPS n'est dans aucun niveau | `SRE` | F2 | `REVIEW_REQUIRED` | limiter au dépôt, CI et artifacts gouvernés ; le diagnostic VPS relève d'une mission read-only distincte (#309) ; interdire la lecture de valeurs d'environnement ; corriger le front-matter |

Décompte :

| Statut | Nombre | Profils |
|---|---|---|
| `MIGRATION_CANDIDATE` | 4 | 1, 2, 5, 6 |
| `REVIEW_REQUIRED` | 4 | 4, 7, 9, 10 |
| `BLOCKED_LEGACY_RECONCILIATION` | 2 | 3, 8 |
| Compatibles sans remédiation | 0 | — |

## 3. Règles de migration

1. Une migration crée un **nouvel** `AgentSpec` selon le schéma ; elle ne «
   convertit » pas un profil existant et n'hérite d'aucun outil.
2. Le fichier source n'est ni modifié ni supprimé par la migration. Retirer ou
   archiver un profil exige la classification `KEEP | INTEGRATE | MOVE | ARCHIVE |
   RETIRE | UNKNOWN`, la preuve des consommateurs et un rollback (CLAUDE.md §5).
3. Aucun profil `BLOCKED_LEGACY_RECONCILIATION` n'est enregistré avant
   réécriture complète et revue.
4. Les profils `REVIEW_REQUIRED` ne sont pas utilisés comme autorité tant que leur
   front-matter n'est pas corrigé et leurs droits effectifs établis.
5. Tout `REGISTERED` ultérieur reste `UNBOUND` : ces profils ne fournissent pas
   de binding de modèle, d'outil ou de credential.

## 4. Incohérences observées (non corrigées, hors scope)

| Id | Constat | Preuve | Classe | Risque | Mission future recommandée |
|---|---|---|---|---|---|
| I1 | Numéros d'ADR en double : deux fichiers `0019-*` et deux `0020-*` | `ls docs/adr` | OBSERVED / NON_BLOCKING | confusion de référence ; les références de la mission pointent `ADR-0019/0020` sans lever l'ambiguïté (D5B R2 = `0019-stockage-durable…` et `0020-contrat-de-confiance…`) | renumérotation ou index ADR (documentation) |
| I2 | Trois profils sans `tools:` et à front-matter non fermé | inventaire §2, lignes 7, 9, 10 | NEEDS_REVIEW | droits effectifs inconnus selon l'outil qui les charge | correction de front-matter (documentation) |
| I3 | `hedge-fund-architect` référence des arbres inexistants et délègue à `sniper-engine` | `ls`, lecture des profils | OBSERVED / NEEDS_REVIEW | profil trompeur et permissif | décision d'archivage ou réécriture |
| I4 | Gate O (#315) ouverte : aucun écrivain autorisé, aucune ancre anti-retour pour un registre | #315 | BLOCKING pour toute implémentation A1 *opérationnelle* | un registre hash-chaîné sans autorité d'écriture ne prouve pas l'authenticité | décision opérateur sur le propriétaire et l'ancre avant A1 source opérationnel |

Aucun de ces points n'a été corrigé par cette mission.
