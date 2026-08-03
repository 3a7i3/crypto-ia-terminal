# FOUNDATION_FREEZE.md — Gel des fondations V5

**Version du gel** : `V5-FOUNDATION-1.0`
**Date de scellement** : 2026-08-02
**Base git au moment de la mesure** : `348e83d` (2026-08-01)
**Statut** : ⚠ **PRÉPARÉ, NON SCELLÉ** — voir §1

> Ce document n'est pas un document d'architecture. C'est un **registre de gel** :
> il enregistre ce qui est figé, sous quelle empreinte, et comment l'amender.
> C'est le dernier artefact de la Phase A.

---

## 1. Avertissement — le gel ne peut pas encore être scellé

**Aucun des artefacts listés ci-dessous n'est suivi par git.** `git ls-files`
retourne 2 fichiers sur les 19 concernés ; les 17 autres sont non suivis, ainsi
que les 5 instruments de mesure et les 4 artefacts de données.

Conséquence directe : un jalon `V5-FOUNDATION-FROZEN` posé sur `348e83d`
**gèlerait un état qui ne contient aucun des travaux de la Phase A**. Le tag
serait vrai sur le plan git et faux sur le plan scientifique — exactement la
classe de défaut mesurée le 2026-07-09 (trois tags d'audit annotés créés sur de
faux succès).

**Séquence correcte, dans cet ordre :**

1. Commiter les artefacts listés au §3 ;
2. Vérifier que les empreintes du §3 correspondent au contenu commité ;
3. Poser le jalon annoté `V5-FOUNDATION-FROZEN` sur ce commit ;
4. Ce document passe de `PRÉPARÉ` à `SCELLÉ`, avec le SHA inscrit ci-dessous.

```
SHA du commit de gel : ____________  (à renseigner à l'étape 3)
```

Aucune de ces étapes n'est faite. Le commit et le tag relèvent de l'opérateur.

---

## 2. Ce que le gel signifie

À compter du scellement, et pour la durée de la Phase B :

| Interdit | Autorisé |
|---|---|
| Nouveau document d'architecture | Code |
| Nouvelle couche conceptuelle | Instruments de mesure |
| Renommage de concept ou de package | Correction d'un fait mesuré faux |
| Modification d'un artefact gelé sans ADR | Registre d'exécution (verdicts, rapports) |

**Le gel porte sur les concepts, pas sur les faits.** Si une mesure ultérieure
contredit un fait cité dans un artefact gelé, la correction du fait n'est pas un
amendement : c'est l'application de la règle qui fonde tout le reste — *la
documentation n'est jamais une preuve, le runtime tranche*. Elle est faite,
datée, et notée au §6 sans ADR.

---

## 3. Artefacts gelés

### 3.1 Fondations conceptuelles — `docs/v5/`

| Artefact | Version | Lignes | sha256 (16) |
|---|---|---:|---|
| `RESEARCH_OS_ARCHITECTURE.md` | 1.0 | 387 | `a762642c26fdbdc5` |
| `SCIENTIFIC_PROTOCOL.md` | 1.0 | 364 | `739f3aa2d309bbda` |
| `KNOWLEDGE_MODEL.md` | 1.0 | 374 | `efaabfe03cbf9d9c` |
| `AI_COUNCIL_SPEC.md` | 1.0 | 243 | `2712ca931861ea2e` |
| `SCIENTIFIC_ARBITER.md` | 1.0 | 174 | `6190ac832b4d1aa7` |
| `KNOWLEDGE_GRAPH_SPEC.md` | 1.0 | 232 | `9bdc0cda6b11b2e0` |
| `PERSISTENT_MEMORY_SPEC.md` | 1.0 | 195 | `2a466ec7ad4241bf` |
| `RESEARCH_ROADMAP_2026_2031.md` | 1.0 | 315 | `1c5583c06ac791bb` |
| `SCIENTIFIC_SAFETY_CONTRACT.md` | 1.0 | 2426 | `ae721adfd94fc369` |

### 3.2 Cartographie mesurée — `docs/cartography/`

