# KNOWLEDGE_MODEL.md

> **Statut : conception.** Modèle d'objets scientifiques cible de la V5.

---

## 0. Principes de modélisation

| # | Principe | Conséquence |
|---|---|---|
| **M1** | Tout objet est **immuable** après création | une correction crée un successeur, jamais une mutation |
| **M2** | Tout objet porte sa **provenance** | on sait toujours qui/quoi l'a produit et à partir de quoi |
| **M3** | Tout objet est **auto-descriptif** | lisible sans le modèle, l'outil ou la conversation qui l'a créé (axiome A5) |
| **M4** | Les relations sont **typées et dirigées** | le graphe est interrogeable, pas seulement navigable |
| **M5** | L'**incertitude** est un attribut, jamais une absence | « non mesuré » est une valeur, pas un champ vide |

### Format
JSON ou Markdown avec front-matter YAML. **Jamais un embedding comme
représentation primaire** (INV-G11) : un vecteur n'est pas lisible sans le
modèle qui l'a produit, ce qui viole A5. Les embeddings sont autorisés comme
**index dérivé et reconstructible**, jamais comme source.

---

## 1. Champs communs à tous les objets

```
id              : identifiant canonique, stable à vie
schema_version  : version du schéma de l'objet
version         : version de l'instance (M1 : incrémentée par succession)
created_at      : horodatage UTC
provenance      : voir §2
status          : cycle de vie propre à chaque type
supersedes      : id de l'objet remplacé, ou null
superseded_by   : rempli lors du remplacement
epoch_id        : époque de dataset applicable
```

### Convention d'identifiants
`<TYPE>-<YYYY>-<NNN>` — ex. `HYP-2026-001`, `EXP-2026-014`, `VRD-2026-014`.
**Jamais réattribué**, même après suppression logique.

---

## 2. Provenance — le bloc qui rend le projet indépendant des modèles

```
provenance:
  actor_type   : human | agent | tool | runtime
  actor_id     : identifiant stable         # ex. "council.proposer.slot-A"
  actor_impl   : implémentation concrète    # ex. "claude-opus-5"
  actor_version: version de l'implémentation
  inputs       : [ids des objets consommés]
  method       : description reproductible du procédé
  confidence   : 0..1, ou null si non applicable
  limitations  : texte libre — ce que l'acteur déclare ne pas savoir
```

**Distinction critique `actor_id` / `actor_impl`.** `actor_id` est un **rôle**
stable (`council.statistician`) ; `actor_impl` est le modèle qui l'occupait ce
jour-là. Quand un modèle disparaît, le rôle survit, l'historique reste
interprétable, et les taux de validation par rôle restent comparables dans le
temps.

**C'est le mécanisme central de l'indépendance aux modèles.** Sans lui, toute
la connaissance produite serait datée par un nom commercial.

---

## 3. Les objets

### 3.1 `Event` — L1

L'atome. La seule chose non reconstructible du système.

```
id, ts_utc, kind, payload
trace_id, policy_version, epoch_id
source: runtime | exchange | observer
```

| | |
|---|---|
| **Cycle de vie** | `RECORDED` → (jamais autre chose) |
| **Relations** | `Event —[BELONGS_TO]→ Epoch` |
| **Invariant** | append-only, jamais modifié, jamais supprimé |

---

### 3.2 `Observation` — L2

Ce qui a été vu. Aucune causalité.

```
id, statement, metrics{}, n, epoch_id
source_events: [Event.id]
```

| | |
|---|---|
| **Cycle de vie** | `RECORDED` → `SUPERSEDED` |
| **Relations** | `—[DERIVED_FROM]→ Event` · `—[MOTIVATES]→ Question` |
| **Invariant** | toute phrase causale invalide l'objet |

---

### 3.3 `Trade` / `Decision` — L1

```
Decision: id, trace_id, market_state_hash, policy_version,
          verdict{allowed, size_usd}, contributions[], blocking[]
Trade:    id, decision_id, fills[], costs{}, outcome{}, simulated: bool
```

| | |
|---|---|
| **Cycle de vie** | `Decision` : `EMITTED` (immuable) · `Trade` : `OPEN` → `CLOSED` |
| **Relations** | `Trade —[REALIZES]→ Decision —[UNDER]→ Policy` |
| **Invariant** | `contributions[]` contient **toutes** les couches, pas seulement la bloquante |

