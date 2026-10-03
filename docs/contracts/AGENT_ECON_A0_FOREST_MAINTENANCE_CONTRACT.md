# AGENT-ECON A0 — Forest Maintenance Contract

**Parent :** [#284](https://github.com/3a7i3/crypto-ia-terminal/issues/284) AGENT-ECON-00
**Roadmap :** [#285](https://github.com/3a7i3/crypto-ia-terminal/issues/285)
**Garde-fou :** [#286](https://github.com/3a7i3/crypto-ia-terminal/issues/286) `ACTIVE_BURN_IN_IMMUTABILITY_GUARD`
**Gate liée :** [#315](https://github.com/3a7i3/crypto-ia-terminal/issues/315) Gate O ouverte
**Base source :** `c561fae406950bf7813102b5b3f59c32388566d0`
**Constitution :** `AGENT_ECON_A0_FOREST_V1`
**Statut :** `CONTRACT DEFINED — READY FOR REVIEW — NON_DEPLOYED — NO RUNTIME AUTHORITY`

Ce document est une constitution, pas une implémentation. Il ne crée aucun
agent, worker, scheduler, fournisseur de modèle, ledger ou producteur. Il
ne modifie aucune autorité PAPER, PPL, FIN, Research ou runtime. En cas de doute :
fail closed.

Documents liés : [A1 Agent Registry](AGENT_ECON_A1_AGENT_REGISTRY_CONTRACT.md),
[catalogue et matrice](AGENT_ECON_A1_CAPABILITY_CATALOG.md),
[schéma AgentSpec](AGENT_ECON_A1_AGENT_SPEC_V1.schema.json),
[inventaire de migration `.github/agents`](AGENT_ECON_A1_EXISTING_AGENTS_MIGRATION_INVENTORY.md).

## 1. Principe racine

```text
AGENT CAPABILITY != AUTHORITY

OBSERVATION     != AUTHORITY
PROPOSAL        != AUTHORITY
CODE            != AUTHORITY
REVIEW          != AUTHORITY
REPUTATION      != AUTHORITY
AIC             != AUTHORITY
AGENT CONSENSUS != AUTHORITY
```

Cette mission ne cherche pas à rendre le système autonome. Elle rend l'autonomie
future plus difficile à mal faire : identité, périmètre, interdictions,
provenance et plafond d'autorité sont définis avant le premier worker.

Prolonge #284 : « L'économie peut acheter du travail et de la recherche. Elle
ne peut jamais acheter l'autorité. »

## 2. Séparation des domaines

```text
FOREST MAINTENANCE != TRADING RUNTIME != PPL AUTHORITY
                   != FIN AUTHORITY  != RESEARCH AUTHORITY
                   != HUMAN GOVERNANCE
```

| Domaine | Rôle | Relation avec le Forest Maintenance Fabric |
|---|---|---|
| Forest Maintenance | entretenir le dépôt : détecter, documenter, diagnostiquer, proposer, construire en isolation, vérifier | domaine du présent contrat |
| Trading runtime | Advisor, PAPER, stratégies, risk, sizing | hors périmètre, gelé par #286, aucune écriture |
| PPL | vérité lifecycle | jamais écrit ; lecture seulement via un artifact gouverné |
| FIN | vérité financière | idem |
| Research | datasets immuables, diagnostics, candidats | lecture seule d'artifacts publiés ; aucune promotion |
| Gouvernance humaine | accepter, refuser, merger, déployer, ouvrir une epoch | domaine externe, voir §7 |

Chaîne future permise :

```text
observe → detect → document → diagnose → propose
        → implement in isolation → independently verify
        → submit to human governance
```

Chaîne interdite à jamais : `observe → decide → mutate active runtime`.

Flux PAPER (#284, #286) : `PAPER FACTS → DATASET → RESEARCH/AGENTS → CANDIDATE/PR
→ REVIEW → HUMAN/GOVERNANCE → FUTURE STATE`. Jamais
`AGENT → ACTIVE PAPER AUTHORITY`.

## 3. Définitions

| Terme | Définition |
|---|---|
| **Agent** | identité logique **déclarée** dans un `AgentSpec` et connue (à terme) du registre A1. Ce n'est ni un processus, ni un modèle, ni un credential, ni un worker. `REGISTERED` ne signifie jamais « en exécution ». |
| **Capability** | opération technique bornée, non autoritaire, nommée dans le **catalogue fermé** et exercée dans le domaine Forest. Une capability décrit ce qu'un agent *peut produire ou lire*, jamais ce qui *devient vrai ou effectif* à cause de lui. |
| **Authority** | pouvoir dont l'exercice rend un effet réel ou définitif sans nouvelle décision humaine indépendante : merger, déployer, muter le runtime/PPL/FIN/epoch, écrire sur exchange, lire un secret, promouvoir, déléguer. Une authority n'est jamais une capability. |
| **Forestier (F0–F4)** | `maintenance_level` : plafond de *nature* d'action. Voir §4. Il n'est pas la classe. |
| **agent_class** | métier de l'agent (SENSOR, SCOUT, …). Elle restreint les niveaux possibles ; elle n'accorde aucune capability à elle seule. |
| **Human gate** | domaine externe de décision humaine, hors agents (§7). |

`agent_class` décrit le **métier** ; `maintenance_level` décrit le **plafond
d'action**. Ne pas les confondre.

## 4. Les cinq niveaux forestiers

Les niveaux sont ordonnés par nature d'effet (F0 < F1 < F2 < F3 < F4) mais leurs
ensembles de capabilities sont **exclusifs** : un spec n'est que d'un seul niveau
et tous les niveaux partagent la base de lecture F0. Un même `agent_id` ne peut
donc pas à la fois proposer et vérifier un problème, ni construire et relire.
Le détail et les listes exactes sont dans le [catalogue](AGENT_ECON_A1_CAPABILITY_CATALOG.md).

| Niveau | Nom | Permet (futur) | Ne permet jamais |
|---|---|---|---|
| **F0** | SENSOR | lire dépôt, CI, métadonnées GitHub, artifacts gouvernés ; analyse statique | toute écriture |
| **F1** | SCOUT / PROBLEM FINDER | produire des `CANDIDATE_PROBLEM` avec preuves | certifier son propre constat ; coder |
| **F2** | DIAGNOSTICIAN / CURATOR | vérifier, dédupliquer, caractériser ; produire `VERIFIED_PROBLEM`, diagnostic, brouillons de bounty/scope/critères | exécuter la solution ; déployer |
| **F3** | ISOLATED BUILDER (futur seulement) | édition source et tests **en environnement isolé** ; préparer branche/PR | merger ; déployer ; valider son propre travail |
| **F4** | INDEPENDENT VERIFIER (futur seulement) | revues test, sécurité, provenance, statistique, architecture, gouvernance ; peut **bloquer** | accepter à la place de l'opérateur ; merger |

F3 et F4 sont des **déclarations de plafond**. L'existence d'un spec F3 ou F4
n'active rien : A6 (sandbox) et A7 (revue indépendante) n'existent pas.

`BLOCK` d'un F4 signifie : le résultat ne doit pas être présenté comme prêt à
l'opérateur. Ce n'est pas un pouvoir sur le runtime ni sur l'humain.

## 5. Invariants constitutionnels

Fermes et non configurables. Une modification exige un nouvel identifiant de
constitution et une décision humaine (§10).

| Id | Invariant |
|---|---|
| C1 | `authority_ceiling = NO_RUNTIME_AUTHORITY` pour tout agent, tout niveau. |
| C2 | Aucune capability inconnue n'est tolérée : `UNKNOWN CAPABILITY → REJECT`, jamais de repli permissif. |
| C3 | Le catalogue ne contient aucune capability de l'ensemble interdit (§6) ni du domaine humain (§7). |
| C4 | Nul agent ne revoit son propre travail ; l'indépendance est un champ non optionnel (`own_work_review_forbidden = true`, `independent_review_required = true`). |
| C5 | Ni AIC, ni réputation, ni consensus d'agents n'accordent de capability ou d'authority. |
| C6 | `execution_binding` est `UNBOUND`, sans provider, sans modèle, sans credential, jusqu'à une mission d'exécution gouvernée distincte. |
| C7 | Aucun agent n'écrit dans le registre, son propre spec compris. |
| C8 | Les chemins gelés par #286 sont refusés comme chemins d'écriture futurs (liste fermée dans le schéma). |
| C9 | `UNKNOWN != 0`, `NON_DEPLOYED != EMPTY`, `UNRESOLVED` reste une donnée. |
| C10 | Une preuve source n'est pas une preuve runtime. Aucune déclaration d'agent n'est une preuve. |

## 6. Ensemble d'autorités interdites (liste fermée)

Ces entrées ne figurent et ne figureront dans **aucun** catalogue de
capabilities, spec ou matrice. Ce sont des invariants, pas des valeurs par défaut.
Les vingt premières sont celles du brief de mission ; les deux dernières sont
des ajouts proposés par cette PR et signalés pour revue.

| # | Autorité interdite | Pourquoi |
|---|---|---|
| 1 | `MAIN_MERGE` | merge = décision humaine |
| 2 | `RUNTIME_DEPLOY` | SOURCE PROOF ≠ RUNTIME PROOF |
| 3 | `ADVISOR_RESTART` | #286 |
| 4 | `SYSTEMD_MUTATE` | #286 |
| 5 | `ACTIVE_EPOCH_MUTATE` | #286 |
| 6 | `PPL_AUTHORITY_WRITE` | PPL = vérité lifecycle |
| 7 | `FIN_AUTHORITY_WRITE` | FIN = vérité financière |
| 8 | `TRADING_CONFIG_MUTATE` | #286 |
| 9 | `RISK_MUTATE` | #286 |
| 10 | `SIZING_MUTATE` | #286 |
| 11 | `PB_MAX_POSITIONS_MUTATE` | #286 |
| 12 | `SECRET_VALUE_READ` | aucun accès par défaut aux secrets |
| 13 | `EXCHANGE_WRITE` | aucune écriture exchange |
| 14 | `TESTNET_ENABLE` | gate distincte et tardive |
| 15 | `LIVE_ENABLE` | idem |
| 16 | `HUMAN_DECISION` | l'humain n'est pas une capability |
| 17 | `RESEARCH_PROMOTION_EXECUTE` | Research → même epoch interdit ; future epoch = gate humaine |
| 18 | `AUTHORITY_DELEGATE` | une autorité ne se délègue pas à un agent |
| 19 | `AIC_BUY_AUTHORITY` | AIC ≠ autorité |
| 20 | `REPUTATION_GRANT_AUTHORITY` | réputation ≠ autorité |
| 21 | `AGENT_REGISTRY_WRITE` *(ajout proposé)* | C7 : un agent ne s'enregistre ni ne se modifie |
| 22 | `PROTECTION_BYPASS` *(ajout proposé)* | contourner protections de branche, gates CI ou baselines équivaut à créer de l'autorité |

## 7. Le domaine humain n'est pas F5

L'humain n'est pas un sixième niveau. Les actions suivantes appartiennent au
domaine de gouvernance humaine et ne deviennent **jamais** des capabilities
d'agent ordinaires ; aucun mécanisme opérationnel n'est construit ici :

```text
HUMAN_ACCEPT   HUMAN_REJECT   MERGE_AUTHORIZATION
DEPLOY_AUTHORIZATION   EPOCH_AUTHORIZATION   PROMOTION_AUTHORIZATION
```

Un agent peut *soumettre* à la gouvernance humaine. Il ne peut ni déclencher
l'acceptation, ni l'imiter, ni l'inférer de l'accord d'autres agents.

## 8. Phases A0 → A8

```text
A0 Forest Contract (ce document)  ← contract only
 ↓ A1 Agent Registry (contrat prêt, implémentation source non autorisée)
 ↓ A2 Problem Registry
 ↓ A3 Bounty Registry
 ↓ A4 Economy Ledger / AIC
 ↓ A5 Cost Accounting
 ↓ A6 Worker Sandbox
 ↓ A7 Independent Review
 ↓ A8 GitHub Automation
```

A1 ne contient aucune logique d'A2+ : pas de Problem Registry, pas de bounty,
pas de wallet, pas de balance AIC, pas de worker, pas de scheduler, pas de
mutation GitHub. Les sorties `CANDIDATE_PROBLEM`, `VERIFIED_PROBLEM`,
`BOUNTY_DRAFT` ne sont que des **noms de sortie** dans le catalogue ; leur
registre, cycle de vie et stockage relèvent de A2/A3.

## 9. Réponses non ambiguës

| # | Question | Réponse |
|---|---|---|
| 1 | Qu'est-ce qu'un agent ? | Identité logique déclarée par un `AgentSpec`, jamais un processus ni un modèle (§3). |
| 2 | Qu'est-ce qu'une capability ? | Opération bornée et non autoritaire du catalogue fermé (§3). |
| 3 | Qu'est-ce qu'une authority ? | Pouvoir d'effet réel ou définitif sans décision humaine indépendante ; aucune n'est accordée (§3, §6). |
| 4 | Qu'est-ce qu'un Forestier F0–F4 ? | Plafond de nature d'action, exclusif par spec (§4). |
| 5 | Qui peut détecter ? | F1 propose des `CANDIDATE_PROBLEM` ; F0 observe seulement ; F2 vérifie. |
| 6 | Qui peut coder ? | Seulement F3, en environnement isolé, et seulement après A6 ; aucun code n'est possible aujourd'hui. |
| 7 | Qui peut reviewer ? | F4, jamais l'auteur du travail revu ; sa revue n'est pas une acceptation. |
| 8 | Qui peut merger ? | Personne parmi les agents. `MAIN_MERGE` est interdit ; le merge reste humain. |
| 9 | Qui peut déployer ? | Personne parmi les agents. `RUNTIME_DEPLOY` est interdit ; gate runtime séparée. |
| 10 | Qui peut modifier PAPER ? | Personne parmi les agents : epoch, config, risk, sizing, PPL, FIN sont interdits. |
| 11 | L'AIC peut-il acheter de l'autorité ? | Non (`AIC_BUY_AUTHORITY`, `economic_status_grants_authority = false`). |
| 12 | La réputation peut-elle acheter de l'autorité ? | Non (`REPUTATION_GRANT_AUTHORITY`, `reputation_grants_authority = false`). |
| 13 | Le consensus d'agents peut-il devenir autorité humaine ? | Non (`consensus_grants_authority = false`) ; N accords d'agents valent N propositions. |
| 14 | Un agent peut-il reviewer son propre travail ? | Non, structurellement (C4 ; F3 et F4 exclusifs). |
| 15 | Que signifie `REGISTERED` ? | Identité connue du registre. Pas de worker, de binding, de permission d'exécution. |
| 16 | `agent_id` vs `agent_spec_id` ? | Le premier est l'identité logique stable ; le second identifie une version exacte du spec. Voir A1 §3. |
| 17 | Capability inconnue ? | Rejet. Aucun repli permissif. |
| 18 | Migration des `.github/agents` ? | Aucune réécriture ici. Inventaire et statuts dans l'[inventaire](AGENT_ECON_A1_EXISTING_AGENTS_MIGRATION_INVENTORY.md) ; ils ne sont pas une autorité. |

## 10. Amendement

La constitution ne change que par une PR documentaire portant un nouvel
identifiant (`AGENT_ECON_A0_FOREST_V2`, …), une décision humaine explicite et
une mise à jour synchronisée de #284 et #285. Aucun agent, vote d'agents, score
AIC ou réputation ne peut proposer cet amendement comme décision ; ils peuvent
seulement l'argumenter dans une PR relue par un humain. Les autres changements
(ajouter une capability au catalogue, un niveau, une classe) sont des amendements
du même type, car le catalogue est fermé.

## 11. État et affichage

Les agents, bounties et AIC restent `NON DÉPLOYÉ`. Aucune surface de l'Operator
App n'affiche un agent, un solde ou un bounty tant qu'un producteur gouverné
n'existe pas. Les fixtures et vecteurs de test de ce dossier ne sont jamais des
entrées de registre.

## 12. Hors périmètre de cette mission

Aucun fichier Python, service, scheduler, client de modèle, client GitHub en
écriture, wallet, ledger, bounty ou problème. Aucune dépendance ajoutée. Aucune
modification des fichiers `.github/agents/*`, du frontend, de la CI ou des baselines.
