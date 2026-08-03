# SCIENTIFIC_SAFETY_CONTRACT.md — SSC

> **Statut : spécification des invariants. Aucun test n'est écrit.**
> Ce document liste les lois du système et l'état d'application de chacune.
> L'écriture des contrôles automatiques est l'étape suivante, distincte.

---

## 1. Nature du document

Une constitution est un texte de gouvernance : on l'invoque. Un **contrat de
sécurité scientifique** est un ensemble d'invariants qu'une machine évalue :
on ne l'invoque pas, il s'applique.

Chaque commit, chaque déploiement et chaque expérience devra satisfaire ce
contrat — **à concurrence de l'état d'application de chaque article**.

---

## 2. Le cliquet à quatre états

```
DESIGNED  ──▶  OBSERVED  ──▶  ENFORCED_NEW  ──▶  ENFORCED_ALL
```

| État | Signification | Effet CI |
|---|---|---|
| `DESIGNED` | L'objet ou le concept n'existe pas encore. L'invariant est **déclaré** comme faisant partie du modèle, mais rien ne peut être observé | aucun |
| `OBSERVED` | Mesurable aujourd'hui. Le contrôle tourne et publie un résultat | **ne bloque rien** |
| `ENFORCED_NEW` | Bloque le code nouveau ou modifié uniquement | bloque partiellement |
| `ENFORCED_ALL` | Bloque tout | bloque totalement |

### Règles du cliquet

| # | Règle |
|---|---|
| **SSC-R1** | La progression est **irréversible**. Un article ne redescend jamais d'état |
| **SSC-R2** | Toute promotion est **datée et signée** par l'opérateur, et enregistrée |
| **SSC-R3** | Un article `OBSERVED` actuellement violé ne peut pas être promu tant que la violation subsiste |
| **SSC-R4** | Un article n'est mis en `ENFORCED_ALL` d'emblée que s'il est **déjà satisfait aujourd'hui** — on verrouille un invariant quand c'est gratuit, jamais quand c'est devenu contraignant |
| **SSC-R5** | La sortie de `DESIGNED` exige que l'objet concerné existe et soit schématisé |

**SSC-R4 est la règle la plus importante.** Elle est la raison pour laquelle
l'interdiction faite aux IA d'avoir une autorité d'exécution doit être verrouillée
**maintenant** : elle est vraie aujourd'hui gratuitement, parce qu'aucune IA n'est
branchée. Le jour où le conseil existera, la verrouiller coûtera des arbitrages
et des exceptions.

### Pourquoi `DESIGNED` était nécessaire

Sans lui, un invariant portant sur un objet inexistant n'a que deux issues :
être omis (et donc oublié), ou être déclaré `OBSERVED` alors qu'aucune
observation n'est possible — ce qui produit un contrôle qui ne mesure rien et
qu'on finit par supprimer. `DESIGNED` enregistre l'intention sans mentir sur la
capacité.

---

## 3. Deux objets de premier niveau

Ces deux objets complètent le `KNOWLEDGE_MODEL.md`. Aucun n'existe aujourd'hui :
tous les invariants qui les concernent sont donc `DESIGNED`.

### 3.1 `Deployment` — quel binaire tournait réellement

C'est l'objet manquant du modèle, et l'endroit où ce projet a le plus saigné.

```
Deployment:
  id                  : DEP-YYYY-NNN, permanent, jamais réattribué
  commit              : SHA du dépôt source
  worktree_clean      : bool — l'arbre était-il propre au moment du build
  build_id            : identifiant de la construction
  artefacts[]         : { path, sha256, size }   # ce qui a été transféré
  runtime_hash        : hash de l'ensemble des artefacts déployés
  machine             : { host, ip, os, arch, hostname }
  container           : image + digest, ou null
  python_env          : version + hash du lock de dépendances
  config_hash         : hash de la configuration effective (secrets exclus)
  policy_id           : Policy en vigueur
  calibration_ids[]   : calibrations actives
  entrypoint          : chemin réellement lancé (constaté, pas déclaré)
  process_start       : horodatage UTC du démarrage constaté
  process_stop        : horodatage UTC de l'arrêt, ou null
  operator            : qui a déclenché
  signature           : signature de l'opérateur
  verification        : { method, verified_at, result }
```

**Trois propriétés fixent la valeur de cet objet.**

*Le champ `entrypoint` est **constaté**, jamais déclaré.* Mesuré cette semaine :
`scripts/crypto_advisor.service` du dépôt déclare `advisor_loop.py`, fichier
inexistant, tandis que l'unité systemd réelle lance `core/advisor_loop.py`. Un
`Deployment` qui recopie la déclaration reproduirait le mensonge ; il doit
enregistrer ce que `ps` et `systemctl` répondent.

*Le champ `verification` est obligatoire et postérieur au transfert.* L'incident
du 2026-07-09 — trois tags d'audit annotés créés sur de faux succès, 55 fichiers
sur 80 jamais transférés — est précisément un déploiement déclaré sans être
vérifié. Un `Deployment` non vérifié est un `Deployment` invalide.

*Chaque `Event` et chaque `Trade` porte un `deployment_id`.* C'est ce qui rend
répondable, dans cinq ans : *quel code exact a produit ce trade, sur quelle
machine, sous quelle politique*. Aujourd'hui la réponse exige une enquête —
j'ai dû comparer des md5 normalisés pour établir que la production exécutait
`f427895` du 20/07.

### 3.2 `ResearchEpoch` — le contexte scientifique complet

```
ResearchEpoch:
  id                  : EPO-NNN, monotone, jamais réutilisé
  opened_at           : UTC
  closed_at           : UTC, ou null si courante
  cause               : pourquoi l'époque s'ouvre
  deployment_ids[]    : déploiements ayant tourné pendant l'époque
  policy_id           : politique en vigueur
  calibration_ids[]   : calibrations actives
  dataset_id          : corpus applicable + borne CLEAN_DATA_SINCE
  universe            : univers tradé (liste épinglée + hash)
  replay_ids[]        : rejeux menés sous cette époque
  knowledge_graph_ver : version du graphe
  runtime_hash        : hash du runtime dominant
  comparability       : { previous_epoch, comparable: bool, reason }
  reconstructible     : bool + méthode
```

**Le champ `comparability` est ce qui manque le plus aujourd'hui.** Quatre bornes
`CLEAN_DATA_SINCE` en six semaines ont chacune remis N à zéro, sans qu'aucun
artefact n'enregistre formellement si la comparaison inter-époque restait
possible. La comparabilité est une **propriété déclarée et justifiée**, pas une
supposition.

**Le champ `reconstructible`** matérialise l'objectif « recharge l'époque 17 » :
une époque est reconstructible si son `deployment` est rejouable, son corpus
est gelé et son `runtime_hash` est retrouvable. Une époque non reconstructible
est enregistrée comme telle — c'est une dette, pas une omission.

### 3.3 Relation aux objets existants

```
ResearchEpoch ──CONTAINS──▶ Deployment ──RUNS──▶ Policy
       │                         │
    SCOPES                    PRODUCES
       ▼                         ▼
   Dataset                    Event ──▶ Trade ──▶ Decision
       │                                              │
    USED_BY                                      GOVERNED_BY
       ▼                                              ▼
   Experiment ──▶ Replay ──▶ Verdict ──▶ Calibration ──▶ Policy
```

La chaîne `Trade → Deployment → commit → artefacts+hashes` est ce qui distingue
un laboratoire d'un atelier. Elle est aujourd'hui **rompue en trois endroits
mesurés** : les trades ne portent pas de `policy_version`, aucun `Deployment`
n'existe, et la machine de production n'est pas un dépôt git.

---
---
---

## 4. Registre des invariants

**117 invariants**, produits par une campagne en trois passes : rédaction par domaine, vérification adverse invariant par invariant, puis critique de complétude et de doublons.

### 4.1 Traçabilité de la production

| Étape | Résultat |
|---|---:|
| Invariants rédigés | 116 |
| Rejetés par la vérification adverse | 3 |
| Signalés avec preuve suspecte | 18 |
| Fusionnés comme doublons | 3 |
| **Retenus au registre** | **117** |

Verdicts de la passe adverse sur les invariants retenus :

| Verdict | Nombre |
|---|---:|
| `CORRIGER` | 77 |
| `GARDER` | 33 |
| `AJOUT_CRITIQUE` | 7 |

`CORRIGER` signifie que l'énoncé ou l'état a été amendé par le vérificateur, pas que l'invariant est douteux. Les corrections sont intégrées ci-dessous.

### 4.2 Répartition par état

| État | Nombre | Part |
|---|---:|---:|
| `DESIGNED` | 65 | 56 % |
| `OBSERVED` | 45 | 38 % |
| `ENFORCED_NEW` | 4 | 3 % |
| `ENFORCED_ALL` | 3 | 3 % |
| **Total** | **117** | |

### 4.3 Corrections d'autorité appliquées après la campagne

Le critique a établi que plusieurs invariants étaient placés en `ENFORCED_*` alors qu'ils sont **actuellement violés** — ce que SSC-R4 interdit, sous peine d'une CI rouge dès le premier jour et d'un contrat désactivé dans la semaine. Rétrogradations appliquées :

| Invariant | État proposé | État retenu | Motif |
|---|---|---|---|
| `No Online Learning In Decision Path` | ENFORCED_ALL | **OBSERVED** | clause large non adossée à une mesure — SSC-R4 |
| `Single Instantiated Kill Switch` | ENFORCED_ALL | **OBSERVED** | clause d'import violée (2 modules kill switch exécutés) — SSC-R4 |
| `Systemd ExecStart Path Exists` | ENFORCED_ALL | **OBSERVED** | violé aujourd'hui (ExecStart=advisor_loop.py inexistant) — SSC-R4 interdit ENFORCED_ALL |
| `Audit Tag Truthfulness` | ENFORCED_NEW | **OBSERVED** | rouge à perpétuité si universel sur l'historique — portée à restreindre au neuf avant promotion |
| `Single Clean Boundary Source` | ENFORCED_NEW | **OBSERVED** | proxy à fort taux de faux positifs signalé par le critique |
| `Epoch Boundary Requires Existing ADR` | ENFORCED_NEW | **OBSERVED** | clause auto-bloquante signalée par le critique |
| `Human Merge Only` | ENFORCED_NEW | **OBSERVED** | clause historique rouge au premier balayage — scinder avant promotion |

Doublons fusionnés :

| Invariant retiré | Fusionné dans |
|---|---|
| `D3/Service Unit Truthfulness` | `D2/Systemd ExecStart Path Exists` |
| `D3/Single Decision Engine Host` | `D2/Single Live Engine Instance` |
| `D6/Hard Veto Cap` | `D1/Hard Veto Cap` |

### 4.4 Preuves à revérifier — 18 invariants

Le vérificateur adverse a signalé que la preuve citée mentionne un fichier, une ligne ou un chiffre **absent du corpus de faits mesurés**. Ces invariants sont conservés — leur énoncé reste valable — mais leur champ *preuve* doit être re-mesuré avant toute promotion d'état. **Aucun d'eux ne peut passer en `ENFORCED_*` en l'état.**

| ID | Invariant | État |
|---|---|---|
| `SSC-D1-12` | Executed Decision Dependency | OBSERVED |
| `SSC-D4-01` | Epoch Id Uniqueness | DESIGNED |
| `SSC-D4-02` | Closed Epoch Immutable | DESIGNED |
| `SSC-D4-05` | Epoch Required On Experimental Variable Change | DESIGNED |
| `SSC-D4-06` | Epoch Required On Data Boundary Change | DESIGNED |
| `SSC-D4-07` | Single Clean Boundary Source | OBSERVED |
| `SSC-D4-08` | Canonical Population Loader | ENFORCED_NEW |
| `SSC-D4-10` | Single Epoch Per Corpus | DESIGNED |
| `SSC-D4-11` | Bypass Trade Indelible Mark | OBSERVED |
| `SSC-D4-15` | Holdout Reserve Untouched | DESIGNED |
| `SSC-D5-02` | Single Intervention Per Experiment | OBSERVED |
| `SSC-D5-03` | Single Primary Metric | OBSERVED |
| `SSC-D5-04` | Stopping Rule Preregistered | OBSERVED |
| `SSC-D5-05` | Experiment Corpus Bound Single Source | ENFORCED_NEW |
| `SSC-D7-01` | Permanent Object Identifier | DESIGNED |
| `SSC-D7-14` | Cited Norm Exists | OBSERVED |
| `SSC-D7-16` | Generated Bootstrap Docs | DESIGNED |
| `SSC-D7-18` | Amnesic Agent Test | DESIGNED |

### 4.5 Table de synthèse