**Écart mesuré.** Aujourd'hui, seul le premier bloqueur est journalisé, ce qui
rend l'attribution non estimable. Ce champ est la correction structurelle.

---

### 3.4 `Hypothesis` — L2

```
id, statement, null_hypothesis, falsifier
mde, min_n, target_power, alpha
question_id, domain
```

| | |
|---|---|
| **Cycle de vie** | `PROPOSED` → `PREREGISTERED` → `UNDER_TEST` → `SUPPORTED` \| `REFUTED` \| `INCONCLUSIVE` → `SUPERSEDED` |
| **Relations** | `—[ANSWERS]→ Question` · `—[TESTED_BY]→ Experiment` · `—[CONTRADICTS]→ Hypothesis` |
| **Invariant** | pas d'état « probablement vrai » (axiome A4). `SUPPORTED` signifie « non réfutée par les expériences menées », jamais « vraie » |

**Note.** `SUPPORTED` est révocable à vie. Une hypothèse soutenue puis
contredite repasse en `INCONCLUSIVE`, jamais en `REFUTED` sans expérience
dédiée.

---

### 3.5 `Corpus` / `Dataset` — L1/L2

```
id, content_hash, time_range, symbols[], regimes[]
epoch_id, n_events, certification{}
usage_count            # protection contre le sur-apprentissage
```

| | |
|---|---|
| **Cycle de vie** | `DRAFT` → `CERTIFIED` → `FROZEN` → `RETIRED` |
| **Invariant** | un corpus `FROZEN` référencé par une expérience ne change jamais |

`usage_count` matérialise la limite §15.3 du protocole : un corpus trop réutilisé
est retiré au profit d'une réserve intacte.

---

### 3.6 `Baseline` — L2

```
id, policy_version, commit, corpus_id
cost_model, slippage_model, seed
metrics{} avec intervalles de confiance
```

| **Cycle de vie** | `ACTIVE` → `HISTORICAL` |
| **Invariant** | immuable et rejouable indéfiniment |

---

### 3.7 `Experiment` — L3

```
id, spec (voir SCIENTIFIC_PROTOCOL §6)
submitted_at, run_started_at
runs: [RunManifest.id]
```

| | |
|---|---|
| **Cycle de vie** | `PREREGISTERED` → `RUNNING` → `COMPLETED` \| `ABORTED` |
| **Invariant** | `submitted_at < run_started_at`, vérifié mécaniquement (INV-G07) |

---

### 3.8 `Replay` / `RunManifest` — L3

```
id, experiment_id, commit, corpus_hash, seed
dependency_versions{}, cost_model, slippage_model
determinism_proof: hash des sorties
results{train, validation, oos}
errors[], artifacts[], environment
```

| | |
|---|---|
| **Cycle de vie** | `EXECUTED` (immuable) |
| **Invariant** | rejouer avec le même manifeste redonne le même `determinism_proof` |

---

### 3.9 `Evidence` / `Verdict` — L3

```
id, experiment_id, hypothesis_id
outcome: PASS | FAIL | INCONCLUSIVE
effect_size, ci, p_value, n, power
limitations[]           # obligatoire, jamais vide
missing_for_conclusion[]  # obligatoire si INCONCLUSIVE
signature
```

| | |
|---|---|
| **Cycle de vie** | `ISSUED` → `SUPERSEDED` |
| **Invariant** | immuable ; `limitations[]` non vide |

Le champ `missing_for_conclusion[]` rend le manque **interrogeable** : il permet
au graphe de répondre à « que faudrait-il pour conclure ? » sans relire les
documents.

---

### 3.10 `Publication` — L2

```
id, verdict_id, narrative, open_questions[]
audience: "lecteur sans historique de conversation"
```

| **Cycle de vie** | `PUBLISHED` (immuable) |
| **Invariant** | publiée pour `PASS`, `FAIL` **et** `INCONCLUSIVE` — protection contre le biais de publication |

---

### 3.11 `Policy` — L5

```
id, version, layers[]                # chacune: VETO_DUR | SCORE | OBSERVATEUR
parameters{}, signed_by, signed_at
derived_from_verdict: Verdict.id | null
```

| | |
|---|---|
| **Cycle de vie** | `DRAFT` → `PROPOSED` → `SIGNED` → `ACTIVE` → `RETIRED` |
| **Invariant** | ≤ 3 `VETO_DUR` ; aucune `Policy` `ACTIVE` sans `signed_by` humain |

---

### 3.12 `Calibration` — L5

Un changement de valeur de paramètre, tracé jusqu'à sa preuve.

