# AGENT-ECON A0 — Forest Maintenance Contract

Statut : **SOURCE CONTRACT V1 / RÉCONCILIATION R1.1 / CONTRACT-ONLY / NON DÉPLOYÉ**
Constitution : `AGENT_ECON_A0_FOREST_V1`
Verdict proposé : `AGENT_ECON_A0_FOREST_CONTRACT_R1_1_READY_FOR_CERTIFICATION`
(pas `CERTIFIED` : la certification appartient à la revue et à la gouvernance humaine).
Réconciliation R1 : cette version intègre les meilleures propriétés d'une conception
indépendante parallèle (PR #347, `INDEPENDENT_DESIGN_REFERENCE`) dans la ligne canonique
(PR #348, `CANONICAL_RECONCILIATION_TARGET`). Aucune troisième PR.

Parent : [#284 — AGENT-ECON-00](https://github.com/3a7i3/crypto-ia-terminal/issues/284)
Roadmap : [#285](https://github.com/3a7i3/crypto-ia-terminal/issues/285) ·
Garde-fou : [#286](https://github.com/3a7i3/crypto-ia-terminal/issues/286)
(`ACTIVE_BURN_IN_IMMUTABILITY_GUARD`) ·
Gate encore ouverte : [#315](https://github.com/3a7i3/crypto-ia-terminal/issues/315)
(Gate O, WEB-DIR-01-D5B-R2).
Base source observée à la rédaction : `main@c561fae406950bf7813102b5b3f59c32388566d0`
(base historique de ce document, pas HEAD perpétuel).

Documents compagnons :
[A1 — Agent Registry](AGENT_ECON_A1_AGENT_REGISTRY_CONTRACT.md) ·
[A1 — Capability Catalog & Matrix](AGENT_ECON_A1_CAPABILITY_CATALOG.md) ·
[schéma AgentSpec](AGENT_ECON_A1_AGENT_SPEC_V1.schema.json) ·
[schéma AgentRegistryEvent](AGENT_ECON_A1_AGENT_REGISTRY_EVENT_V1.schema.json) ·
[inventaire `.github/agents`](../forensics/AGENT_ECON_A0_GITHUB_AGENTS_INVENTORY.md).

---

## 0. Ce que ce document est, et n'est pas

C'est la **constitution** des futurs agents de maintenance de la forêt de code.
Elle est écrite *avant* tout worker, pour que l'autonomie future soit plus difficile
à mal construire.

Ce document **n'autorise** : aucun agent, worker, scheduler, provider de modèle,
écriture GitHub, ledger AIC, registre Problem/Bounty, déploiement, restart, mutation
PAPER/PPL/FIN, écriture exchange, ni aucun changement de la machine active sous #286.
Il ne crée aucune donnée : l'état des agents, bounties et AIC reste **`NON DÉPLOYÉ`**
(≠ vide, ≠ zéro). Une surface qui présenterait « N agents actifs » avant l'existence
d'un producteur gouverné violerait ce contrat.

Principe racine :

```text
AGENT CAPABILITY != AUTHORITY
```

L'économie peut acheter du travail et de la recherche ; elle ne peut jamais acheter
l'autorité ([#284](https://github.com/3a7i3/crypto-ia-terminal/issues/284)).

---

## 1. Invariants racines

```text
CAPABILITY      != AUTHORITY
OBSERVATION     != AUTHORITY
PROPOSAL        != AUTHORITY
CODE            != AUTHORITY
REVIEW          != AUTHORITY
REPUTATION      != AUTHORITY
AIC             != AUTHORITY
AGENT CONSENSUS != AUTHORITY
```

Même si plusieurs agents sont d'accord, ils ne fabriquent ni autorité humaine, ni
autorité runtime, PAPER, TESTNET ou LIVE.

Séparation de domaines :

```text
FOREST MAINTENANCE != TRADING RUNTIME != PPL AUTHORITY != FIN AUTHORITY
                   != RESEARCH AUTHORITY != HUMAN GOVERNANCE
```

Invariants hérités, non réinterprétés ici (CLAUDE.md §1) :
`SOURCE PROOF ≠ RUNTIME PROOF` · `UNKNOWN ≠ 0` · `NON DÉPLOYÉ ≠ vide` ·
`UNRESOLVED IS DATA` · l'intelligence n'est pas l'autorité.

---

## 2. Définitions

**Agent.** Une identité logique stable (`agent_id`), décrite par des `AgentSpec`
versionnées et immuables (`agent_spec_id`), qui déclarent classe, plafond d'action,
capacités, périmètre et lien d'exécution. Un agent **n'est pas** un processus, un
modèle, un credential, un wallet ni une autorité. Qu'un agent soit *connu du registre*
(`REGISTERED`) ne signifie jamais qu'il tourne.

**Capability.** Un permis **nommé, borné et issu d'un catalogue fermé**
([catalogue](AGENT_ECON_A1_CAPABILITY_CATALOG.md)) d'accomplir une classe d'action
non-autoritaire ou d'émettre une classe d'artefact non-autoritaire. Une capability est
nécessaire mais jamais suffisante pour qu'un effet devienne contraignant. Elle est
déclarée dans la spec ; son application effective relève d'un point d'enforcement
externe à l'agent (futur, A6) — la déclaration seule ne protège rien et ne prouve rien.

**Authority.** Le pouvoir de rendre un état *contraignant* pour le système ou pour
l'opérateur. Deux faces, aucune détenue par un agent :

1. *autorité de décision* — accepter/rejeter, merger, déployer, ouvrir/autoriser une
   epoch, promouvoir, activer TESTNET/LIVE, écrire sur exchange. Détenue par
   `HUMAN_OPERATOR` (cf. D5A) via les gates gouvernées ;
2. *autorité de vérité* — PPL pour le lifecycle, FIN pour la valeur financière. Les
   agents les **lisent** (exports certifiés) ; ils ne les écrivent jamais.

**Évidence ≠ autorité.** Une sortie d'agent est une *proposition avec preuves*
(`CANDIDATE_PROBLEM`, `DIAGNOSTIC`, `BOUNTY_DRAFT`, etc.). Elle est inspectable,
critiquable, bloquable ; elle ne lie personne.

**Indépendance.** Voir §8. Elle réduit l'erreur corrélée ; elle ne crée jamais d'autorité.

**Forest Maintenance Fabric.** L'ensemble futur d'agents, registres et workflows qui
maintiennent le dépôt. Capacité future :

```text
observe → detect → document → diagnose → propose
        → implement in isolation → independently verify → submit to human governance
```

Jamais :

```text
observe → decide → mutate active runtime
```

---

## 3. Flux admis et interdits

Admis (aligné #286) : `PAPER FACTS → DATASET immuable → Research/Agents → CANDIDATE/PR → REVIEW → HUMAN/GOVERNANCE → FUTURE STATE`.

Interdit : `AGENT → ACTIVE PAPER AUTHORITY`, `Research/Agent → même epoch active`,
`agent → merge/deploy`, `consensus d'agents → décision humaine`.

Une session d'outil invoquée par l'opérateur (par exemple une session Claude Code
travaillant sur une mission nommée) **n'est pas un agent de la forêt** : elle n'est pas
dans un registre, et ses autorisations (« merger quand tout est vert » sous #315,
exceptions bornées sous #286) sont des **actes `HUMAN_DECISION` adressés à cette
session**, dans leur périmètre daté. A0 ne les accorde ni ne les révoque, et un agent
enregistré ne peut en hériter ni se les déléguer (`AUTHORITY_DELEGATE`, §6).

---

## 4. Niveaux forestiers F0–F4

`agent_class` décrit le **métier** ; `maintenance_level` décrit le **plafond d'action**.
Ne pas les confondre. Le plafond n'est jamais augmenté par la réputation, l'AIC ou un
consensus (§7).

| Niveau | Rôle | Peut | Ne peut jamais | Admissible dans `AGENT_SPEC_V1` |
|---|---|---|---|---|
| **F0 — SENSOR** | observation seule | lire dépôt, chercher, lire CI/métadonnées GitHub, lire artefacts gouvernés, analyse statique ; renvoyer un `OBSERVATION_REPORT` *transitoire* à l'invocateur | écrire quoi que ce soit ; émettre un artefact gouverné | oui |
| **F1 — SCOUT / PROBLEM FINDER** | trouver | tout F0 + proposer un `CANDIDATE_PROBLEM` avec preuves | coder ; certifier son propre constat ; ouvrir un bounty | oui |
| **F2 — DIAGNOSTICIAN / CURATOR** | vérifier, dédupliquer, caractériser | tout F1 + `VERIFIED_PROBLEM` (revendication), `DIAGNOSTIC`, `BOUNTY_DRAFT`, `SCOPE_DRAFT`, `ACCEPTANCE_CRITERIA_DRAFT` | exécuter la solution ; déployer ; financer ; vérifier un problème qu'il a lui-même proposé | oui |
| **F3 — ISOLATED BUILDER** | construire en isolation | **FUTUR** : `SOURCE_EDIT_ISOLATED`, `TEST_RUN_ISOLATED`, `BRANCH_PREPARE`, `PR_PREPARE` | `MAIN_MERGE`, `RUNTIME_DEPLOY` ; valider indépendamment son propre travail ; toute capacité de review | **non — vocabulaire réservé** |
| **F4 — INDEPENDENT VERIFIER** | vérifier de façon indépendante | **FUTUR** : `TEST_REVIEW`, `SECURITY_REVIEW`, `DATA_PROVENANCE_REVIEW`, `STATISTICAL_REVIEW`, `ARCHITECTURE_REVIEW`, `GOVERNANCE_REVIEW` ; **peut bloquer** | accepter à la place de l'opérateur ; merger ; éditer le travail qu'il relit | **non — vocabulaire réservé** |

Règles :

- **Plafonds cumulatifs F0 → F1 → F2.** Un niveau inclut les capabilities du niveau
  inférieur : F1 = F0 + proposition de `CANDIDATE_PROBLEM` ; F2 = F1 + vérification,
  déduplication, caractérisation, diagnostic, brouillons. Cumulatif ≠ auto-validation :
  voir `A2_REQUIRED_INVARIANT` au §8.
- F3 et F4 sont **définis** pour que leurs contraintes soient fixées avant leur
  existence : ce sont des termes **connus et réservés**, pas des inconnus. Leurs valeurs
  et capacités sont **rejetées** par `AGENT_SPEC_V1` (`RESERVED_CAPABILITY` pour une
  capability, `CLASS_LEVEL_INADMISSIBLE` pour un niveau ou une classe). Les admettre exige une nouvelle version de schéma,
  amendée par gouvernance après que les contrats A6/A7 existent (§14).
- **L'humain n'est pas F5.** La gouvernance humaine est un domaine externe aux agents.
  Il n'existe ni niveau, ni classe, ni capability qui la représente (§5).
- Un F4 peut **bloquer** ; l'absence de blocage n'est pas une acceptation. Un « PASS »
  d'un agent est une absence de finding, jamais un accord.
- F0 est lecture seule : il n'émet aucun artefact gouverné (un rapport rendu à
  l'invocateur est une réponse transitoire, non persistée par l'agent, non-evidence tant
  qu'un écrivain gouverné ne l'a pas persistée avec provenance).

La matrice complète (capabilities autorisées/interdites, indépendance requise, sorties
permises) est dans le [catalogue](AGENT_ECON_A1_CAPABILITY_CATALOG.md) et encodée dans
le schéma, pas seulement décrite.

---

## 5. Human Gate — hors du domaine des agents

Les actions suivantes ne sont **jamais** des capabilities d'agent, à aucun niveau,
même réservé :

```text
HUMAN_ACCEPT   HUMAN_REJECT   MERGE_AUTHORIZATION
DEPLOY_AUTHORIZATION   EPOCH_AUTHORIZATION   PROMOTION_AUTHORIZATION
```

Elles appartiennent à `HUMAN_OPERATOR` et s'exercent via les gates gouvernées
(protections GitHub, gates runtime, D5A/D5B). Cette mission ne construit **aucun**
mécanisme opérationnel pour ces actions. Elles n'apparaissent dans aucune énumération
de capability : un spec qui en porte une est rejeté `FORBIDDEN_AUTHORITY_REQUESTED`
(distinct de `UNKNOWN_CAPABILITY`, pour que la tentative soit lisible dans l'audit).

L'agrément d'une action humaine ne contourne ni CI, ni review, ni protections de
branche, ni gates runtime/epoch/déploiement, ni TESTNET/LIVE (D5A §3).

---

## 6. Forbidden Authority Set — liste constitutionnelle fermée

Ce sont des **invariants**, pas des valeurs par défaut. Aucun niveau, classe, spec,
statut économique, réputation, consensus ou version future de registre ne peut en
accorder un. Aucune ne figure dans l'énumération des capabilities.

Ensemble minimal exigé par la mission (20) :

| Token | Interdiction |
|---|---|
| `MAIN_MERGE` | fusionner vers `main` |
| `RUNTIME_DEPLOY` | déployer sur un runtime/VPS |
| `ADVISOR_RESTART` | redémarrer/recharger l'Advisor |
| `SYSTEMD_MUTATE` | modifier unités/état systemd |
| `ACTIVE_EPOCH_MUTATE` | modifier l'epoch active, son manifest, son `paper_epoch_id` |
| `PPL_AUTHORITY_WRITE` | écrire dans l'autorité lifecycle PPL |
| `FIN_AUTHORITY_WRITE` | écrire dans l'autorité financière FIN |
| `TRADING_CONFIG_MUTATE` | modifier stratégie, signaux, seuils, calibration, config d'expérience |
| `RISK_MUTATE` | modifier le risk |
| `SIZING_MUTATE` | modifier le sizing et le capital |
| `PB_MAX_POSITIONS_MUTATE` | modifier `PB_MAX_POSITIONS` |
| `SECRET_VALUE_READ` | lire la valeur d'un secret |
| `EXCHANGE_WRITE` | écrire sur un exchange |
| `TESTNET_ENABLE` | activer TESTNET |
| `LIVE_ENABLE` | activer LIVE |
| `HUMAN_DECISION` | produire une décision humaine ou s'y substituer |
| `RESEARCH_PROMOTION_EXECUTE` | exécuter une promotion Research |
| `AUTHORITY_DELEGATE` | déléguer, transférer ou re-déléguer une autorité |
| `AIC_BUY_AUTHORITY` | acheter de l'autorité avec l'AIC |
| `REPUTATION_GRANT_AUTHORITY` | accorder de l'autorité par la réputation |

Extensions canoniques de la réconciliation R1 (exactement 4), chacune justifiée par un
invariant du dépôt déjà posé ailleurs ; elles resserrent et n'élargissent aucune capacité :

| Token | Interdiction | Fondement |
|---|---|---|
| `AGENT_REGISTRY_MUTATE` | toute mutation autonome du registre : auto-enregistrement, auto-révision de spec (niveau, capabilities, périmètre), suspension d'un autre agent, réintégration, retrait | sans cela une révision est une escalade de privilège par soi-même ; le registre n'est écrit que par un registrar sur décision humaine (A1 §7.4) |
| `CONSENSUS_AUTHORITY_ASSERT` | traiter un accord/quorum d'agents comme autorité | principe `AGENT CONSENSUS != AUTHORITY` (§7.5) |
| `GOVERNANCE_GATE_BYPASS` | contourner ou neutraliser une gate de gouvernance : protections de branche, CI et checks requis, review requise, manipulation d'un baseline ou suppression/désactivation d'un test destinée à franchir une gate | CLAUDE.md §4–§5 : ni baseline modifiée, ni test supprimé pour masquer une régression |
| `EVIDENCE_MUTATE` | modifier ou supprimer des preuves immuables ou historiques : logs, JSONL, datasets immuables, sauvegardes, specs publiées, événements de registre | CLAUDE.md §5 : préserver l'audit et la reprise |

Total : **24 tokens**, liste **fermée**.

**Mapping de migration des noms de brouillon.** Les deux conceptions indépendantes avaient
choisi des noms différents pour les mêmes interdits. Aucun de ces noms n'a été fusionné
dans `main` ; ils ne sont **pas** des alias acceptés : un validateur les classe
`UNKNOWN_CAPABILITY` comme tout autre jeton absent de l'ensemble.

| Nom de brouillon | Source | Token canonique |
|---|---|---|
| `AGENT_SPEC_SELF_REVISE` | #348 avant R1 | `AGENT_REGISTRY_MUTATE` |
| `AGENT_REGISTRY_WRITE` | #347 | `AGENT_REGISTRY_MUTATE` |
| `GATE_NEUTRALIZE` | #348 avant R1 | `GOVERNANCE_GATE_BYPASS` |
| `PROTECTION_BYPASS` | #347 | `GOVERNANCE_GATE_BYPASS` |
| `CONSENSUS_AUTHORITY_ASSERT` | #348 avant R1 | inchangé |
| `EVIDENCE_MUTATE` | #348 avant R1 | inchangé |

Étendre cet ensemble est un amendement constitutionnel (§14), jamais un effet de bord
d'un spec ou d'un worker.

Application : ces tokens sont **absents** de l'énumération de capabilities du schéma ;
un token interdit présenté comme capability est rejeté avec le code
`FORBIDDEN_AUTHORITY_REQUESTED`, un token inconnu avec `UNKNOWN_CAPABILITY`, un token
F3/F4 réservé avec `RESERVED_CAPABILITY`. Les trois rejettent ; la distinction sert
l'audit.

---

## 7. Preuve de séparation des autorités

Chaque affirmation est liée à un mécanisme vérifiable, pas à une intention.

### 7.1 `CAPABILITY != AUTHORITY`

Le catalogue ne contient que des actions *non-autoritaires* (lire, chercher, proposer,
vérifier, diagnostiquer, préparer un brouillon). Toute action autoritaire est dans §5/§6,
donc hors énumération : **il n'existe aucune valeur de capability qui soit une autorité**.
`authority_policy.authority_ceiling` est la constante `NO_RUNTIME_AUTHORITY` ; une
capability ne peut pas relever ce plafond car il n'est pas dérivé des capabilities.

### 7.2 `AIC != AUTHORITY`

`authority_policy.economic_status_grants_authority = false` (constante) ;
`AIC_BUY_AUTHORITY` est interdit. L'AIC est une unité comptable interne, non
transférable, sans valeur externe (#284) ; elle alloue du compute et rémunère une
*preuve acceptée*, jamais une autorité. Aucun champ d'`AgentSpec` ni d'événement de
registre ne porte de solde AIC (A4 est hors A1).

### 7.3 `REPUTATION != AUTHORITY`

`reputation_grants_authority = false` (constante) ; `REPUTATION_GRANT_AUTHORITY`
interdit. La réputation (A11, futur) pourra prioriser l'attention portée à un agent ;
elle ne modifie ni `maintenance_level`, ni capabilities, ni plafond.

### 7.4 `PROPOSAL / CODE / REVIEW / OBSERVATION != AUTHORITY`

Chaque sortie permise est une proposition ou un constat ; la transition vers un effet
contraignant passe par un tiers (F2 vérifie F1 ; F4 relit F3 ; l'humain décide). Un F4
ne possède que le droit de **bloquer** ; son silence n'accepte rien.

### 7.5 `AGENT CONSENSUS != AUTHORITY`

`consensus_grants_authority = false` (constante) ; `CONSENSUS_AUTHORITY_ASSERT` interdit.
Raison de fond : plusieurs agents peuvent partager un même modèle, un même contexte ou
les mêmes biais. N accords valent **un** faisceau de preuves aux erreurs corrélées, pas
N garanties indépendantes. Aucun quorum n'est défini ; aucun seuil ne convertit un
accord en `HUMAN_DECISION`, en merge ou en déploiement. Les agents de la forêt ne
disposent d'aucun mécanisme de vote qui produise un effet.

### 7.5 bis `REGISTERED != RUNNING` et `HASH_CHAIN != AUTHENTICITY`

- `REGISTERED` est la projection d'un événement de registre : une identité connue. Aucun
  champ de spec ou d'événement ne désigne un processus, un binding (`execution_binding`
  est la constante `UNBOUND`) ni une permission d'agir. `ACTIVE` n'existe pas.
- Une hash-chain atteste l'**intégrité** d'une suite d'événements. Elle n'atteste ni
  l'**authenticité de l'écrivain**, ni la **complétude de la queue**, ni une **autorité
  humaine** : `integrity != authenticity != tail completeness != human authority`. Registrar
  authentifié et ancre anti-retour sont `UNRESOLVED` ; la disponibilité `AVAILABLE` du
  registre est donc **inatteignable** (A1 §7.3 et §9.4).

### 7.6 Point d'application

Aujourd'hui l'enforcement est **structurel au niveau du contrat** : énumérations
fermées, constantes, `additionalProperties: false`, absence de toute capability
autoritaire. Il n'existe pas de runtime : ce document ne prétend pas qu'un agent
*ne peut pas* agir, seulement qu'aucune spec valide ne *déclare* un pouvoir
autoritaire. L'enforcement d'exécution (sandbox, permissions) est A6, hors mission.

---

## 8. Indépendance

- `own_work_review_forbidden = true` et `independent_review_required = true` sont des
  **constantes** de toute spec V1 (aucune valeur `false` n'existe).
- Un agent ne vérifie pas (`PROBLEM_VERIFY`) un `CANDIDATE_PROBLEM` qu'il a proposé ;
  un F4 futur ne relit pas un travail dont il est l'auteur ni un diff auquel il a
  contribué.
- **`A2_REQUIRED_INVARIANT`** (exigence imposée à la future mission A2, non implémentée ici) :

  ```text
  problem.created_by_agent_id != verification.verified_by_agent_id
  ```

  Un agent F2 dispose, par cumul de plafond, des capabilities F1 et F2 ; il **ne peut
  pas** vérifier un problème qu'il a lui-même proposé. Le contrat A1 ne peut pas le
  faire respecter (il ne contient aucun problème) ; A2 ne peut pas être déclaré
  complet sans cette contrainte.
- **Limite connue.** Dans A1, « indépendant » n'est vérifiable que comme
  `agent_id` différent. Ce n'est **pas** une preuve d'indépendance épistémique : deux
  `agent_id` peuvent être servis par le même modèle. L'indépendance sert à réduire
  l'erreur ; elle ne remplace aucune gate humaine. Une définition plus forte (famille de
  modèle, credential, contexte distincts) est reportée à A7 et signalée en questions
  ouvertes.

---

## 9. Compatibilité avec le garde-fou #286

| Élément gelé par #286 | Comment A0/A1 l'empêche | Preuve possible |
|---|---|---|
| stratégie, signaux, seuils, calibration | aucune capability d'écriture ; `TRADING_CONFIG_MUTATE` interdit | enum fermée |
| risk, sizing, capital, `PB_MAX_POSITIONS` | `RISK_MUTATE`, `SIZING_MUTATE`, `PB_MAX_POSITIONS_MUTATE` interdits | enum fermée |
| epoch, manifest, `paper_epoch_id`, autorité PPL/FIN | `ACTIVE_EPOCH_MUTATE`, `PPL_AUTHORITY_WRITE`, `FIN_AUTHORITY_WRITE` interdits ; aucun domaine runtime dans `artifact_domains` | enum fermée |
| Advisor, systemd, Watchdog, VPS | `ADVISOR_RESTART`, `SYSTEMD_MUTATE`, `RUNTIME_DEPLOY` interdits ; **aucune capability de lecture runtime n'existe** | enum fermée |
| TESTNET/LIVE, exchange | `TESTNET_ENABLE`, `LIVE_ENABLE`, `EXCHANGE_WRITE` interdits | enum fermée |
| secrets | `SECRET_VALUE_READ` interdit ; `credential_mode = NONE` ; chemins `.env*`/clés/`secrets/` refusés | schéma |
| Research → même epoch | `RESEARCH_PROMOTION_EXECUTE` interdit | enum fermée |
| freeze levé automatiquement | `HUMAN_DECISION`, `EPOCH_AUTHORIZATION` hors domaine agent | §5 |

Conséquence assumée : **aucun agent de la forêt n'a de lecture runtime/VPS**. Les
checkpoints VPS READ-ONLY restent des missions humaines distinctes (#282, #309). Si un
besoin de lecture runtime apparaît, c'est un amendement constitutionnel, pas une
capability.

---

## 10. Sémantique d'état

- `REGISTERED` = *identité connue du registre*. **Jamais** « worker en exécution ».
  `ACTIVE` est volontairement absent du vocabulaire.
- `NON DÉPLOYÉ` ≠ registre vide : l'absence d'artefact est `NON_DEPLOYED`, pas « 0 agent ».
- `UNKNOWN ≠ 0` : un registre non lisible, non vérifiable ou rompu donne `UNKNOWN` /
  `NOT_CERTIFIABLE` pour chaque agent, jamais un décompte.
- Tant qu'aucun mécanisme authentifié de complétude n'existe (même famille que la
  Gate O de #315), les seules réponses légitimes sur « combien d'agents » sont
  `NON_DEPLOYED` ou `UNKNOWN` ; un décompte est interdit.
- Aucune donnée synthétique (« 3 agents actifs », « 120 AIC », « 5 bounties ») ne
  doit apparaître dans l'Operator App.

---

## 11. Migration des anciens `.github/agents`

Les profils existants sont des **artefacts historiques/candidats**, non une autorité.
Aucun n'est déclaré compatible sans inspection ; aucun n'est modifié par cette mission.
Statuts : `MIGRATION_CANDIDATE` · `REVIEW_REQUIRED` · `BLOCKED_LEGACY_RECONCILIATION`.

Règles :

1. Un profil legacy n'acquiert **aucune** capability de par son texte ; son pouvoir
   effectif est `tools` déclaré + comportement de la plateforme (non vérifié ici),
   pas la prose. La prose restrictive n'est pas un enforcement.
2. Migrer = produire une `AgentSpec` neuve, validée par le schéma, par PR humaine.
   Un profil dont les pouvoirs ne s'expriment pas dans le catalogue (exécution d'ordres,
   `edit`/`execute`, réseau externe, lecture runtime) n'est **pas** migré tel quel.
3. Un profil qui décrit une capacité d'exécution d'ordres (`sniper-engine`) ou
   d'édition/exécution large avec délégation (`hedge-fund-architect`) est
   `BLOCKED_LEGACY_RECONCILIATION` tant qu'il n'est pas réécrit/archivé par décision
   humaine (classification CLAUDE.md §5 : `UNKNOWN` = ne pas supprimer).
4. Le vocabulaire de verdict auto-certifiant des profils (`*_COMPLETE`, `CLOSED`,
   `PASS`) ne vaut pas certification (§1) ; il doit être renommé lors de la migration.

Diagnostic complet par fichier :
[AGENT_ECON_A0_GITHUB_AGENTS_INVENTORY.md](../forensics/AGENT_ECON_A0_GITHUB_AGENTS_INVENTORY.md).

---

## 12. Phases et frontières

```text
A0 Forest Contract → A1 Agent Registry → A2 Problem Registry → A3 Bounty Registry
→ A4 Economy Ledger / AIC → A5 Cost Accounting → A6 Worker Sandbox
→ A7 Independent Review → A8 GitHub Automation
```

(La numérotation A0–A8 est celle de #284 ; seul l'intitulé de A0 diffère — voir §16, I9.)

| Phase | Propriétaire de | Interdit dans les phases précédentes |
|---|---|---|
| A0 | constitution, plafonds, interdits | — |
| A1 | identité, spec, états, événements, intégrité des agents | tout ce qui suit |
| A2 | problèmes, cycle `CANDIDATE_PROBLEM → VERIFIED_PROBLEM` | registre de problèmes dans A1 |
| A3 | bounties | bounty/claim/récompense dans A1–A2 |
| A4 | ledger AIC, wallets, treasury | solde/wallet/AIC dans A1–A3 |
| A5 | coût réel API/compute | coût dans A1–A4 |
| A6 | sandbox, branches/PR isolées, enforcement runtime | worker, scheduler, provider, credential avant A6 |
| A7 | review indépendante (F4) | review exécutable avant A7 |
| A8 | automatisation GitHub | toute mutation GitHub avant A8 |

A1 ne contient **aucune** logique de A2+ : pas de Problem Registry, de bounty, de wallet,
de balance AIC, de worker, de scheduler, de mutation GitHub.

---

## 13. Critères d'acceptation A0 — questions et réponses

Si une réponse reste ambiguë, A0 n'est pas fini. Chaque réponse est ancrée.

| # | Question | Réponse | Ancre |
|---|---|---|---|
| 1 | Qu'est-ce qu'un agent ? | identité logique stable + specs immuables ; ni processus, ni modèle, ni autorité | §2 |
| 2 | Qu'est-ce qu'une capability ? | permis nommé, borné, de catalogue fermé, non-autoritaire ; nécessaire jamais suffisante | §2, catalogue |
| 3 | Qu'est-ce qu'une authority ? | pouvoir de rendre un état contraignant : décision (humain) et vérité (PPL/FIN) ; aucune détenue par un agent | §2, §5, §6 |
| 4 | Que sont F0–F4 ? | plafonds d'action : lire / proposer / vérifier / construire en isolation (réservé) / relire indépendamment (réservé) | §4 |
| 5 | Qui peut détecter ? | F1 propose un `CANDIDATE_PROBLEM` ; F0 observe ; F2 vérifie | §4 |
| 6 | Qui peut coder ? | aucun agent en V1 ; F3 (futur, isolé, jamais merge/deploy) ; l'humain via la gouvernance | §4, §3 |
| 7 | Qui peut reviewer ? | F4 (futur) ; jamais l'auteur ; peut bloquer, pas accepter | §4, §8 |
| 8 | Qui peut merger ? | aucun agent (`MAIN_MERGE`, `MERGE_AUTHORIZATION`) ; l'humain via les protections | §5, §6 |
| 9 | Qui peut déployer ? | aucun agent (`RUNTIME_DEPLOY`, `DEPLOY_AUTHORIZATION`) ; l'humain sous gate runtime | §5, §6, §9 |
| 10 | Qui peut modifier PAPER ? | aucun agent ; aucun domaine runtime/PPL/FIN n'existe dans le périmètre | §6, §9 |
| 11 | L'AIC peut-il acheter de l'autorité ? | non : constante `false` + `AIC_BUY_AUTHORITY` interdit | §7.2 |
| 12 | La réputation ? | non : constante `false` + `REPUTATION_GRANT_AUTHORITY` interdit | §7.3 |
| 13 | Le consensus d'agents ? | non : constante `false` + `CONSENSUS_AUTHORITY_ASSERT` interdit ; erreurs corrélées | §7.5 |
| 14 | Un agent peut-il reviewer son propre travail ? | non : constante `own_work_review_forbidden = true` | §8 |
| 15 | Que signifie `REGISTERED` ? | identité connue du registre, pas worker actif | §10 |
| 16 | `agent_id` vs `agent_spec_id` ? | logique stable (namespace, nom canonique, classe) vs version exacte et matérielle d'une spec | A1 §2 |
| 17 | Capability inconnue ? | rejet (`UNKNOWN_CAPABILITY`), jamais de repli permissif | §6, catalogue |
| 18 | Migration des anciens `.github/agents` ? | nouvelle spec par PR humaine ; legacy jamais hérité ; diagnostic par fichier | §11, inventaire |

---

## 14. Amendement et fail-closed

- **Deux dimensions de version, à ne pas confondre.** `agent_schema` (`AGENT_SPEC_V1`)
  est la version **technique** de la forme d'une spec ; `constitution_version`
  (`AGENT_ECON_A0_FOREST_V1`) est la version **normative** de la constitution sous
  laquelle une spec a été produite. Le schéma technique peut évoluer sans modification
  constitutionnelle, et la constitution peut évoluer sans exactement la même mutation
  structurelle. Toute spec déclare explicitement sa `constitution_version`, qui est
  **matérielle** (entre dans `agent_spec_id`).
- Cette constitution et ses listes fermées (capabilities, interdits, gate humaine,
  niveaux, classes) ne sont modifiables que par une **PR humaine** gouvernée, avec
  nouvel identifiant de constitution et, si la forme change, incrément de `agent_schema`.
  Aucune sortie d'agent, aucune spec,
  aucun consensus, aucun statut économique n'amende la constitution.
- Toute valeur inconnue (capability, classe, niveau, champ, état, événement, raison)
  est **rejetée**. Il n'existe aucun repli permissif ni valeur par défaut tacite.
- Aucune réparation silencieuse : une anomalie d'intégrité rend le registre non
  certifiable, elle n'est jamais corrigée par le lecteur ni par l'agent.
- Une spec V1 valide reste une *déclaration bien formée*, pas une autorisation.
- La modification de profils ou de contrats par un agent ne vaut pas gouvernance ;
  voir §16, I8 sur la protection CODEOWNERS.

---

## 15. Non-goals absolus de cette mission

Aucun fichier `worker.py`, `runner.py`, `scheduler.py`, `daemon.py`, `provider.py`,
`claude_client.py`, `openai_client.py`, `github_writer.py`, `wallet.py`,
`treasury.py`, `bounty_registry.py`, `problem_registry.py`, `runtime_service.py`, ni
`agent_economy/*.py`. Aucune dépendance (LangChain, CrewAI, AutoGen, autre) ajoutée.
Aucun loader, service, registre exécutable. Aucun provider binding réel. Aucun
changement frontend. Aucun SSH, restart, déploiement.

Cette mission ne contient aucune autorisation, plus récente et vérifiée dans #284, pour
une implémentation source A1 : le dernier état lu de #284 (statut courant du
2026-10-01 + deux commentaires du 2026-09-27) indique `ARCHITECTURE FUTURE / AUCUNE
AUTORITÉ RUNTIME` et « documentation/contract-only ». **FAIL CLOSED : contract-only.**

---

## 16. Incohérences observées (non corrigées hors scope)

Classement : `OBSERVED | NEEDS_REVIEW | BLOCKING | NON_BLOCKING`.
`BLOCKING` s'entend « bloque la migration/l'étape indiquée », pas cette mission.

| ID | Classe | Observation | Preuve | Composant | Risque | Mission future |
|---|---|---|---|---|---|---|
| I1 | BLOCKING (migration) | `sniper-engine.agent.md` décrit l'exécution d'ordres « en quelques secondes » ; aucun front matter, aucun `tools` | `.github/agents/sniper-engine.agent.md` (20 lignes) | profil legacy | si chargé par la plateforme sans restriction, intention d'exécution d'ordres | réécriture/archivage par décision humaine ; hors #286 |
| I2 | BLOCKING (migration) | `hedge-fund-architect` : `tools: [read, edit, search, execute, agent, todo]`, `agents: [sniper-engine]` (délégation transitive vers I1), règle « jamais de live *sauf si l'utilisateur le demande* », chemins `crypto_quant_v16/`, `main_v16.py` absents de l'arbre suivi | `.github/agents/hedge-fund-architect.agent.md` ; `git ls-files` | profil legacy | pouvoir d'édition+exécution large ; contourne #286 si invoqué ; représentation d'architecture périmée | `BLOCKED_LEGACY_RECONCILIATION` ; décision humaine d'archiver ou réécrire |
| I3 | NEEDS_REVIEW | 5 profils (`security-Guardian-agent`, `statistician-agent`, `system-diagnostic`, `../repo-architect`, `../research-scientist`) ont un `---` d'ouverture **sans fermeture** et **aucun `tools`** : pouvoirs non déclarés, restrictions seulement en prose | lecture des fichiers | profils legacy | enforcement indéterminé ; comportement par défaut de la plateforme **non vérifié ici** (INFERRED, pas prouvé) | vérifier la sémantique plateforme en lecture seule ; migrer |
| I4 | NEEDS_REVIEW, NON_BLOCKING | `.github/copilot-instructions.md` décrit une architecture legacy (`crypto_quant_v16`, `quant-ai-system`, `main_v16.py`) absente de l'arbre | `.github/copilot-instructions.md` | instructions agent | guide un agent vers des chemins périmés | revue documentaire |
| I5 | NEEDS_REVIEW | autres surfaces d'instruction agent **non inventoriées** par cette mission : `.github/prompts/*.prompt.md`, `.github/instructions/`, `.github/skills/` | `ls .github` | surfaces d'instruction | capacités implicites non évaluées | étendre l'inventaire |
| I6 | NON_BLOCKING | numérotation ADR dupliquée (deux `0019`, deux `0020`, deux `0008`) | `docs/adr/` | ADR | ambiguïté de référence ; ce contrat cite les ADR **par nom de fichier** | hygiène ADR |
| I7 | NEEDS_REVIEW, NON_BLOCKING | verdicts auto-labellisés (`CARTOGRAPHY_COMPLETE`, `DATA_PROVENANCE_COMPLETE`, `DECISION_GRAPH_CLOSED`, `READY_FOR_PROMPT`, `PASS`) | profils lecture seule | vocabulaire | lecture comme certification | renommage à la migration |
| I8 | **NEEDS_REVIEW** — **BLOCKING avant toute mutation GitHub autonome / A8** ; **NON_BLOCKING** pour la réconciliation de contrat A0/A1 | `.github/CODEOWNERS` couvre `/.github/` (profils d'agents) et `/CLAUDE.md`, mais **pas** `docs/contracts/` : cette constitution et ses schémas ne sont **pas** protégés par CODEOWNERS | `.github/CODEOWNERS` (32 lignes) | gouvernance GitHub | une PR rédigée par un agent pourrait modifier la constitution sans revue du propriétaire si les protections de branche ne l'exigent pas (**non vérifié ici** ; les protections de branche n'ont pas été lues) | mission de protections GitHub distincte (CLAUDE.md §4) ; **non faite ici** |
| I9 | NON_BLOCKING | #284 intitule A0 « contrat économique et frontières » ; cette mission livre A0 sous le nom « Forest Maintenance Contract » (domaine de maintenance seulement). La partie économique (AIC, ledger, coûts) relève de A4/A5 et n'est pas couverte ici. Les phases A1–A8 sont alignées avec #284 (A7 y est nommée « Reviewer/Validator agents », A8 « GitHub issue/PR automation ») | issue #284 | roadmap | un lecteur pourrait croire A0 « contrat économique » livré | aligner l'intitulé de #284 après revue humaine ; livrer le contrat économique avec A4/A5 |
| I10 | OBSERVED | pas de précédent `*.schema.json` : les JSON machine-lisibles de `docs/contracts/` sont des profils/revues, pas des JSON Schemas | `docs/contracts/` | conventions | — | voir A1 §2 |
| I11 | OBSERVED | `RL-CANDIDATE` registre : événements avec `event_id` déterministe, `registry_sequence`, ordinal par objet, **sans** chaîne de hash ; D5B durable : chaîne de hash avec `GENESIS`. A1 reprend les deux idées | `research_candidate/registry.py`, `observability/operator_decisions/durable_store.py` | précédents | — | — |

---

## 17. Verdict

`AGENT_ECON_A0_FOREST_CONTRACT_R1_1_READY_FOR_CERTIFICATION` (proposition ; non certifié).

**Portée de certification.** Ce verdict ne couvre que le sous-périmètre contractuel
`AGENT_ECON_A0_FOREST_CONTRACT` (et `AGENT_ECON_A1_AGENT_REGISTRY_CONTRACT`). Il ne
clôt **pas** l'A0 économique de #284 : AIC, Treasury, wallets et comptabilité des coûts
restent du travail futur (A4/A5). Non déclaré : `AGENT_ECON_A0_ECONOMIC_CONTRACT_COMPLETE`.

Non déclaré : `CERTIFIED`, `AGENT_ECONOMY_DEPLOYED`,
`AGENT_ECONOMY_ARCHITECTURE_CERTIFIED`. Aucune autorité runtime n'est créée ou
modifiée ; #286 reste actif.