| Artefact | Version | Lignes | sha256 (16) |
|---|---|---:|---|
| `SYSTEM_RUNTIME_MAP.md` | 1.0 | 272 | `fb1364eaf59db8bc` |
| `AUTHORITY_CHAIN.md` | 1.0 | 124 | `cad99fe8b894d5eb` |
| `DEAD_MODULES.md` | 1.0 | 855 | `03d28e0927148e0d` |
| `RUNTIME_GRAPH.md` | 1.0 | 355 | `a5642bf5c4a28b83` |
| `DECISION_PATH.md` | 1.0 | 65 | `9d6853afe710dff8` |
| `CONTRADICTIONS.md` | 1.0 | 332 | `840ffd75647121a1` |
| `SCIENTIFIC_DEBT.md` | 1.0 | 234 | `58a38a958230473f` |
| `AMPUTATION_PLAN.md` | 1.0 | 912 | `06b33fb35af24cb6` |
| `CANONICAL_RUNTIME_SPEC.md` | 1.0 | 351 | `1fda7bca5246bf45` |
| `CHIEF_SCIENTIST_DIAGNOSTIC_2026-08.md` | 1.0 | 435 | `6ba9301d8a7f46c8` |

### 3.3 Instruments de mesure — `tools/` *(gelés en tant qu'interfaces, pas en tant que code)*

`runtime_cartographer.py` · `cartography_report.py` · `runtime_import_trace.py`
· `amputation_plan.py` · `build_ssc_registry.py`

Ils restent modifiables : ce sont des instruments. Ce qui est gelé, c'est que
leurs sorties restent régénérables et comparables.

### 3.4 Données de mesure — `artifacts/`

`cartography.json` · `import_trace.json` · `prod_executed_modules.txt`
· `prod_deployed_files.txt`

**Datées du 2026-08-01/02, hôte `136.85.107.18`, code de production `f427895`.**
Toute mesure ultérieure produit un nouvel artefact daté ; celui-ci n'est jamais
écrasé.

### 3.5 Décompte gelé

| Élément | Valeur |
|---|---|
| Invariants SSC | **117** (65 DESIGNED · 45 OBSERVED · 4 ENFORCED_NEW · 3 ENFORCED_ALL) |
| Objets scientifiques | **16** (dont `Deployment` et `ResearchEpoch`) |
| Contrats inter-couches | **10** (C-01 → C-10) |
| Invariants globaux d'architecture | **13** (INV-G01 → INV-G13) |
| Phases de roadmap | **8** |
| Contradictions mesurées | **10** |
| Dettes scientifiques | **19** |

---

## 4. Ce qui **n'est pas** gelé

| Ouvert | Raison |
|---|---|
| Les 13 fusions d'invariants (SSC §6) | arbitrage requis ; le registre est à 117 pour une cible ~104 |
| Les 18 preuves marquées ⚠ (SSC §4.4) | à re-mesurer avant toute promotion d'état |
| L'état de chaque invariant | le cliquet est fait pour progresser — c'est son objet |
| Le plan d'amputation | classement provisoire, seconde mesure requise après ≥ 7 jours |
| Le nom du cœur | voir §5.3 |

Un gel qui interdirait la progression du cliquet se contredirait lui-même.

---

## 5. Trois contradictions à trancher **avant** l'ouverture de la Phase B

Chacune est peu coûteuse maintenant et empoisonnerait la phase entière.

### 5.1 Frontière d'autonomie du laboratoire — ✅ **TRANCHÉE le 2026-08-02**

> **Décision de l'opérateur : arrêt sur signature.**
>
> Le laboratoire est autonome de `Observation` jusqu'à `Proposal` inclus.
> Il **s'arrête** à la signature humaine. `Calibration` et `Deployment` sont
> **déclenchés par** cette signature, jamais avant.
>
> ```
> Observation → Hypothesis → Experiment → Replay → Evidence → Proposal
>                                                                 │
>                                                      ⟨ SIGNATURE HUMAINE ⟩
>                                                                 │
>                                                    Calibration → Deployment
> ```
>
> **L'autonomie porte sur la production de preuve, jamais sur l'application.**
>
> Conséquences normatives : les contrats **C-08/C-09** et l'invariant
> **INV-G08** sont maintenus sans amendement ; l'article *« aucune IA n'a
> d'autorité d'exécution »* est confirmé comme candidat au verrouillage
> `ENFORCED_ALL` dès le jour 0 de la Phase B.
>
> Cette décision définit le MVP de la Phase B et n'est pas rouvrable sans ADR.

*Exposé du problème qui a motivé l'arbitrage, conservé pour l'audit :*

#### Le MVP initialement proposé violait la constitution

Le MVP proposé est :

> `Observation → Hypothesis → Experiment → Replay → Evidence → Calibration → Deployment`, **sans intervention humaine**.

Or trois invariants gelés l'interdisent : contrat **C-08/C-09** (L6 est le seul
écrivain), **INV-G08** (aucune fusion de `Policy` sans signature humaine), et
l'article que nous convenons de verrouiller en `ENFORCED_ALL` dès le jour 0 —
*aucune IA n'a d'autorité d'exécution*.