| ID | Nom | Objet | État | Portée |
|---|---|---|---|---|
| `SSC-D1-01` | Single Decision Writer | Verdict d'exécution trade_allowed (core/advisor_loop.py) | `OBSERVED` | merge |
| `SSC-D1-02` | Decision Write Site Ratchet | Sites d'écriture de trade_allowed dans le code atteignable p | `ENFORCED_NEW` | commit |
| `SSC-D1-03` | Post Verdict Immutability | Verdict d'exécution une fois calculé | `OBSERVED` | merge |
| `SSC-D1-04` | Full Refusal Attribution | Enregistrement de décision de chaque cycle | `DESIGNED` | experience |
| `SSC-D1-05` | Layer Type Registry | Registre versionné des couches du chemin de décision | `DESIGNED` | commit |
| `SSC-D1-06` | Hard Veto Cap | Couches typées VETO_DUR dans le registre | `DESIGNED` | merge |
| `SSC-D1-07` | Observer Non Interference | Couches typées OBSERVATEUR (ADR-0007) | `DESIGNED` | merge |
| `SSC-D1-08` | Pure Decision Function | Corps de la fonction qui calcule le verdict d'exécution | `OBSERVED` | merge |
| `SSC-D1-09` | No Environment Bypass | Variables d'environnement du processus runtime | `OBSERVED` | merge |
| `SSC-D1-10` | Bypass Trade Tagging | Marqueur de bypass dans l'enregistrement de trade | `DESIGNED` | experience |
| `SSC-D1-11` | No Dead Element In Decision Path | Paramètres et valeurs locales de la fonction de décision | `OBSERVED` | merge |
| `SSC-D1-12` | Executed Decision Dependency ⚠ | Modules dont dépendent les termes du verdict | `OBSERVED` | deploiement |
| `SSC-D1-13` | Authority Class Name Unicity | Noms de classes d'autorité (Gate, KillSwitch, StateMachine,  | `OBSERVED` | merge |
| `SSC-D1-14` | No Runtime Parameter Write | Fichiers de paramètres et de configuration lus par le runtim | `OBSERVED` | merge |
| `SSC-D1-15` | No Online Learning In Decision Path | Drapeaux de calibration automatique et leur unique consommat | `OBSERVED` | runtime_boot |
| `SSC-D2-01` | Single Runtime State Machine | Machine d'état du moteur (RuntimeStateMachine, SystemStateMa | `OBSERVED` | merge |
| `SSC-D2-02` | Single System State Vocabulary | Énumération SystemState | `OBSERVED` | merge |
| `SSC-D2-03` | State Transition Ledger | Journal des transitions d'état du moteur | `DESIGNED` | merge |
| `SSC-D2-04` | Single Instantiated Kill Switch | Kill switch (supervision/killswitch_hardened.py, supervision | `OBSERVED` | merge |
| `SSC-D2-05` | Kill Switch Halt Proof | Effet de l'activation du kill switch sur trade_allowed | `OBSERVED` | merge |
| `SSC-D2-06` | No Class Name Aliasing | Alias d'import de classe (core/advisor_runtime_adapters.py:1 | `ENFORCED_NEW` | commit |
| `SSC-D2-07` | Single SAFE_MODE Writer | Drapeau SAFE_MODE | `OBSERVED` | merge |
| `SSC-D2-08` | Fail Closed Outside Running | Conjonction trade_allowed (core/advisor_loop.py:1983) face à | `OBSERVED` | merge |
| `SSC-D2-09` | State Machine Never Writes Decision | Frontière entre machine d'état et décision d'exécution | `ENFORCED_ALL` | commit |
| `SSC-D2-10` | Single Live Engine Instance | Parc d'hôtes exécutant core/advisor_loop.py | `OBSERVED` | deploiement |
| `SSC-D2-11` | Engine Instance Lock | Verrou d'instance du processus moteur au point d'entrée core | `DESIGNED` | runtime_boot |
| `SSC-D2-12` | Systemd ExecStart Path Exists | scripts/crypto_advisor.service | `OBSERVED` | commit |
| `SSC-D2-13` | Deployed Unit Matches Repo Unit | Unité systemd réellement installée sur l'hôte de production | `OBSERVED` | deploiement |
| `SSC-D2-14` | No Untagged Execution Override | FORCE_TEST_EXECUTION (core/advisor_loop.py:1943-1980) | `OBSERVED` | runtime_boot |
| `SSC-D3-01` | Unique Deployment Identity | Objet Deployment (registre des déploiements) | `DESIGNED` | deploiement |
| `SSC-D3-02` | Trade Carries Deployment | Enregistrements de trades (dataset scientifique, époque V4) | `DESIGNED` | runtime_boot |
| `SSC-D3-03` | Event Carries Deployment | Journal d'événements append-only (Event, L1) | `DESIGNED` | runtime_boot |
| `SSC-D3-04` | Artifact Hash Matches Commit | Artefacts transférés vers la machine de production | `DESIGNED` | deploiement |
| `SSC-D3-05` | Verification Precedes Declaration | Champ verification d'un Deployment | `DESIGNED` | deploiement |
| `SSC-D3-06` | Audit Tag Truthfulness | Tags git annotés deploy-YYYYMMDD-HHMM | `OBSERVED` | deploiement |
| `SSC-D3-07` | Deploy Script Stdin Safety | scripts/deploy_vps.sh | `OBSERVED` | commit |
| `SSC-D3-08` | Clean Worktree Deploy | Arbre de travail du dépôt source au moment du déploiement | `OBSERVED` | deploiement |
| `SSC-D3-09` | Signed Deployment | Champs operator et signature d'un Deployment | `DESIGNED` | deploiement |
| `SSC-D3-10` | Entrypoint Is Observed Not Declared | Champ entrypoint d'un Deployment | `DESIGNED` | deploiement |
| `SSC-D3-11` | Production Code Fingerprint | Machine de production (VPS exécutant le moteur) | `OBSERVED` | deploiement |
| `SSC-D3-12` | One Active Deployment Per Machine | Registre des Deployment, dimension machine | `DESIGNED` | deploiement |
| `SSC-D3-13` | Reproducible Deployment Build | Champ runtime_hash d'un Deployment | `DESIGNED` | experience |
| `SSC-D3-14` | No Forcing Env Switch In Production | Environnement effectif du processus moteur (FORCE_TEST_EXECU | `OBSERVED` | runtime_boot |
| `SSC-D4-01` | Epoch Id Uniqueness ⚠ | ResearchEpoch — registre des époques | `DESIGNED` | commit |
| `SSC-D4-02` | Closed Epoch Immutable ⚠ | ResearchEpoch dont closed_at est renseigné | `DESIGNED` | commit |
| `SSC-D4-03` | Epoch Reference Completeness | ResearchEpoch — bloc de références | `DESIGNED` | commit |
| `SSC-D4-04` | Epoch Reconstructibility Computed | ResearchEpoch — champ reconstructible | `DESIGNED` | merge |
| `SSC-D4-05` | Epoch Required On Experimental Variable Change ⚠ | univers tradé épinglé et policy_version active | `DESIGNED` | deploiement |
| `SSC-D4-06` | Epoch Required On Data Boundary Change ⚠ | constante de borne d'époque CLEAN_DATA_SINCE_ACTIVE | `DESIGNED` | commit |
| `SSC-D4-07` | Single Clean Boundary Source ⚠ | constante CLEAN_DATA_SINCE_ACTIVE (scripts/data_quality.py:7 | `OBSERVED` | commit |
| `SSC-D4-08` | Canonical Population Loader ⚠ | modules producteurs de N, PF, WR, comptes de regret et seuil | `ENFORCED_NEW` | commit |
| `SSC-D4-09` | Cited ADR Exists | références ADR-NNNN dans le code et les artefacts de dataset | `OBSERVED` | commit |
| `SSC-D4-10` | Single Epoch Per Corpus ⚠ | Corpus / Dataset certifié | `DESIGNED` | experience |
| `SSC-D4-11` | Bypass Trade Indelible Mark ⚠ | FORCE_TEST_EXECUTION (core/advisor_loop.py:1941-1980) et enr | `OBSERVED` | runtime_boot |
| `SSC-D4-12` | Frozen Corpus Content Hash | Corpus à l'état FROZEN | `DESIGNED` | experience |
| `SSC-D4-13` | Corpus Immutable Once Referenced | Corpus référencé par une ExperimentSpec pré-enregistrée | `DESIGNED` | experience |
| `SSC-D4-14` | Corpus Usage Budget | Corpus — compteur usage_count et budget déclaré | `DESIGNED` | experience |
| `SSC-D4-15` | Holdout Reserve Untouched ⚠ | Corpus — fraction déclarée comme réserve | `DESIGNED` | experience |
| `SSC-D5-01` | Experiment Preregistration Precedence | ExperimentSpec scellée (experiments/EXP-*/spec.yaml) et RunM | `DESIGNED` | experience |
| `SSC-D5-02` | Single Intervention Per Experiment ⚠ | Bloc intervention de l'ExperimentSpec | `OBSERVED` | merge |
| `SSC-D5-03` | Single Primary Metric ⚠ | Bloc metrics de l'ExperimentSpec | `OBSERVED` | merge |
| `SSC-D5-04` | Stopping Rule Preregistered ⚠ | Champ design.stopping_rule de l'ExperimentSpec | `OBSERVED` | merge |
| `SSC-D5-05` | Experiment Corpus Bound Single Source ⚠ | Borne d'époque CLEAN_DATA_SINCE utilisée par tout outil d'ex | `ENFORCED_NEW` | commit |
| `SSC-D5-06` | Replay Bit Determinism | Artefacts d'un Replay (replay/*.jsonl et run_manifest.json) | `DESIGNED` | experience |
| `SSC-D5-07` | Replay Authority Identity | Autorité de décision : conjonction de 12 booléens à core/adv | `DESIGNED` | merge |
| `SSC-D5-08` | Replay Hermeticity | Processus d'exécution d'un Replay | `DESIGNED` | experience |
| `SSC-D5-09` | No Forcing Env In Replay Closure | FORCE_TEST_EXECUTION (core/advisor_loop.py:1943-1980) et tou | `OBSERVED` | experience |
| `SSC-D5-10` | Run Manifest Completeness | run_manifest.json de tout run (rejeu, ablation, walk-forward | `DESIGNED` | experience |
| `SSC-D5-11` | Replay Isolation From Production Runtime | Modules de laboratoire (ReplayEngine, ablation, walk-forward | `ENFORCED_ALL` | deploiement |
| `SSC-D5-12` | Ablation Corpus And Seed Identity | Bras d'une AblationResult (baseline incluse) | `DESIGNED` | experience |
| `SSC-D5-13` | Ablation Groups Preregistered | Liste des couches et groupes de couches désarmés, déclarée d | `DESIGNED` | experience |
| `SSC-D5-14` | No Lookahead Test Mandatory | Résultats de rejeu, d'ablation et de walk-forward | `DESIGNED` | experience |
| `SSC-D5-15` | Walk Forward Segmentation Preregistered | WalkForwardResult et son bloc de segmentation | `DESIGNED` | experience |
| `SSC-D5-16` | Mandatory Stress Scenarios | StressResult (experiments/EXP-*/stress.json) | `DESIGNED` | experience |
| `SSC-D5-17` | Cost Stress Downgrade To Inconclusive | Règle de dérivation du Verdict à partir du StressResult | `DESIGNED` | experience |
| `SSC-D5-18` | Simulator Fidelity Disclosure | run_manifest.json et Verdict, au regard de paper_trading/mex | `ENFORCED_ALL` | experience |
| `SSC-D6-01` | Verdict Immutability | Verdict | `DESIGNED` | experience |
| `SSC-D6-02` | Verdict Limitations Not Empty | Verdict.limitations[] | `DESIGNED` | experience |
| `SSC-D6-03` | Inconclusive Declares Missing Evidence | Verdict.missing_for_conclusion[] | `DESIGNED` | experience |
| `SSC-D6-04` | Succession Not Mutation | Tout objet scientifique (Verdict, Calibration, Policy, Basel | `DESIGNED` | experience |
| `SSC-D6-05` | Calibration Requires Justifying Verdict | Calibration | `DESIGNED` | deploiement |
| `SSC-D6-06` | Refuted Verdict Invalidates Dependent Calibrations | Arête Verdict —[JUSTIFIES]→ Calibration | `DESIGNED` | deploiement |
| `SSC-D6-07` | Active Policy Requires Human Signature | Policy | `DESIGNED` | runtime_boot |
| `SSC-D6-08` | Policy Change Requires Evidence Bundle | Proposal / pull request modifiant une Policy | `DESIGNED` | merge |
| `SSC-D6-09` | Publication Mandatory For Every Verdict | Publication | `DESIGNED` | experience |
| `SSC-D6-10` | Replay Verdict Declares Simulator Fidelity Gap | Verdict issu d'un rejeu ou d'une simulation | `DESIGNED` | experience |
| `SSC-D6-11` | Three Role Separation | provenance.actor_id des rôles proposer / valider / appliquer | `DESIGNED` | deploiement |
| `SSC-D6-12` | Cited ADR Must Exist | Références ADR dans le code, la documentation et les artefac | `OBSERVED` | merge |
| `SSC-D6-13` | Epoch Boundary Requires Existing ADR | Borne canonique CLEAN_DATA_SINCE (source unique scripts/data | `OBSERVED` | commit |
| `SSC-D6-14` | Human Merge Only | Branche principale du dépôt | `OBSERVED` | merge |
| `SSC-D6-15` | No Automated Deployment Trigger | Chaîne de déploiement vers la production | `OBSERVED` | deploiement |
| `SSC-D6-16` | No Runtime Auto Calibration | config/feature_flags.py et chemins d'écriture des paramètres | `OBSERVED` | commit |
| `SSC-D7-01` | Permanent Object Identifier ⚠ | Identifiant canonique de tout objet scientifique (Event, Obs | `DESIGNED` | commit |
| `SSC-D7-02` | Role Impl Separation | Bloc provenance : champs actor_id (rôle permanent) et actor_ | `DESIGNED` | commit |
| `SSC-D7-03` | Mandatory Provenance Block | Bloc provenance de tout objet déposé dans un registre scient | `DESIGNED` | commit |
| `SSC-D7-04` | Open Text Primary Representation | Représentation primaire de tout objet de connaissance (regis | `DESIGNED` | commit |
| `SSC-D7-05` | Graph Is Derived Index | Base du Knowledge Graph et fichiers texte versionnés dont el | `DESIGNED` | merge |
| `SSC-D7-06` | No Retroactive Edges | Arêtes du Knowledge Graph reliant des objets créés avant l'a | `DESIGNED` | commit |
| `SSC-D7-07` | Edges Never Deleted | Fichiers de relations du Knowledge Graph (arêtes typées et d | `DESIGNED` | commit |
| `SSC-D7-08` | Acyclic Supersedes | Sous-graphe SUPERSEDES (champs supersedes / superseded_by de | `DESIGNED` | commit |
| `SSC-D7-09` | No AI Decision Authority | Sites d'écriture de la décision d'exécution trade_allowed da | `OBSERVED` | commit |
| `SSC-D7-10` | No Agent Write Identity In Production | Identités, jetons et clés disposant d'un droit d'écriture su | `DESIGNED` | deploiement |
| `SSC-D7-11` | No Self Validation | Chaîne Hypothesis → Critique → Réplication → Verdict et cham | `DESIGNED` | experience |
| `SSC-D7-12` | Blind Contribution | Contributions d'un même tour de conseil (scellement et champ | `DESIGNED` | experience |
| `SSC-D7-13` | Verified Citations | Champs de référence des contributions et objets du graphe (e | `DESIGNED` | commit |
| `SSC-D7-14` | Cited Norm Exists ⚠ | Références normatives ADR-XXXX citées par le code et la docu | `OBSERVED` | commit |
| `SSC-D7-15` | Mandatory Limitations Field | Champ limitations des contributions, observations et verdict | `DESIGNED` | commit |
| `SSC-D7-16` | Generated Bootstrap Docs ⚠ | Les six documents d'amorçage de knowledge/ (STATE_OF_KNOWLED | `DESIGNED` | merge |
| `SSC-D7-17` | Stale Doc Marking | Fichiers markdown du dépôt décrivant l'état du système (raci | `OBSERVED` | commit |
| `SSC-D7-18` | Amnesic Agent Test ⚠ | Manifeste de reprise : les six questions Q-A à Q-F et les po | `DESIGNED` | merge |
| `SSC-D8-01` | Executed Module Inventory Is A Versioned Artifact | Inventaire des modules réellement exécutés en production (me | `OBSERVED` | deploiement |
| `SSC-D8-02` | No Import Cycle In Decision Closure | Graphe d'import des modules exécutés en production | `OBSERVED` | merge |
| `SSC-D8-03` | No sys.path Dependent Internal Import | Clauses d'import des modules exécutés en production | `OBSERVED` | merge |
| `SSC-D8-04` | Single Definition For Executed Record Types | Types de données du chemin d'enregistrement (TradeRecord, Po | `OBSERVED` | merge |
| `SSC-D8-05` | Evaluation Horizon Covered By Realized Holding | Horizon d'évaluation de la spec scellée et distribution de d | `DESIGNED` | experience |
| `SSC-D8-06` | Single Fingerprint Canonicalization Spec | Règle de calcul d'empreinte utilisée par tous les contrôles  | `OBSERVED` | commit |
| `SSC-D8-07` | Safe Mode Halt Proof | Effet de SAFE_MODE sur l'ouverture de position | `OBSERVED` | experience |

⚠ = preuve à revérifier (§4.4)

---

## 5. Registre détaillé

### D1 — Autorité d'exécution et décision

#### `SSC-D1-01` — Single Decision Writer

| | |
|---|---|
| **Objet** | Verdict d'exécution trade_allowed (core/advisor_loop.py) |
| **État** | `OBSERVED` |
| **Portée du blocage** | merge |

**Énoncé.** Dans l'ensemble des modules exécutés en production, il existe exactement UN site d'écriture du verdict d'exécution trade_allowed. Tout autre site qui affecte cette variable ou la clé "trade_allowed" d'un dictionnaire de résultat constitue une violation.

**Justification de l'état.** Le contrôle est exécutable aujourd'hui (analyse statique du dépôt + liste des 210 modules exécutés mesurée par .pyc) et publierait immédiatement un résultat, mais il ne peut rien bloquer : l'état courant le viole 5 fois dans le fichier d'entrée lui-même. Le passer en ENFORCED exigerait de refondre la fonction de décision (dette DEBT-GV-01).

**Preuve actuelle.** 5 sites d'écriture mesurés : calcul à core/advisor_loop.py:1983 (conjonction de 12 booléens) ; révocations à core/advisor_loop.py:5626 (risk_governor), :5658 (safety_auditor), :5734 et :5808 (decision_packet).

**Contrôle futur.** Analyse statique AST sur les modules exécutés en production : comptage des affectations de la variable trade_allowed et des écritures de la clé "trade_allowed". Échec si le compte est différent de 1.

#### `SSC-D1-02` — Decision Write Site Ratchet

| | |
|---|---|
| **Objet** | Sites d'écriture de trade_allowed dans le code atteignable par le runtime |
| **État** | `ENFORCED_NEW` |
| **Portée du blocage** | commit |
| **Dépend de** | `Single Decision Writer` |

**Énoncé.** Le nombre de sites d'écriture du verdict trade_allowed dans le code exécutable ne peut jamais augmenter : aucun commit ne peut introduire un site d'écriture supplémentaire au-delà du compte de référence gelé (5). Il ne peut que décroître.

**Justification de l'état.** Satisfait aujourd'hui par construction (le compte de référence est le compte mesuré). Le contrôle est un simple comparateur d'entier entre la mesure du commit et la valeur gelée, donc bloquant sans coût et sans refonte préalable. Il n'agit que sur le code nouveau ou modifié.

**Preuve actuelle.** Compte de référence = 5, mesuré : core/advisor_loop.py:1983, :5626, :5658, :5734, :5808.

**Contrôle futur.** Test de non-régression : recomptage des sites d'écriture à chaque commit et comparaison au compte de référence versionné. Échec strict si supérieur ; mise à jour obligatoire du compte de référence si inférieur.

#### `SSC-D1-03` — Post Verdict Immutability

| | |
|---|---|
| **Objet** | Verdict d'exécution une fois calculé |
| **État** | `OBSERVED` |
| **Portée du blocage** | merge |
| **Dépend de** | `Single Decision Writer` |

**Énoncé.** Le verdict consomme par le composant qui declenche l'execution est identique au verdict produit par le site de calcul : l'empreinte enregistree a la production et l'empreinte enregistree a la consommation sont egales pour chaque cycle, et toute divergence est un echec. (L'interdiction statique de reecriture en aval est supprimee de cet invariant : elle est deja entierement portee par Single Decision Writer. Etat OBSERVED conserve, portee_blocage a passer de merge a experience puisque le controle est runtime.)

**Justification de l'état.** Mesurable dès aujourd'hui par analyse statique (position des écritures relativement au site de calcul dans le graphe d'appel) et, plus tard, par comparaison d'empreinte entre le verdict calculé et le verdict consommé par l'exécution. Non bloquant : les 4 révocations mesurées sont dans le chemin exécuté.

**Preuve actuelle.** 4 réécritures postérieures au calcul de core/advisor_loop.py:1983 : core/advisor_loop.py:5626, :5658, :5734, :5808 — toutes forcent le verdict à False après coup.

**Contrôle futur.** Analyse statique du graphe d'appel : toute écriture du verdict atteignable depuis le site de calcul est un échec. Complétée par une vérification d'intégrité runtime comparant l'empreinte du verdict à sa production et à sa consommation.

#### `SSC-D1-04` — Full Refusal Attribution

| | |
|---|---|
| **Objet** | Enregistrement de décision de chaque cycle |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Layer Type Registry` |

**Énoncé.** Tout cycle dont le verdict est un refus produit un enregistrement nommant l'ensemble exact des couches ayant refusé, révocations postérieures comprises. Un refus dont la liste de couches bloqueuses est vide, absente, ou incohérente avec le verdict est interdit.

**Justification de l'état.** Le contrôle peut tourner aujourd'hui sur les enregistrements existants et publier un taux de complétude d'attribution, mais il ne peut rien bloquer tant que les 4 révocations écrivent hors du site de calcul et ne sont pas comptabilisées comme couches.

**Preuve actuelle.** 5 sites d'écriture du verdict (core/advisor_loop.py:1983 calcul ; :5626, :5658, :5734, :5808 révocations). Part des refus imputable à chaque site : NON MESURÉ.

**Contrôle futur.** Validation de schéma sur le journal de décisions : chaque enregistrement en refus doit porter une liste non vide de couches bloqueuses appartenant au registre des couches, et chaque site d'écriture doit posséder un identifiant de couche distinct.

#### `SSC-D1-05` — Layer Type Registry

| | |
|---|---|
| **Objet** | Registre versionné des couches du chemin de décision |
| **État** | `DESIGNED` |
| **Portée du blocage** | commit |

**Énoncé.** Chaque couche capable d'intervenir dans le chemin de décision est déclarée dans un registre versionné avec exactement un type parmi VETO_DUR, SCORE, OBSERVATEUR. Toute couche capable de faire passer le verdict à False est typée VETO_DUR. Aucune couche du code exécuté ne peut être absente du registre, et aucune entrée du registre ne peut être sans couche correspondante.

**Justification de l'état.** L'objet n'existe pas : il n'y a aujourd'hui aucun registre de couches, aucun typage, et les couches ne sont identifiables que par la lecture manuelle d'une conjonction de 12 booléens et de 4 révocations. Rien ne peut être observé tant que l'objet n'est pas créé.

**Preuve actuelle.** Aucun registre mesuré. Les couches sont implicites : 12 booléens conjoints à core/advisor_loop.py:1983 plus 4 révocations à :5626, :5658, :5734, :5808. Typage des couches : NON MESURÉ.

**Contrôle futur.** Validation de schéma du registre, puis analyse statique croisant les termes du calcul et les sites d'écriture du verdict avec les entrées du registre. Échec sur toute couche non déclarée ou déclarée sans code correspondant.

#### `SSC-D1-06` — Hard Veto Cap

| | |
|---|---|
| **Objet** | Couches typées VETO_DUR dans le registre |
| **État** | `DESIGNED` |
| **Portée du blocage** | merge |
| **Dépend de** | `Layer Type Registry` |

**Énoncé.** Le nombre de couches capables de faire passer seules le verdict a False ne peut jamais augmenter au-dela du compte de reference mesure, fige a 16 (12 termes conjoints a core/advisor_loop.py:1983 plus les 4 revocations a :5626, :5658, :5734, :5808) ; toute reduction met a jour le compte de reference a la baisse et de facon irreversible. Un plafond absolu inferieur (3 ou toute autre valeur) ne peut etre fixe que par un ADR signe qui le justifie explicitement.

**Justification de l'état.** Le registre qui porte le typage n'existe pas, donc le plafond n'est pas évaluable aujourd'hui. Le comptage brut des pouvoirs de veto actuels (12 termes conjoints plus 4 révocations, soit 16 pouvoirs de refus indépendants) montre que l'invariant sera violé dès sa première évaluation.

**Preuve actuelle.** 16 pouvoirs de refus indépendants mesurés : 12 booléens conjoints à core/advisor_loop.py:1983 plus les révocations :5626, :5658, :5734, :5808.

**Contrôle futur.** Comptage des entrées de type VETO_DUR dans le registre versionné et comparaison au plafond 3. Échec strict au-dessus du plafond.

#### `SSC-D1-07` — Observer Non Interference

| | |
|---|---|
| **Objet** | Couches typées OBSERVATEUR (ADR-0007) |
| **État** | `DESIGNED` |
| **Portée du blocage** | merge |
| **Dépend de** | `Layer Type Registry` |

**Énoncé.** Scinder en deux invariants distincts. (a) Observer Not In Verdict : aucune couche typee OBSERVATEUR dans le registre n'apparait parmi les termes du calcul du verdict ni parmi les sites d'ecriture du verdict — comparaison d'ensembles, DESIGNED, portee merge. (b) Observer Data Flow Isolation : aucune valeur produite par une couche OBSERVATEUR n'est lue par une couche VETO_DUR ou SCORE dans le meme cycle — analyse de flux inter-modules, DESIGNED, portee experience, a activer apres (a).

**Justification de l'état.** C'est la forme exécutable de la règle constitutionnelle de passivité des observers, mais elle est inévaluable sans le registre de typage : aujourd'hui rien ne distingue mécaniquement un observateur d'un bloqueur dans le chemin de décision.

**Preuve actuelle.** Aucune séparation observateur/décideur mesurée. Le seul consommateur de drapeau de calibration mesuré est quant_hedge_ai/agents/intelligence/regret_engine.py:339-341, avec delta toujours nul.

**Contrôle futur.** Requête de graphe sur le flux de données du cycle : recherche d'un chemin depuis une couche typée OBSERVATEUR vers le calcul du verdict ou vers une couche VETO_DUR/SCORE. Tout chemin trouvé est un échec.

#### `SSC-D1-08` — Pure Decision Function

| | |
|---|---|
| **Objet** | Corps de la fonction qui calcule le verdict d'exécution |
| **État** | `OBSERVED` |
| **Portée du blocage** | merge |

**Énoncé.** La fonction qui calcule le verdict n'effectue aucune entrée/sortie : ni lecture de fichier, ni accès réseau, ni lecture d'horloge, ni lecture de variable d'environnement, ni source aléatoire non graine. Toutes ses entrées lui sont passées en arguments explicites.

**Justification de l'état.** Le contrôle est exécutable aujourd'hui par analyse statique du sous-graphe d'appel, et il échouerait immédiatement : au moins deux lectures d'environnement sont mesurées dans le corps décisionnel. Le rendre bloquant exige d'abord l'extraction d'une fonction de décision isolée, qui n'existe pas (fichier d'entrée monolithique).

**Preuve actuelle.** core/advisor_loop.py:1943-1980 lit une variable d'environnement (FORCE_TEST_EXECUTION) à l'intérieur du corps décisionnel et en dérive l'état de 8 couches. Accès réseau, horloge et aléa dans ce corps : NON MESURÉ.

**Contrôle futur.** Analyse statique du sous-graphe d'appel de la fonction de décision avec liste noire d'appels (ouverture de fichier, socket/HTTP, horloge, lecture d'environnement, aléa non graine). Tout appel atteint est un échec.

#### `SSC-D1-09` — No Environment Bypass

| | |
|---|---|
| **Objet** | Variables d'environnement du processus runtime |
| **État** | `OBSERVED` |
| **Portée du blocage** | merge |

**Énoncé.** Aucune variable d'environnement ne peut forcer à True un terme du verdict, ni court-circuiter une couche du chemin de décision. Aucune affectation d'un terme de décision ne peut être gardée par une lecture d'environnement.

**Justification de l'état.** Directement mesurable par analyse statique aujourd'hui, et directement violé par un bloc unique et localisé. Non bloquant tant que ce bloc n'est pas retiré ou remplacé par un mécanisme tracé ; sa suppression est un geste isolé, donc l'invariant est un candidat rapide à ENFORCED_ALL.

**Preuve actuelle.** core/advisor_loop.py:1943-1980 : FORCE_TEST_EXECUTION force 8 couches à True depuis une variable d'environnement, sans marquer les trades produits.

**Contrôle futur.** Analyse statique cherchant toute affectation à True d'un terme du verdict placée sous une condition dépendant d'une lecture d'environnement. Toute occurrence est un échec.

#### `SSC-D1-10` — Bypass Trade Tagging

| | |
|---|---|
| **Objet** | Marqueur de bypass dans l'enregistrement de trade |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `No Environment Bypass` |

**Énoncé.** Tant qu'un mecanisme de bypass existe, tout trade produit alors qu'un bypass est actif porte dans son enregistrement un marqueur explicite de bypass, et l'etat des variables d'environnement du processus est enregistre au demarrage ; un enregistrement de trade depourvu du champ de marquage est invalide. La clause d'exclusion du dataset scientifique ('aucun trade marque n'entre dans le dataset d'une epoque') devient un invariant distinct du domaine dataset. Preuve a reduire a : 'core/advisor_loop.py:1943-1980 force 8 couches a True sans marquer les trades produits ; un trade force est aujourd'hui indiscernable d'un trade decide.'

**Justification de l'état.** L'objet n'existe pas : le bypass mesuré ne produit aucun marqueur, donc un trade forcé est aujourd'hui indiscernable d'un trade décidé dans le journal. On ne peut pas observer ce qui n'est pas écrit ; il faut d'abord créer le champ et l'enregistrement de l'état d'environnement au démarrage.

**Preuve actuelle.** core/advisor_loop.py:1943-1980 force 8 couches à True sans marquer les trades produits. Ce vecteur est identique à celui ayant contaminé l'époque v2 du dataset (incident 2026-07-09, gate SEC-01 inactif).

**Contrôle futur.** Validation de schéma sur le journal des trades (champ de marquage obligatoire) croisée avec l'état des variables d'environnement enregistré au démarrage du processus ; un trade non marqué alors que le bypass était actif invalide l'époque.

#### `SSC-D1-11` — No Dead Element In Decision Path

| | |
|---|---|
| **Objet** | Paramètres et valeurs locales de la fonction de décision |
| **État** | `OBSERVED` |
| **Portée du blocage** | merge |

**Énoncé.** Scinder. (a) Tout parametre declare dans la signature de la fonction de decision est transmis par au moins un site d'appel atteignable — controle statique signature contre arguments effectifs, etat OBSERVED, portee merge, aucune dependance. (b) Toute valeur calculee dans le chemin de decision est lue par au moins un terme du verdict ou declaree comme observation dans le registre des couches — etat DESIGNED, depend_de: Layer Type Registry.

**Justification de l'état.** Mesurable aujourd'hui par analyse statique de flux (signature contre arguments effectifs, puis définition-usage sur les variables locales), avec deux violations déjà établies. Non bloquant : la mise en conformité suppose de trancher le sort de la couche V2, décision non prise.

**Preuve actuelle.** 12 paramètres v2_* déclarés à core/advisor_loop.py:1082-1096, AUCUN transmis au site d'appel :5511-5568. timing_signal calculé à core/advisor_loop.py:1866-1881 puis jamais relu par la décision.

**Contrôle futur.** Analyse statique croisant la signature de la fonction de décision avec les arguments effectifs de chaque site d'appel atteignable, puis analyse définition-usage des variables locales du chemin de décision.

#### `SSC-D1-12` — Executed Decision Dependency

| | |
|---|---|
| **Objet** | Modules dont dépendent les termes du verdict |
| **État** | `OBSERVED` |
| **Portée du blocage** | deploiement |

**Énoncé.** Enonce inchange. Preuve a remplacer par : 'decision_arbitrator.py n'a produit AUCUN .pyc en production alors que core/advisor_loop.py:1996 ajoute un terme d'arbitrage a la conjonction du verdict ; le rattachement de ce terme au module decision_arbitrator.py, son nom et sa valeur par defaut sont NON MESURES. Contexte mesure : 210 modules executes sur 1115, borne statique 102-170, 52 modules classes ORPHAN/TEST_ONLY reellement executes.'

**Justification de l'état.** Mesurable aujourd'hui en croisant le graphe de dépendance des termes avec la liste des modules exécutés obtenue par présence de .pyc en production ; une violation est déjà établie. Non bloquant car le contrôle exige un accès à la machine de production, pas seulement au dépôt.

**Preuve actuelle.** ⚠ **À REVÉRIFIER** — _arb_ok est le 12e terme de la conjonction (core/advisor_loop.py:1983) et dépend de decision_arbitrator.py, qui n'a produit AUCUN .pyc en production. 210 modules exécutés mesurés sur 1115 (borne statique 102-170, dont 52 modules classés ORPHAN/TEST_ONLY par le statique sont en réalité exécutés).

**Contrôle futur.** Requête de graphe : intersection entre les dépendances transitives des termes du verdict et l'inventaire des modules exécutés en production mesuré par empreinte des .pyc. Toute dépendance hors de l'inventaire est un échec.

#### `SSC-D1-13` — Authority Class Name Unicity

| | |
|---|---|
| **Objet** | Noms de classes d'autorité (Gate, KillSwitch, StateMachine, SystemState, CapitalThrottle) |
| **État** | `OBSERVED` |
| **Portée du blocage** | merge |

**Énoncé.** Scinder en deux invariants. (a) Authority Name Collision In Production : aucun nom de classe correspondant au motif d'autorite (liste fermee et versionnee : Gate, KillSwitch, StateMachine, SystemState, CapitalThrottle) n'est defini par deux modules simultanement executes en production — preuve : 8 paires mesurees dont SystemState et CapitalThrottle, plus 18 classes Gate definies pour 3 executees ; etat OBSERVED. (b) Authority Instantiation Name Identity : au site d'instanciation, une classe d'autorite porte le nom sous lequel elle est definie, aucun alias d'import ne la renomme — preuve : KillSwitchHardened aliase en TelegramKillSwitch a core/advisor_runtime_adapters.py:109 alors que 2 classes portant reellement ce nom ne sont jamais instanciees ; etat OBSERVED. La clause 'defini au plus une fois hors tests' a l'echelle du depot est un objectif de nettoyage, pas un invariant : la retirer ou la porter par un cliquet sur les 69 noms dupliques mesures.

**Justification de l'état.** Entièrement mesurable aujourd'hui (inventaire des définitions de classes plus inventaire des modules exécutés), avec plusieurs violations établies. Non bloquant : la mise en conformité impose des renommages dans le chemin d'exécution, geste à faire hors période d'observation du dataset.

**Preuve actuelle.** 18 classes Gate définies, 3 exécutées ; GlobalRiskGate défini 2 fois (quant_hedge_ai/agents/risk/global_risk_gate.py:183 exécuté ; risk/global_risk_gate.py:63 non exécuté). KillSwitchHardened est aliasé en "TelegramKillSwitch" à core/advisor_runtime_adapters.py:109 alors que 2 autres classes portent réellement ce nom et ne sont jamais instanciées. 8 paires de noms de classes dont les DEUX définitions sont exécutées en production, dont SystemState et CapitalThrottle.

**Contrôle futur.** Analyse statique : inventaire des définitions de classes correspondant au motif d'autorité, détection des noms définis plus d'une fois hors tests, croisement avec l'inventaire des modules exécutés, et détection des imports aliasés portant sur ces classes.

#### `SSC-D1-14` — No Runtime Parameter Write

| | |
|---|---|
| **Objet** | Fichiers de paramètres et de configuration lus par le runtime |
| **État** | `OBSERVED` |
| **Portée du blocage** | merge |

**Énoncé.** Scinder. (a) No Runtime Parameter Write : le processus runtime n'ouvre aucun fichier figurant dans la liste versionnee des fichiers de parametres, seuils et drapeaux en mode ecriture, et l'empreinte de chacun de ces fichiers est identique au demarrage et a l'arret du processus — etat OBSERVED, portee merge. (b) Parameter Provenance : l'empreinte de chaque fichier de parametre en production est egale a celle de l'artefact versionne dont il est issu — etat DESIGNED, depend d'un objet de provenance de deploiement qui n'existe pas.

**Justification de l'état.** Deux moitiés mesurables aujourd'hui sans blocage : l'analyse statique des ouvertures en écriture dans le sous-graphe runtime, et la comparaison d'empreintes avant/après un cycle. Aucune mesure d'écriture n'existe encore, donc l'invariant ne peut pas être déclaré satisfait ni verrouillé.

**Preuve actuelle.** NON MESURÉ : aucune mesure d'écriture de fichier de paramètre par le processus runtime. Contexte mesuré : FEATURE_AUTO_CALIBRATION=False et FEATURE_ADAPTIVE_CALIBRATION=False (config/feature_flags.py:47,50).

**Contrôle futur.** Analyse statique des ouvertures en écriture visant des chemins de configuration depuis le sous-graphe runtime, complétée par une vérification d'intégrité comparant les empreintes des fichiers de paramètres avant et après un cycle de production.

#### `SSC-D1-15` — No Online Learning In Decision Path

| | |
|---|---|
| **Objet** | Drapeaux de calibration automatique et leur unique consommateur |
| **État** | `OBSERVED` *(rétrogradé depuis ENFORCED_ALL)* |
| **Portée du blocage** | runtime_boot |
| **Dépend de** | `Observer Non Interference` |

**Énoncé.** Reduire l'enonce a ce qui est mesure et satisfait : 'FEATURE_AUTO_CALIBRATION et FEATURE_ADAPTIVE_CALIBRATION valent False au demarrage du processus, et leur unique consommateur (quant_hedge_ai/agents/intelligence/regret_engine.py:339-341) applique un delta nul ; le processus refuse de demarrer si l'un des deux drapeaux est vrai sans reference a un ADR signe.' — ENFORCED_ALL alors legitime, et depend_de vide. La clause large ('aucune couche du chemin de decision n'ajuste un seuil, un poids ou un parametre persistant en fonction du resultat des trades pendant l'execution') devient un invariant separe, etat OBSERVED, car rien ne l'a mesuree.

**Justification de l'état.** Déjà satisfait aujourd'hui et mesuré : les deux drapeaux sont à False et l'unique consommateur produit un delta toujours nul. Le verrouillage est donc gratuit et immédiat, et il traduit en contrôle exécutable la règle constitutionnelle de passivité des observers (ADR-0007), qui n'était jusqu'ici qu'un texte.

**Preuve actuelle.** FEATURE_AUTO_CALIBRATION=False et FEATURE_ADAPTIVE_CALIBRATION=False (config/feature_flags.py:47,50). Unique consommateur : quant_hedge_ai/agents/intelligence/regret_engine.py:339-341, delta toujours nul.

**Contrôle futur.** Vérification au démarrage de la valeur des deux drapeaux (refus de démarrer si l'un est vrai sans ADR signé référencé), plus un test de non-régression garantissant que le consommateur unique produit un delta nul.

### D2 — État runtime, arrêt d'urgence, sécurité

#### `SSC-D2-01` — Single Runtime State Machine

| | |
|---|---|
| **Objet** | Machine d'état du moteur (RuntimeStateMachine, SystemStateMachine) |
| **État** | `OBSERVED` |
| **Portée du blocage** | merge |
| **Dépend de** | `Single System State Vocabulary` |

**Énoncé.** Exactement une classe de la liste épinglée et versionnée des machines d'état du moteur (aujourd'hui : RuntimeStateMachine à quant_hedge_ai/runtime/runtime_state_machine.py:53, SystemStateMachine à system/state_machine.py:69) possède un site d'instanciation dans les modules prouvés exécutés en production ; les autres classes de cette liste n'ont aucun site d'instanciation atteignable depuis core/advisor_loop.py.

**Justification de l'état.** Violé aujourd'hui : deux machines d'état sont simultanément exécutées en production. Bloquer l'existant arrêterait le moteur ; on bloque donc l'ajout ou la modification de toute machine d'état tant que la fusion n'a pas eu lieu.

**Preuve actuelle.** 2 machines d'état simultanément EXÉCUTÉES en prod : quant_hedge_ai/runtime/runtime_state_machine.py:53 (RuntimeStateMachine) et system/state_machine.py:69 (SystemStateMachine).

**Contrôle futur.** Requête sur le graphe d'exécution (modules prouvés exécutés par empreinte .pyc) recensant les sites d'instanciation de classes de machine d'état ; échec si le compte diffère de 1.

#### `SSC-D2-02` — Single System State Vocabulary

| | |
|---|---|
| **Objet** | Énumération SystemState |
| **État** | `OBSERVED` |
| **Portée du blocage** | merge |

**Énoncé.** Le nom SystemState ne possède qu'une seule définition de classe/énumération dans l'ensemble des modules prouvés exécutés en production. (La clause « tout état manipulé appartient à cette énumération » doit être retirée ou portée par un invariant distinct assorti d'un contrôle runtime, pas statique.)

**Justification de l'état.** SystemState figure parmi les 8 paires dont les DEUX définitions sont exécutées en prod : la violation est actuelle et non corrigeable sans refonte, seul le code nouveau ou modifié peut être bloqué immédiatement.

**Preuve actuelle.** 69 noms de classe dupliqués hors tests ; 8 paires dont les DEUX définitions sont exécutées en prod, dont SystemState (avec CapitalThrottle, TradeRecord, Position, PortfolioSnapshot, MarketSnapshot, Alert, ValidationResult).

**Contrôle futur.** Analyse statique de l'index des définitions de classes croisée avec la liste des modules prouvés exécutés ; échec si un nom de type d'état possède plus d'une définition dans l'ensemble exécuté.

#### `SSC-D2-03` — State Transition Ledger

| | |
|---|---|
| **Objet** | Journal des transitions d'état du moteur |
| **État** | `DESIGNED` |
| **Portée du blocage** | merge |
| **Dépend de** | `Single Runtime State Machine` |

**Énoncé.** Toute transition d'état du moteur est écrite dans un journal append-only avec horodatage UTC, état sortant, état entrant, cause et identifiant d'instance ; aucune affectation de l'attribut d'état n'a lieu hors de l'unique méthode de transition qui écrit ce journal.

**Justification de l'état.** Le journal de transitions n'existe pas comme objet du système : aucun fait mesuré ne l'atteste. On ne peut pas encore l'observer, seulement le spécifier.

**Preuve actuelle.** NON MESURÉ — aucun journal de transitions n'apparaît dans la cartographie ; les 2 machines d'état exécutées (quant_hedge_ai/runtime/runtime_state_machine.py:53 et system/state_machine.py:69) n'ont aucun journal mesuré.

**Contrôle futur.** Analyse statique interdisant toute affectation de l'attribut d'état hors de la méthode de transition unique, complétée par une vérification d'intégrité du journal (append-only, horodatages monotones, état entrant d'une ligne égal à l'état sortant de la suivante).

#### `SSC-D2-04` — Single Instantiated Kill Switch

| | |
|---|---|
| **Objet** | Kill switch (supervision/killswitch_hardened.py, supervision/kill_switch.py) |
| **État** | `OBSERVED` *(rétrogradé depuis ENFORCED_ALL)* |
| **Portée du blocage** | merge |

**Énoncé.** Au plus une classe figurant dans la liste épinglée et versionnée des classes de kill switch est instanciée dans le processus moteur (aujourd'hui : KillSwitchHardened, instanciée via core/advisor_runtime_adapters.py:109). La clause d'interdiction d'IMPORT est retirée : elle est violée aujourd'hui et relève d'un invariant séparé sur la réduction des modules kill switch exécutés.

**Justification de l'état.** Déjà satisfait aujourd'hui : sur 6 classes définies, une seule est réellement instanciée. Le verrouillage est gratuit et empêche la réapparition d'un second arrêt d'urgence concurrent.

**Preuve actuelle.** 6 classes kill switch définies ; 2 modules exécutés en prod (supervision/kill_switch.py, supervision/killswitch_hardened.py) ; la seule classe réellement instanciée est KillSwitchHardened, via core/advisor_runtime_adapters.py:109.

**Contrôle futur.** Requête de graphe sur les modules prouvés exécutés comptant les sites d'instanciation de classes de kill switch ; échec si ce compte dépasse 1.

#### `SSC-D2-05` — Kill Switch Halt Proof

| | |
|---|---|
| **Objet** | Effet de l'activation du kill switch sur trade_allowed |
| **État** | `OBSERVED` |
| **Portée du blocage** | merge |
| **Dépend de** | `Single Instantiated Kill Switch`, `Fail Closed Outside Running` |

**Énoncé.** Lorsque le kill switch est armé, trade_allowed vaut False au cycle suivant et aucun ordre n'est émis, quel que soit le site d'écriture emprunté parmi les cinq.

**Justification de l'état.** L'effet réel de l'armement n'a jamais été mesuré ; un test de non-régression peut être écrit et publier un verdict dès aujourd'hui, mais rien ne bloque encore tant que ce verdict n'est pas connu.

**Preuve actuelle.** NON MESURÉ — l'effet de KillSwitchHardened (instancié via core/advisor_runtime_adapters.py:109) sur les 5 sites d'écriture de trade_allowed (core/advisor_loop.py:1983, :5626, :5658, :5734, :5808) n'est pas mesuré.

**Contrôle futur.** Test de non-régression armant le kill switch puis exerçant un cycle de décision complet, avec assertion sur trade_allowed=False et sur l'absence de tout appel d'émission d'ordre.

#### `SSC-D2-06` — No Class Name Aliasing

| | |
|---|---|
| **Objet** | Alias d'import de classe (core/advisor_runtime_adapters.py:109) |
| **État** | `ENFORCED_NEW` |
| **Portée du blocage** | commit |

**Énoncé.** Aucune clause d'import introduite ou modifiée dans le dépôt ne renomme une classe en un nom déjà porté par une autre définition de classe du dépôt (index des noms de définition calculé sur l'arborescence versionnée, hors tests).

**Justification de l'état.** Une violation est en place aujourd'hui sur le kill switch et doit être corrigée avant tout verrouillage global ; en attendant, aucun nouvel alias trompeur ne doit être introduit.

**Preuve actuelle.** core/advisor_runtime_adapters.py:109 aliase KillSwitchHardened en "TelegramKillSwitch", alors que deux autres classes se nomment réellement TelegramKillSwitch et ne sont jamais instanciées.

**Contrôle futur.** Analyse statique des clauses d'import comportant un renommage, croisée avec l'index des noms de classes du dépôt ; échec si le nom cible existe déjà comme nom de définition ailleurs.

#### `SSC-D2-07` — Single SAFE_MODE Writer

| | |
|---|---|
| **Objet** | Drapeau SAFE_MODE |
| **État** | `OBSERVED` |
| **Portée du blocage** | merge |

**Énoncé.** Un seul module du graphe exécuté affecte SAFE_MODE ; tous les autres modules atteignables ne peuvent que le lire.

**Justification de l'état.** La mesure actuelle compte les fichiers qui mentionnent SAFE_MODE sans distinguer lecture et écriture ; le contrôle doit d'abord publier cette distinction avant de pouvoir bloquer quoi que ce soit.

**Preuve actuelle.** SAFE_MODE présent dans 18 fichiers de production, 8 atteignables par le runtime ; la répartition écriture/lecture est NON MESURÉE.

**Contrôle futur.** Analyse statique distinguant affectations et lectures de SAFE_MODE, restreinte aux modules prouvés exécutés ; échec si plus d'un module écrit le drapeau.

#### `SSC-D2-08` — Fail Closed Outside Running

| | |
|---|---|
| **Objet** | Conjonction trade_allowed (core/advisor_loop.py:1983) face à l'état du moteur |
| **État** | `OBSERVED` |
| **Portée du blocage** | merge |
| **Dépend de** | `Single Runtime State Machine`, `Single System State Vocabulary` |

**Énoncé.** Tout état du moteur différent de l'état RUNNING de l'énumération canonique unique — y compris un état indéterminé ou non initialisé — impose trade_allowed = False en sortie de cycle, sur les cinq sites d'écriture mesurés (core/advisor_loop.py:1983, :5626, :5658, :5734, :5808), et aucun ordre n'est émis.

**Justification de l'état.** Aucun des cinq sites d'écriture mesurés n'est prouvé lire une machine d'état ; le contrôle par injection de chaque état non-RUNNING est écrivable aujourd'hui et peut publier un verdict sans bloquer.

**Preuve actuelle.** trade_allowed est calculé à core/advisor_loop.py:1983 comme conjonction de 12 booléens, puis révoqué à :5626 (risk_governor), :5658 (safety_auditor), :5734 et :5808 (decision_packet) ; qu'une des 2 machines d'état exécutées conditionne cette valeur est NON MESURÉ.

**Contrôle futur.** Test de non-régression paramétré par l'énumération d'états : pour chaque état non-RUNNING injecté, assertion que trade_allowed est False en sortie de cycle, y compris sur les chemins de révocation.

#### `SSC-D2-09` — State Machine Never Writes Decision

| | |
|---|---|
| **Objet** | Frontière entre machine d'état et décision d'exécution |
| **État** | `ENFORCED_ALL` |
| **Portée du blocage** | commit |

**Énoncé.** Aucun fichier autre que core/advisor_loop.py ne contient d'affectation de trade_allowed (liste des fichiers autorisés épinglée et versionnée dans le contrat ; toute extension de cette liste est un amendement explicite du contrat).

**Justification de l'état.** Déjà satisfait : les 5 sites d'écriture mesurés sont tous dans core/advisor_loop.py, aucun dans les deux machines d'état exécutées. Verrouiller coûte zéro aujourd'hui et interdit la contamination future de l'état vers la décision.

**Preuve actuelle.** 5 sites d'écriture de trade_allowed au total, tous situés dans core/advisor_loop.py (:1983, :5626, :5658, :5734, :5808) ; aucun dans quant_hedge_ai/runtime/runtime_state_machine.py ni system/state_machine.py.

**Contrôle futur.** Analyse statique des affectations de trade_allowed ; échec si un fichier de machine d'état en contient une.

#### `SSC-D2-10` — Single Live Engine Instance

| | |
|---|---|
| **Objet** | Parc d'hôtes exécutant core/advisor_loop.py |
| **État** | `OBSERVED` |
| **Portée du blocage** | deploiement |
| **Dépend de** | `Engine Instance Lock`, `Deployed Unit Matches Repo Unit` |

**Énoncé.** À tout instant, exactement un hôte du parc exécute le moteur, et aucun autre hôte n'a l'unité systemd du moteur en état 'enabled'.

**Justification de l'état.** Mesurable dès aujourd'hui par inventaire du parc et relevé de l'état d'activation des unités ; l'épisode du 01/08 prouve que le contrôle est nécessaire, mais rien ne l'automatise ni ne bloque encore.

**Preuve actuelle.** 2 VM GCP ont coexisté le 01/08 ; l'ancienne (35.240.166.72) avait son service encore 'enabled' ; elle a été supprimée depuis (vérifié : ne répond plus).

**Contrôle futur.** Inventaire automatique des instances du projet et relevé de l'état d'activation de l'unité systemd sur chacune, comparés à un manifeste déclarant l'unique hôte autorisé ; échec si plus d'un hôte est actif ou enabled.

#### `SSC-D2-11` — Engine Instance Lock

| | |
|---|---|
| **Objet** | Verrou d'instance du processus moteur au point d'entrée core/advisor_loop.py |
| **État** | `DESIGNED` |
| **Portée du blocage** | runtime_boot |

**Énoncé.** Au démarrage, le moteur acquiert un verrou exclusif nommé et refuse de démarrer si ce verrou est détenu par un processus vivant ; un verrou orphelin est détecté et invalidé explicitement, jamais ignoré.

**Justification de l'état.** Aucun verrou d'instance n'apparaît dans les faits mesurés au point d'entrée runtime : l'objet n'existe pas encore dans le système et ne peut donc pas être observé.

**Preuve actuelle.** NON MESURÉ — aucun verrou d'instance mesuré à core/advisor_loop.py (point d'entrée runtime réel, ExecStart systemd vérifié sur VPS) ; le seul garde-fou constaté contre le double moteur est humain (2 VM coexistantes le 01/08).

**Contrôle futur.** Test de non-régression lançant deux processus moteur sur le même hôte : le second doit sortir en erreur sans avoir ouvert de position ; vérification complémentaire que le verrou porte l'identifiant du processus détenteur.

#### `SSC-D2-12` — Systemd ExecStart Path Exists

| | |
|---|---|
| **Objet** | scripts/crypto_advisor.service |
| **État** | `OBSERVED` *(rétrogradé depuis ENFORCED_ALL)* |
| **Portée du blocage** | commit |

**Énoncé.** Le chemin déclaré par ExecStart dans chaque fichier d'unité systemd versionné du dépôt correspond à un fichier existant du dépôt.

**Justification de l'état.** Trivialement satisfaisable — une ligne à corriger — et le contrôle est purement statique sur le dépôt, donc il peut bloquer dès aujourd'hui sans coût.

**Preuve actuelle.** scripts/crypto_advisor.service du dépôt déclare ExecStart=advisor_loop.py — fichier INEXISTANT ; seul core/advisor_loop.py existe.

**Contrôle futur.** Analyse statique des fichiers d'unité versionnés : extraction du chemin ExecStart et vérification d'existence dans l'arborescence du dépôt.

#### `SSC-D2-13` — Deployed Unit Matches Repo Unit

| | |
|---|---|
| **Objet** | Unité systemd réellement installée sur l'hôte de production |
| **État** | `OBSERVED` |
| **Portée du blocage** | deploiement |
| **Dépend de** | `Systemd ExecStart Path Exists` |

**Énoncé.** L'unité systemd installée sur l'hôte de production est identique au fichier d'unité versionné correspondant, après application d'une unique substitution déclarée et versionnée (racine de déploiement et compte d'exécution) ; toute divergence résiduelle, y compris sur le répertoire de travail, fait échouer le contrôle. Le chemin ExecStart, une fois la substitution inversée, doit désigner un fichier existant du dépôt.

**Justification de l'état.** La divergence entre fichier versionné et unité réelle est déjà constatée ; la comparaison d'empreintes est réalisable aujourd'hui par relevé sur l'hôte, mais aucun contrôle ne la fait tourner ni ne bloque.

**Preuve actuelle.** scripts/crypto_advisor.service du dépôt déclare ExecStart=advisor_loop.py (inexistant) alors que le vrai unit systemd déclare core/advisor_loop.py ; le VPS n'est de plus PAS un dépôt git (.git absent).

**Contrôle futur.** Vérification d'intégrité comparant l'empreinte de l'unité installée relevée sur l'hôte à celle du fichier versionné correspondant ; échec en cas de divergence, y compris sur le chemin utilisateur et le répertoire de travail.

#### `SSC-D2-14` — No Untagged Execution Override

| | |
|---|---|
| **Objet** | FORCE_TEST_EXECUTION (core/advisor_loop.py:1943-1980) |
| **État** | `OBSERVED` |
| **Portée du blocage** | runtime_boot |
| **Dépend de** | `Fail Closed Outside Running` |

**Énoncé.** Scinder en deux : (1) OBSERVED — tout enregistrement de trade produit alors qu'un forçage de couche par variable d'environnement était actif porte un champ marqueur d'override non vide, et tout enregistrement dépourvu de ce champ est exclu du dataset scientifique (validation de schéma) ; (2) DESIGNED — le démarrage en mode production est refusé si une variable d'environnement force à True l'un des booléens de décision de la liste épinglée (core/advisor_loop.py:1943-1980), invariant subordonné à la définition formelle préalable du « mode production ».

**Justification de l'état.** Le forçage et l'absence de marquage sont mesurés ; l'analyse statique et la validation de schéma peuvent publier un verdict immédiatement, mais refuser le boot exige d'abord de définir formellement le mode production.

**Preuve actuelle.** FORCE_TEST_EXECUTION à core/advisor_loop.py:1943-1980 force 8 couches à True depuis une variable d'environnement, sans marquer les trades produits.

**Contrôle futur.** Analyse statique recensant les affectations de booléens de décision conditionnées par une variable d'environnement, complétée par une validation de schéma exigeant un champ marqueur d'override sur chaque enregistrement de trade.

### D3 — Deployment

#### `SSC-D3-01` — Unique Deployment Identity

| | |
|---|---|
| **Objet** | Objet Deployment (registre des déploiements) |
| **État** | `DESIGNED` |
| **Portée du blocage** | deploiement |

**Énoncé.** Tout code exécuté sur une machine de production est décrit par exactement un objet Deployment persisté, dont le deployment_id (forme DEP-YYYY-NNN) est unique et n'est jamais réattribué ; aucun processus moteur ne tourne sans qu'un Deployment ouvert le décrive.

**Justification de l'état.** L'objet Deployment n'existe nulle part dans le système : il n'y a ni registre, ni identifiant, ni schéma. Rien ne peut être observé aujourd'hui, donc DESIGNED (SSC-R5 : la sortie de DESIGNED exige que l'objet existe et soit schématisé).

**Preuve actuelle.** Aucun objet Deployment n'existe. L'identification du code réellement exécuté en production a exigé une enquête manuelle a posteriori : commit f427895 (2026-07-20) établi par comparaison de md5 normalisés LF, le VPS n'étant pas un dépôt git.

**Contrôle futur.** Validation de schéma du registre Deployment (format de l'id, unicité, non-réattribution après suppression logique) complétée par un rapprochement entre l'inventaire des machines de production actives et la liste des deployment_id ouverts : toute machine sans Deployment, ou tout id dupliqué, échoue.

#### `SSC-D3-02` — Trade Carries Deployment

| | |
|---|---|
| **Objet** | Enregistrements de trades (dataset scientifique, époque V4) |
| **État** | `DESIGNED` |
| **Portée du blocage** | runtime_boot |
| **Dépend de** | `Unique Deployment Identity` |

**Énoncé.** Tout enregistrement de trade porte un champ deployment_id non nul qui résout vers un Deployment existant du registre.

**Justification de l'état.** Le champ ne peut ni être écrit ni être résolu tant que l'objet Deployment n'existe pas ; le contrôle d'intégrité référentielle n'a aujourd'hui aucune table cible. DESIGNED, dépendant de Unique Deployment Identity.

**Preuve actuelle.** Aucun Deployment n'existe ; les 139 trades de l'époque V4 (PF=0.617, WR=34.9%) ne portent aucun rattachement au binaire qui les a produits, la chaîne Trade→Deployment→commit→hashes étant rompue.

**Contrôle futur.** Validation de schéma à l'écriture du trade (deployment_id obligatoire) plus audit périodique d'intégrité référentielle du corpus de trades contre le registre Deployment ; tout trade orphelin est un échec bloquant.

#### `SSC-D3-03` — Event Carries Deployment

| | |
|---|---|
| **Objet** | Journal d'événements append-only (Event, L1) |
| **État** | `DESIGNED` |
| **Portée du blocage** | runtime_boot |
| **Dépend de** | `Unique Deployment Identity` |

**Énoncé.** Tout événement écrit dans le journal append-only porte un deployment_id non nul résolvant vers un Deployment existant ; un événement sans deployment_id est rejeté à l'écriture.

**Justification de l'état.** Même raison que pour les trades : aucun identifiant à référencer n'existe. L'objet Event est par ailleurs immuable, donc l'estampillage doit être fait à l'écriture, ce qui suppose que le runtime connaisse son propre deployment_id — capacité inexistante aujourd'hui.

**Preuve actuelle.** Aucun objet Deployment n'existe (identification du binaire de production par md5 manuel). Le rattachement des événements journalisés à un déploiement est NON MESURÉ.

**Contrôle futur.** Validation de schéma à l'écriture dans le journal, plus balayage d'intégrité référentielle du journal complet contre le registre Deployment, avec taux d'événements orphelins publié.

#### `SSC-D3-04` — Artifact Hash Matches Commit

| | |
|---|---|
| **Objet** | Artefacts transférés vers la machine de production |
| **État** | `DESIGNED` |
| **Portée du blocage** | deploiement |
| **Dépend de** | `Unique Deployment Identity` |

**Énoncé.** Pour tout Deployment, l'empreinte de chaque artefact présent sur la machine cible après transfert est identique à l'empreinte du même chemin dans le commit déclaré, calculée selon une règle de normalisation versionnée (fins de ligne LF pour les fichiers texte, octets bruts pour les binaires, ensemble des chemins défini par un manifeste versionné excluant caches et artefacts générés) ; le manifeste distingue trois échecs indépendants — fichier manquant sur la cible, fichier présent hors manifeste, contenu divergent — et l'un quelconque interdit le passage à ACTIVE.

**Justification de l'état.** Il n'existe ni manifeste d'artefacts, ni champ runtime_hash, ni procédure automatique de recalcul côté cible : le contrôle n'a pas d'entrée à comparer. La seule comparaison jamais réalisée a été manuelle et ponctuelle.

**Preuve actuelle.** Code de production identifié comme commit f427895 par md5 normalisé LF, mesure manuelle sans manifeste. Incident 2026-07-09 : 55 fichiers sur 80 jamais transférés, non détecté, gate SEC-01 resté inactif.

**Contrôle futur.** Vérification d'intégrité post-transfert : recalcul des empreintes sur la machine cible, comparaison fichier par fichier au manifeste dérivé du commit déclaré, échec au premier écart de contenu, de chemin ou de fichier manquant.

#### `SSC-D3-05` — Verification Precedes Declaration

| | |
|---|---|
| **Objet** | Champ verification d'un Deployment |
| **État** | `DESIGNED` |
| **Portée du blocage** | deploiement |
| **Dépend de** | `Unique Deployment Identity`, `Artifact Hash Matches Commit` |

**Énoncé.** Aucun Deployment ne passe à ACTIVE sans un bloc verification postérieur à la fin du transfert, portant méthode, horodatage et résultat, dont la méthode appartient à une liste blanche versionnée de méthodes lisant l'état de la machine cible (au minimum recalcul des empreintes sur la cible et confrontation au manifeste) ; tout code de retour du transport, tout journal du script émetteur et toute méthode hors liste blanche sont explicitement inéligibles comme preuve.

**Justification de l'état.** Le champ verification n'existe pas puisque l'objet n'existe pas. Le contrôle ne peut donc rien évaluer aujourd'hui : DESIGNED. C'est l'invariant qui matérialise directement l'incident historique.

**Preuve actuelle.** Incident 2026-07-09 : bug ssh sans -n dans deploy_vps.sh, 3 tags d'audit annotés créés sur de faux succès, 55 fichiers sur 80 jamais déployés, contamination de l'époque v2 du dataset.

**Contrôle futur.** Validation de schéma de la transition d'état du Deployment : ACTIVE refusé si verification est absent, si verification.result n'est pas un succès, ou si verification.verified_at est antérieur à l'horodatage de fin de transfert.

#### `SSC-D3-06` — Audit Tag Truthfulness

| | |
|---|---|
| **Objet** | Tags git annotés deploy-YYYYMMDD-HHMM |
| **État** | `OBSERVED` *(rétrogradé depuis ENFORCED_NEW)* |
| **Portée du blocage** | deploiement |
| **Dépend de** | `Verification Precedes Declaration` |

**Énoncé.** Aucun tag d'audit deploy-* créé après l'entrée en vigueur du contrat n'existe sans un enregistrement de vérification lié attestant que la totalité des fichiers listés dans le message du tag a été relue sur la machine cible ; les tags antérieurs sont énumérés une fois dans une liste de quarantaine versionnée, marqués non vérifiables, et ne peuvent servir de preuve de déploiement à aucune expérience.

**Justification de l'état.** Le contrôle peut tourner aujourd'hui : énumérer les tags deploy-* et chercher pour chacun un enregistrement de vérification. Il publierait un résultat immédiat et massivement violé (aucun enregistrement n'existe), ce qui interdit toute promotion tant que la violation subsiste (SSC-R3).

**Preuve actuelle.** Incident 2026-07-09 : 3 tags d'audit mensongers créés sur de faux succès alors que 55 fichiers sur 80 n'avaient jamais été transférés.

**Contrôle futur.** Vérification d'intégrité sur l'historique des tags : pour chaque tag deploy-*, exigence d'un enregistrement de vérification lié, avec confrontation de la liste de fichiers du message du tag à la liste effectivement relue sur la cible.

#### `SSC-D3-07` — Deploy Script Stdin Safety

| | |
|---|---|
| **Objet** | scripts/deploy_vps.sh |
| **État** | `OBSERVED` |
| **Portée du blocage** | commit |

**Énoncé.** Aucune invocation de commande distante (ssh, scp, rsync via ssh) située dans une boucle du script de déploiement ne consomme l'entrée standard de la boucle : toute invocation doit être neutralisée (option -n ou redirection depuis /dev/null).

**Justification de l'état.** C'est une analyse statique exécutable dès aujourd'hui sur un fichier existant. Elle n'est pas verrouillée parce que l'état actuel du script après l'incident n'est pas dans les faits mesurés ; SSC-R4 interdit de passer en ENFORCED sans avoir constaté la satisfaction. Promotion gratuite dès que le balayage renvoie zéro occurrence.

**Preuve actuelle.** Incident 2026-07-09 : bug "ssh sans -n" dans deploy_vps.sh, cause directe de 55 fichiers non déployés et de 3 tags mensongers. État actuel du script : NON MESURÉ.

**Contrôle futur.** Analyse statique du script de déploiement recherchant tout appel distant à l'intérieur d'une structure de boucle sans neutralisation de stdin ; échec sur la première occurrence.

#### `SSC-D3-08` — Clean Worktree Deploy

| | |
|---|---|
| **Objet** | Arbre de travail du dépôt source au moment du déploiement |
| **État** | `OBSERVED` |
| **Portée du blocage** | deploiement |

**Énoncé.** Scinder en deux : (1) au moment du transfert, l'arbre de travail source ne contient aucune modification non validée ni fichier non suivi dans le périmètre effectivement transféré (périmètre défini par le filtre d'exclusion versionné du script de déploiement) ; (2) le commit HEAD transféré est joignable sur la remote déclarée. Chaque contrôle publie son résultat dans le journal de déploiement de façon autonome ; le report dans un champ worktree_clean n'intervient qu'après existence du registre Deployment (depend_de : Unique Deployment Identity).

**Justification de l'état.** Le contrôle est exécutable aujourd'hui (interrogation de l'état du dépôt au moment du déploiement) et publie un résultat sans rien bloquer. Il n'est pas verrouillé car sa satisfaction actuelle n'est pas établie et le verrou n'est pas gratuit.

**Preuve actuelle.** NON MESURÉ : l'existence d'un contrôle de propreté de l'arbre dans le geste de déploiement n'est pas dans les faits mesurés. Fait connexe : la production exécute f427895 (2026-07-20) alors que le commit local 032d4ee (2026-07-31) n'est pas déployé.

**Contrôle futur.** Contrôle pré-transfert de l'état du dépôt source (modifications non validées, fichiers non suivis dans le périmètre, présence du HEAD sur la remote) ; le résultat est enregistré dans le champ worktree_clean du Deployment.

#### `SSC-D3-09` — Signed Deployment

| | |
|---|---|
| **Objet** | Champs operator et signature d'un Deployment |
| **État** | `DESIGNED` |
| **Portée du blocage** | deploiement |
| **Dépend de** | `Unique Deployment Identity` |

**Énoncé.** Tout Deployment ACTIVE porte une signature cryptographique valide dont la clé publique figure dans un registre versionné d'opérateurs, chaque entrée du registre nommant l'opérateur responsable et la machine ou le support détenant la clé ; l'ajout d'une entrée au registre est lui-même un acte versionné et revu. La propriété garantie est l'imputabilité à une entrée nommée du registre, pas l'humanité du signataire.

**Justification de l'état.** Ni l'objet, ni les champs operator/signature, ni le mécanisme de signature n'existent : rien n'est observable. À verrouiller tôt, tant qu'aucun agent automatique ne déploie — le coût du verrou augmentera dès qu'un tel agent existera (SSC-R4).

**Preuve actuelle.** Aucun objet Deployment n'existe ; aucune signature d'opérateur n'est enregistrée pour un déploiement. NON MESURÉ au-delà de ce constat d'absence.

**Contrôle futur.** Validation de schéma et vérification cryptographique de la signature au passage du Deployment à ACTIVE, avec contrôle que le signataire figure dans le registre des opérateurs humains.

#### `SSC-D3-10` — Entrypoint Is Observed Not Declared

| | |
|---|---|
| **Objet** | Champ entrypoint d'un Deployment |
| **État** | `DESIGNED` |
| **Portée du blocage** | deploiement |
| **Dépend de** | `Unique Deployment Identity` |

**Énoncé.** Scinder en deux : (1) le champ entrypoint d'un Deployment est égal à la valeur re-observée sur la machine (unité systemd active et ligne de commande du processus) lors d'un contrôle indépendant postérieur ; toute divergence entre valeur enregistrée et valeur re-observée invalide le Deployment ; (2) l'entrypoint observé en production correspond à un chemin déclaré par une unité systemd versionnée du dépôt et existant dans l'arbre ; toute divergence est publiée comme dérive dépôt/production (depend_de : Service Unit Truthfulness).

**Justification de l'état.** Le champ n'existe pas, donc l'invariant ne peut pas être évalué. L'écart qu'il interdit est en revanche déjà mesuré, ce qui prouve que la propriété est nécessaire dès la création de l'objet.

**Preuve actuelle.** scripts/crypto_advisor.service du dépôt déclare ExecStart=advisor_loop.py, fichier inexistant (seul core/advisor_loop.py existe), tandis que l'unité systemd réelle du VPS déclare core/advisor_loop.py.

**Contrôle futur.** Sonde de collecte sur la machine cible lisant l'unité active et la ligne de commande du processus, écriture directe dans entrypoint, puis comparaison au chemin déclaré dans le dépôt avec échec sur divergence.

#### `SSC-D3-11` — Production Code Fingerprint

| | |
|---|---|
| **Objet** | Machine de production (VPS exécutant le moteur) |
| **État** | `OBSERVED` |
| **Portée du blocage** | deploiement |

**Énoncé.** La machine de production expose en permanence une empreinte de code auto-descriptive et vérifiable — dépôt git avec HEAD résolu, ou manifeste signé listant chemin et sha256 de chaque fichier déployé — de sorte que l'identification du code exécuté ne demande jamais d'enquête manuelle.

**Justification de l'état.** Mesurable aujourd'hui par une simple sonde distante (présence et lisibilité d'un HEAD ou d'un manifeste). Le contrôle tourne et publie un échec immédiat ; il ne peut pas être promu tant que la violation subsiste (SSC-R3).

**Preuve actuelle.** La production n'est PAS un dépôt git (.git absent) ; le code exécuté (commit f427895 du 2026-07-20) n'a pu être identifié que par comparaison de md5 normalisés LF.

**Contrôle futur.** Sonde périodique sur la machine : présence, lisibilité et fraîcheur du manifeste ou du HEAD, puis comparaison de l'empreinte annoncée aux empreintes recalculées des fichiers présents.

#### `SSC-D3-12` — One Active Deployment Per Machine

| | |
|---|---|
| **Objet** | Registre des Deployment, dimension machine |
| **État** | `DESIGNED` |
| **Portée du blocage** | deploiement |
| **Dépend de** | `Unique Deployment Identity` |

**Énoncé.** Pour une machine donnée, au plus un Deployment est dans l'état ACTIVE à un instant donné ; l'ouverture d'un nouveau Deployment sur une machine clôt obligatoirement le précédent en renseignant son process_stop.

**Justification de l'état.** Le registre et les états ACTIVE/process_stop n'existent pas : la propriété n'est pas observable. Elle est distincte de l'unicité de la machine — elle interdit la superposition de deux descriptions du même hôte, source de l'ambiguïté "quel binaire tournait".

**Preuve actuelle.** Aucun objet Deployment n'existe, donc aucun état ACTIVE n'est enregistré ; la production exécute f427895 sans qu'aucun enregistrement ne date le démarrage du processus.

**Contrôle futur.** Requête sur le registre Deployment groupée par machine, comptant les enregistrements ACTIVE, plus vérification de la cohérence temporelle des intervalles process_start/process_stop (aucun recouvrement pour une même machine).

#### `SSC-D3-13` — Reproducible Deployment Build

| | |
|---|---|
| **Objet** | Champ runtime_hash d'un Deployment |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Unique Deployment Identity`, `Artifact Hash Matches Commit` |

**Énoncé.** Scinder en deux : (1) reconstruire un Deployment à partir de son commit, de son lock de dépendances et de sa config_hash dans un environnement isolé produit un runtime_hash identique à celui enregistré, runtime_hash étant défini par une spécification versionnée (liste de chemins issue du manifeste, exclusion des caches et bytecode, normalisation LF des fichiers texte, ordre de parcours fixé) ; (2) un Deployment dont la reconstruction diverge est marqué non reconstructible et ne peut être cité comme référence par aucune expérience enregistrée — règle d'éligibilité rattachée au domaine expérience.

**Justification de l'état.** Ni runtime_hash, ni config_hash, ni lock enregistré n'existent, et aucun mécanisme de rejeu n'est exécuté : rien ne peut être reconstruit ni comparé aujourd'hui.

**Preuve actuelle.** Aucun objet Deployment n'existe ; 2 ReplayEngine sont définis (audit/replay_engine.py:131, market_data/replay_engine.py:70) mais AUCUN n'est exécuté en production — zéro rejeu, Evidence Score = 0.

**Contrôle futur.** Reconstruction périodique en environnement isolé à partir des seuls champs enregistrés, recalcul du runtime_hash et comparaison à la valeur du registre ; le résultat alimente le drapeau de reconstructibilité utilisé par les expériences.

#### `SSC-D3-14` — No Forcing Env Switch In Production

| | |
|---|---|
| **Objet** | Environnement effectif du processus moteur (FORCE_TEST_EXECUTION, core/advisor_loop.py:1943-1980) |
| **État** | `OBSERVED` |
| **Portée du blocage** | runtime_boot |

**Énoncé.** Scinder en deux : (1) au démarrage, l'environnement effectif du processus moteur ne contient aucune variable figurant dans la liste noire versionnée des commutateurs de forçage, quelle que soit sa valeur ; sa présence interdit le démarrage. (2) Analyse statique complémentaire : tout site du code lisant une variable d'environnement pour forcer une couche de décision à True doit figurer dans cette liste noire, sinon le contrôle échoue. Le report du résultat dans la config_hash d'un Deployment n'intervient qu'après existence du registre (depend_de : Unique Deployment Identity).

**Justification de l'état.** L'environnement effectif d'un processus est lisible aujourd'hui sur la machine, et la liste noire des commutateurs est dérivable du code : le contrôle peut tourner et publier. Il n'est pas verrouillé car la valeur réellement présente en production n'a pas été mesurée, donc la satisfaction n'est pas établie (SSC-R4).

**Preuve actuelle.** FORCE_TEST_EXECUTION force 8 couches à True depuis une variable d'environnement, sans marquer les trades produits (core/advisor_loop.py:1943-1980). Sa valeur dans l'environnement du processus de production est NON MESURÉE.

**Contrôle futur.** Sonde au démarrage lisant l'environnement effectif du processus et le comparant à une liste noire versionnée de commutateurs de forçage ; le résultat est figé dans la config_hash du Deployment et publié.

### D4 — Research Epoch et Dataset

#### `SSC-D4-01` — Epoch Id Uniqueness

| | |
|---|---|
| **Objet** | ResearchEpoch — registre des époques |
| **État** | `DESIGNED` |
| **Portée du blocage** | commit |

**Énoncé.** Enonce conserve. Correction portant sur la preuve : citer uniquement les faits mesures — 4 bornes CLEAN_DATA_SINCE en 6 semaines (v1 25/06, v2 09/07 01:16, v3 09/07 07:45, v4 17/07 01:30), borne active CLEAN_DATA_SINCE_V4=2026-07-17T01:30:00Z, aucun identifiant d'epoque produit, 0 verdict, 0 rejeu, Evidence Score=0. Le controle sera decompose en trois assertions distinctes : unicite, allocation strictement croissante, non-reattribution via journal des identifiants retires.

**Justification de l'état.** L'objet ResearchEpoch n'existe dans aucun module du dépôt : il n'y a rien à observer. Les quatre changements d'époque déjà survenus n'ont produit aucun identifiant, seulement des constantes datées dans un fichier Python.

**Preuve actuelle.** ⚠ **À REVÉRIFIER** — 4 bornes CLEAN_DATA_SINCE en 6 semaines matérialisées uniquement comme constantes — scripts/data_quality.py:47 (v2), :56 (v3), :65 (v4) ; aucun objet Epoch, 0 verdict, 0 rejeu, Evidence Score = 0.

**Contrôle futur.** Validation de schéma à l'écriture du registre, complétée d'une requête d'unicité et de monotonie sur l'ensemble des identifiants, incluant le journal des identifiants retirés pour interdire toute réattribution.

#### `SSC-D4-02` — Closed Epoch Immutable

| | |
|---|---|
| **Objet** | ResearchEpoch dont closed_at est renseigné |
| **État** | `DESIGNED` |
| **Portée du blocage** | commit |
| **Dépend de** | `Epoch Id Uniqueness` |

**Énoncé.** Scinder en deux : (A) 'Aucun champ d'une epoque dont closed_at est renseigne ne change apres la cloture : le hash de contenu recalcule egale le hash scelle a la cloture.' (B) 'Toute epoque creee en correction d'une epoque close renseigne un champ replaces_epoch_id qui se resout vers une epoque close existante, et aucune epoque close n'est referencee par plus d'un successeur.' Preuve a recoller sur le fait mesure (4 bornes en 6 semaines sans artefact de succession) sans citer de lignes absentes de la base.

**Justification de l'état.** Aucune époque n'existe comme objet : ni scellement, ni hash de clôture, ni chaîne de succession ne sont observables aujourd'hui.

**Preuve actuelle.** ⚠ **À REVÉRIFIER** — Les époques v1 à v4 n'existent que sous forme de constantes réécrites en place dans scripts/data_quality.py:31,47,56,65 — une réécriture de constante ne laisse aucune trace de succession dans un artefact scientifique.

**Contrôle futur.** Vérification d'intégrité : hash de contenu de chaque époque close recalculé et comparé à la valeur scellée à la clôture ; toute divergence échoue le contrôle.

#### `SSC-D4-03` — Epoch Reference Completeness

| | |
|---|---|
| **Objet** | ResearchEpoch — bloc de références |
| **État** | `DESIGNED` |
| **Portée du blocage** | commit |
| **Dépend de** | `Epoch Id Uniqueness` |

**Énoncé.** Scinder en trois invariants : (A) 'Toute epoque ouverte porte le jeu ferme de cles [deployment_ids, policy_id, calibration_ids, dataset_id, dataset_boundary, universe_hash, replay_ids, knowledge_graph_version, runtime_hash, comparability{previous_epoch, comparable, reason}] ; aucune cle absente.' (B) 'Toute reference non marquee NON MESURE se resout dans son registre.' (C) 'Seuls les champs inscrits dans une liste versionnee peuvent valoir NON MESURE ; chacun porte alors une raison d'au moins N caracteres et une echeance datee au-dela de laquelle le controle echoue.'

**Justification de l'état.** Les objets référencés (Deployment, Policy, Calibration, Replay, Corpus) n'existent pas : les champs ne peuvent même pas être remplis, donc l'invariant n'est pas évaluable.

**Preuve actuelle.** Aucun objet Deployment n'existe et la production n'est pas un dépôt git (.git absent) — le code exécuté f427895 (2026-07-20) a dû être identifié a posteriori par md5 normalisé LF ; 0 rejeu : les 2 ReplayEngine définis (audit/replay_engine.py:131, market_data/replay_engine.py:70) n'ont produit aucun .pyc en prod.

**Contrôle futur.** Validation de schéma bloquante à l'ouverture d'une époque : chaque référence doit se résoudre dans son registre respectif, et aucun champ ne peut être absent ou nul.

#### `SSC-D4-04` — Epoch Reconstructibility Computed

| | |
|---|---|
| **Objet** | ResearchEpoch — champ reconstructible |
| **État** | `DESIGNED` |
| **Portée du blocage** | merge |
| **Dépend de** | `Epoch Reference Completeness`, `Frozen Corpus Content Hash` |

**Énoncé.** Le champ reconstructible d'une époque est dérivé, jamais saisi à la main : il ne vaut vrai que si le déploiement référencé est rejouable, si le corpus référencé est FROZEN avec content_hash vérifié et si le runtime_hash est retrouvable ; dans tout autre cas il vaut faux et enregistre laquelle des trois conditions manque.

**Justification de l'état.** Aucune des trois conditions n'est aujourd'hui évaluable : ni objet Deployment, ni objet Corpus, ni rejeu exécuté. Le champ ne peut donc être ni calculé ni contredit.

**Preuve actuelle.** 0 rejeu exécuté en production (2 ReplayEngine définis, aucun .pyc) ; production non-git, commit exécuté f427895 identifié par md5 ; fidélité du simulateur paper_trading/mexc_simulator.py (966 lignes, exécuté) NON MESURÉE.

**Contrôle futur.** Contrôle dérivé en intégration continue : recalcul du booléen à partir des registres déploiement / corpus / runtime, et échec si la valeur stockée diffère de la valeur recalculée.

#### `SSC-D4-05` — Epoch Required On Experimental Variable Change

| | |
|---|---|
| **Objet** | univers tradé épinglé et policy_version active |
| **État** | `DESIGNED` |
| **Portée du blocage** | deploiement |
| **Dépend de** | `Epoch Reference Completeness` |

**Énoncé.** Scinder : (A) 'Tout changement du hash de l'univers trade epingle ouvre une nouvelle epoque declaree avant la production du premier enregistrement sous le nouvel univers.' (B) 'Tout changement de policy_version active ouvre une nouvelle epoque declaree avant la production du premier enregistrement sous la nouvelle version.' (C) 'Au demarrage du runtime, le couple (universe_hash, policy_version) effectif egale celui de l'epoque ouverte courante, sinon aucun enregistrement n'est produit.' Preuve a reconstruire sur les seuls faits mesures : 4 bornes CLEAN_DATA_SINCE traitees comme changements de constante, 0 objet Calibration, 0 verdict.

**Justification de l'état.** Le déclencheur est mesurable en principe, mais l'artefact exigé — l'époque — n'existe pas, et aucun objet Policy n'existe pour porter une policy_version : l'invariant ne peut être ni satisfait ni violé mécaniquement.

**Preuve actuelle.** ⚠ **À REVÉRIFIER** — L'élargissement de l'univers de 28 à 135 paires épinglées (ADR-0017) a été traité comme un simple changement de borne — CLEAN_DATA_SINCE_V4 à scripts/data_quality.py:65 — et non comme l'ouverture d'un objet Epoch ; 0 objet Policy, 0 objet Calibration.

**Contrôle futur.** Comparaison d'empreintes au déploiement et au démarrage : hash de l'univers effectif et policy_version effective confrontés à ceux de l'époque courante ; toute divergence sans époque nouvellement déclarée échoue le contrôle.

#### `SSC-D4-06` — Epoch Required On Data Boundary Change

| | |
|---|---|
| **Objet** | constante de borne d'époque CLEAN_DATA_SINCE_ACTIVE |
| **État** | `DESIGNED` |
| **Portée du blocage** | commit |
| **Dépend de** | `Epoch Id Uniqueness`, `Cited ADR Exists` |

**Énoncé.** 'Toute modification de la valeur de la borne d'epoque active dans une revision du depot est accompagnee, dans le meme changement, (a) d'un nouvel enregistrement d'epoque et (b) d'un champ adr_id renseigne, et (c) d'un bloc comparability statuant comparable=true/false avec une raison non vide vis-a-vis de l'epoque precedente. La resolvabilite de adr_id est verifiee par l'invariant Cited ADR Exists et n'est pas re-testee ici.' Preuve limitee aux faits mesures : 4 bornes en 6 semaines, borne active 2026-07-17T01:30:00Z, N=139 en epoque V4, aucun artefact de comparabilite.

**Justification de l'état.** Le déclencheur (diff de la constante entre deux révisions) est mesurable dès aujourd'hui, mais les artefacts exigés — époque et déclaration de comparabilité — n'existent pas : le contrôle n'aurait rien à vérifier.

**Preuve actuelle.** ⚠ **À REVÉRIFIER** — 4 bornes en 6 semaines (v1 25/06, v2 09/07 01:16, v3 09/07 07:45, v4 17/07 01:30), borne active CLEAN_DATA_SINCE_V4 = 2026-07-17T01:30:00Z à scripts/data_quality.py:65 ; chaque changement a remis N à zéro (N=139 en époque V4) sans artefact déclarant la comparabilité.

**Contrôle futur.** Comparaison de valeurs entre deux révisions du dépôt : tout diff touchant la constante de borne exige, dans le même changement, un enregistrement d'époque nouveau et un identifiant d'ADR résolvable.

#### `SSC-D4-07` — Single Clean Boundary Source

| | |
|---|---|
| **Objet** | constante CLEAN_DATA_SINCE_ACTIVE (scripts/data_quality.py:70) |
| **État** | `OBSERVED` *(rétrogradé depuis ENFORCED_NEW)* |
| **Portée du blocage** | commit |

**Énoncé.** 'Hors du module source de la borne, aucun module n'assigne de litteral datetime a un nom correspondant a CLEAN_DATA_SINCE* ni ne reproduit la valeur de la borne active ; tout usage de la borne provient d'un import de l'alias canonique CLEAN_DATA_SINCE_ACTIVE.' Preuve a corriger : 15 fichiers .py referencent CLEAN_DATA_SINCE (58 occurrences), dont le module source et 6 fichiers de tests — et non 16.

**Justification de l'état.** Le contrôle est écrivable aujourd'hui par analyse statique et la source unique existe déjà, mais la conformité de la totalité des modules qui référencent la borne n'est pas établie ; on bloque donc le code nouveau ou modifié sans prétendre que l'existant est conforme.

**Preuve actuelle.** ⚠ **À REVÉRIFIER** — Source unique mesurée : CLEAN_DATA_SINCE_V4 défini à scripts/data_quality.py:65 et aliasé CLEAN_DATA_SINCE_ACTIVE à scripts/data_quality.py:70 ; 16 fichiers .py du dépôt référencent CLEAN_DATA_SINCE (recherche sur le dépôt).

**Contrôle futur.** Analyse statique : détection de tout littéral de date situé dans la plage des époques hors du module source, et vérification que chaque usage de la borne provient d'un import de l'alias canonique.

#### `SSC-D4-08` — Canonical Population Loader

| | |
|---|---|
| **Objet** | modules producteurs de N, PF, WR, comptes de regret et seuils |
| **État** | `ENFORCED_NEW` |
| **Portée du blocage** | commit |
| **Dépend de** | `Single Clean Boundary Source` |

**Énoncé.** 'Aucun module du depot autre que le chargeur canonique n'ouvre directement les fichiers bruts de trades et de regret (aucun appel d'ouverture, de lecture ou de parsing pointant vers ces chemins hors du chargeur) ; tout calcul de N, PF, WR, compte de regret ou seuil consomme la population retournee par ce chargeur.' La premiere clause est verifiable par analyse statique sans liste curee ; la seconde reste indicative tant qu'aucune classification fiable des producteurs de metriques n'existe.

**Justification de l'état.** Mesurable par analyse statique dès aujourd'hui, mais la conformité de l'existant n'est pas établie module par module — un outil d'audit a déjà été constaté inerte faute de population canonique — donc pas de verrouillage rétroactif.

**Preuve actuelle.** ⚠ **À REVÉRIFIER** — Borne canonique unique implémentée à scripts/data_quality.py:65-70 et imposée par CLAUDE.md ; état scientifique mesuré sur population canonique : N=139 trades époque V4, PF=0.617, WR=34.9%, t=-1.571 non significatif.

**Contrôle futur.** Analyse statique : chaque module d'une liste versionnée de producteurs de métriques doit importer le chargeur canonique et ne contenir aucune ouverture directe des fichiers de trades.

#### `SSC-D4-09` — Cited ADR Exists

| | |
|---|---|
| **Objet** | références ADR-NNNN dans le code et les artefacts de dataset |
| **État** | `OBSERVED` |
| **Portée du blocage** | commit |

**Énoncé.** 'Tout identifiant ADR-NNNN apparaissant dans un fichier du depot hors tests et hors docs/adr/ correspond a un document present dans docs/adr/. Tant que l'invariant est OBSERVED, la liste des references orphelines est publiee a chaque execution ; la promotion en bloquant exige une liste vide.'

**Justification de l'état.** Entièrement mesurable aujourd'hui par résolution référentielle, mais actuellement VIOLÉ : la promotion vers un état bloquant est interdite tant que la violation subsiste.

**Preuve actuelle.** ADR-0018 cité comme source canonique par tools/score_calibration_audit.py:675 mais ABSENT de docs/adr/ (la séquence passe de 0017 à 0019).

**Contrôle futur.** Vérification d'intégrité référentielle : extraction de tous les identifiants ADR cités hors tests, résolution contre l'index des ADR, publication de la liste des références orphelines.

#### `SSC-D4-10` — Single Epoch Per Corpus

| | |
|---|---|
| **Objet** | Corpus / Dataset certifié |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Epoch Id Uniqueness` |

**Énoncé.** 'Un corpus ne contient que des enregistrements portant un unique epoch_id. Un corpus type inter-epoques est admis uniquement si, pour chaque paire d'epoques agregees, un bloc comparability existe avec comparable=true et une raison non vide ; toute paire portant comparable=false ou une raison vide refuse la certification.'

**Justification de l'état.** Le champ epoch_id n'existe sur aucun enregistrement produit : l'appartenance à une époque est aujourd'hui reconstruite après coup par comparaison d'horodatage à une constante, et non lue sur l'enregistrement.

**Preuve actuelle.** ⚠ **À REVÉRIFIER** — L'appartenance à l'époque V4 est déduite par filtrage temporel sur CLEAN_DATA_SINCE_V4 (scripts/data_quality.py:65) ; aucun objet Corpus n'existe — experiments/ contient 1 fichier YAML et 0 module Python.

**Contrôle futur.** Validation de schéma à la certification d'un corpus : agrégation des epoch_id distincts présents, refus si le cardinal dépasse un sans typage inter-époques explicite.

#### `SSC-D4-11` — Bypass Trade Indelible Mark

| | |
|---|---|
| **Objet** | FORCE_TEST_EXECUTION (core/advisor_loop.py:1941-1980) et enregistrements de trades |
| **État** | `OBSERVED` |
| **Portée du blocage** | runtime_boot |

**Énoncé.** Scinder en trois, avec des etats et des portees distincts : (A) OBSERVED, portee=aucune : 'Tout enregistrement de trade porte un champ bypassed_layers, liste eventuellement vide des couches desarmees au moment de la production ; l'absence du champ est comptee et publiee.' (B) ENFORCED_NEW une fois l'emetteur corrige, portee=runtime_boot : 'Le runtime refuse de demarrer si l'emetteur d'enregistrements ne renseigne pas bypassed_layers.' (C) DESIGNED, portee=experience : 'Aucun corpus certifie ne contient d'enregistrement dont bypassed_layers est non vide.' Preuve a recoller sur la plage mesuree core/advisor_loop.py:1943-1980.

**Justification de l'état.** Le champ n'existe pas : le bypass force huit couches à vrai sans laisser la moindre trace dans le trade produit, donc aucune observation n'est possible aujourd'hui.

**Preuve actuelle.** ⚠ **À REVÉRIFIER** — FORCE_TEST_EXECUTION force 8 couches à True depuis une variable d'environnement à core/advisor_loop.py:1943-1980 sans marquer les trades produits (lecture de la variable à :1941, journal à :1965).

**Contrôle futur.** Validation de schéma à l'écriture de l'enregistrement (champ obligatoire, même vide) et filtre bloquant à la certification d'un corpus exigeant zéro enregistrement marqué ; refus de démarrage du runtime si l'émetteur ne renseigne pas le champ.

#### `SSC-D4-12` — Frozen Corpus Content Hash

| | |
|---|---|
| **Objet** | Corpus à l'état FROZEN |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |

**Énoncé.** Tout corpus à l'état FROZEN porte un content_hash calculé sur l'intégralité de son contenu, et le recalcul de ce hash à tout moment redonne exactement la valeur scellée au gel.

**Justification de l'état.** Aucun objet Corpus n'existe, donc aucun hash de contenu n'est calculé ni stockable : rien n'est observable.

**Preuve actuelle.** 0 objet Corpus (experiments/ = 1 YAML, 0 module Python ; research/ = 1 fichier .md, 0 module Python) et 0 rejeu — les deux ReplayEngine définis (audit/replay_engine.py:131, market_data/replay_engine.py:70) n'ont produit aucun .pyc en production.

**Contrôle futur.** Vérification d'intégrité périodique et bloquante avant toute expérience : recalcul du hash de contenu et comparaison au hash scellé.

#### `SSC-D4-13` — Corpus Immutable Once Referenced

| | |
|---|---|
| **Objet** | Corpus référencé par une ExperimentSpec pré-enregistrée |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Frozen Corpus Content Hash` |

**Énoncé.** 'Avant toute execution d'une experience pre-enregistree, le hash courant de chaque corpus reference egale le hash inscrit dans la spec, sinon l'execution est refusee ; toute evolution d'un corpus reference produit un corpus dote d'une nouvelle identite et d'un nouveau hash, le corpus d'origine restant lisible et sa spec inchangee. La rejouabilite releve d'un invariant de rejeu distinct et n'est pas testee ici.'

**Justification de l'état.** Ni l'objet Corpus ni une expérience exécutable ne sont implémentés : aucune expérience n'a jamais référencé un corpus identifié, donc la relation à protéger n'existe pas.

**Preuve actuelle.** experiments/ contient 1 fichier YAML et 0 module Python ; 0 verdict, 0 rejeu, 1 seule hypothèse conclue (H3 rejetée le 2026-07-31, Cohen's d=-0.097).

**Contrôle futur.** Requête de graphe avant chaque exécution : pour chaque corpus référencé par une expérience, comparaison du hash courant au hash inscrit dans la spec ; toute divergence refuse l'exécution.

#### `SSC-D4-14` — Corpus Usage Budget

| | |
|---|---|
| **Objet** | Corpus — compteur usage_count et budget déclaré |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Corpus Immutable Once Referenced` |

**Énoncé.** 'Chaque corpus porte, fige a sa certification et inclus dans son contenu hache, un budget d'usages non modifiable, et un compteur d'usages incremente a chaque experience pre-enregistree qui le reference. Toute tentative de pre-enregistrement referencant un corpus dont le compteur est superieur ou egal au budget est refusee, et le corpus passe a l'etat RETIRED, etat terminal duquel il ne peut plus fonder aucun nouveau verdict. Toute modification du budget apres certification est une violation.'

**Justification de l'état.** Ni l'objet Corpus ni l'objet Experiment exécutable n'existent : aucun compteur ne peut être incrémenté ni comparé à un budget.

**Preuve actuelle.** 0 verdict, 0 rejeu, 0 objet Calibration, Evidence Score = 0 ; research/ contient 1 fichier .md et 0 module Python.

**Contrôle futur.** Compteur persistant vérifié au pré-enregistrement : refus d'enregistrer une expérience référençant un corpus dont le compteur est supérieur ou égal à son budget déclaré.

#### `SSC-D4-15` — Holdout Reserve Untouched

| | |
|---|---|
| **Objet** | Corpus — fraction déclarée comme réserve |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Corpus Usage Budget` |

**Énoncé.** Scinder : (A) 'Les donnees declarees en reserve a la certification d'un corpus ne sont accessibles que via un lecteur instrumente unique ; aucune execution ne peut les lire par un autre chemin, cette impossibilite etant structurelle et non simplement journalisee.' (B) 'Aucun manifeste d'execution anterieur a l'emission du verdict final ne comporte de plage recouvrant la reserve ; le premier recouvrement refuse l'execution.' (C) 'Chaque ouverture de la reserve par le lecteur instrumente est comptee et consomme definitivement la fraction lue, qui ne peut plus fonder de verdict ulterieur.' Preuve a limiter aux faits mesures : 0 rejeu execute, 2 ReplayEngine definis sans .pyc, aucune segmentation de corpus existante.

**Justification de l'état.** Aucune segmentation de corpus n'existe, aucun manifeste d'exécution n'est produit : il n'y a ni réserve à protéger ni journal d'accès à inspecter.

**Preuve actuelle.** ⚠ **À REVÉRIFIER** — 0 rejeu et 0 walk-forward exécutés ; la seule mesure hors échantillon disponible reste descriptive (horizon d'information du score : rho=0.16, AUC=0.60 à 12-24h, détention réalisée 5.92h).

**Contrôle futur.** Contrôle de provenance sur les manifestes d'exécution : comparaison des plages de données effectivement lues aux plages déclarées comme réserve, échec au premier recouvrement non journalisé.

### D5 — Experiment, Replay, Ablation

#### `SSC-D5-01` — Experiment Preregistration Precedence

| | |
|---|---|
| **Objet** | ExperimentSpec scellée (experiments/EXP-*/spec.yaml) et RunManifest de tout run rattaché |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Run Manifest Completeness` |

**Énoncé.** Ancrer la précédence sur un horodatage non forgeable par l'auteur : submitted_at doit être égal (à la minute) à la date du commit git qui scelle la spec, et c'est cette date de commit — non le champ YAML — qui est comparée au minimum des run_started_at. Un écart entre submitted_at et la date du commit de scellement invalide la spec.

**Justification de l'état.** L'objet Run n'existe pas : aucun rejeu n'a jamais été exécuté et aucun run_manifest n'est produit, donc run_started_at n'est enregistré nulle part et la comparaison d'horodatages ne peut pas tourner aujourd'hui.

**Preuve actuelle.** 2 ReplayEngine définis (audit/replay_engine.py:131, market_data/replay_engine.py:70), AUCUN exécuté en prod, donc zéro rejeu ; experiments/ contient 1 fichier YAML et 0 module Python ; 0 verdict.

**Contrôle futur.** Comparaison d'horodatages : le contrôle lit submitted_at de la spec scellée et le compare au minimum des run_started_at des manifestes rattachés ; échec si submitted_at est absent, égal ou postérieur.

#### `SSC-D5-02` — Single Intervention Per Experiment

| | |
|---|---|
| **Objet** | Bloc intervention de l'ExperimentSpec |
| **État** | `OBSERVED` |
| **Portée du blocage** | merge |

**Énoncé.** Énoncé conservé tel quel ; seule la preuve_actuelle doit être réécrite sur une mesure versée aux FAITS (inventaire des champs de chaque fichier de experiments/, produit par le contrôle lui-même), pas sur une citation de lignes non mesurée.

**Justification de l'état.** Le répertoire experiments/ existe et contient une spec : une validation de schéma peut tourner et publier un résultat dès aujourd'hui. Elle échouerait — la seule spec présente ne comporte aucun bloc intervention et teste quatre hypothèses simultanément. Un article violé ne peut pas être promu (SSC-R3).

**Preuve actuelle.** ⚠ **À REVÉRIFIER** — experiments/ contient 1 fichier YAML et 0 module Python ; vérifié dans le dépôt : experiments/EXP-001.yaml:84-88 déclare hypotheses_testées H1, H2, H3, H4 et ne contient aucun champ intervention.

**Contrôle futur.** Validation de schéma sur tous les fichiers de experiments/ : cardinalité du champ intervention strictement égale à 1, chaque intervention nommant un module unique.

#### `SSC-D5-03` — Single Primary Metric

| | |
|---|---|
| **Objet** | Bloc metrics de l'ExperimentSpec |
| **État** | `OBSERVED` |
| **Portée du blocage** | merge |
| **Dépend de** | `Single Intervention Per Experiment` |

**Énoncé.** Scinder : (a) 'Primary Metric Declared' — toute spec déclare exactement une métrique primaire (OBSERVED, portée merge) ; (b) 'Verdict Grounded On Primary Metric' — tout verdict PASS cite l'identifiant de la métrique primaire de sa spec et aucun autre (DESIGNED, portée expérience, dépend de Run Manifest Completeness).

**Justification de l'état.** La validation de schéma des specs existantes est exécutable aujourd'hui et publierait une violation : la seule spec présente ne déclare aucune métrique primaire mais huit critères go/no-go de même rang. Le volet portant sur le verdict n'est pas encore observable (0 verdict).

**Preuve actuelle.** ⚠ **À REVÉRIFIER** — experiments/ contient 1 fichier YAML et 0 module Python ; vérifié dans le dépôt : experiments/EXP-001.yaml:90-99 aligne 8 critères go_no_go (n_min, profit_factor, expectancy, max_drawdown, sharpe, health_check, data_quality, hypotheses) sans champ metrics.primary ; 0 verdict à ce jour.

**Contrôle futur.** Validation de schéma : cardinalité de metrics.primary égale à 1 ; puis, dès que l'objet Verdict existe, vérification que l'identifiant de métrique cité par un verdict PASS appartient à ce singleton.

#### `SSC-D5-04` — Stopping Rule Preregistered

| | |
|---|---|
| **Objet** | Champ design.stopping_rule de l'ExperimentSpec |
| **État** | `OBSERVED` |
| **Portée du blocage** | merge |
| **Dépend de** | `Experiment Preregistration Precedence` |

**Énoncé.** Scinder : (a) 'Stopping Rule Declared' — design.stopping_rule présent et non vide dans toute spec (OBSERVED) ; (b) 'Sealed Spec Immutability' — aucun champ de la spec (dont stopping_rule et l'énumération des bras) modifié dans un commit postérieur au commit de scellement (DESIGNED, à mutualiser avec Experiment Preregistration Precedence et Ablation Groups Preregistered au lieu d'être répété dans trois articles).

**Justification de l'état.** La présence du champ et l'historique git du fichier sont vérifiables aujourd'hui sur les specs existantes, et le contrôle publierait une violation : la seule spec présente n'a ni règle d'arrêt ni submitted_at. Violé, donc non promouvable (SSC-R3).

**Preuve actuelle.** ⚠ **À REVÉRIFIER** — experiments/ contient 1 fichier YAML et 0 module Python ; vérifié dans le dépôt : experiments/EXP-001.yaml ne contient ni champ stopping_rule ni champ submitted_at, et son champ date_end reste null depuis le 2026-06-30.

**Contrôle futur.** Validation de schéma (champ présent et non vide) complétée par une vérification d'intégrité de l'historique git : aucune modification du champ dans un commit postérieur à celui qui porte submitted_at.

#### `SSC-D5-05` — Experiment Corpus Bound Single Source

| | |
|---|---|
| **Objet** | Borne d'époque CLEAN_DATA_SINCE utilisée par tout outil d'expérience, de rejeu, d'ablation, de walk-forward ou de stress |
| **État** | `ENFORCED_NEW` |
| **Portée du blocage** | commit |

**Énoncé.** Énumérer le périmètre par chemins versionnés (liste explicite de fichiers/répertoires, révisée par ADR) et rendre le contrôle purement syntaxique : aucun littéral date/datetime ISO-8601 dans ces fichiers, sauf dans la source unique déclarée ; la borne doit provenir d'un import nommé de cette source.

**Justification de l'état.** L'analyse statique du diff est praticable immédiatement et la règle est déjà appliquée aux outils réalignés sur load_clean_trades ; en revanche l'ensemble du dépôt n'est pas prouvé conforme, ce qui interdit ENFORCED_ALL aujourd'hui.

**Preuve actuelle.** ⚠ **À REVÉRIFIER** — 4 bornes CLEAN_DATA_SINCE en 6 semaines (v1 25/06, v2 09/07 01:16, v3 09/07 07:45, v4 17/07 01:30) ; borne canonique active CLEAN_DATA_SINCE_V4 = 2026-07-17T01:30:00Z, source unique scripts/data_quality.py.

**Contrôle futur.** Analyse statique du diff : rejet de toute constante date/datetime ISO servant de borne d'époque hors de scripts/data_quality.py, et vérification que la borne provient d'un import de cette source unique.

#### `SSC-D5-06` — Replay Bit Determinism

| | |
|---|---|
| **Objet** | Artefacts d'un Replay (replay/*.jsonl et run_manifest.json) |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Replay Hermeticity`, `Run Manifest Completeness` |

**Énoncé.** Deux exécutions d'un même rejeu — même spec scellée, même corpus, même seed, même commit — produisent des artefacts identiques octet pour octet ; toute divergence hors champs volatils explicitement déclarés dans la spec invalide le run et force le verdict INCONCLUSIVE.

**Justification de l'état.** Aucun rejeu n'existe : les deux ReplayEngine définis n'ont produit aucun .pyc en production, il n'y a donc aucun artefact à comparer et le contrôle ne peut rien mesurer.

**Preuve actuelle.** 2 ReplayEngine définis (audit/replay_engine.py:131, market_data/replay_engine.py:70), AUCUN exécuté en prod. Donc zéro rejeu.

**Contrôle futur.** Test de non-régression : double exécution du rejeu dans la chaîne d'intégration puis comparaison de hachages sur l'ensemble des fichiers produits, la liste des champs volatils autorisés étant déclarée dans la spec et vide par défaut.

#### `SSC-D5-07` — Replay Authority Identity

| | |
|---|---|
| **Objet** | Autorité de décision : conjonction de 12 booléens à core/advisor_loop.py:1983 et ses 4 révocations |
| **État** | `DESIGNED` |
| **Portée du blocage** | merge |
| **Dépend de** | `Replay Isolation From Production Runtime` |

**Énoncé.** Scinder : (a) 'Decision Authority Write Sites Bounded' — le nombre de sites d'écriture de trade_allowed est <= 5 et TOUS résident dans core/advisor_loop.py (mesurable et satisfait aujourd'hui, verrouillable) ; (b) 'Replay Authority Identity' — le point d'entrée de rejeu importe et invoque l'objet d'autorité de production (identité d'objet, pas égalité de valeur) et n'ajoute aucun site d'écriture de trade_allowed dans sa fermeture d'import (DESIGNED).

**Justification de l'état.** Le rejeu n'existe pas (zéro rejeu) : l'identité de symbole entre rejeu et production ne peut pas être testée aujourd'hui. Le comptage des sites d'écriture est mesurable, mais l'invariant porte sur une relation rejeu↔production qui n'a aucun terme gauche.

**Preuve actuelle.** trade_allowed = conjonction de 12 booléens à core/advisor_loop.py:1983 ; révocations à core/advisor_loop.py:5626 (risk_governor), :5658 (safety_auditor), :5734 et :5808 (decision_packet) — 5 sites d'écriture au total ; 0 rejeu exécuté.

**Contrôle futur.** Test d'identité de symbole à l'exécution (le rejeu importe et invoque l'objet de production, comparaison d'identité, pas d'égalité de valeur) complété par une analyse statique comptant les sites d'écriture de trade_allowed dans la fermeture d'import du point d'entrée de rejeu.

#### `SSC-D5-08` — Replay Hermeticity

| | |
|---|---|
| **Objet** | Processus d'exécution d'un Replay |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Replay Bit Determinism` |

**Énoncé.** Supprimer la dépendance vers Replay Bit Determinism (l'herméticité est la précondition, pas la conséquence). Scinder en trois articles à contrôle unique : No Network In Replay ; No System Clock In Replay ; Replay Writes Confined To Run Directory.

**Justification de l'état.** Il n'existe aucun harnais de rejeu à instrumenter : aucun des deux ReplayEngine n'est exécuté, donc ni l'analyse de fermeture d'import du point d'entrée de rejeu ni l'exécution sous bac à sable n'ont d'objet.

**Preuve actuelle.** 2 ReplayEngine définis (audit/replay_engine.py:131, market_data/replay_engine.py:70), AUCUN exécuté en prod ; experiments/ contient 1 fichier YAML et 0 module Python.

**Contrôle futur.** Analyse statique de la fermeture d'import du point d'entrée de rejeu (interdiction des clients réseau et des sources d'horloge système) doublée d'une exécution sous bac à sable interdisant les sockets et toute écriture hors du répertoire du run.

#### `SSC-D5-09` — No Forcing Env In Replay Closure

| | |
|---|---|
| **Objet** | FORCE_TEST_EXECUTION (core/advisor_loop.py:1943-1980) et toute variable d'environnement forçant une couche de décision |
| **État** | `OBSERVED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Replay Authority Identity`, `Run Manifest Completeness` |

**Énoncé.** Scinder : (a) 'No Forcing Env In Decision Authority' — aucun module de la fermeture d'import de l'autorité de décision de production ne lit une variable d'environnement forçant une couche à True (OBSERVED, portée merge, violé aujourd'hui par FORCE_TEST_EXECUTION) ; (b) 'Run Environment Recorded And Clean' — l'environnement effectif du run est enregistré au manifeste et ne contient aucune variable de forçage (DESIGNED, portée expérience).

**Justification de l'état.** L'inventaire statique des lectures d'environnement forçant une couche tourne et publie un résultat aujourd'hui, et il est VIOLÉ : le module qui sera précisément l'autorité rejouée force 8 couches depuis l'environnement. Un article violé ne peut pas être promu (SSC-R3).

**Preuve actuelle.** FORCE_TEST_EXECUTION à core/advisor_loop.py:1943-1980 force 8 couches à True depuis une variable d'environnement, sans marquer les trades produits.

**Contrôle futur.** Analyse statique : inventaire des lectures d'environnement affectant une couche de décision dans la fermeture d'import de l'autorité ; puis, dès que le manifeste existe, comparaison de cet inventaire avec l'environnement effectif enregistré.

#### `SSC-D5-10` — Run Manifest Completeness

| | |
|---|---|
| **Objet** | run_manifest.json de tout run (rejeu, ablation, walk-forward, stress) |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |

**Énoncé.** Définir un noyau obligatoire commun à tout run (commit git, hash du corpus, versions de dépendances, seed, date, environnement effectif, artefacts produits, collection d'erreurs — présente, possiblement vide) puis des extensions obligatoires par type de run (walk-forward : segmentation + bloc hors échantillon ; ablation : bras + baseline ; stress : scénarios). Remplacer 'non nul' par 'présent et conforme au schéma du type'.

**Justification de l'état.** L'objet RunManifest n'existe pas : zéro rejeu, zéro verdict, zéro module Python dans experiments/. Aucun schéma ne peut être validé contre un ensemble vide d'instances.

**Preuve actuelle.** 0 rejeu ; 0 verdict, 0 publication ; experiments/ contient 1 fichier YAML et 0 module Python, research/ contient 1 fichier .md et 0 module Python.

**Contrôle futur.** Validation de schéma à l'écriture du manifeste, avec refus d'enregistrer tout résultat dont le manifeste est incomplet, et refus symétrique côté agrégation du verdict.

#### `SSC-D5-11` — Replay Isolation From Production Runtime

| | |
|---|---|
| **Objet** | Modules de laboratoire (ReplayEngine, ablation, walk-forward, stress) vs fermeture d'exécution de core/advisor_loop.py |
| **État** | `ENFORCED_ALL` |
| **Portée du blocage** | deploiement |

**Énoncé.** Énumérer le périmètre laboratoire par chemins versionnés (au minimum audit/replay_engine.py et market_data/replay_engine.py, plus research/ et experiments/), et désigner la mesure .pyc post-déploiement comme contrôle AUTORITAIRE, l'analyse statique n'étant qu'un pré-filtre non concluant en raison de ses 52 faux négatifs mesurés.

**Justification de l'état.** Déjà satisfait aujourd'hui, donc verrouillable gratuitement (SSC-R4) : aucun des deux ReplayEngine ne figure parmi les modules réellement exécutés en production, mesurés par les .pyc.

**Preuve actuelle.** 2 ReplayEngine définis (audit/replay_engine.py:131, market_data/replay_engine.py:70), AUCUN exécuté en prod ; 210 modules EXÉCUTÉS en prod sur 1115 (mesure .pyc), point d'entrée runtime réel core/advisor_loop.py.

**Contrôle futur.** Requête de graphe sur la fermeture d'import du point d'entrée de production, recoupée par la mesure des .pyc réellement produits sur la machine ; échec si un module de laboratoire y figure.

#### `SSC-D5-12` — Ablation Corpus And Seed Identity

| | |
|---|---|
| **Objet** | Bras d'une AblationResult (baseline incluse) |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Run Manifest Completeness`, `Replay Bit Determinism` |

**Énoncé.** Tous les bras d'une même ablation, baseline comprise, partagent un corpus de hash identique et un seed identique ; toute différence sur l'un de ces deux champs entre deux bras invalide l'ablation entière et interdit toute lecture d'effet marginal.

**Justification de l'état.** Aucune ablation n'a jamais été exécutée et aucun manifeste ne porte de corpus_hash ou de seed : il n'existe aucune paire de bras à comparer.

**Preuve actuelle.** 0 rejeu, donc 0 ablation ; experiments/ contient 1 fichier YAML et 0 module Python ; 1 seule hypothèse conclue à ce jour (H3 rejetée le 31/07, Cohen's d = -0,097) sans ablation.

**Contrôle futur.** Comparaison des champs corpus_hash et seed des manifestes de tous les bras avant agrégation des effets marginaux ; refus d'agrégation en cas d'écart.

#### `SSC-D5-13` — Ablation Groups Preregistered

| | |
|---|---|
| **Objet** | Liste des couches et groupes de couches désarmés, déclarée dans l'ExperimentSpec scellée |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Experiment Preregistration Precedence`, `Ablation Corpus And Seed Identity` |

**Énoncé.** Réduire l'article à une seule condition falsifiable : l'ensemble des bras exécutés d'après les manifestes est exactement égal à l'ensemble des bras énumérés dans la spec scellée. Déplacer l'exhaustivité (couverture des 12 booléens et des 4 révocations) vers un article distinct de niveau programme, non de niveau expérience, et déléguer l'immuabilité post-scellement à l'article Sealed Spec Immutability.

**Justification de l'état.** Ni l'objet Ablation ni un champ d'énumération de bras n'existent : la seule spec du dépôt ne déclare aucune couche à désarmer. Rien ne peut être comparé aujourd'hui.

**Preuve actuelle.** trade_allowed = conjonction de 12 booléens à core/advisor_loop.py:1983, révocations à :5626, :5658, :5734, :5808 ; 0 ablation exécutée ; experiments/ contient 1 fichier YAML et 0 module Python.

**Contrôle futur.** Comparaison d'ensembles entre les bras déclarés dans la spec scellée, les bras effectivement exécutés d'après les manifestes, et la liste des couches extraite statiquement du site de conjonction et des sites de révocation ; plus vérification d'intégrité git de la spec après submitted_at.

#### `SSC-D5-14` — No Lookahead Test Mandatory

| | |
|---|---|
| **Objet** | Résultats de rejeu, d'ablation et de walk-forward |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Run Manifest Completeness` |

**Énoncé.** Tout résultat de rejeu, d'ablation ou de walk-forward référence l'identifiant d'un test anti-lookahead passé sur le même corpus — altération des données postérieures à l'instant de décision devant laisser les décisions strictement inchangées ; l'absence de référence ou l'échec du test force le verdict INCONCLUSIVE.

**Justification de l'état.** Il n'existe ni harnais de rejeu ni manifeste où inscrire une référence de test : aucun corpus n'est rejoué, aucun test anti-lookahead ne peut donc être exécuté ni référencé.

**Preuve actuelle.** 0 rejeu ; experiments/ contient 1 fichier YAML et 0 module Python ; research/ contient 1 fichier .md et 0 module Python.

**Contrôle futur.** Test de non-régression dédié sur corpus synthétique dont le futur est corrompu, dont l'identifiant et le résultat sont inscrits au run_manifest et vérifiés à l'agrégation du verdict.

#### `SSC-D5-15` — Walk Forward Segmentation Preregistered

| | |
|---|---|
| **Objet** | WalkForwardResult et son bloc de segmentation |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Experiment Preregistration Precedence`, `No Lookahead Test Mandatory` |

**Énoncé.** Réduire à : la segmentation (nombre de segments, bornes, taille) enregistrée au manifeste est identique à celle déclarée dans la spec scellée avant exécution ; tout écart invalide le résultat. Supprimer la clause sur le bloc hors échantillon (couverte par l'extension walk-forward de Run Manifest Completeness) et la clause rhétorique.

**Justification de l'état.** Aucun walk-forward n'a été exécuté et aucune spec ne comporte de champ de segmentation : les deux termes de la comparaison sont absents.

**Preuve actuelle.** 0 rejeu et aucun walk-forward exécuté ; N = 139 trades sur l'époque V4, 0 verdict, 0 publication.

**Contrôle futur.** Comparaison de la segmentation déclarée dans la spec scellée et de celle enregistrée au manifeste, plus contrôle de présence obligatoire du bloc de résultats hors échantillon à l'écriture du manifeste.

#### `SSC-D5-16` — Mandatory Stress Scenarios

| | |
|---|---|
| **Objet** | StressResult (experiments/EXP-*/stress.json) |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Run Manifest Completeness` |

**Énoncé.** Tout jeu de stress contient et exécute les sept scénarios minimaux — coûts ×2, slippage ×3, latence dégradée, régime de marché absent du corpus, panne d'exchange, données manquantes, redémarrage à froid ; un scénario manquant ou non exécuté rend le stress incomplet et interdit tout verdict PASS.

**Justification de l'état.** L'objet StressResult n'existe pas : aucun module de stress n'est présent dans experiments/ ni dans research/, et aucun rejeu ne permettrait de l'alimenter.

**Preuve actuelle.** experiments/ contient 1 fichier YAML et 0 module Python ; research/ contient 1 fichier .md et 0 module Python ; 0 rejeu, 0 verdict.

**Contrôle futur.** Validation de schéma par énumération fermée : l'ensemble des identifiants de scénarios présents dans stress.json doit contenir les sept identifiants obligatoires, chacun assorti d'un statut d'exécution et d'un résultat.

#### `SSC-D5-17` — Cost Stress Downgrade To Inconclusive

| | |
|---|---|
| **Objet** | Règle de dérivation du Verdict à partir du StressResult |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Mandatory Stress Scenarios`, `Single Primary Metric` |

**Énoncé.** Conditionner explicitement : la spec doit déclarer la métrique primaire en rendement net de coûts par trade pour que la clause du plancher de friction s'applique ; sinon la spec doit déclarer la fonction de conversion vers cette unité. Scinder en (a) dégradation en INCONCLUSIVE si l'effet sous coûts ×2 tombe sous le MDE déclaré, (b) dégradation si le rendement net par trade ne franchit pas le plancher de friction mesuré.

**Justification de l'état.** Ni l'objet Verdict ni l'objet StressResult n'existent : aucun verdict n'a jamais été émis, donc aucune règle de dégradation ne peut s'appliquer ni être observée.

**Preuve actuelle.** Plancher de friction mesuré non franchi : 0,194 % (INV-FRICTION-001) ; 0 verdict, 0 publication ; état scientifique N = 139, PF = 0,617, t = -1,571 non significatif.

**Contrôle futur.** Règle de dérivation évaluée à l'agrégation : lecture du résultat du scénario coûts ×2, comparaison de l'effet net au MDE déclaré et au plancher de friction, dégradation automatique et journalisée du verdict si la condition n'est pas remplie.

#### `SSC-D5-18` — Simulator Fidelity Disclosure

| | |
|---|---|
| **Objet** | run_manifest.json et Verdict, au regard de paper_trading/mexc_simulator.py |
| **État** | `ENFORCED_ALL` |
| **Portée du blocage** | experience |
| **Dépend de** | `Run Manifest Completeness` |

**Énoncé.** Rendre la sortie mécanique et contraignante : la mention ne peut être retirée que si le manifeste référence, par hash, un artefact de mesure de fidélité contenant un échantillon apparié fills simulés / fills réels de taille N déclarée et une statistique d'écart bornée, et que cet artefact porte sur le même exchange et le même type d'ordre que le run.

**Justification de l'état.** Verrouillable gratuitement (SSC-R4) : il n'existe aujourd'hui ni manifeste ni verdict, l'invariant est donc satisfait à vide et s'appliquera dès le premier artefact produit, avant que le retrait de la mention ne devienne un enjeu.

**Preuve actuelle.** Fidélité du simulateur MEXC (paper_trading/mexc_simulator.py, 966 lignes, exécuté en prod) : NON MESURÉE ; 0 verdict, 0 publication, 0 rejeu.

**Contrôle futur.** Vérification de contenu à l'écriture de tout manifeste ou verdict : présence du champ de limitation de fidélité, et — s'il est absent — présence obligatoire d'une référence à un artefact de mesure de fidélité existant et daté.

### D6 — Evidence, Calibration, Policy

#### `SSC-D6-01` — Verdict Immutability

| | |
|---|---|
| **Objet** | Verdict |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |

**Énoncé.** Un Verdict émis n'est jamais modifié : son contenu (outcome, effect_size, ci, p_value, n, power, limitations) est figé par une empreinte signée à l'émission, recalculée à chaque lecture et en CI ; le magasin refuse toute écriture sur un identifiant déjà émis. La règle de succession (supersedes / superseded_by) est portée exclusivement par 'Succession Not Mutation' et retirée d'ici.

**Justification de l'état.** L'objet Verdict n'existe dans aucun artefact du dépôt : rien n'est observable, aucun contrôle ne peut publier de résultat aujourd'hui (SSC-R5). L'invariant est déclaré pour ne pas être oublié à la création de l'objet.

**Preuve actuelle.** 0 verdict, 0 publication, 0 objet Calibration, 0 rejeu ; Evidence Score = 0 ; la seule hypothèse conclue (H3 rejetée le 31/07, Cohen's d=-0.097) n'a produit aucun artefact Verdict.

**Contrôle futur.** Vérification d'intégrité : empreinte et signature calculées à l'émission, recalculées à chaque lecture et en CI ; magasin append-only refusant toute réécriture sur un identifiant déjà émis.

#### `SSC-D6-02` — Verdict Limitations Not Empty

| | |
|---|---|
| **Objet** | Verdict.limitations[] |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Verdict Immutability` |

**Énoncé.** Aucun Verdict ne peut être émis sans un champ limitations contenant au moins une entrée typée {code, portée, valeur}, dont le code appartient à un vocabulaire fermé et versionné (au minimum : simulator_fidelity, taille d'échantillon, horizon d'information, univers/époque, friction) ; le verdict est refusé si le champ est absent, vide, ou si une entrée porte une valeur de remplissage (chaîne vide, 'n/a', 'aucune', 'RAS').

**Justification de l'état.** Le champ n'existe pas puisque l'objet n'existe pas ; aucun corpus de verdicts ne peut être scanné aujourd'hui.

**Preuve actuelle.** 0 verdict existant (Evidence Score = 0) ; la seule conclusion produite (H3 rejetée le 31/07) n'est portée par aucun artefact structuré comportant un champ limitations.

**Contrôle futur.** Validation de schéma à l'écriture, rejouée en CI sur l'ensemble du corpus de verdicts : rejet si limitations est absent ou vide.

#### `SSC-D6-03` — Inconclusive Declares Missing Evidence

| | |
|---|---|
| **Objet** | Verdict.missing_for_conclusion[] |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Verdict Immutability` |

**Énoncé.** Tout Verdict d'outcome INCONCLUSIVE porte un champ missing_for_conclusion non vide énumérant ce qui manque (N supplémentaire, puissance, rejeu déterministe, scénario de stress) ; un INCONCLUSIVE sans ce champ est invalide.

**Justification de l'état.** Objet inexistant, donc non observable. La condition est purement conditionnelle à l'outcome et sera vérifiable dès la première écriture d'un Verdict.

**Preuve actuelle.** 0 verdict ; l'état scientifique actuel est précisément un manque non enregistré : N=139 trades sur l'époque V4, PF=0.617, WR=34.9%, t=-1.571 non significatif, sans aucun artefact déclarant ce qu'il faudrait pour conclure.

**Contrôle futur.** Validation de schéma conditionnelle à l'écriture, doublée d'une requête de graphe de contrôle qui doit pouvoir répondre « que faudrait-il pour conclure ? » sans relire aucun document.

#### `SSC-D6-04` — Succession Not Mutation

| | |
|---|---|
| **Objet** | Tout objet scientifique (Verdict, Calibration, Policy, Baseline, Corpus, ADR) |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Verdict Immutability` |

**Énoncé.** Restreindre l'objet aux artefacts créés par le contrat (Verdict, Calibration, Policy, Publication, Baseline) : leur correction se fait exclusivement par création d'un successeur (version incrémentée, supersedes sur le nouvel objet, superseded_by sur l'ancien, aucune réécriture du contenu émis). La succession des ADR, objets déjà existants, fait l'objet d'un invariant distinct en état OBSERVED.

**Justification de l'état.** Aucun de ces objets n'existe : il n'y a rien à muter ni à succéder, donc rien à mesurer. La pratique de correction actuelle (réécriture de constantes en place) montre pourquoi l'invariant doit être posé avant la création des objets.

**Preuve actuelle.** 0 verdict, 0 objet Calibration, 0 publication ; unique mécanisme de correction observé = réécriture en place d'une constante : 4 bornes CLEAN_DATA_SINCE en 6 semaines (v1 25/06, v2 09/07 01:16, v3 09/07 07:45, v4 17/07 01:30) sans chaîne de succession entre elles.

**Contrôle futur.** Contrôle append-only du magasin d'objets et requête de graphe vérifiant que chaque couple (supersedes, superseded_by) est réciproque, acyclique, et qu'aucun identifiant n'a deux contenus distincts dans l'historique.

#### `SSC-D6-05` — Calibration Requires Justifying Verdict

| | |
|---|---|
| **Objet** | Calibration |
| **État** | `DESIGNED` |
| **Portée du blocage** | deploiement |
| **Dépend de** | `Verdict Immutability`, `Policy Change Requires Evidence Bundle` |

**Énoncé.** Scinder. (a) « Calibration Requires Justifying Verdict » : aucune Calibration n'atteint APPROVED ni APPLIED sans justification_verdict résolvable vers un Verdict existant d'outcome PASS. (b) « Decision Parameter Change Requires Calibration » : toute modification d'une valeur inscrite dans un registre versionné et fermé de paramètres de décision (initialisé au minimum avec les 5 sites d'écriture mesurés — core/advisor_loop.py:1983, :5626, :5658, :5734, :5808 — et config/feature_flags.py) exige une Calibration associée ; hors registre, aucune détection n'est réclamée.

**Justification de l'état.** L'objet Calibration n'existe pas et aucun Verdict n'existe pour le justifier ; le contrôle n'aurait aujourd'hui aucun objet à évaluer.

**Preuve actuelle.** 0 objet Calibration et 0 verdict ; les paramètres de décision sont câblés dans la conjonction de 12 booléens à core/advisor_loop.py:1983 avec 5 sites d'écriture (:5626, :5658, :5734, :5808), sans aucun lien vers une preuve.

**Contrôle futur.** Requête de graphe avant application : refus si justification_verdict est nul, non résolvable, ou pointe vers un Verdict d'outcome autre que PASS ; complétée par une analyse statique du diff détectant tout changement de valeur d'un paramètre de décision non couvert par une Calibration.

#### `SSC-D6-06` — Refuted Verdict Invalidates Dependent Calibrations

| | |
|---|---|
| **Objet** | Arête Verdict —[JUSTIFIES]→ Calibration |
| **État** | `DESIGNED` |
| **Portée du blocage** | deploiement |
| **Dépend de** | `Calibration Requires Justifying Verdict` |

**Énoncé.** Aucune Calibration à l'état APPLIED ne repose sur un Verdict REFUTED, ni sur un Verdict SUPERSEDED dont le successeur n'est pas d'outcome PASS ; tout basculement vers l'un de ces cas marque automatiquement les Calibrations dépendantes et interdit leur reconduction au déploiement suivant.

**Justification de l'état.** Ni les Calibrations ni les Verdicts n'existent : l'arête à parcourir n'existe pas, aucune alerte ne peut être produite aujourd'hui.

**Preuve actuelle.** 0 Calibration et 0 verdict ; la question « quels paramètres actifs reposent sur une hypothèse depuis réfutée ? » n'est pas posable, alors qu'une réfutation a déjà eu lieu (H3 rejetée le 31/07, Cohen's d=-0.097).

**Contrôle futur.** Requête de graphe déclenchée à chaque émission ou changement d'état de Verdict : parcours inverse des arêtes JUSTIFIES, alerte et marquage des Calibrations concernées ; au déploiement, refus si une Calibration marquée est encore active.

#### `SSC-D6-07` — Active Policy Requires Human Signature

| | |
|---|---|
| **Objet** | Policy |
| **État** | `DESIGNED` |
| **Portée du blocage** | runtime_boot |
| **Dépend de** | `Succession Not Mutation` |

**Énoncé.** Aucune Policy à l'état ACTIVE sans signed_by d'un acteur de type human et signed_at renseignés ; le runtime refuse de démarrer sur une Policy non signée ou dont la signature ne vérifie pas le contenu.

**Justification de l'état.** Aucun objet Policy versionné et signé n'existe : la politique effective est câblée dans le code, il n'y a pas de champ signed_by à valider ni de chargement de Policy au boot.

**Preuve actuelle.** La politique effective est câblée en dur — conjonction de 12 booléens à core/advisor_loop.py:1983, révocations à :5626, :5658, :5734, :5808 — sans version ni signature ; aucun objet Policy n'apparaît dans la cartographie (1115 modules, 210 exécutés).

**Contrôle futur.** Validation de schéma au chargement de la Policy et vérification cryptographique de signature au démarrage : refus de boot si signed_by est absent, d'un type autre que human, ou si la signature ne correspond pas au contenu chargé.

#### `SSC-D6-08` — Policy Change Requires Evidence Bundle

| | |
|---|---|
| **Objet** | Proposal / pull request modifiant une Policy |
| **État** | `DESIGNED` |
| **Portée du blocage** | merge |
| **Dépend de** | `Verdict Immutability`, `Human Merge Only` |

**Énoncé.** Scinder en trois invariants indépendants, chacun avec son propre état et sa propre date d'activation : (a) toute PR modifiant une Policy porte un identifiant de Verdict résolvable d'outcome PASS ; (b) toute PR modifiant une Policy porte un RunManifest rejoué dont le determinism_proof est reproduit à l'identique ; (c) toute PR modifiant une Policy porte un N supérieur ou égal au min_n préenregistré dans la spec d'expérience.

**Justification de l'état.** Les trois pièces exigées n'existent pas : ni Verdict, ni rejeu, ni spec d'expérience exécutable. Le contrôle ne pourrait aujourd'hui que refuser systématiquement, sans rien mesurer.

**Preuve actuelle.** 0 verdict et 0 rejeu : les 2 ReplayEngine définis (audit/replay_engine.py:131, market_data/replay_engine.py:70) ne sont exécutés ni l'un ni l'autre en production ; experiments/ contient 1 fichier YAML et 0 module Python ; N=139 trades époque V4, t=-1.571 non significatif.

**Contrôle futur.** Contrôle CI sur la PR : résolution de l'identifiant de Verdict et vérification de son outcome PASS, réexécution du RunManifest et comparaison du determinism_proof, comparaison de N au min_n préenregistré ; échec bloquant si une pièce manque ou ne se vérifie pas.

#### `SSC-D6-09` — Publication Mandatory For Every Verdict

| | |
|---|---|
| **Objet** | Publication |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Verdict Immutability` |

**Énoncé.** Tout Verdict émis donne lieu à une Publication liée avant clôture de l'expérience, quel que soit son outcome — PASS, FAIL et INCONCLUSIVE compris ; une Experiment ne peut pas passer à COMPLETED si son verdict n'est pas publié.

**Justification de l'état.** Ni Verdict ni Publication n'existent comme objets : l'arête à contrôler n'est pas instanciable aujourd'hui. Le biais de publication est pourtant déjà réalisé, ce qui justifie de déclarer l'invariant maintenant.

**Preuve actuelle.** 0 publication pour 1 hypothèse conclue : H3 rejetée le 31/07 (Cohen's d=-0.097) est un résultat négatif non publié ; research/ contient 1 fichier .md et 0 module Python.

**Contrôle futur.** Requête de graphe au moment de la clôture : tout Verdict sans arête REPORTED_IN vers une Publication bloque la transition de l'Experiment vers COMPLETED ; le contrôle publie en continu le taux de publication par outcome pour rendre visible tout déséquilibre PASS/FAIL.

#### `SSC-D6-10` — Replay Verdict Declares Simulator Fidelity Gap

| | |
|---|---|
| **Objet** | Verdict issu d'un rejeu ou d'une simulation |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Verdict Limitations Not Empty` |

**Énoncé.** Tout Verdict dérivé d'un rejeu ou d'une simulation porte dans limitations une entrée typée sur l'écart entre fills simulés et fills réels : soit une valeur mesurée référencée, soit la mention explicite « NON MESURÉ » ; l'absence de cette entrée invalide le verdict.

**Justification de l'état.** Aucun Verdict ni aucun rejeu n'existe ; l'entrée à valider ne peut pas être observée. L'écart lui-même n'est pas mesuré, ce qui rend l'invariant d'autant plus nécessaire dès le premier verdict.

**Preuve actuelle.** Fidélité du simulateur MEXC (paper_trading/mexc_simulator.py, 966 lignes, exécuté en production) : NON MESURÉE ; plancher de friction mesuré 0,194 % non franchi (INV-FRICTION-001) ; 0 rejeu exécuté en production.

**Contrôle futur.** Validation de schéma à l'écriture : le champ limitations doit contenir une entrée simulator_fidelity dont la valeur est soit un écart chiffré référençant une mesure datée, soit le littéral NON MESURÉ ; contrôle rejoué en CI sur tout le corpus.

#### `SSC-D6-11` — Three Role Separation

| | |
|---|---|
| **Objet** | provenance.actor_id des rôles proposer / valider / appliquer |
| **État** | `DESIGNED` |
| **Portée du blocage** | deploiement |
| **Dépend de** | `Human Merge Only`, `No Automated Deployment Trigger` |

**Énoncé.** Pour un même changement de paramètre de décision, l'acteur qui propose n'est jamais celui qui valide, et aucun acteur de type agent n'occupe les rôles valider ou appliquer. Le cumul valider = appliquer par un même acteur humain est autorisé tant qu'un seul opérateur humain est enregistré, à condition d'être explicitement enregistré comme tel dans le bloc provenance.

**Justification de l'état.** Aucun objet ne porte de bloc provenance aujourd'hui : les trois rôles ne sont pas enregistrés, donc leur distinction n'est pas vérifiable mécaniquement, même si la séparation existe de fait.

**Preuve actuelle.** 0 verdict, 0 Calibration, 0 objet Deployment : aucun bloc provenance n'existe. Séparation observable seulement de façon indirecte : la production exécute f427895 (20/07, identifié par md5 normalisé LF) alors que le commit local 032d4ee (31/07) n'est pas déployé — proposer et appliquer sont disjoints en pratique, mais rien ne l'enregistre.

**Contrôle futur.** Contrôle de provenance aux trois points du cycle (Proposal, approbation, application) : refus si deux rôles partagent le même actor_id, ou si un actor_type=agent apparaît en rôle valider ou appliquer.

#### `SSC-D6-12` — Cited ADR Must Exist

| | |
|---|---|
| **Objet** | Références ADR dans le code, la documentation et les artefacts |
| **État** | `OBSERVED` |
| **Portée du blocage** | merge |

**Énoncé.** Restreindre à : tout identifiant ADR cité dans le dépôt (code, documentation, artefacts) résout vers un fichier existant de docs/adr/ ; une citation orpheline est un défaut. La condition de statut (REVOKED ou SUPERSEDED sans successeur déclaré) devient un invariant distinct, en état DESIGNED tant qu'aucun champ de statut lisible par machine n'existe dans les ADR.

**Justification de l'état.** Mesurable immédiatement par analyse statique, mais l'invariant est VIOLÉ aujourd'hui : il ne peut donc pas être promu tant que la violation subsiste (SSC-R3). Le contrôle tourne et publie, il ne bloque rien.

**Preuve actuelle.** ADR-0018 est cité comme source canonique par tools/score_calibration_audit.py:675 mais est ABSENT de docs/adr/ (la séquence passe de 0017 à 0019).

**Contrôle futur.** Analyse statique : extraction de toutes les occurrences d'identifiants ADR du dépôt, résolution vers les fichiers de docs/adr/, échec pour toute référence non résolue ou pointant vers un ADR révoqué sans successeur.

#### `SSC-D6-13` — Epoch Boundary Requires Existing ADR

| | |
|---|---|
| **Objet** | Borne canonique CLEAN_DATA_SINCE (source unique scripts/data_quality.py) |
| **État** | `OBSERVED` *(rétrogradé depuis ENFORCED_NEW)* |
| **Portée du blocage** | commit |
| **Dépend de** | `Cited ADR Must Exist` |

**Énoncé.** (a) Toute modification de la constante de borne canonique dans le module source unique (scripts/data_quality.py) est accompagnée, dans le même changement, d'un identifiant ADR résolvant vers un fichier existant de docs/adr/. (b) Invariant distinct : aucune occurrence littérale d'une valeur de borne n'est introduite dans un fichier Python exécutable hors du module source unique ; la documentation et les ADR sont explicitement hors périmètre.

**Justification de l'état.** La borne existe et sa valeur est observable dès aujourd'hui ; le contrôle s'applique immédiatement à tout nouveau changement sans exiger de reconstruire l'historique des quatre bornes déjà passées.

**Preuve actuelle.** 4 bornes CLEAN_DATA_SINCE en 6 semaines (v1 25/06, v2 09/07 01:16, v3 09/07 07:45, v4 17/07 01:30) ; borne canonique active CLEAN_DATA_SINCE_V4 = 2026-07-17T01:30:00Z ; et une citation d'ADR déjà non résolvable (ADR-0018 cité par tools/score_calibration_audit.py:675, absent de docs/adr/).

**Contrôle futur.** Analyse statique du diff : si la constante de borne change, exiger dans le même changement un identifiant ADR résolvable vers un fichier de docs/adr/ ; refuser en outre toute nouvelle occurrence littérale d'une date de borne hors du module source unique.

#### `SSC-D6-14` — Human Merge Only

| | |
|---|---|
| **Objet** | Branche principale du dépôt |
| **État** | `OBSERVED` *(rétrogradé depuis ENFORCED_NEW)* |
| **Portée du blocage** | merge |

**Énoncé.** Scinder : (a) aucun compte de service ni acteur de type agent ne dispose du droit de fusion sur la branche principale — vérifié sur la configuration de protection de branche, qui doit d'abord être mesurée ; (b) toute fusion postérieure à l'adoption du contrat porte une approbation d'un acteur humain vérifiable, l'historique antérieur n'étant ni réécrit ni exigé conforme.

**Justification de l'état.** Verrouillable gratuitement aujourd'hui (SSC-R4) : aucun pipeline d'agent capable de produire ou fusionner un changement n'existe. Le jour où un conseil d'agents existera, poser ce verrou coûtera des arbitrages et des exceptions.

**Preuve actuelle.** experiments/ contient 1 fichier YAML et 0 module Python ; research/ contient 1 fichier .md et 0 module Python ; 0 verdict et 0 publication produits — aucun producteur automatisé de changements n'existe. Configuration effective des droits de fusion du dépôt : NON MESURÉ.

**Contrôle futur.** Inspection de la configuration de protection de branche et de l'historique des fusions : échec si une fusion n'est pas associée à une approbation d'acteur humain, ou si un compte de service dispose du droit de fusion.

#### `SSC-D6-15` — No Automated Deployment Trigger

| | |
|---|---|
| **Objet** | Chaîne de déploiement vers la production |
| **État** | `OBSERVED` |
| **Portée du blocage** | deploiement |
| **Dépend de** | `Human Merge Only` |

**Énoncé.** Scinder et mesurer d'abord : (a) inventaire exhaustif des hooks git, workflows d'intégration continue et tâches planifiées, locales et sur la machine de production ; aucun n'invoque le script de déploiement — état OBSERVED jusqu'à la première mesure, promotion en ENFORCED_ALL seulement si l'inventaire mesuré est vide ; (b) tout tag d'audit de déploiement créé après l'adoption du contrat est adossé à une comparaison d'empreintes des fichiers effectivement présents en production, jamais à un code de retour — état ENFORCED_NEW, l'historique des tags antérieurs restant marqué comme non vérifié.

**Justification de l'état.** Déjà satisfait en pratique — les commits ne se déploient pas tout seuls — donc verrouillable sans coût (SSC-R4). C'est la contre-mesure directe de l'incident du 2026-07-09.

**Preuve actuelle.** La production exécute f427895 (20/07, identifié par md5 normalisé LF) alors que le commit local 032d4ee (31/07) n'est pas déployé : aucun automatisme n'a transféré les commits intermédiaires. Incident 2026-07-09 : bug « ssh sans -n » dans deploy_vps.sh, 3 tags d'audit mensongers, 55 fichiers sur 80 jamais déployés, gate SEC-01 inactif. Contenu exact de .git/hooks et des workflows CI : NON MESURÉ.

**Contrôle futur.** Analyse statique des hooks, workflows et tâches planifiées à la recherche de toute invocation du script de déploiement, plus vérification que chaque tag d'audit est adossé à une comparaison d'empreintes post-transfert et non à un simple code de retour.

#### `SSC-D6-16` — No Runtime Auto Calibration

| | |
|---|---|
| **Objet** | config/feature_flags.py et chemins d'écriture des paramètres de décision |
| **État** | `OBSERVED` |
| **Portée du blocage** | commit |
| **Dépend de** | `Calibration Requires Justifying Verdict` |

**Énoncé.** Scinder. (a) ENFORCED_ALL, gratuit et déjà satisfait : FEATURE_AUTO_CALIBRATION et FEATURE_ADAPTIVE_CALIBRATION conservent la valeur False dans le code versionné, et leur liste de consommateurs, épinglée, ne s'élargit pas sans changement déclaré. (b) OBSERVED : aucun module d'un périmètre de décision explicitement énuméré n'écrit un paramètre de décision hors Calibration, FORCE_TEST_EXECUTION (core/advisor_loop.py:1943-1980) étant enregistré comme violation ouverte ; le périmètre est un registre versionné, jamais un calcul d'atteignabilité statique. Retirer la dépendance vers un invariant DESIGNED.

**Justification de l'état.** Invariant déjà satisfait aujourd'hui et mesuré comme tel : le verrouiller est gratuit maintenant (SSC-R4). Il transcrit la règle constitutionnelle de passivité des observers (ADR-0007).

**Preuve actuelle.** FEATURE_AUTO_CALIBRATION=False et FEATURE_ADAPTIVE_CALIBRATION=False (config/feature_flags.py:47,50) ; unique consommateur quant_hedge_ai/agents/intelligence/regret_engine.py:339-341, delta toujours nul.

**Contrôle futur.** Analyse statique vérifiant que les deux drapeaux conservent la valeur False par défaut, que la liste de leurs consommateurs ne s'élargit pas sans changement déclaré, et qu'aucun module atteignable depuis le point d'entrée core/advisor_loop.py n'écrit un paramètre de décision ; complétée par un test de non-régression asseyant la nullité du delta.

### D7 — Provenance, Graphe, Mémoire, Conseil

#### `SSC-D7-01` — Permanent Object Identifier

| | |
|---|---|
| **Objet** | Identifiant canonique de tout objet scientifique (Event, Observation, Question, Hypothesis, Experiment, RunManifest, Verdict, Publication, Calibration, Policy, ADR, Deployment, ResearchEpoch) |
| **État** | `DESIGNED` |
| **Portée du blocage** | commit |

**Énoncé.** Un identifiant de la forme <TYPE>-<ANNÉE>-<NNN> attribué une fois n'est jamais réattribué à un autre objet, même après suppression logique, retrait ou remplacement de l'objet initial.

**Justification de l'état.** Les registres d'objets scientifiques n'existent pas : il n'y a rien sur quoi faire tourner un contrôle d'unicité. On ne peut pas observer aujourd'hui la réattribution d'un identifiant qui n'a jamais été attribué.

**Preuve actuelle.** ⚠ **À REVÉRIFIER** — 0 verdict, 0 objet Calibration, 0 publication ; experiments/ contient 1 fichier YAML et 0 module Python ; research/ contient 1 fichier .md et 0 module Python. Symptôme homologue vérifié dans docs/adr/ : deux fichiers portent le numéro 0008 (0008-ds001-runtime-path-resolution.md et 0008-scientific-intelligence-layer.md), et le numéro 0018 est absent (séquence 0017 puis 0019).

**Contrôle futur.** Contrôle d'unicité sur l'ensemble des identifiants présents dans les registres versionnés, croisé avec un journal append-only des identifiants déjà consommés reconstruit depuis l'historique git. Toute collision ou toute réapparition d'un identifiant retiré bloque.

#### `SSC-D7-02` — Role Impl Separation

| | |
|---|---|
| **Objet** | Bloc provenance : champs actor_id (rôle permanent) et actor_impl (implémentation remplaçable) |
| **État** | `DESIGNED` |
| **Portée du blocage** | commit |
| **Dépend de** | `Mandatory Provenance Block` |

**Énoncé.** Tout objet produit par un acteur porte simultanément actor_id et actor_impl non vides, et actor_id appartient à la liste close des rôles déclarés dans le registre des acteurs versionné (aucune valeur hors liste n'est recevable).

**Justification de l'état.** Aucun objet du dépôt ne porte de bloc provenance, aucun registre d'acteurs n'existe et le conseil d'IA n'est pas activé : le champ à contrôler n'existe dans aucun schéma exécuté.

**Preuve actuelle.** NON MESURÉ — aucun objet portant provenance n'existe dans le système ; 0 verdict et 1 seule hypothèse conclue (H3 rejetée le 31/07, Cohen's d=-0.097), sans acteur enregistré.

**Contrôle futur.** Validation de schéma à l'insertion en registre : présence obligatoire des deux champs, plus vérification que actor_id appartient à la liste close des rôles déclarés et ne correspond à aucun motif de nom de modèle ou de fournisseur.

#### `SSC-D7-03` — Mandatory Provenance Block

| | |
|---|---|
| **Objet** | Bloc provenance de tout objet déposé dans un registre scientifique versionné |
| **État** | `DESIGNED` |
| **Portée du blocage** | commit |

**Énoncé.** Aucun objet n'entre dans un registre scientifique sans un bloc provenance complet et non vide : actor_type, actor_id, actor_impl, actor_version, inputs, method, limitations ; un champ absent, vide ou renseigné par une valeur sentinelle rend l'objet irrecevable.

**Justification de l'état.** Les registres qui devraient porter ce bloc n'existent pas (aucun objet Verdict, Calibration ou Publication), donc aucune violation n'est observable et aucun contrôle ne peut publier de résultat aujourd'hui.

**Preuve actuelle.** 0 verdict, 0 objet Calibration, 0 publication, 0 rejeu ; Evidence Score = 0. La provenance des enregistrements existants (paper_trades.jsonl, store JSONL d'observations) est NON MESURÉE.

**Contrôle futur.** Validation de schéma bloquante à l'écriture dans tout registre, plus balayage périodique de l'intégralité des registres versionnés pour détecter les objets antérieurs non conformes.

#### `SSC-D7-04` — Open Text Primary Representation

| | |
|---|---|
| **Objet** | Représentation primaire de tout objet de connaissance (registres, verdicts, hypothèses, documents d'amorçage, index sémantiques) |
| **État** | `DESIGNED` |
| **Portée du blocage** | commit |

**Énoncé.** La représentation primaire de tout objet de connaissance déposé dans un chemin figurant à la liste versionnée des registres scientifiques est un fichier texte de format ouvert (JSON, JSONL, YAML, Markdown) ; toute représentation binaire ou vectorielle de ces mêmes objets est un index dérivé, reconstructible intégralement depuis ces fichiers, et jamais une source.

**Justification de l'état.** Le contrôle est applicable immédiatement aux chemins de registre nouvellement créés ou modifiés, mais l'inventaire complet des formats déjà présents dans le dépôt (bases binaires sous databases/, artefacts historiques) n'a pas été mesuré : verrouiller l'existant reviendrait à bloquer sur un périmètre inconnu.

**Preuve actuelle.** NON MESURÉ — aucune mesure de la liste des formats de stockage employés parmi les 1115 modules cartographiés ni parmi les 210 modules exécutés en production ; aucun magasin d'embeddings identifié dans les FAITS MESURÉS.

**Contrôle futur.** Analyse statique des chemins déclarés comme registres scientifiques : contrôle de l'extension et du caractère textuel des fichiers ajoutés ou modifiés, et vérification qu'aucun code nouveau ne lit un objet de connaissance depuis une représentation vectorielle ou binaire sans passer par le fichier texte source.

#### `SSC-D7-05` — Graph Is Derived Index

| | |
|---|---|
| **Objet** | Base du Knowledge Graph et fichiers texte versionnés dont elle dérive |
| **État** | `DESIGNED` |
| **Portée du blocage** | merge |
| **Dépend de** | `Open Text Primary Representation` |

**Énoncé.** Le Knowledge Graph est un index entièrement dérivé : sa destruction complète suivie d'une reconstruction depuis les seuls fichiers versionnés redonne un graphe identique (mêmes nœuds, mêmes arêtes, même empreinte), et aucune connaissance n'existe uniquement dans la base de graphe.

**Justification de l'état.** Aucun graphe n'existe et son seuil d'activation déclaré (au moins 20 verdicts) n'est pas atteint : il n'y a ni base à détruire ni fichiers de relations à reconstruire.

**Preuve actuelle.** 0 verdict, 0 rejeu, 0 objet Calibration ; 2 ReplayEngine définis (audit/replay_engine.py:131, market_data/replay_engine.py:70) et AUCUN exécuté en production.

**Contrôle futur.** Vérification d'intégrité en intégration continue : reconstruction du graphe à partir d'un clone vierge du dépôt et comparaison d'empreinte avec le graphe en service ; toute divergence signale une connaissance résidant hors des fichiers versionnés.

#### `SSC-D7-06` — No Retroactive Edges

| | |
|---|---|
| **Objet** | Arêtes du Knowledge Graph reliant des objets créés avant l'activation du protocole |
| **État** | `DESIGNED` |
| **Portée du blocage** | commit |
| **Dépend de** | `Graph Is Derived Index` |

**Énoncé.** Toute arête porte un created_at postérieur à la borne d'activation déclarée du protocole et postérieur ou égal au created_at du plus récent des deux nœuds qu'elle relie ; aucune arête ne relie deux nœuds tous deux antérieurs à cette borne.

**Justification de l'état.** Le graphe et le champ created_at des arêtes n'existent pas ; aucune arête ne peut être inspectée aujourd'hui.

**Preuve actuelle.** N=139 trades de l'époque V4 et 0 verdict : aucun objet historique du système ne porte de relation enregistrée à sa création. 4 bornes CLEAN_DATA_SINCE en 6 semaines (v1 25/06, v2 09/07 01:16, v3 09/07 07:45, v4 17/07 01:30) sans artefact de comparabilité.

**Contrôle futur.** Comparaison d'horodatages : pour chaque arête, created_at de l'arête doit être postérieur à la borne d'activation du protocole et postérieur ou égal au created_at du nœud le plus récent qu'elle relie.

#### `SSC-D7-07` — Edges Never Deleted

| | |
|---|---|
| **Objet** | Fichiers de relations du Knowledge Graph (arêtes typées et dirigées) |
| **État** | `DESIGNED` |
| **Portée du blocage** | commit |
| **Dépend de** | `Graph Is Derived Index` |

**Énoncé.** Une arête n'est jamais supprimée : elle passe au statut INVALIDATED en conservant sa raison d'invalidation, son auteur et sa date ; le nombre d'arêtes déclarées ne décroît jamais entre deux révisions du dépôt.

**Justification de l'état.** Aucun fichier de relations n'existe : il n'y a pas d'historique d'arêtes sur lequel mesurer une suppression.

**Preuve actuelle.** 0 verdict, 0 objet Calibration, 0 publication : aucune arête n'a jamais été enregistrée dans le système.

**Contrôle futur.** Contrôle append-only sur l'historique git des fichiers de relations : toute ligne d'arête disparue ou modifiée autrement que par ajout d'un statut INVALIDATED et de ses métadonnées bloque.

#### `SSC-D7-08` — Acyclic Supersedes

| | |
|---|---|
| **Objet** | Sous-graphe SUPERSEDES (champs supersedes / superseded_by de tous les objets) |
| **État** | `DESIGNED` |
| **Portée du blocage** | commit |
| **Dépend de** | `Graph Is Derived Index` |

**Énoncé.** Le sous-graphe formé par les arêtes SUPERSEDES est acyclique et chaque objet possède au plus un successeur direct et au plus un prédécesseur direct.

**Justification de l'état.** Les champs supersedes et superseded_by n'existent sur aucun objet du système ; la chaîne de succession n'est matérialisée nulle part.

**Preuve actuelle.** 0 verdict, 0 publication, 0 objet Calibration. Chaîne de succession existante mais non matérialisée en objets : les 4 bornes CLEAN_DATA_SINCE (v1 → v2 → v3 → v4, canonique CLEAN_DATA_SINCE_V4 = 2026-07-17T01:30:00Z) ne sont décrites qu'en prose dans CLAUDE.md.

**Contrôle futur.** Requête de graphe : tri topologique du sous-graphe SUPERSEDES, plus contrôle de cardinalité (au plus un successeur et un prédécesseur par objet). Tout cycle ou toute bifurcation bloque.

#### `SSC-D7-09` — No AI Decision Authority

| | |
|---|---|
| **Objet** | Sites d'écriture de la décision d'exécution trade_allowed dans le runtime de production |
| **État** | `OBSERVED` |
| **Portée du blocage** | commit |

**Énoncé.** L'ensemble des sites de code capables d'écrire, de révoquer ou de forcer la décision d'exécution est exactement la liste enregistrée dans le contrat — les 5 sites d'écriture mesurés (core/advisor_loop.py:1983, :5626, :5658, :5734, :5808) plus le site de forçage d'entrées FORCE_TEST_EXECUTION (core/advisor_loop.py:1943-1980) — et aucun de ces sites n'appartient à un module d'IA générative, d'agent, de conseil ou de recommandation.

**Justification de l'état.** L'invariant est déjà satisfait aujourd'hui et le verrouiller est gratuit : les 5 sites d'écriture mesurés sont tous dans le module de décision, aucun agent d'IA n'écrit la décision. Conformément à la règle du cliquet, on verrouille maintenant plutôt qu'au moment où un conseil existera et où l'exception coûtera un arbitrage.

**Preuve actuelle.** 5 sites d'écriture mesurés : conjonction de 12 booléens à core/advisor_loop.py:1983, révocations à core/advisor_loop.py:5626 (risk_governor), :5658 (safety_auditor), :5734 et :5808 (decision_packet). Aucun n'est un module d'IA.

**Contrôle futur.** Analyse statique du point d'entrée runtime (core/advisor_loop.py) et des 210 modules exécutés : extraction de toutes les affectations de la variable de décision, comparaison avec la liste enregistrée, et rejet de tout site nouveau ou situé dans un module classé agent/IA.

#### `SSC-D7-10` — No Agent Write Identity In Production

| | |
|---|---|
| **Objet** | Identités, jetons et clés disposant d'un droit d'écriture sur la machine de production et sur la branche principale |
| **État** | `DESIGNED` |
| **Portée du blocage** | deploiement |
| **Dépend de** | `No AI Decision Authority` |

**Énoncé.** Aucune identité d'écriture sur la machine de production ni sur la branche principale du dépôt — compte système, clé SSH autorisée, jeton d'API, droit de fusion — n'est associée dans le registre des acteurs à un acteur de type agent.

**Justification de l'état.** Le contrôle est exécutable dès aujourd'hui (inventaire des clés et comptes de la machine de production, lecture des protections de branche), mais l'inventaire n'a jamais été produit ; tant que la mesure n'existe pas, le contrat ne peut rien bloquer sans risquer de bloquer à l'aveugle.

**Preuve actuelle.** NON MESURÉ — aucun inventaire des accès d'écriture de la production n'a été réalisé. Contexte mesuré : la production n'est PAS un dépôt git (.git absent), le code exécuté est le commit f427895 (2026-07-20) identifié par md5 normalisé, et le commit local 032d4ee (31/07) n'est pas déployé.

**Contrôle futur.** Vérification d'intégrité périodique : inventaire des comptes, clés autorisées et jetons sur la machine de production et des protections de branche du dépôt, croisé avec le registre des acteurs ; toute identité de type agent disposant d'un droit d'écriture est une violation.

#### `SSC-D7-11` — No Self Validation

| | |
|---|---|
| **Objet** | Chaîne Hypothesis → Critique → Réplication → Verdict et champs de provenance associés |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Role Impl Separation`, `Mandatory Provenance Block` |

**Énoncé.** Pour une hypothèse donnée, l'actor_impl qui a produit l'hypothèse ne peut être celui de la critique, ni celui de la réplication, ni celui qui émet le verdict ; aucun acteur ne figure des deux côtés de la séparation proposer/valider.

**Justification de l'état.** Ni les objets Contribution, Verdict et RunManifest, ni le registre d'acteurs n'existent : la comparaison de provenance ne porte sur rien.

**Preuve actuelle.** 0 verdict ; 1 seule hypothèse conclue (H3 rejetée le 31/07, Cohen's d=-0.097) sans acteur enregistré ; 2 ReplayEngine définis, AUCUN exécuté en production, donc zéro rejeu indépendant possible.

**Contrôle futur.** Requête de graphe comparant provenance.actor_impl de l'hypothèse, de la critique, de la réplication et du verdict ; toute intersection non vide invalide l'expérience avant son exécution.

#### `SSC-D7-12` — Blind Contribution

| | |
|---|---|
| **Objet** | Contributions d'un même tour de conseil (scellement et champ inputs) |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Mandatory Provenance Block` |

**Énoncé.** Chaque tour de conseil enregistre un événement de révélation horodaté ; le scellement horodaté de toute contribution du tour est antérieur à cet événement, et le champ inputs d'une contribution ne cite aucun identifiant de contribution du même tour.

**Justification de l'état.** Le conseil n'est pas activé, aucune contribution n'existe et le seuil d'activation déclaré n'est pas atteint ; il n'y a aucun tour à observer.

**Preuve actuelle.** 0 verdict, 0 rejeu opérationnel (2 ReplayEngine définis, aucun exécuté), aucune contribution enregistrée dans le système.

**Contrôle futur.** Comparaison d'horodatages entre le scellement de chaque contribution et l'ouverture du tour, plus contrôle référentiel que inputs ne cite aucun identifiant du même tour.

#### `SSC-D7-13` — Verified Citations

| | |
|---|---|
| **Objet** | Champs de référence des contributions et objets du graphe (evidence, inputs, supersedes, justification_verdict) |
| **État** | `DESIGNED` |
| **Portée du blocage** | commit |
| **Dépend de** | `Permanent Object Identifier`, `Mandatory Provenance Block` |

**Énoncé.** Toute référence portée par un objet pointe vers un identifiant existant dans les registres ; une seule référence vers un objet inexistant rend la contribution ou l'objet irrecevable.

**Justification de l'état.** Les registres et les champs de référence n'existent pas ; l'intégrité référentielle ne peut être évaluée sur aucun objet aujourd'hui. Le défaut homologue est en revanche déjà mesuré côté documentation (voir Cited Norm Exists).

**Preuve actuelle.** 0 verdict, 0 objet Calibration, 0 publication. Défaut homologue mesuré sur les citations de norme : ADR-0018 est cité comme source canonique par tools/score_calibration_audit.py:675 alors qu'il est ABSENT de docs/adr/ (séquence 0017 puis 0019).

**Contrôle futur.** Validation d'intégrité référentielle à l'insertion : chaque identifiant cité est résolu contre l'index des objets existants ; toute référence non résolue rejette l'objet entier, l'hallucination de référence étant traitée comme une erreur de schéma.

#### `SSC-D7-14` — Cited Norm Exists

| | |
|---|---|
| **Objet** | Références normatives ADR-XXXX citées par le code et la documentation du dépôt |
| **État** | `OBSERVED` |
| **Portée du blocage** | commit |

**Énoncé.** Tout identifiant ADR-nnnn cité comme source canonique dans un fichier de code ou de documentation du dépôt correspond à un fichier existant dans docs/adr/.

**Justification de l'état.** Le contrôle est exécutable immédiatement (extraction de motifs et comparaison à l'inventaire de docs/adr/) mais l'invariant est actuellement VIOLÉ ; la règle du cliquet interdit de promouvoir un article tant que la violation subsiste.

**Preuve actuelle.** ⚠ **À REVÉRIFIER** — ADR-0018 cité comme source canonique par tools/score_calibration_audit.py:675 et ABSENT de docs/adr/ (séquence 0017 puis 0019). Second défaut vérifié dans docs/adr/ : deux fichiers portent le numéro 0008.

**Contrôle futur.** Analyse statique : extraction des motifs ADR-nnnn dans l'ensemble des fichiers de code et de documentation, résolution contre l'inventaire de docs/adr/, plus contrôle d'unicité des numéros de fichiers.

#### `SSC-D7-15` — Mandatory Limitations Field

| | |
|---|---|
| **Objet** | Champ limitations des contributions, observations et verdicts |
| **État** | `DESIGNED` |
| **Portée du blocage** | commit |
| **Dépend de** | `Mandatory Provenance Block` |

**Énoncé.** Aucune hypothèse n'est recevable si son champ falsifier est absent, vide, égal à une valeur de la liste close des sentinelles, ou plus court que la longueur minimale déclarée ; la même règle de longueur minimale s'applique au champ limitations exigé par le bloc provenance.

**Justification de l'état.** Les objets porteurs de ce champ n'existent pas : 0 contribution, 0 verdict, 0 publication. Rien ne peut être validé aujourd'hui.

**Preuve actuelle.** 0 verdict, 0 publication, 1 hypothèse conclue (H3 rejetée le 31/07) hors de tout registre ; Evidence Score = 0.

**Contrôle futur.** Validation de schéma à l'insertion : champ présent, non vide, distinct d'une liste close de valeurs sentinelles, et de longueur minimale déclarée.

#### `SSC-D7-16` — Generated Bootstrap Docs

| | |
|---|---|
| **Objet** | Les six documents d'amorçage de knowledge/ (STATE_OF_KNOWLEDGE, OPEN_QUESTIONS, FORBIDDEN, EPOCHS, CURRENT_TRUTH, README_FOR_AGENTS) |
| **État** | `DESIGNED` |
| **Portée du blocage** | merge |
| **Dépend de** | `Mandatory Provenance Block` |

**Énoncé.** Les six documents d'amorçage de knowledge/ sont produits par des générateurs déterministes (sortie sans horodatage d'exécution ni ordre non stable) et leur régénération depuis l'état courant du dépôt reproduit à l'identique l'empreinte de la version versionnée ; toute divergence est rejetée.

**Justification de l'état.** Le répertoire knowledge/ n'existe pas dans le dépôt (vérifié) et les registres qui alimenteraient les générateurs n'existent pas non plus : aucun document à comparer, aucun générateur à exécuter.

**Preuve actuelle.** ⚠ **À REVÉRIFIER** — knowledge/ absent du dépôt (vérifié). Documentation actuelle rédigée à la main : 66 fichiers markdown à la racine, la plupart datés du 05/05 au 08/06/2026. 0 verdict et 0 publication à publier.

**Contrôle futur.** Test de non-régression en intégration continue : exécution des générateurs sur l'état courant du dépôt et comparaison d'empreinte avec les fichiers versionnés ; toute divergence bloque la fusion.

#### `SSC-D7-17` — Stale Doc Marking

| | |
|---|---|
| **Objet** | Fichiers markdown du dépôt décrivant l'état du système (racine et docs/) |
| **État** | `OBSERVED` |
| **Portée du blocage** | commit |
| **Dépend de** | `Generated Bootstrap Docs` |

**Énoncé.** Tout fichier markdown suivi par git et absent de la liste versionnée des références courantes, ou dont la date de dernière modification git est antérieure à la borne de fraîcheur déclarée dans un fichier versionné, porte en première ligne un bandeau de péremption daté renvoyant vers la référence en vigueur.

**Justification de l'état.** Le contrôle est exécutable dès aujourd'hui (dates de dernière modification git et présence d'un bandeau en tête de fichier) mais l'invariant est massivement violé ; il ne peut être promu tant que les documents concernés ne sont pas marqués ou déplacés.

**Preuve actuelle.** 66 fichiers markdown à la racine, la plupart datés du 05/05 au 08/06/2026, jamais marqués comme périmés ; ils ont déjà induit en erreur une analyse externe.

**Contrôle futur.** Comparaison d'horodatages entre la date de dernière modification enregistrée par git et la borne de fraîcheur, croisée avec la détection du bandeau de péremption en tête de fichier et avec la liste des références courantes.

#### `SSC-D7-18` — Amnesic Agent Test

| | |
|---|---|
| **Objet** | Manifeste de reprise : les six questions Q-A à Q-F et les pointeurs versionnés qui y répondent |
| **État** | `DESIGNED` |
| **Portée du blocage** | merge |
| **Dépend de** | `Generated Bootstrap Docs`, `Stale Doc Marking` |

**Énoncé.** Chacune des six questions de reprise (ce que le projet cherche à savoir, ce qui est démontré, ce qui est cru sans preuve, ce qui est inconnu, ce qui est indémontrable avec l'instrumentation actuelle, ce qu'il ne faut pas faire et pourquoi) est associée dans le manifeste à un pointeur résolvable vers un fichier versionné existant, non vide et régénéré depuis la dernière modification des registres.

**Justification de l'état.** Le contrôle mécanique (résolution des six pointeurs, existence, non-vacuité, fraîcheur) est exécutable aujourd'hui et son résultat serait immédiat : six pointeurs non résolus. Il ne bloque rien tant que les documents cibles n'existent pas.

**Preuve actuelle.** ⚠ **À REVÉRIFIER** — knowledge/ absent du dépôt (vérifié) : aucun des six documents d'amorçage n'existe. Faits corroborants : 0 verdict et Evidence Score = 0 (Q-B sans réponse) ; 66 markdown racine non marqués ayant déjà induit en erreur une analyse externe (Q-F noyée).

**Contrôle futur.** Validation de schéma du manifeste plus vérification d'intégrité : les six pointeurs doivent se résoudre vers des fichiers existants et non vides, et la comparaison d'horodatages doit montrer une régénération postérieure à la dernière écriture dans les registres.

### D8 — Intégrité de l'instrument de mesure (manques comblés)

#### `SSC-D8-01` — Executed Module Inventory Is A Versioned Artifact

| | |
|---|---|
| **Objet** | Inventaire des modules réellement exécutés en production (mesure .pyc) |
| **État** | `OBSERVED` |
| **Portée du blocage** | deploiement |
| **Dépend de** | `Production Code Fingerprint` |

**Énoncé.** L'inventaire des modules exécutés en production est un artefact versionné du dépôt, portant sa date de mesure, l'hôte mesuré et le commit exécuté, produit par une procédure rejouable. Tout contrôle du contrat dont le périmètre est « les modules exécutés en production » cite l'identifiant de cet artefact et échoue si l'artefact est absent ou antérieur au dernier déploiement. Aucun contrôle ne substitue une approximation statique à cet artefact.

**Justification de l'état.** Le contrôle (présence, datation, fraîcheur) est exécutable aujourd'hui et échoue immédiatement : la mesure des 210 modules existe, l'artefact versionné non.

**Preuve actuelle.** 210 modules exécutés mesurés sur 1115 ; borne statique 102-170 ; 52 modules classés ORPHAN/TEST_ONLY par le statique sont exécutés en prod. Rejouabilité de la mesure : NON MESURÉE.

**Contrôle futur.** Contrôle de présence et de fraîcheur de l'artefact ; contrôle de reproductibilité (seconde mesure sur le même hôte redonnant le même ensemble) ; analyse statique du contrat vérifiant que tout invariant à périmètre « modules exécutés » référence l'artefact.

#### `SSC-D8-02` — No Import Cycle In Decision Closure

| | |
|---|---|
| **Objet** | Graphe d'import des modules exécutés en production |
| **État** | `OBSERVED` |
| **Portée du blocage** | merge |
| **Dépend de** | `Executed Module Inventory Is A Versioned Artifact` |

**Énoncé.** La fermeture d'import du point d'entrée core/advisor_loop.py ne contient aucune composante fortement connexe de taille supérieure à un.

**Justification de l'état.** Détection exécutable aujourd'hui, et violée : l'un des 3 cycles mesurés relie core.decision_packet, module des révocations :5734 et :5808. Casser ce cycle exige une refonte non décidée.

**Preuve actuelle.** 3 cycles d'import mesurés, dont core.decision_packet <-> core.lifecycle ; core.decision_packet écrit le verdict à core/advisor_loop.py:5734 et :5808. Effet sur l'ordre d'initialisation : NON MESURÉ.

**Contrôle futur.** Extraction des composantes fortement connexes du graphe d'import, intersection avec la fermeture du point d'entrée. Cliquet complémentaire : le compte total de cycles ne peut dépasser 3.

#### `SSC-D8-03` — No sys.path Dependent Internal Import

| | |
|---|---|
| **Objet** | Clauses d'import des modules exécutés en production |
| **État** | `OBSERVED` |
| **Portée du blocage** | merge |
| **Dépend de** | `Executed Module Inventory Is A Versioned Artifact` |

**Énoncé.** Aucun module exécuté en production n'importe un autre module du dépôt par nom nu : toute importation interne est qualifiée par son paquet, de sorte que l'ensemble des modules chargés soit fonction du seul contenu des fichiers et non du répertoire de lancement.

**Justification de l'état.** Analyse statique exécutable aujourd'hui, violée par au moins une occurrence mesurée. Le nombre total d'occurrences n'est pas encore connu.

**Preuve actuelle.** core/advisor_loop.py:33 fait « from advisor_runtime_adapters import ... », nom nu résolu par sys.path. Nombre total d'occurrences dans les 210 modules exécutés : NON MESURÉ.

**Contrôle futur.** Analyse statique des clauses d'import des modules de l'inventaire d'exécution ; échec pour tout nom importé correspondant à un fichier du dépôt sans être qualifié par son paquet.

#### `SSC-D8-04` — Single Definition For Executed Record Types

| | |
|---|---|
| **Objet** | Types de données du chemin d'enregistrement (TradeRecord, Position, PortfolioSnapshot, MarketSnapshot, Alert, ValidationResult) |
| **État** | `OBSERVED` |
| **Portée du blocage** | merge |
| **Dépend de** | `Executed Module Inventory Is A Versioned Artifact` |

**Énoncé.** Aucun nom de la liste fermée et versionnée des types d'enregistrement n'est défini par deux modules simultanément exécutés en production ; tous les enregistrements d'une même époque partagent le même ensemble de champs.

**Justification de l'état.** Mesurable aujourd'hui et violé : 6 des 8 paires doublement exécutées sont des types d'enregistrement. La déduplication impose des renommages dans le chemin d'exécution.

**Preuve actuelle.** 8 paires dont les DEUX définitions sont exécutées en prod, dont TradeRecord, Position, PortfolioSnapshot, MarketSnapshot, Alert, ValidationResult ; 69 noms dupliqués hors tests. Laquelle des deux définitions de TradeRecord a écrit chacun des 139 trades V4 : NON MESURÉ.

**Contrôle futur.** Index des définitions croisé avec l'inventaire d'exécution ; échec si un nom de la liste fermée a plus d'une définition exécutée. Cliquet : le compte de noms dupliqués hors tests ne peut dépasser 69.

#### `SSC-D8-05` — Evaluation Horizon Covered By Realized Holding

| | |
|---|---|
| **Objet** | Horizon d'évaluation de la spec scellée et distribution de détention réalisée du corpus |
| **État** | `DESIGNED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Single Primary Metric`, `Frozen Corpus Content Hash` |

**Énoncé.** La spec scellée déclare, avant exécution, l'horizon d'évaluation et le critère de couverture par la distribution de détention réalisée du corpus. Tout verdict dont l'horizon d'évaluation ne satisfait pas le critère déclaré est INCONCLUSIVE et porte l'entrée de limitation « horizon d'information ».

**Justification de l'état.** Ni ExperimentSpec exécutable, ni Corpus, ni Verdict n'existent : les deux termes de la comparaison sont absents. Le fait mesuré montre que la propriété est aujourd'hui fausse, mais aucun objet ne permet de l'évaluer.

**Preuve actuelle.** Le score ne classe rien à <=1h et classe faiblement à 12-24h (rho=0.16, AUC=0.60) alors que la détention réalisée est de 5.92h ; N=139 époque V4, 0 verdict. Aucun artefact ne rapproche ces deux horizons.

**Contrôle futur.** Comparaison numérique, à l'agrégation du verdict, entre l'horizon déclaré dans la spec scellée et les quantiles de détention du corpus référencé ; dégradation automatique et journalisée en INCONCLUSIVE hors critère.

#### `SSC-D8-06` — Single Fingerprint Canonicalization Spec

| | |
|---|---|
| **Objet** | Règle de calcul d'empreinte utilisée par tous les contrôles de hachage |
| **État** | `OBSERVED` |
| **Portée du blocage** | commit |

**Énoncé.** Il existe une seule spécification versionnée de canonicalisation d'empreinte (encodage, fins de ligne, ordre de parcours, exclusions) ; tout contrôle du contrat qui hache un fichier ou un ensemble de fichiers la référence et n'en définit pas une autre.

**Justification de l'état.** Huit invariants du contrat hachent, aucun ne possède la règle. Mesurable immédiatement par lecture du contrat lui-même ; violé dès aujourd'hui.

**Preuve actuelle.** Le commit de production f427895 n'a pu être identifié que par md5 NORMALISÉ LF — l'identité octet à octet ne survit pas au chemin de déploiement (taille locale 345307 contre 342959 en production).

**Contrôle futur.** Analyse statique du registre d'invariants : tout contrôle de hachage référence l'identifiant de la spécification de canonicalisation ; échec sinon.

#### `SSC-D8-07` — Safe Mode Halt Proof

| | |
|---|---|
| **Objet** | Effet de SAFE_MODE sur l'ouverture de position |
| **État** | `OBSERVED` |
| **Portée du blocage** | experience |
| **Dépend de** | `Single Runtime State Machine` |

**Énoncé.** Lorsque SAFE_MODE est actif, aucune ouverture de position n'est émise : l'ensemble des verdicts d'exécution produits pendant une fenêtre SAFE_MODE est vide.

**Justification de l'état.** Un pendant existe pour le kill switch mais pas pour SAFE_MODE, alors que SAFE_MODE est écrit dans 18 fichiers de production dont 8 atteignables. L'effet réel n'a jamais été mesuré.

**Preuve actuelle.** SAFE_MODE présent dans 18 fichiers de production, 8 atteignables par le runtime ; 2 machines d'état simultanément exécutées en portent chacune une notion. Effet sur l'émission d'ordres : NON MESURÉ.

**Contrôle futur.** Vérification d'intégrité sur le journal de décisions : intersection entre les fenêtres SAFE_MODE et les verdicts d'ouverture émis ; échec si non vide.

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
