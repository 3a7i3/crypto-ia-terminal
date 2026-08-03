# RESEARCH_OS_ARCHITECTURE.md

> **Statut : conception. Aucun code, aucune implémentation.**
> Document normatif cible de la V5, en attente de validation opérateur.
>
> Chaque « état actuel » cité est **mesuré** (cartographie J1-J2,
> `artifacts/cartography.json`, `artifacts/prod_executed_modules.txt`).
> Tout le reste est **conception** et doit être lu comme tel.

---

## 1. Philosophie

### 1.1 La thèse

> Un système de trading cherche à avoir raison sur le marché.
> Un système de recherche cherche à **réduire son incertitude sur lui-même**.

Le premier optimise un P&L. Le second optimise un **taux de conversion de
l'observation en connaissance opposable**. Les deux sont compatibles, mais l'un
est subordonné à l'autre : on ne peut pas optimiser durablement ce qu'on n'a pas
d'abord su mesurer.

Ce projet a passé un an à construire le premier. La V5 construit le second, et
**le trading en devient la première application, pas la finalité**.

### 1.2 Le fait qui justifie ce renversement

Après douze mois : **Evidence Score = 0**. Une seule hypothèse conclue (H3,
rejetée le 2026-07-31, Cohen's d = −0,097). N = 139 trades en époque canonique
V4. Aucun moteur de rejeu exécuté en production (mesuré : zéro `.pyc` pour les
deux `ReplayEngine` définis).

Le goulot n'a jamais été la sophistication du moteur. Il a toujours été le
**débit de production de connaissance**. La V5 est une architecture conçue
autour de ce débit.

### 1.3 Les cinq axiomes

| # | Axiome | Conséquence architecturale |
|---|---|---|
| **A1** | Le runtime n'apprend pas. Il exécute une politique versionnée. | Aucune écriture de paramètre depuis le runtime |
| **A2** | Une IA n'est jamais une autorité. Elle produit des hypothèses datées et signées. | Aucun agent n'a de droit d'écriture sur une `Policy` |
| **A3** | La preuve expérimentale domine toute opinion, y compris la mienne. | Le rejeu est l'arbitre terminal, pas le consensus |
| **A4** | Une hypothèse non démontrée reste une hypothèse, indéfiniment. | Pas d'état « probablement vrai » dans le modèle de connaissance |
| **A5** | La connaissance survit aux modèles. | Tout artefact est lisible sans le modèle qui l'a produit |

**A5 est la contrainte de conception la plus forte.** Elle interdit tout format
propriétaire, tout embedding comme représentation primaire, toute connaissance
qui n'existerait que dans un poids de réseau ou un contexte de conversation.

### 1.4 Ce que l'architecture refuse explicitement

- **L'auto-optimisation en boucle fermée.** Aucun chemin ne va d'une mesure à un
  paramètre sans signature humaine. Ce n'est pas de la prudence : un système qui
  s'optimise sur ses propres métriques finit par optimiser la métrique.
- **L'autorité par réputation.** Aucune hypothèse n'est acceptée parce qu'elle
  vient du modèle le plus performant. Voir `AI_COUNCIL_SPEC.md §3`.
- **La croissance par accrétion.** Toute couche ajoutée doit éliminer plus de
  variables expérimentales qu'elle n'en crée (Scientific Debt Rule).

---

## 2. Les sept couches

```
┌─────────────────────────────────────────────────────────────────┐
│ L6  OPERATOR PLANE            signature humaine — seul écrivain │
└───────────────────────────┬─────────────────────────────────────┘
                            │ approbation
┌───────────────────────────▼─────────────────────────────────────┐
│ L5  GOVERNANCE PLANE      Policy, ADR, gates de promotion       │
└───────────────────────────┬─────────────────────────────────────┘
                            │ propositions + preuves
┌───────────────────────────▼─────────────────────────────────────┐
│ L4  INFERENCE PLANE       AI Council · Arbiter · Hypothèses     │
│                           (aucune autorité — produit des objets)│
└───────────────────────────┬─────────────────────────────────────┘
                            │ questions ← / verdicts →
┌───────────────────────────▼─────────────────────────────────────┐
│ L3  EVIDENCE PLANE        Experiment · Replay · Ablation ·      │
│                           Walk-forward · Stress · Verdicts      │
└───────────────────────────┬─────────────────────────────────────┘
                            │ lecture seule
┌───────────────────────────▼─────────────────────────────────────┐
│ L2  KNOWLEDGE PLANE       Knowledge Graph · Registres ·         │
│                           Provenance · Mémoire persistante      │
└───────────────────────────┬─────────────────────────────────────┘
                            │ dérivation
┌───────────────────────────▼─────────────────────────────────────┐
│ L1  LEDGER PLANE          Event Ledger append-only · Datasets   │
│                           certifiés · Époques                   │
└───────────────────────────┬─────────────────────────────────────┘
                            │ événements
┌───────────────────────────▼─────────────────────────────────────┐
│ L0  EXECUTION PLANE       Runtime déterministe                  │
│                           TradeAuthority · RuntimeState         │
│                           n'apprend jamais, n'écrit jamais L2+  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.1 Règle de flux — la contrainte structurante

> **L'information monte. L'autorité descend. Rien ne traverse.**

- Une couche ne lit que la couche **immédiatement inférieure**.
- Une couche n'écrit que dans **sa propre** couche.
- Le seul chemin descendant est `L6 → L5 → L0` : la signature humaine produit
  une `Policy` versionnée que le runtime consomme.
- **Aucun raccourci n'est permis**, notamment `L4 → L0` (une IA modifiant le
  runtime) et `L0 → L2` (le runtime écrivant sa propre connaissance).

Cette règle est vérifiable mécaniquement : le graphe d'import entre packages de
couche doit être acyclique et monotone. C'est un contrôle CI, pas une intention.

### 2.2 Pourquoi sept couches et pas deux

Le découpage « Trading Runtime / Research Runtime » est insuffisant parce qu'il
laisse implicite l'endroit où la connaissance est **stockée** (L2) et celui où
elle est **prouvée** (L3). Ce sont deux fonctions distinctes : un résultat
d'expérience n'est pas encore une connaissance tant qu'il n'a pas été relié,
versionné et rendu interrogeable.

L'échec mesuré du projet actuel se situe précisément à cette jointure : les
outils de mesure (`tools/`, 22 modules) produisent des résultats que rien ne
transforme en connaissance opposable.

---

## 3. Contrats entre couches

Un contrat définit : la direction, le type d'objet transporté, le mode d'accès
et l'invariant qui ne peut être violé.

### C-01 · L0 → L1 — Émission d'événements

| | |
|---|---|
| **Direction** | montante, unidirectionnelle |
| **Objet** | `Event` (voir `KNOWLEDGE_MODEL.md`) |
| **Mode** | append-only, jamais de mise à jour ni de suppression |
| **Invariant** | Tout événement porte `trace_id`, `policy_version`, `epoch_id`, `schema_version` et un horodatage monotone |

**Rationale mesurée.** L'absence de `policy_version` sur les trades actuels est
la cause directe de la contamination ayant coûté l'époque v2 : un trade produit
sous `FORCE_TEST_EXECUTION` est aujourd'hui indiscernable d'un trade nominal
dans `paper_trades.jsonl`.

### C-02 · L1 → L2 — Dérivation de connaissance

| | |
|---|---|
| **Direction** | montante |
| **Objet** | `Dataset` certifié, `Observation` |
| **Mode** | lecture seule sur L1 ; L2 ne modifie jamais le ledger |
| **Invariant** | Tout `Dataset` porte le hash de contenu de son extrait et la borne d'époque appliquée. Deux dérivations du même hash produisent le même dataset |

### C-03 · L2 → L3 — Fourniture de corpus

| | |
|---|---|
| **Objet** | `Corpus` (dataset figé + manifeste) |
| **Mode** | lecture seule, immuable |
| **Invariant** | Un `Corpus` référencé par une expérience ne peut jamais changer. S'il doit évoluer, il devient un nouveau `Corpus` avec une nouvelle identité |

### C-04 · L3 → L2 — Dépôt de verdict

| | |
|---|---|
| **Objet** | `Verdict` (`PASS` / `FAIL` / `INCONCLUSIVE`) + `RunManifest` |
| **Mode** | append-only |
| **Invariant** | Un verdict est immuable. Il n'est jamais corrigé, seulement **remplacé** par un verdict ultérieur qui le référence explicitement |

### C-05 · L2 → L4 — Lecture de l'état de connaissance

| | |
|---|---|
| **Objet** | sous-graphe du Knowledge Graph |
| **Mode** | **lecture seule stricte** |
| **Invariant** | Aucun agent de L4 n'a de droit d'écriture sur L2. Ce que produit une IA entre par C-06, jamais directement |

### C-06 · L4 → L3 — Soumission d'hypothèse

| | |
|---|---|
| **Objet** | `Hypothesis` + `ExperimentSpec` **pré-enregistrée** |
| **Mode** | append-only dans un registre de propositions |
| **Invariant** | La prédiction est déposée **avant** l'exécution de l'expérience. Une spec dont le `submitted_at` est postérieur au `run_started_at` est rejetée automatiquement |

**Rationale.** C'est l'unique protection contre le p-hacking, et elle devient
indispensable dès lors qu'un agent génère les hypothèses en volume.

### C-07 · L4 → L5 — Proposition de changement

| | |
|---|---|
| **Objet** | `Proposal` = diff de `Policy` + verdict + preuve de rejeu |
| **Mode** | pull request |
| **Invariant** | Une `Proposal` sans verdict `PASS` attaché, sans preuve de rejeu déterministe, ou sans N suffisant, est refusée par le CI **avant** toute revue humaine |

### C-08 · L5 → L6 — Demande de signature

| | |
|---|---|
| **Objet** | `Proposal` recevable |
| **Invariant** | L6 est le **seul** écrivain effectif. Aucun automatisme ne fusionne |

### C-09 · L6 → L0 — Application

| | |
|---|---|
| **Objet** | `Policy` signée et versionnée |
| **Mode** | descendant, unique chemin d'écriture vers le runtime |
| **Invariant** | Le runtime refuse de démarrer sur une `Policy` non signée. Toute application ouvre une **nouvelle époque** déclarée |

### C-10 · L3 → L0 — Réutilisation de l'autorité de décision

| | |
|---|---|
| **Objet** | appel à `TradeAuthority` |
| **Invariant** | **Le rejeu appelle exactement la même `TradeAuthority` que la production.** Aucune réimplémentation de la logique de décision à des fins de test |

**C-10 est le contrat le plus important du document.** Sans lui, un résultat de
rejeu ne prouve rien sur la production. C'est aussi ce qui rend `TradeAuthority`
nécessairement pure : elle doit être appelable sans réseau, sans horloge et sans
état mutable.

---

## 4. Responsabilités par couche

### L0 — Execution Plane

**Responsable de** : appliquer une `Policy` à un `MarketState` et produire un
`TradeVerdict` ; émettre des événements ; maintenir `RuntimeState`.

**Interdit de** : apprendre ; écrire un paramètre ; lire L2 ou au-dessus ;
contenir une branche conditionnée par une variable d'environnement qui
désarmerait une couche de décision.

**État actuel mesuré** : 5 sites d'écriture de la décision, 2 machines d'état
simultanément chargées, 2 kill switches chargés, `FORCE_TEST_EXECUTION`
présent dans le chemin de production. **Aucune de ces propriétés n'est
conforme.** Cible détaillée dans `CANONICAL_RUNTIME_SPEC.md`.

### L1 — Ledger Plane

**Responsable de** : l'immuabilité, l'ordre, la complétude, la déclaration des
époques, la certification des datasets.

**Interdit de** : interpréter. Le ledger n'a pas d'opinion sur ce qu'il stocke.

**Propriété clé — le ledger est la seule chose qu'on ne peut pas reconstruire.**
Tout le reste (connaissance, verdicts, graphe) est dérivable et donc
reconstructible. C'est ce qui fixe la priorité de sauvegarde et de réplication.

### L2 — Knowledge Plane

**Responsable de** : la représentation des objets scientifiques, leurs
relations, leur provenance, leur versionnement ; et de la capacité du système à
**se décrire lui-même** sans mémoire externe.

**Interdit de** : produire une conclusion. L2 stocke et relie ; il ne conclut pas.

### L3 — Evidence Plane

**Responsable de** : exécuter des protocoles, rejouer, ablater, valider hors
échantillon, stresser, et émettre des verdicts.

**Interdit de** : formuler l'hypothèse qu'il teste. **La séparation
proposer/valider est structurelle** : celui qui teste ne peut pas être celui qui
a proposé.

### L4 — Inference Plane

**Responsable de** : lire l'état de connaissance, formuler des hypothèses
falsifiables, proposer des protocoles, critiquer.

**Interdit de** : valider sa propre hypothèse ; écrire dans L2 ; toucher L0.
**Une IA de L4 peut se tromper sans conséquence** — c'est une propriété
recherchée, pas tolérée.

### L5 — Governance Plane

**Responsable de** : les `Policy`, les ADR, les gates de promotion, les
contrôles CI qui rendent les invariants exécutables.

**Interdit de** : approuver. La gouvernance **filtre**, elle ne signe pas.

### L6 — Operator Plane

**Responsable de** : signer. Unique autorité d'écriture effective sur le vivant.

**Propriété** : L6 doit rester **capable de refuser sans expliquer**. Un
opérateur contraint de justifier chaque refus devant un système automatisé
n'est plus une autorité.

---

## 5. Invariants globaux

Chaque invariant est formulé pour être **vérifiable mécaniquement**. Un
invariant non testable est une intention, pas un invariant.

| ID | Invariant | Contrôle |
|---|---|---|
| **INV-G01** | Le graphe d'import inter-couches est acyclique et monotone (Ln n'importe que L(n−1)) | analyse statique, bloquante au merge |
| **INV-G02** | Aucun agent de L4 ne dispose d'un droit d'écriture sur L0, L1, L2, L5 | inspection des permissions, bloquante |
| **INV-G03** | Tout objet scientifique porte `id`, `version`, `provenance`, `schema_version` | validation de schéma à l'écriture |
| **INV-G04** | Tout `Verdict` référence un `RunManifest` reproductible | CI |
| **INV-G05** | Le rejeu est bit-à-bit déterministe sur corpus figé | test de non-régression bloquant |
| **INV-G06** | Le rejeu et la production appellent la même `TradeAuthority` | test d'identité de symbole |
| **INV-G07** | Une `ExperimentSpec` est déposée avant le premier run | comparaison d'horodatages |
| **INV-G08** | Aucune fusion de `Policy` sans signature humaine | protection de branche |
| **INV-G09** | Tout événement porte son `policy_version` et son `epoch_id` | validation de schéma |
| **INV-G10** | Aucune variable d'environnement ne désarme une couche de décision | analyse statique |
| **INV-G11** | Tout artefact de connaissance est lisible sans le modèle qui l'a produit | audit de format : texte/JSON, jamais d'embedding comme représentation primaire |
| **INV-G12** | Le solde en variables expérimentales de tout changement est ≤ 0 | revue, déclaré dans l'ADR |
| **INV-G13** | Aucune couche n'est construite avant que le volume d'objets la justifie | gate de capacité, §6 |

---

## 6. Gate de capacité — la protection contre la sur-ingénierie

**Le risque principal de cette architecture est de la construire trop tôt.**

État mesuré : **1 hypothèse conclue, 1 fichier d'expérience, 0 verdict, 0 rejeu**.
Un Knowledge Graph sur un corpus d'un nœud est une ligne de texte avec une
base de données autour. Un AI Council produisant des hypothèses qu'aucun moteur
de rejeu ne peut trancher est un générateur d'opinions non falsifiables — c'est-
à-dire exactement ce que l'architecture prétend éliminer.

**Règle.** Chaque couche a un seuil d'activation mesurable. Tant que le seuil
n'est pas franchi, la couche reste une spécification.

| Couche | Seuil d'activation | État mesuré |
|---|---|---|
| L0 canonique | 1 autorité de décision, 1 machine d'état | **non atteint** (5 sites, 2 machines) |
| L1 ledger | événements schématisés avec `policy_version` | non atteint |
| L3 replay | rejeu déterministe vérifié sur corpus figé | **non atteint** |
| L3 ablation | replay opérationnel | bloqué par le précédent |
| L2 knowledge graph | **≥ 20 verdicts** déposés | **0** |
| L4 AI council | **≥ 20 verdicts** + arbitre opérationnel | **0** |
| L2 mémoire persistante | ≥ 10 hypothèses conclues | **1** |

**INV-G13 interdit d'anticiper.** Construire L4 avant L3 reproduirait, à un
niveau plus abstrait, l'erreur exacte des douze derniers mois : un appareil
sophistiqué autour d'un objet non validé.

---

## 7. Ce que cette architecture ne résout pas

Honnêteté de conception — trois limites structurelles.

**7.1 Elle ne crée pas d'alpha.** Aucune de ces sept couches ne produit un signal
prédictif. Elle accélère la *falsification*, pas la découverte. Si aucun edge
n'existe au-delà du plancher de friction mesuré (0,194 %), cette architecture le
démontrera plus vite et plus proprement — elle ne le fabriquera pas.

**7.2 Elle ne protège pas contre une mauvaise question.** Le pré-enregistrement
protège du p-hacking, pas d'un programme de recherche mal orienté. Le résultat
le plus actionnable mesuré à ce jour — le score classe à 12-24 h alors que la
détention est de 5,92 h — a été trouvé en changeant de question, pas en
appliquant un protocole.

**7.3 Elle dépend d'un simulateur dont la fidélité est NON MESURÉE.** Le rejeu
n'est un arbitre valable que si la simulation d'exécution est fidèle. Aucune
mesure d'écart entre fills simulés et fills réels n'existe aujourd'hui. **Tant
que cet écart n'est pas quantifié, tout verdict de rejeu porte une incertitude
non bornée.** C'est la dépendance la plus sous-estimée de tout l'édifice, et
elle conditionne L3 entière.

---

## 8. Vue d'ensemble des documents V5

| Document | Objet |
|---|---|
| `RESEARCH_OS_ARCHITECTURE.md` | ce document — couches, contrats, invariants |
| `SCIENTIFIC_PROTOCOL.md` | les 13 étapes, entrées/sorties/artefacts/critères |
| `KNOWLEDGE_MODEL.md` | les objets scientifiques, cycles de vie, relations |
| `AI_COUNCIL_SPEC.md` | rôles fonctionnels des agents, sans autorité |
| `SCIENTIFIC_ARBITER.md` | comparaison d'hypothèses, consensus, conflits, lacunes |
| `KNOWLEDGE_GRAPH_SPEC.md` | schéma du graphe et requêtes de gouvernance |
| `PERSISTENT_MEMORY_SPEC.md` | reprise du projet sans historique de conversation |
| `RESEARCH_ROADMAP_2026_2031.md` | phases, dépendances, risques, critères |
