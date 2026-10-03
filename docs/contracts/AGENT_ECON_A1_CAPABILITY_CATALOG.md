# AGENT-ECON A1 — Catalogue de capabilities et matrice

**Constitution :** `AGENT_ECON_A0_FOREST_V1` ·
[A0](AGENT_ECON_A0_FOREST_MAINTENANCE_CONTRACT.md) ·
[A1](AGENT_ECON_A1_AGENT_REGISTRY_CONTRACT.md) ·
[schéma](AGENT_ECON_A1_AGENT_SPEC_V1.schema.json)
**Base source :** `c561fae406950bf7813102b5b3f59c32388566d0`
**Statut :** `CONTRACT DEFINED — NON_DEPLOYED`

Le catalogue est **fermé**. `UNKNOWN CAPABILITY → REJECT`. Une capability absente
d'ici n'existe pas : l'ajouter est un amendement constitutionnel (A0 §10). Le
schéma JSON est la forme machine-readable des noms et des restrictions
par niveau et par classe ; en cas de divergence entre ce document et le schéma,
le contrat est considéré invalide (fail closed) et la divergence est un défaut à
corriger avant toute implémentation.

Aucune capability ne désigne un outil, un modèle ou un fournisseur. Les `tools:`
des profils GitHub existants n'y sont pas équivalents.

## 1. Catalogue

Base F0 : partagée par tous les niveaux.

| Capability | Niveau | Sens | Sortie permise | Effet interdit |
|---|---|---|---|---|
| `REPOSITORY_READ` | F0 (base) | lire des chemins déclarés du dépôt | rapport d'observation | écrire ; lire `.env`, clés |
| `REPOSITORY_SEARCH` | F0 (base) | rechercher dans ces chemins | idem | idem |
| `CI_READ` | F0 (base) | lire état et logs CI | idem | relancer, modifier un workflow |
| `GITHUB_METADATA_READ` | F0 (base) | lire issues, PR, commits, checks | idem | commenter, assigner, labelliser |
| `GOVERNED_ARTIFACT_READ` | F0 (base) | lire un artifact publié et gouverné d'un domaine déclaré | idem | lire JSONL/DB/exchange bruts ; écrire |
| `STATIC_ANALYSIS` | F0 (base) | analyser la source sans l'exécuter | idem | exécuter le code analysé |
| `CANDIDATE_PROBLEM_PROPOSE` | F1 | proposer un problème avec preuves | `CANDIDATE_PROBLEM` | certifier son propre constat |
| `PROBLEM_VERIFY` | F2 | vérifier un problème proposé par un autre agent | `VERIFIED_PROBLEM` | exécuter la solution |
| `PROBLEM_DEDUPLICATE` | F2 | rapprocher des problèmes équivalents | rapport de déduplication | fermer ou fusionner des issues |
| `DIAGNOSTIC_PRODUCE` | F2 | caractériser la cause | `DIAGNOSTIC` | corriger |
| `BOUNTY_DRAFT_PRODUCE` | F2 | rédiger un brouillon | `BOUNTY_DRAFT` | ouvrir, financer, réserver un bounty |
| `SCOPE_DRAFT_PRODUCE` | F2 | rédiger un périmètre | `SCOPE_DRAFT` | accorder un périmètre |
| `ACCEPTANCE_CRITERIA_DRAFT_PRODUCE` | F2 | rédiger des critères de sortie | `ACCEPTANCE_CRITERIA_DRAFT` | déclarer un critère satisfait |
| `SOURCE_EDIT_ISOLATED` | F3 | modifier des chemins `repository_write_paths_future` **dans un environnement isolé** | diff local | chemins gelés ; toute écriture hors isolation |
| `TEST_RUN_ISOLATED` | F3 | exécuter des tests en isolation | résultat de test | exécuter hors isolation ; modifier un baseline |
| `BRANCH_PREPARE` | F3 | préparer une branche locale isolée | branche préparée, non publiée | publier |
| `PR_PREPARE` | F3 | préparer le contenu d'une PR | brouillon de PR, non publié | ouvrir ou modifier une PR sur GitHub (A8) |
| `TEST_REVIEW` | F4 | revue des tests | `REVIEW_REPORT` | modifier les tests |
| `SECURITY_REVIEW` | F4 | revue défensive | idem | action offensive ; lecture de valeur secrète |
| `DATA_PROVENANCE_REVIEW` | F4 | revue de provenance et complétude | idem | modifier un dataset |
| `STATISTICAL_REVIEW` | F4 | revue statistique | idem | recalculer PnL/equity comme vérité |
| `ARCHITECTURE_REVIEW` | F4 | revue d'architecture | idem | refactoriser |
| `GOVERNANCE_REVIEW` | F4 | revue de scope, preuves, SHA, rollback | idem | accepter, merger, déployer |