Si le MVP est pris au pied de la lettre, **la première chose que fait le
laboratoire est de violer son propre contrat de sécurité**.

**Reformulation proposée** — même ambition, aucune violation :

> `Observation → Hypothesis → Experiment → Replay → Evidence → Proposal`
> **sans intervention humaine**, puis **arrêt sur signature**, puis
> `Calibration → Deployment` **déclenchés par la signature**.

L'autonomie porte sur la **production de preuve**, jamais sur l'application.
C'est la seule version du MVP qui soit à la fois ambitieuse et constitutionnelle.
**À trancher explicitement**, car tout le reste de la Phase B en découle.

### 5.2 La règle de PR rejetterait B1

La règle proposée — *« cette PR rapproche-t-elle le laboratoire de la boucle ?
sinon refus »* — rejetterait le **SSC Runtime**, qui n'est aucune étape de la
boucle. B1 serait interdit par la règle qui gouverne B1.

**Amendement proposé :**

> Une PR est recevable si elle fait avancer une étape de la boucle, **ou** si
> elle implémente un invariant qui garde une étape de la boucle.
> Le second motif est plafonné à **20 % des PR de la phase**.

Le plafond est ce qui empêche la dérive vers « 117 tests, zéro laboratoire » que
vous identifiez à juste titre comme le danger principal.

### 5.3 Le gel interdit les renommages, et le premier acte proposé est un renommage

`SciOS Core` est le bon nom du concept. Mais renommer le cœur toucherait les
**210 modules exécutés en production**, dont 8 paires de classes dupliquées
simultanément actives et un graphe d'import qui n'est pas décidable
statiquement — la plus haute opération à risque du dépôt, pour une valeur nulle
au regard de la boucle.

**Proposition :** `SciOS` est adopté comme **nom conceptuel** dès maintenant
(documents, discours, jalons). Le renommage des packages est reporté à la fin de
la Phase B, quand le rejeu pourra en prouver l'innocuité. Le nom du dépôt ne
change pas.

---

## 6. Procédure d'amendement

### 6.1 Amendement conceptuel — ADR obligatoire

Toute modification d'un artefact du §3.1 ou §3.2 exige un ADR dédié
(`docs/adr/00NN-*.md`) contenant : l'artefact visé et son empreinte gelée, ce
qui change, **le fait mesuré ou le verdict qui justifie le changement**, l'impact
sur les invariants du SSC, et le solde en variables expérimentales (≤ 0).

**L'ADR n'est pas écrit d'avance.** Il est écrit au moment où un amendement est
proposé — écrire aujourd'hui l'ADR d'un amendement inconnu serait un document
d'architecture de plus.

Rappel mesuré : `ADR-0018` est cité comme norme canonique par
`tools/score_calibration_audit.py:675` et **n'existe pas**. La séquence des ADR
est elle-même une dette ouverte.

### 6.2 Correction de fait — pas d'ADR

Une mesure contredisant un fait cité : correction directe, datée, journalisée
ci-dessous. Précédent de cette session : 52 modules classés morts par l'analyse
statique se sont révélés vivants en production — la correction n'a pas exigé
d'ADR, elle a exigé une mesure.

### 6.3 Journal des corrections post-gel

| Date | Artefact | Fait corrigé | Mesure source |
|---|---|---|---|
| *(vide)* | | | |

---

## 7. Critères d'ouverture de la Phase B

- [x] **Contradiction 5.1 tranchée** — arrêt sur signature (2026-08-02) — *était bloquante*
- [x] Artefacts du §3 commités et empreintes vérifiées
- [x] Jalon `V5-FOUNDATION-FROZEN` posé, SHA inscrit au §1
- [ ] Contradictions 5.2 et 5.3 tranchées
- [ ] Lot de verrouillage jour 0 arbitré (SSC §7)

Les points 5.2 (règle de PR qui rejetterait B1) et 5.3 (renommage `SciOS`)
restent ouverts. Aucun n'est bloquant : le premier se tranche avant la première
PR de Phase B, le second avant la fin de la phase.

---

## 8. Ce que ce gel protège

Douze mois ont produit une architecture riche et un Evidence Score de zéro. La
Phase A a produit la première description fidèle du système réellement exécuté,
et 117 lois pour l'empêcher de redevenir opaque.

Le gel protège contre la répétition du même échec à un niveau plus abstrait :
**une architecture parfaitement documentée autour d'un laboratoire qui n'existe
pas**. Chaque ligne de code de la Phase B doit rapprocher le système de la
boucle, ou garder une de ses étapes. Rien d'autre.

> Dernier artefact de la Phase A. Le suivant sera du code.
