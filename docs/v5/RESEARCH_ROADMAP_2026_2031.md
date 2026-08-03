# RESEARCH_ROADMAP_2026_2031.md

> **Statut : conception.** Aucune phase n'est engagée.

---

## 0. Avertissement sur l'horizon

Une feuille de route à cinq ans dans un domaine où les modèles changent tous les
six mois est **partiellement une fiction**. Je l'écris quand même, avec une
règle explicite de densité décroissante :

| Horizon | Nature | Fiabilité |
|---|---|---|
| **Phases 1-3** (0-9 mois) | plan engageable, critères binaires | élevée |
| **Phases 4-6** (9-24 mois) | direction avec critères, calendrier indicatif | moyenne |
| **Phases 7-8** (2-5 ans) | intention, **pas un plan** | faible — à réécrire |

**Une roadmap qui prétend à la même précision à 5 ans qu'à 3 mois est une
roadmap qui ment.** Les phases 7-8 sont formulées pour orienter les décisions
d'aujourd'hui, pas pour être exécutées telles quelles.

### Règle de séquencement
Chaque phase a un **critère de sortie binaire**. Une phase non sortie n'autorise
pas la suivante. Le gate de capacité (INV-G13) prime sur le calendrier : **une
couche dont le seuil d'activation n'est pas atteint reste une spécification**,
quel que soit le temps écoulé.

---

## Phase 1 — Canonical Runtime
**0-3 mois · fondation**

### Objectifs
Une seule autorité de décision, un seul site d'écriture, une seule machine
d'état, un seul kill switch, une fonction `decide()` pure.

### État de départ mesuré
5 sites d'écriture de `trade_allowed` · 2 machines d'état simultanément
chargées · 2 kill switches chargés · 12 vétos conjonctifs · `FORCE_TEST_EXECUTION`
dans le chemin de production · god object de 7 815 lignes.

### Dépendances
Aucune. **C'est la seule phase exécutable immédiatement.**

### Risques
| Risque | Mitigation |
|---|---|
| Régression comportementale pendant l'extraction | égalité stricte des sorties sur corpus de 30 jours avant/après |
| Découverte de couplages cachés | la trace d'exécution (210 modules) borne la surface |
| Tentation de « corriger en passant » | interdiction absolue de changer le comportement dans cette phase |

### Critères de réussite
- [ ] Exactement 1 site d'écriture de la décision dans tout le dépôt
- [ ] 1 machine d'état atteignable depuis le point d'entrée
- [ ] 1 classe de kill switch, sans aliasing de nom
- [ ] `decide(market_state, config, policy)` pure : aucune E/S, aucune horloge
- [ ] `FORCE_TEST_EXECUTION` retiré du chemin de production
- [ ] **Comportement strictement inchangé**, prouvé par égalité sur corpus

### Critère de passage
Le comportement du runtime est **identique** à celui d'aujourd'hui, avec une
architecture d'autorité unique. Toute divergence est un échec de phase.

---

## Phase 2 — Ledger & Protocole
**2-5 mois · en recouvrement partiel avec la phase 1**

### Objectifs
Ledger d'événements schématisé ; tout événement porte `policy_version`,
`epoch_id`, `trace_id` ; format d'`ExperimentSpec` et de `Verdict` ; documents
d'amorçage générés.

### Dépendances
`policy_version` exige la `Policy` de la phase 1.

### Risques
| Risque | Mitigation |
|---|---|
| Le protocole devient bureaucratique et personne ne l'utilise | valider sur **une** expérience réelle complète avant de le figer |
| Le ledger duplique l'existant sans le remplacer | migration explicite, ancien format déclaré `RETIRED` |

### Critères de réussite
- [ ] 100 % des événements portent `policy_version` et `epoch_id`
- [ ] `spec.yaml` et `verdict.json` schématisés et validés en CI
- [ ] `knowledge/` généré, test de l'agent amnésique passé sur Q-A, Q-F
- [ ] 66 markdown racine déplacés vers `docs/_historique/` avec en-tête de péremption

### Critère de passage
Un trade émis est traçable jusqu'à la version de politique qui l'a produit.

---

## Phase 3 — Replay Engine
**4-8 mois · LE PIVOT**

### Objectifs
Rejeu déterministe bit-à-bit ; corpus figés et versionnés ; identité stricte
entre l'autorité de décision du rejeu et celle de la production.

### Dépendances
Phase 1 (fonction pure) et phase 2 (corpus schématisés). **Bloquante pour tout
le reste.**