Les sorties `CANDIDATE_PROBLEM`, `VERIFIED_PROBLEM`, `BOUNTY_DRAFT` sont des
noms de type d'artifact ; leur registre est A2/A3. Un `REVIEW_REPORT` porte un
verdict `PASS | PASS_WITH_WARNINGS | BLOCK` ; `BLOCK` retire la qualité « prêt
pour l'opérateur » et ne contraint pas l'humain.

Pas de capability de publication GitHub (commenter, ouvrir une PR, assigner),
de lecture VPS/runtime, d'accès web externe, ni d'exécution hors isolation :
elles n'existent pas dans ce catalogue. Elles seraient des amendements
(A8, mission VPS read-only distincte #309).

Domaines et surfaces déclarables :

| Champ | Valeurs fermées |
|---|---|
| `github_surfaces` | `CHECK_RUNS_READ`, `COMMITS_READ`, `ISSUES_READ`, `PULL_REQUESTS_READ`, `WORKFLOW_RUNS_READ` |
| `artifact_domains` | `BURNIN_CHECKPOINT_EVIDENCE`, `CI_ARTIFACTS`, `RESEARCH_DATASET_IMMUTABLE`, `RESEARCH_PUBLICATION` |

Aucun domaine PPL/FIN brut. Ces listes sont proposées et nécessitent l'accord
des propriétaires de chaque source (même exigence que la Gate O #315, point 4).

Chemins de lecture : préfixes de dossier (terminés par `/`) ou fichiers exacts,
relatifs, sans glob, sans `..`, sans `.env*`, `*.pem`, `*.key`. Chemins
d'écriture futurs : mêmes règles, plus refus des préfixes gelés `core`,
`paper_trading`, `financial_institute`, `runtime`, `config`, `deploy`,
`scripts`, `governance`, `.github`, `.ci`, `observability/operator_decisions`.

## 2. Matrice classe × niveau

`✓` = niveau possible pour cette classe. Une classe n'accorde aucune capability.

| agent_class | F0 | F1 | F2 | F3 | F4 | Remarque |
|---|---|---|---|---|---|---|
| SENSOR | ✓ | | | | | |
| SCOUT | | ✓ | | | | |
| CURATOR | | | ✓ | | | |
| ENGINEER | | | | ✓ | | |
| UX | | | | ✓ | | pas de recomputation scientifique côté UI |
| TEST_VERIFIER | | | | | ✓ | |
| FORENSIC | ✓ | ✓ | ✓ | | | READ-ONLY jusqu'à cause démontrée |
| DATA_STEWARD | | | ✓ | | ✓ | protège UNKNOWN / UNRESOLVED / NOT_AVAILABLE |
| RESEARCH | ✓ | ✓ | ✓ | | | datasets immuables ; jamais l'epoch active |
| STRATEGY | ✓ | ✓ | | | | voir note ci-dessous |
| SECURITY | | ✓ | ✓ | | ✓ | défensif seulement |
| SRE | | ✓ | ✓ | | | analyse ; ne redémarre ni ne déploie |
| REVIEWER | | | | | ✓ | |
| GOVERNANCE | | | | | ✓ | `GOVERNANCE_REVIEW` n'est pas une décision |

Note STRATEGY : #284 décrit un Strategy Agent qui crée des candidats de
stratégie. Ce métier relève du domaine Research (`research_candidate/`, RL-CANDIDATE-01),
pas de la maintenance. Cette matrice ne l'autorise donc qu'en lecture (F0, F1) ;
toute extension exige un contrat Research propre. C'est une question ouverte.

## 3. Matrice niveau → capabilities

| Niveau | Capabilities permises | Capabilities interdites | Indépendance exigée | Sorties permises |
|---|---|---|---|---|
| F0 | base de lecture | tout le reste | n/a (aucune sortie qui engage) | rapports d'observation |
| F1 | base + `CANDIDATE_PROBLEM_PROPOSE` | F2, F3, F4 | un F2 d'un `agent_id` différent vérifie | `CANDIDATE_PROBLEM` |
| F2 | base + capabilities F2 | F1, F3, F4 | un F4 relit tout ce qui devient bounty/scope | `VERIFIED_PROBLEM`, `DIAGNOSTIC`, brouillons |
| F3 | base + capabilities F3 | F1, F2, F4, tout déploiement | un F4 d'un `agent_id` différent relit chaque diff | diff, branche et PR *préparées* |
| F4 | base + capabilities F4 | F1, F2, F3, merge | revue par un `agent_id` différent de l'auteur du travail revu | `REVIEW_REPORT` |
| (humain) | n/a — domaine externe | n/a | n/a | acceptation, merge, déploiement, epoch |

Chaque colonne « capabilities interdites » s'ajoute à l'ensemble d'autorités
interdites (A0 §6) qui s'applique à tous les niveaux.

## 4. Invariants vérifiables

Chacun est testable sur le schéma et la matrice, sans exécuter d'agent.

| Id | Invariant | Où il est imposé |
|---|---|---|
| M1 | F0 : aucune capability hors base ; aucune écriture | schéma : `enum` par niveau ; `repository_write_paths_future` vide |
| M2 | F1 ne code pas : pas de `SOURCE_EDIT_ISOLATED`, `BRANCH_PREPARE`, `PR_PREPARE`, `TEST_RUN_ISOLATED` | schéma par niveau |
| M3 | F2 ne déploie pas ni n'exécute la solution : aucune capability F3 ; aucune autorité interdite dans le catalogue | schéma par niveau ; catalogue fermé |
| M4 | F3 ne relit pas son travail : aucune capability F4 ; `own_work_review_forbidden = true` | schéma ; règle croisée A1 §9 |
| M5 | F4 ne merge pas : `MAIN_MERGE` absent du catalogue | catalogue fermé |
| M6 | aucun niveau ne possède l'autorité humaine : `HUMAN_*` absent du catalogue ; `human_decision = false` | catalogue ; schéma |
| M7 | capability inconnue rejetée | schéma : `enum` |
| M8 | une classe n'autorise que les niveaux de §2 | schéma : conditionnels par classe |
| M9 | pas de chemin d'écriture sans `SOURCE_EDIT_ISOLATED`, et inversement | schéma |
| M10 | pas de surface GitHub/domaine d'artifact sans la capability de lecture correspondante | schéma |
| M11 | `execution_binding` est `UNBOUND` | schéma |
| M12 | l'indépendance entre `agent_id` auteur et relecteur | **non exprimable dans le schéma** : règle A1 §9 pour l'implémentation source |

Vérification locale effectuée pour cette PR : voir la section « Validation » du
rapport de mission ; le schéma est validé contre le métaschéma Draft 2020-12 et
contre des cas positifs et négatifs jetables non commités.
