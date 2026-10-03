# AGENT-ECON A1 — Capability Catalog & Matrix

Statut : **SOURCE CONTRACT V1 / CONTRACT-ONLY / NON DÉPLOYÉ**
Dépend de : [A0 — Forest Maintenance Contract](AGENT_ECON_A0_FOREST_MAINTENANCE_CONTRACT.md)
Appliqué par : [`AGENT_SPEC_V1.schema.json`](AGENT_ECON_A1_AGENT_SPEC_V1.schema.json)
Base source observée : `main@c561fae406950bf7813102b5b3f59c32388566d0`.

Ce catalogue est **fermé**. Il ne crée aucune capacité d'exécution : c'est un
vocabulaire que des specs *déclarent* et qu'un futur point d'enforcement (A6) devra
appliquer. Déclarer une capability ne prouve rien et n'autorise rien.

```text
UNKNOWN CAPABILITY  → REJECT
jamais              → repli permissif
```

---

## 1. Classes de jetons — trois ensembles disjoints

| Ensemble | Contenu | Présent dans l'énumération `capabilities` de V1 ? | Code de rejet |
|---|---|---|---|
| **Catalogue V1** (§2) | capabilities non-autoritaires F0–F2 | **oui, seul** | — |
| **Réservé** (§3) | capabilities F3/F4 futures | non | `RESERVED_CAPABILITY` |
| **Interdit** (§4) | Forbidden Authority Set (24) + Human Gate (6) | non, jamais | `FORBIDDEN_AUTHORITY_REQUESTED` |
| tout autre jeton | — | non | `UNKNOWN_CAPABILITY` |

Les quatre cas **rejettent**. Un jeton ne migre jamais d'un ensemble à l'autre sans
amendement constitutionnel (A0 §14). Un validateur classe un jeton rejeté dans cet ordre
(interdit → réservé → inconnu) pour que la tentative reste lisible dans l'audit.

---

## 2. Catalogue V1 (admissible, 14 capabilities)

Tri lexicographique = ordre canonique des tableaux dans une spec.

