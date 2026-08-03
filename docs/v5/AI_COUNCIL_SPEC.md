# AI_COUNCIL_SPEC.md

> **Statut : conception.** Seuil d'activation **non atteint** — voir §8.
> Aucun agent n'est déployé, et aucun ne doit l'être avant le rejeu.

---

## 1. Position du problème

Le cahier des charges attribue à chaque fournisseur un domaine exclusif :
Claude → architecture, GPT → statistiques, Gemini → macro, DeepSeek →
génération d'algorithmes, Qwen → optimisation, Mistral → anomalies.

**Je recommande de ne pas retenir cette structure, pour trois raisons.**

### 1.1 Un domaine exclusif *est* une autorité

Si une seule IA traite les statistiques, son verdict statistique est
irréfutable *à l'intérieur du conseil* — personne d'autre n'est habilité à le
contester. C'est la définition d'une autorité, et cela contredit directement
l'axiome A2 du projet.

### 1.2 L'attribution repose sur une réputation, pas sur une mesure

Aucune donnée du projet n'établit qu'un modèle donné est supérieur sur un
domaine donné **pour les questions de ce projet**. C'est exactement le mode de
raisonnement que le projet a passé un an à combattre : décider sur une
impression plutôt que sur une mesure.

### 1.3 Le couplage à des noms commerciaux viole l'axiome A5

« Si Claude disparaît demain, le projet ne doit rien perdre. » Une architecture
où `Claude = architecture` perd sa couche architecture le jour où le fournisseur
change. L'objectif déclaré et la structure proposée sont incompatibles.

### 1.4 Contre-proposition

> **Les rôles sont fonctionnels et stables. Les modèles sont interchangeables
> à l'intérieur d'un rôle. La compétence par domaine est *mesurée*, jamais
> supposée.**

C'est la traduction directe de la distinction `actor_id` / `actor_impl` du
`KNOWLEDGE_MODEL.md §2`.

---

## 2. Les six rôles fonctionnels

Chaque rôle est un **poste**. Un modèle l'occupe pour une période donnée, et
peut être remplacé sans perte de connaissance ni rupture de comparabilité.

| Rôle | `actor_id` | Produit | Ne produit jamais |
|---|---|---|---|
| **Observateur** | `council.observer` | `Observation` — descriptif seul | aucune causalité |
| **Questionneur** | `council.questioner` | `Question` à partir de lacunes du graphe | aucune réponse |
| **Proposeur** | `council.proposer` | `Hypothesis` + `ExperimentSpec` | ne valide jamais sa propre hypothèse |
| **Critique** | `council.critic` | réfutations, biais, confusions, lookahead | ne propose pas d'alternative |
| **Répliquateur** | `council.replicator` | reproduction indépendante d'un résultat | n'interprète pas |
| **Archiviste** | `council.archivist` | cohérence du graphe, contradictions, dettes | ne conclut pas |

### 2.1 Règles de composition

| # | Règle |
|---|---|
| **R1** | Un même `actor_impl` ne peut pas occuper simultanément **Proposeur** et **Critique** sur la même hypothèse |
| **R2** | Le **Répliquateur** d'une expérience utilise un `actor_impl` différent de son Proposeur |
| **R3** | Un rôle peut être occupé par un humain. Rien n'est réservé aux modèles |
| **R4** | Un rôle peut rester vacant. Un conseil incomplet est préférable à un rôle mal tenu |
| **R5** | Le passage d'un `actor_impl` à un autre est un événement journalisé, avec date et raison |

**R1 et R2 sont la traduction opérationnelle de la séparation
proposer/valider.** Elles sont vérifiables mécaniquement sur les champs de
provenance.

---

## 3. Ce que produit un agent

Format unique, quel que soit le rôle et le modèle.

```
contribution:
  id, role, actor_impl, actor_version, created_at
  type: observation | question | hypothesis | critique | replication | audit
  content: <objet conforme au KNOWLEDGE_MODEL>
  confidence: 0..1
  confidence_basis: enum(
      "verdict_existant",     # s'appuie sur une preuve du graphe
      "raisonnement",         # déduction non testée
      "analogie",             # ressemblance avec un cas connu
      "intuition_du_modele"   # aucune base traçable
  )
  evidence: [ids d'objets du graphe]   # peut être vide
  limitations: texte                    # OBLIGATOIRE, jamais vide
  falsifier: "ce qui me contredirait"   # OBLIGATOIRE pour une hypothèse
```

### 3.1 Le champ `confidence_basis` est le plus important

Une confiance de 0,9 fondée sur `intuition_du_modele` et une confiance de 0,6
fondée sur `verdict_existant` ne sont pas comparables. **Sans ce champ, le
nombre de confiance est décoratif et dangereux** — il donne l'apparence de la
rigueur à une opinion.

### 3.2 Règles de recevabilité

| # | Règle |
|---|---|
| **P1** | `limitations` vide → contribution rejetée automatiquement |
| **P2** | Hypothèse sans `falsifier` → rejetée |
| **P3** | `confidence_basis = intuition_du_modele` → recevable, mais **ne peut jamais fonder à elle seule une `ExperimentSpec` prioritaire** |
| **P4** | Toute citation d'un objet du graphe est vérifiée : un `evidence` pointant vers un objet inexistant invalide la contribution |

**P4 traite l'hallucination comme une erreur de schéma, pas comme un problème de
modèle.** C'est mécanique, donc fiable, donc indépendant du modèle.

---

## 4. Ce qu'un agent ne peut jamais faire