### Risques
| Risque | Mitigation |
|---|---|
| Non-déterminisme résiduel (dict, threads, horloge) | test de non-régression bloquant dès le premier jour |
| **Fidélité du simulateur non mesurée** | quantifier l'écart fills simulés / réels **dans cette phase**, pas après |
| Le rejeu diverge de la production | INV-G06 : test d'identité de symbole, pas de réimplémentation |

> **Le risque « fidélité du simulateur » est le plus sous-estimé de toute la
> roadmap.** Un rejeu déterministe sur un simulateur infidèle produit des
> verdicts précis et faux. Cette mesure conditionne la valeur de tout ce qui
> suit et doit être un critère de sortie, pas une amélioration ultérieure.

### Critères de réussite
- [ ] Même corpus + même policy + même seed → sorties identiques octet pour octet
- [ ] Test de déterminisme bloquant au merge
- [ ] Rejeu et production partagent le même symbole `TradeAuthority`
- [ ] **Écart fills simulés / fills réels quantifié et publié**

### Critère de passage
Une hypothèse peut être testée **sans attendre le marché**. Le débit de recherche
cesse d'être plafonné par le débit de trades (~2,4/jour mesuré).

---

## Phase 4 — Evidence Engine
**7-12 mois**

### Objectifs
Ablation, walk-forward, stress ; émission de verdicts signés ; **premier
remboursement de la dette d'attribution**.

### Dépendances
Phase 3.

### Livrable central
> **L'effet marginal de chacune des 12 couches de décision sur le débit, le PF,
> le WR et le regret, mesuré par ablation sur corpus figé.**

C'est le livrable le plus important des cinq ans. Il rend enfin décidable la
question « quelles couches méritent d'exister », indécidable aujourd'hui par
construction (conjonction de 12 termes → attribution non estimable sans
intervention).

### Risques
| Risque | Mitigation |
|---|---|
| Sur-apprentissage du corpus | `usage_count`, réserve de données jamais touchée |
| Verdicts fondés sur un N insuffisant | `INCONCLUSIVE` par défaut ; N minimal déclaré avant run |
| Résultat politiquement inconfortable (des couches inutiles) | le verdict est publié quel qu'il soit |

### Critères de réussite
- [ ] ≥ 20 verdicts déposés, dont `FAIL` et `INCONCLUSIVE` publiés
- [ ] Effet marginal chiffré pour les 12 couches
- [ ] Aucune PR de `Policy` mergeable sans verdict + preuve de rejeu

### Critère de passage
Le nombre de `VETO_DUR` peut être réduit **sur preuve**, non sur opinion. C'est
la sortie du deadlock épistémique identifié au diagnostic initial.

---

## Phase 5 — Knowledge Graph
**11-18 mois**

### Objectifs
Index dérivé, requêtes de gouvernance Q1-Q8 opérationnelles.

### Dépendances
**≥ 20 verdicts** (sortie de phase 4). Le seuil est un gate dur, pas un
calendrier.

### Risques
| Risque | Mitigation |
|---|---|
| Construire trop tôt un index vide | INV-G13 |
| Tentation de reconstruire l'historique | **interdit** — produirait de la fausse provenance (KG §7.3) |
| Le graphe devient la source au lieu de l'index | les fichiers versionnés restent la vérité |