| Capability | Niveau min. | Famille | Sens | Périmètre requis dans la spec | Sortie |
|---|---|---|---|---|---|
| `CI_READ` | F0 | lecture | lire résultats/logs CI GitHub | `github_surfaces` ⊆ {`CHECK_RUNS`,`WORKFLOW_RUNS`}, non vide | — |
| `GITHUB_METADATA_READ` | F0 | lecture | lire issues, PR, commits, branches (métadonnées) | `github_surfaces` ⊆ {`BRANCHES`,`COMMITS`,`ISSUES`,`PULL_REQUESTS`}, non vide | — |
| `GOVERNED_ARTIFACT_READ` | F0 | lecture | lire des artefacts certifiés/immuables d'un domaine déclaré | `artifact_domains` non vide | — |
| `REPOSITORY_READ` | F0 | lecture | lire des fichiers du dépôt | `repository_read_paths` non vide | — |
| `REPOSITORY_SEARCH` | F0 | lecture | chercher dans le dépôt | `repository_read_paths` non vide | — |
| `STATIC_ANALYSIS` | F0 | lecture | analyse statique sans exécuter de code du dépôt, sans écriture | `repository_read_paths` non vide | — |
| `CANDIDATE_PROBLEM_PROPOSE` | F1 | proposition | soumettre un `CANDIDATE_PROBLEM` avec preuves (futur intake A2) | — | `CANDIDATE_PROBLEM` |
| `PROBLEM_VERIFY` | F2 | curation | émettre une *revendication* de vérification sur un problème d'un **autre** agent | — | `VERIFIED_PROBLEM` |
| `PROBLEM_DEDUPLICATE` | F2 | curation | relier/dédupliquer des problèmes | — | `DIAGNOSTIC` |
| `PROBLEM_CHARACTERIZE` | F2 | curation | caractériser un problème (périmètre, risque, cause apparente) | — | `DIAGNOSTIC` |
| `DIAGNOSTIC_PRODUCE` | F2 | curation | produire un diagnostic | — | `DIAGNOSTIC` |
| `BOUNTY_DRAFT_PREPARE` | F2 | brouillon | préparer un brouillon de bounty (n'ouvre, ne finance, ne réserve rien) | — | `BOUNTY_DRAFT` |
| `SCOPE_DRAFT_PREPARE` | F2 | brouillon | préparer un brouillon de périmètre | — | `SCOPE_DRAFT` |
| `ACCEPTANCE_CRITERIA_DRAFT_PREPARE` | F2 | brouillon | préparer des critères d'acceptation en brouillon | — | `ACCEPTANCE_CRITERIA_DRAFT` |

Remarques normatives :

- Les noms `VERIFIED_PROBLEM`, `BOUNTY_DRAFT`… sont des **types d'artefact**
  (sorties de proposition). Leur *cycle de vie* (`CANDIDATE_PROBLEM → VERIFIED_PROBLEM
  → BOUNTY_OPEN…`) appartient à A2/A3 ; A1 ne l'implémente pas.
- `GITHUB_METADATA_READ`/`CI_READ`/lectures : **aucune écriture GitHub n'existe** dans le
  catalogue (ni commentaire, ni label, ni assignation, ni issue, ni PR, ni branche).
- Aucune capability de **lecture runtime/VPS**, de **réseau externe**, d'**exécution de
  code**, de **lecture de secret** n'existe. Un besoin de ce type est un amendement (A0 §9).
- Les sorties ne sont jamais une décision. `VERIFIED_PROBLEM` est une revendication
  d'un agent ; seul un état A2 gouverné ou une décision humaine la rend contraignante.

---

## 3. Réservé (F3/F4) — rejeté par `AGENT_SPEC_V1`

| Capability | Niveau | Sens futur | Contrainte que toute future version DOIT conserver |
|---|---|---|---|
| `SOURCE_EDIT_ISOLATED` | F3 | éditer des sources **dans un environnement isolé uniquement** | jamais hors sandbox ; jamais vers `main` |
| `TEST_RUN_ISOLATED` | F3 | exécuter des tests en isolation | sans secret, sans réseau runtime |
| `BRANCH_PREPARE` | F3 | préparer une branche isolée | préparer ≠ pousser/fusionner ; l'écriture GitHub réelle relève de A8 |
| `PR_PREPARE` | F3 | préparer une PR | idem |
| `TEST_REVIEW` | F4 | relire des tests | auteur ≠ relecteur |
| `SECURITY_REVIEW` | F4 | relire la sécurité | idem |
| `DATA_PROVENANCE_REVIEW` | F4 | relire la provenance de données | idem |
| `STATISTICAL_REVIEW` | F4 | relire la validité statistique | idem |
| `ARCHITECTURE_REVIEW` | F4 | relire l'architecture | idem |
| `GOVERNANCE_REVIEW` | F4 | relire scope, preuves, SHA, rollback | ne possède pas le droit final de merge/deploy |

Contraintes transversales invariantes :

1. **F3 n'a aucune capability de review** ; F4 n'a aucune capability d'édition ni de
   merge. Aucun niveau ne combine construire et valider le même travail.
2. Un F4 peut **bloquer** (sortie `BLOCKING_FINDING`) ; son absence de blocage n'est
   pas une acceptation (A0 §4).
3. Aucun niveau ne possède `MAIN_MERGE`, `RUNTIME_DEPLOY` ni aucune action de §4.
4. Les classes `ENGINEER`, `UX`, `TEST_VERIFIER`, `REVIEWER`, `GOVERNANCE` dépendent de
   ces capacités ; elles sont **vocabulaire réservé** et non enregistrables en V1 (§6).

Sorties futures réservées : `BRANCH_PREPARED`, `PR_PREPARED`, `ISOLATED_TEST_RESULT`
(F3) ; `REVIEW_REPORT`, `BLOCKING_FINDING` (F4).

---

## 4. Interdit — jamais une capability

Forbidden Authority Set (24, fermé ; détail et fondement en A0 §6) :

```text
MAIN_MERGE  RUNTIME_DEPLOY  ADVISOR_RESTART  SYSTEMD_MUTATE  ACTIVE_EPOCH_MUTATE
PPL_AUTHORITY_WRITE  FIN_AUTHORITY_WRITE  TRADING_CONFIG_MUTATE  RISK_MUTATE
SIZING_MUTATE  PB_MAX_POSITIONS_MUTATE  SECRET_VALUE_READ  EXCHANGE_WRITE
TESTNET_ENABLE  LIVE_ENABLE  HUMAN_DECISION  RESEARCH_PROMOTION_EXECUTE
AUTHORITY_DELEGATE  AIC_BUY_AUTHORITY  REPUTATION_GRANT_AUTHORITY
AGENT_SPEC_SELF_REVISE  CONSENSUS_AUTHORITY_ASSERT  GATE_NEUTRALIZE  EVIDENCE_MUTATE
```

Human Gate (6, jamais capabilities d'agent à aucun niveau) :

```text
HUMAN_ACCEPT  HUMAN_REJECT  MERGE_AUTHORIZATION
DEPLOY_AUTHORIZATION  EPOCH_AUTHORIZATION  PROMOTION_AUTHORIZATION
```

---

## 5. Sorties (artefacts de proposition)

| Sortie | Niveau | Persistance | Nature |
|---|---|---|---|
| `OBSERVATION_REPORT` | F0 | **transitoire** : rendue à l'invocateur, non persistée par l'agent ; n'est une preuve que si un écrivain gouverné la persiste avec provenance | constat |
| `CANDIDATE_PROBLEM` | F1 | soumission à un futur intake A2 (n'existe pas) | proposition avec preuves ; non certifiée par son auteur |
| `VERIFIED_PROBLEM` | F2 | futur A2 | revendication de vérification ; auteur de la vérification ≠ auteur du problème |
| `DIAGNOSTIC` | F2 | futur | analyse |
| `BOUNTY_DRAFT` | F2 | futur A3 | brouillon ; n'ouvre ni ne finance aucun bounty |
| `SCOPE_DRAFT` | F2 | futur | brouillon |
| `ACCEPTANCE_CRITERIA_DRAFT` | F2 | futur | brouillon |

Aucune sortie n'est une décision, un merge, un déploiement ni une autorité. Les
« futur A2/A3 » ne sont pas définis par A1 : A1 ne contient aucun de ces registres.

---

## 6. Classes et plafonds admissibles en V1

`agent_class` décrit le métier ; `maintenance_level` le plafond. Le **plafond maximal
admissible par classe en V1** est encodé dans le schéma :

| `agent_class` | Niveau max. V1 | Commentaire |
|---|---|---|
| `SENSOR` | F0 | observation |
| `SCOUT` | F1 | trouve des problèmes |
| `CURATOR` | F2 | vérifie, dédoublonne, rédige des brouillons |
| `FORENSIC` | F2 | diagnostic ; read-only jusqu'à cause démontrée |
| `DATA_STEWARD` | F2 | provenance, complétude |
| `SECURITY` | F2 | audit défensif, diagnostic seulement ; `SECURITY_REVIEW` est F4 réservé |
| `SRE` | F2 | diagnostic ; **sans lecture runtime** (A0 §9) |
| `RESEARCH` | F1 | domaine Research ≠ forêt : en V1, propositions seulement ; les verdicts Research relèvent des contrats `RL-*` |
| `STRATEGY` | F1 | idem ; aucune production de candidat stratégie dans la forêt (domaine `RL-CANDIDATE`) |
| `ENGINEER` | — réservé | dépend de F3 |
| `UX` | — réservé | dépend de F3 |
| `TEST_VERIFIER` | — réservé | dépend de F3/F4 |
| `REVIEWER` | — réservé | dépend de F4 |
| `GOVERNANCE` | — réservé | dépend de F4 ; ne possède jamais le droit final de merge/deploy |

Un niveau inférieur au max. de la classe reste admissible. « Réservé » = valeur du
vocabulaire reconnue mais **aucun niveau V1 n'est admissible** : une spec est rejetée
`CLASS_LEVEL_INADMISSIBLE`.

---

## 7. Matrice : niveau → capacités, interdits, indépendance, sorties

| | **F0 SENSOR** | **F1 SCOUT** | **F2 CURATOR/DIAGNOSTICIAN** | **F3 BUILDER** *(réservé)* | **F4 VERIFIER** *(réservé)* |
|---|---|---|---|---|---|
| **Allowed capabilities** | `CI_READ` `GITHUB_METADATA_READ` `GOVERNED_ARTIFACT_READ` `REPOSITORY_READ` `REPOSITORY_SEARCH` `STATIC_ANALYSIS` | F0 + `CANDIDATE_PROBLEM_PROPOSE` | F1 + `PROBLEM_VERIFY` `PROBLEM_DEDUPLICATE` `PROBLEM_CHARACTERIZE` `DIAGNOSTIC_PRODUCE` `BOUNTY_DRAFT_PREPARE` `SCOPE_DRAFT_PREPARE` `ACCEPTANCE_CRITERIA_DRAFT_PREPARE` | F2 + `SOURCE_EDIT_ISOLATED` `TEST_RUN_ISOLATED` `BRANCH_PREPARE` `PR_PREPARE` | F0 + `TEST_REVIEW` `SECURITY_REVIEW` `DATA_PROVENANCE_REVIEW` `STATISTICAL_REVIEW` `ARCHITECTURE_REVIEW` `GOVERNANCE_REVIEW` |
| **Forbidden capabilities** | tout ce qui n'est pas lecture ; tout §4 | toute écriture/édition ; tout §3 ; tout §4 | exécution de la solution ; tout §3 ; tout §4 | toute review ; `MAIN_MERGE` `RUNTIME_DEPLOY` ; tout §4 | toute édition ; `MAIN_MERGE` ; acceptation ; tout §4 |
| **Required independence** | n/a (aucun artefact gouverné) | `CANDIDATE_PROBLEM` jamais auto-vérifié : vérificateur `agent_id` ≠ proposeur | `VERIFIED_PROBLEM` : vérificateur ≠ proposeur ; brouillons non auto-acceptés | sortie relue par un F4 `agent_id` ≠ auteur, puis gate humaine avant tout merge | relecteur ≠ auteur ≠ contributeur du diff ; blocage possible, acceptation impossible |
| **Permitted outputs** | `OBSERVATION_REPORT` (transitoire) | F0 + `CANDIDATE_PROBLEM` | F1 + `VERIFIED_PROBLEM` `DIAGNOSTIC` `BOUNTY_DRAFT` `SCOPE_DRAFT` `ACCEPTANCE_CRITERIA_DRAFT` | F2 + `BRANCH_PREPARED` `PR_PREPARED` `ISOLATED_TEST_RESULT` | `REVIEW_REPORT` `BLOCKING_FINDING` |
| **Human authority** | aucune | aucune | aucune | aucune | aucune |
| **Admissible `AGENT_SPEC_V1`** | oui | oui | oui | **non** | **non** |

---

## 8. Vérification des propriétés demandées

Chaque propriété est liée à un mécanisme et à un cas négatif à reproduire par la future
mission d'implémentation.

| Propriété | Mécanisme (V = validateur, S = schéma) | Cas négatif à tester |
|---|---|---|
| F0 = lecture seulement | S : `capabilities ⊆` ensemble F0 quand `maintenance_level = F0` | F0 + `CANDIDATE_PROBLEM_PROPOSE` ⇒ rejet ; F0 + `PROBLEM_VERIFY` ⇒ rejet |
| F1 ne code pas | S : aucune capability d'édition dans l'ensemble F1 ; F3 réservé | F1 + `SOURCE_EDIT_ISOLATED` ⇒ `RESERVED_CAPABILITY` |
| F2 ne déploie pas | S : aucune capability de déploiement n'existe ; V : `RUNTIME_DEPLOY` ⇒ `FORBIDDEN_AUTHORITY_REQUESTED` | F2 + `RUNTIME_DEPLOY` ⇒ rejet |
| F3 ne review pas son travail | S : F3 réservé (rejet) ; contrainte §3.1 pour toute version future ; `own_work_review_forbidden` constante | spec V1 F3 ⇒ rejet ; `own_work_review_forbidden=false` ⇒ rejet |
| F4 ne merge pas | S : F4 réservé ; `MAIN_MERGE` interdit | F4 + `MAIN_MERGE` ⇒ rejet |
| aucun niveau n'a l'autorité humaine | S : `human_decision = false` constante ; §4 hors énumération | `human_decision=true` ⇒ rejet ; `HUMAN_ACCEPT` en capability ⇒ `FORBIDDEN_AUTHORITY_REQUESTED` |
| capability inconnue ⇒ rejet | S : `enum` fermé ; V : classement des jetons §1 | jeton `TELEPORT` ⇒ `UNKNOWN_CAPABILITY` |
| cohérence capability ↔ périmètre | V (non exprimable en JSON Schema) : tableau §2 « Périmètre requis » | `REPOSITORY_READ` avec `repository_read_paths` vide ⇒ `SCOPE_CAPABILITY_INCOHERENT` ; `github_surfaces` non vide sans `GITHUB_METADATA_READ`/`CI_READ` ⇒ idem |

Ces vérifications du **schéma** ont été exercées par un banc jetable lors de la
rédaction (cf. rapport de mission) ; ce banc n'est pas livré. Les règles marquées V ne
sont **pas** exprimables en JSON Schema et ne sont donc **pas** couvertes par lui.

---

## 9. Dérive catalogue ↔ schéma

L'énumération `capabilities` du schéma et la matrice par niveau sont **dérivées** de ce
document. Règles :

1. Toute modification du catalogue, des niveaux ou des classes change le schéma **dans
   la même PR** et incrémente `agent_schema` (A0 §14).
2. La mission A1 SOURCE doit livrer un test qui compare mécaniquement cette table
   (jetons des §2–§4 et §6) au schéma ; une divergence fait échouer la CI.
3. Cette mission n'ajoute **aucun** test (aucun consommateur Python n'existe) ;
   ajouter un test qui ne ferait que relire du texte n'est pas requis
   ([DEVELOPER_ENTRYPOINT](../DEVELOPER_ENTRYPOINT.md) §9).