| Interdiction | Application technique |
|---|---|
| Modifier le runtime (L0) | aucun droit d'écriture ; INV-G02 |
| Écrire dans le Knowledge Graph (L2) | lecture seule ; les contributions entrent par C-06 |
| Signer une `Policy` | signature réservée à L6 |
| Fusionner une pull request | protection de branche |
| Valider sa propre hypothèse | R1, vérifié sur la provenance |
| Choisir seul la priorité de recherche | la priorisation est humaine |
| Déclarer une hypothèse « vraie » | seuls `SUPPORTED` / `REFUTED` / `INCONCLUSIVE` existent |

**Une IA qui se trompe dans ce système ne coûte rien.** C'est la propriété
recherchée : elle rend acceptable l'emploi de modèles faillibles, et rend inutile
la course au « meilleur » modèle.

---

## 5. Mesure de la compétence — remplacer la réputation par des données

Le système enregistre par `actor_id` **et** par `actor_impl` :

| Métrique | Définition |
|---|---|
| `hypotheses_submitted` | volume |
| `validation_rate` | part de `PASS` parmi les hypothèses testées |
| `refutation_rate` | part de `REFUTED` |
| `inconclusive_rate` | part d'hypothèses mal dimensionnées (mauvais N/MDE) |
| `calibration_error` | écart entre `confidence` déclarée et fréquence observée de `PASS` |
| `critique_hit_rate` | part des critiques ultérieurement confirmées |
| `citation_integrity` | part de contributions sans violation P4 |

### 5.1 `calibration_error` est la métrique reine

Un modèle qui annonce 0,9 et a raison 9 fois sur 10 est utilisable. Un modèle
qui annonce 0,9 et a raison 5 fois sur 10 est **inutilisable même s'il a de
bonnes idées**, parce que sa confiance ne peut pas être intégrée à une décision.

### 5.2 Usage autorisé de ces métriques

Elles servent à **affecter les rôles** et à pondérer la priorisation. Elles ne
servent **jamais** à valider une hypothèse : un modèle bien calibré peut se
tromper, et le rejeu reste l'arbitre terminal (axiome A3).

### 5.3 Comparabilité dans le temps
Les métriques sont attachées au rôle autant qu'à l'implémentation. Le
remplacement d'un modèle n'efface pas l'historique du poste — condition de la
survie de la connaissance aux modèles.

---

## 6. Domaines — mesurés, jamais assignés

Un domaine (`microstructure`, `régime`, `exécution`, `statistiques`,
`architecture`, `macro`) est une **étiquette d'hypothèse**, pas une attribution
de fournisseur.

**Tout rôle peut travailler sur tout domaine.** Après un volume suffisant, les
métriques du §5 révèlent — ou ne révèlent pas — un avantage par
`actor_impl × domaine`. Cet avantage devient alors une **observation**, entre
dans le graphe, et peut orienter l'affectation.

> Autrement dit : la répartition des domaines du cahier des charges devient une
> **hypothèse à tester**, `HYP-XXXX : « le modèle M est supérieur sur le domaine
> D pour les questions de ce projet »`, plutôt qu'un postulat de conception.

C'est la seule formulation compatible avec la philosophie du projet.

---

## 7. Protocole de session

```
1. Cadrage       — l'humain fixe la question ou le domaine
2. Lecture       — chaque agent lit le sous-graphe pertinent (lecture seule)
3. Contribution  — production indépendante, SANS voir les autres
4. Dépôt         — contributions scellées et horodatées
5. Arbitrage     — SCIENTIFIC_ARBITER.md
6. Priorisation  — humaine
7. Pré-enreg.    — la spec retenue est scellée avant tout run
8. Exécution     — L3, sans aucun agent dans la boucle
9. Verdict       — indépendant des agents
10. Mise à jour  — le graphe intègre verdict et métriques d'agents
```

**L'étape 3 exige l'indépendance.** Des agents qui se lisent convergent, et une
convergence obtenue par contagion n'est pas un consensus — c'est un artefact de
protocole. Les contributions sont produites en aveugle, puis comparées.

---

## 8. Seuil d'activation — pourquoi le conseil n'est pas construit maintenant

| Prérequis | État mesuré |
|---|---|
| Rejeu déterministe opérationnel | **absent** — 2 `ReplayEngine` définis, 0 exécuté |
| ≥ 20 verdicts déposés | **0** |
| Arbitre opérationnel | absent |
| Knowledge Graph interrogeable | absent |

> **Un conseil d'IA sans arbitre expérimental est un parlement sans
> constitution.** Il produirait des hypothèses en volume, qu'aucun mécanisme ne
> pourrait trancher — c'est-à-dire des opinions, en quantité, avec l'apparence
> de la rigueur.

Cela s'est déjà produit à l'échelle 3 : trois analyses indépendantes de ce
projet ont produit trois conclusions partiellement incompatibles, et il a fallu
**mesurer le code** pour arbitrer. Le facteur limitant n'était pas le nombre
d'analystes, c'était l'absence d'arbitre.

**Le conseil s'active après la phase 4 de la roadmap, jamais avant.**

---

## 9. Risques propres au conseil

| Risque | Mitigation |
|---|---|
| **Volume sans valeur** — les agents produisent plus d'hypothèses qu'on n'en peut tester | quota d'hypothèses par période, indexé sur la capacité de rejeu |
| **Convergence artificielle** — les modèles partagent des biais d'entraînement | contributions en aveugle (§7.3) ; R2 impose des implémentations différentes |
| **Sur-confiance systématique** | `calibration_error` suivi et publié ; un rôle mal calibré est suspendu |
| **Hallucination de références** | P4, vérification mécanique des citations |
| **Dérive du corpus** — les agents optimisent sur les données vues | `usage_count` du corpus ; réserve jamais touchée |
| **Capture par le modèle dominant** | R1, R2, et interdiction des domaines exclusifs (§6) |
| **Coût** | le conseil est cadencé par la capacité de rejeu, pas par la disponibilité des modèles |