```
id, parameter, old_value, new_value
justification_verdict: Verdict.id     # OBLIGATOIRE
policy_version_before, policy_version_after
```

| | |
|---|---|
| **Cycle de vie** | `PROPOSED` → `APPROVED` → `APPLIED` → `REVERTED` |
| **Invariant** | **aucune calibration sans verdict justificatif.** Une calibration dont le verdict source passe à `REFUTED` est automatiquement signalée |

**C'est l'objet qui ferme la boucle manquante.** Il rend répondable :
« quels paramètres actifs reposent sur une hypothèse depuis réfutée ? »

---

### 3.13 `ADR` — L5

```
id, title, context, decision, consequences
status: PROPOSED | ACCEPTED | SUPERSEDED | REVOKED
evidence[]: [Verdict.id]
supersedes, superseded_by
```

| **Invariant** | un ADR cité comme norme doit exister (défaut mesuré : ADR-0018 cité, absent) |

---

### 3.14 `Knowledge` — L2

Objet dérivé, agrégeant l'état de croyance sur une question.

```
id, question_id
state: UNKNOWN | CONTESTED | SUPPORTED | REFUTED | UNMEASURABLE
supporting[], contradicting[]
confidence_basis: "verdicts", jamais "opinion d'un modèle"
last_reviewed
```

| | |
|---|---|
| **Cycle de vie** | recalculé à chaque nouveau verdict |
| **Invariant** | **entièrement dérivé** — jamais écrit à la main, jamais par un agent |

`UNMEASURABLE` est un état de plein droit : il enregistre les questions que
l'architecture actuelle ne peut pas trancher, ce qui oriente les investissements
d'instrumentation.

---

## 4. Carte des relations

```
Event ──DERIVED_FROM──▶ Observation ──MOTIVATES──▶ Question
                                                      │
                                                  ANSWERS
                                                      ▼
Corpus ──USED_BY──▶ Experiment ◀──TESTED_BY── Hypothesis
                        │                          │
                    PRODUCES                  CONTRADICTS
                        ▼                          ▼
                  RunManifest ──YIELDS──▶ Verdict ──ABOUT──▶ Hypothesis
                                             │
                              ┌──────────────┼──────────────┐
                        JUSTIFIES        REPORTED_IN     UPDATES
                              ▼              ▼              ▼
                        Calibration    Publication     Knowledge
                              │
                          CHANGES
                              ▼
                           Policy ──SIGNED_BY──▶ Operator
                              │
                           GOVERNS
                              ▼
                          Decision ──REALIZED_BY──▶ Trade ──▶ Event
```

La boucle se ferme : `Event → … → Policy → Decision → Trade → Event`. Chaque
tour produit une époque.

---

## 5. Règles de cohérence vérifiables

| ID | Règle | Détection |
|---|---|---|
| **K-01** | Aucune `Calibration` `APPLIED` dont le verdict justificatif est `REFUTED` | requête de graphe, alerte |
| **K-02** | Aucune `Policy` `ACTIVE` sans `signed_by` humain | validation de schéma |
| **K-03** | Aucun `Verdict` `PASS` sans `RunManifest` déterministe | CI |
| **K-04** | Aucune `Hypothesis` `UNDER_TEST` depuis plus de 90 jours sans verdict | revue périodique |
| **K-05** | Aucun ADR référençant un ADR inexistant | validation d'intégrité |
| **K-06** | Aucun `Corpus` `FROZEN` dont le `content_hash` a changé | vérification d'intégrité |
| **K-07** | Aucune `Knowledge` écrite autrement que par dérivation | contrôle de provenance |
| **K-08** | Aucun objet sans `provenance.actor_id` | validation de schéma |

---

## 6. Ce que le modèle ne capture pas

**6.1 L'intuition.** Une bonne question naît souvent avant l'observation qui la
justifie. Le modèle force à rattacher toute question à une observation ; ce
rattachement sera parfois reconstruit après coup. **C'est une fiction assumée**,
préférable à l'absence de traçabilité — mais elle doit être connue de ceux qui
liront le graphe.

**6.2 Le coût d'opportunité.** Le modèle enregistre les expériences menées, pas
celles qui ne l'ont pas été. Un biais de sélection invisible subsiste.

**6.3 La qualité d'une question.** Aucun champ ne distingue une question féconde
d'une question anodine. Cette évaluation reste humaine, et le modèle ne prétend
pas l'automatiser.