### Critères de réussite
- [ ] Q1 (hypothèses réfutées encore utilisées) répond sur données réelles
- [ ] Q7 (intégrité de la chaîne de preuve) retourne vide
- [ ] Q8 (généalogie d'un trade) répond de bout en bout sur un trade réel

### Critère de passage
Q8 répond. C'est le test d'intégration du Research OS entier.

---

## Phase 6 — Mémoire scientifique persistante
**16-24 mois**

### Objectifs
Test de l'agent amnésique passé sur **les six questions**.

### Dépendances
Phase 5 (les documents d'amorçage sont générés depuis le graphe).

### Critères de réussite
- [ ] Un agent sans historique répond à Q-A…Q-F en < 1 h, sur fichiers seuls
- [ ] CI détectant la péremption des documents d'amorçage
- [ ] Ledger répliqué hors dépôt

### Critère de passage
Le projet peut changer d'assistant IA sans perte de connaissance. **C'est la
réalisation de l'objectif à 5 ans énoncé dans le cahier des charges** — atteinte
au bout de deux, sans aucun conseil d'IA.

> Point important : l'indépendance aux modèles ne vient **pas** du multi-agents.
> Elle vient de la mémoire persistante. Les phases 7-8 sont un supplément de
> débit, pas la condition de la survie.

---

## Phase 7 — AI Council
**24-36 mois · direction, pas plan**

### Objectifs
Rôles fonctionnels (Observateur, Questionneur, Proposeur, Critique,
Répliquateur, Archiviste), arbitre opérationnel, mesure de calibration par
`actor_id` × `actor_impl`.

### Dépendances
Phases 4, 5, 6. **Aucun agent avant que le rejeu ne puisse trancher.**

### Risques
| Risque | Mitigation |
|---|---|
| Volume d'hypothèses > capacité de test | quota indexé sur le débit de rejeu |
| Convergence par biais commun | contributions en aveugle ; règle C-1 de l'arbitre |
| Retour de l'autorité par réputation | domaines mesurés, jamais assignés |

### Critères de réussite
- [ ] ≥ 1 hypothèse produite par un agent, testée, publiée
- [ ] `calibration_error` mesurée par rôle et par implémentation
- [ ] Un modèle peut être remplacé sans rupture d'historique

### Critère de passage
Le conseil produit plus de gain d'information qu'il ne consomme de capacité de
test. **Si ce n'est pas démontré, la phase est abandonnée** — c'est une option,
pas une obligation.

---

## Phase 8 — Laboratoire scientifique autonome
**36-60 mois · intention**

### Objectif
Le système propose seul une amélioration, la teste, la documente, et ouvre une
pull request — **qui attend une signature humaine**.

### Ce qui ne change jamais
L6 reste le seul écrivain. Aucun agent ne ferme la boucle sur lui-même. La
séparation proposer/valider/appliquer est structurelle, pas paramétrable.

### Risques
| Risque | Mitigation |
|---|---|
| Optimisation de la métrique plutôt que de l'objectif | métriques primaires fixées par l'humain, jamais par le système |
| Volume de propositions ingérable | quota et priorisation humaine |
| Illusion d'autonomie | l'autonomie porte sur la **proposition**, jamais sur la décision |

### Critère de réussite
Une PR entièrement produite par le système, avec preuve complète, jugée
recevable par un humain qui n'a pas participé à sa production.

### Honnêteté
**Cette phase n'est pas planifiable aujourd'hui.** Elle dépend de capacités de
modèles qui n'existent pas encore et d'un volume de connaissance que le projet
n'a pas. Elle est écrite pour que les phases 1-6 ne ferment aucune porte, pas
pour être exécutée telle quelle.

---

## Vue d'ensemble

| Phase | Horizon | Bloquée par | Critère de passage |
|---|---|---|---|
| 1 Canonical Runtime | 0-3 m | — | comportement identique, autorité unique |
| 2 Ledger & Protocole | 2-5 m | 1 | trade traçable jusqu'à sa policy |
| 3 **Replay Engine** | 4-8 m | 1, 2 | test sans attendre le marché |
| 4 Evidence Engine | 7-12 m | 3 | réduction des vétos **sur preuve** |
| 5 Knowledge Graph | 11-18 m | 4 (≥20 verdicts) | Q8 répond |
| 6 Mémoire persistante | 16-24 m | 5 | test de l'agent amnésique passé |
| 7 AI Council | 24-36 m | 4, 5, 6 | gain > coût, sinon abandon |
| 8 Laboratoire autonome | 36-60 m | 7 | PR recevable produite seule |

---

## Ce que la roadmap n'ajoute pas

Aucune couche de décision. Aucun indicateur. Aucune stratégie. Aucun modèle RL.
Le solde en variables expérimentales est **négatif** sur les six premières
phases : elles suppriment 5 sites d'écriture, 1 machine d'état, 5 kill switches,
9 duplications de classes actives et ≥ 9 vétos conjonctifs.

**Conformité à la Scientific Debt Rule : vérifiée par construction.**

---

## Les trois décisions qui appartiennent à l'opérateur

1. **Accepter que la phase 1 ne produise aucun gain de performance.** Elle
   n'améliore rien de visible. Elle rend le reste possible.
2. **Accepter qu'un « pas d'edge » soit un succès.** Si la phase 4 démontre
   qu'aucune couche n'apporte de valeur et qu'aucun edge ne franchit le plancher
   de friction, c'est la conclusion la plus précieuse en deux ans — et la
   plateforme reste valide pour la source d'alpha suivante.
3. **Accepter d'abandonner les phases 7-8 si la phase 6 suffit.** L'objectif
   déclaré — survivre aux modèles — est atteint en phase 6. Tout ce qui suit est
   un pari sur le débit, pas une nécessité.
