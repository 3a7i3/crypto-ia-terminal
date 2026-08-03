# KNOWLEDGE_GRAPH_SPEC.md

> **Statut : conception.** Seuil d'activation : **≥ 20 verdicts déposés**.
> État mesuré : **0 verdict, 1 hypothèse conclue**. Ne pas construire maintenant.

---

## 1. Fonction

Le graphe n'est pas une base de documents. C'est l'organe qui rend le système
capable de répondre à des questions **sur lui-même** que personne ne peut tenir
en tête.

Trois questions de gouvernance justifient à elles seules son existence :

1. Quels paramètres actifs reposent sur une hypothèse depuis réfutée ?
2. Quel code en production dérive d'une expérience jamais validée ?
3. Que faudrait-il mesurer pour débloquer le plus de questions ouvertes ?

Aucune ne se répond en lisant des fichiers. Toutes se répondent par une requête
si — et seulement si — les relations ont été enregistrées **au moment de la
création**, jamais reconstruites après coup.

---

## 2. Substrat

| Contrainte | Choix |
|---|---|
| **Source de vérité** | fichiers texte versionnés dans git (JSON / Markdown + front-matter) |
| **Graphe** | **index dérivé, entièrement reconstructible** depuis les fichiers |
| **Corollaire** | perdre la base de graphe ne perd aucune connaissance |

**Le graphe n'est jamais la source.** Cette règle découle de l'axiome A5 : une
connaissance qui n'existerait que dans une base de données propriétaire ne
survivrait ni à un changement de technologie ni à dix ans.

Aucun moteur n'est prescrit à ce stade — le choix est une décision d'ingénierie
à prendre au moment de l'activation, sur des volumes réels.

---

## 3. Nœuds

Types repris du `KNOWLEDGE_MODEL.md`, sans ajout :

`Event` · `Observation` · `Question` · `Hypothesis` · `Corpus` · `Baseline` ·
`Experiment` · `RunManifest` · `Verdict` · `Publication` · `Policy` ·
`Calibration` · `ADR` · `Commit` · `Decision` · `Trade` · `Knowledge` ·
`Contribution` · `Arbitration` · `Actor` · `Epoch` · `Module`

Deux nœuds méritent une note :

- **`Actor`** porte la distinction `actor_id` (rôle, stable) /
  `actor_impl` (modèle, remplaçable). C'est ce qui permet de répondre à « quel
  rôle produit le plus d'hypothèses validées » **et** « quel modèle », sans que
  la disparition d'un modèle n'invalide l'historique du rôle.
- **`Module`** relie la connaissance au code : c'est le nœud qui rend
  interrogeable « ce module dépend-il d'une hypothèse réfutée ? ».

---

## 4. Arêtes

| Arête | De → Vers | Cardinalité |
|---|---|---|
| `DERIVED_FROM` | Observation → Event | n:m |
| `MOTIVATES` | Observation → Question | n:m |
| `ANSWERS` | Hypothesis → Question | n:1 |
| `CONTRADICTS` | Hypothesis → Hypothesis | n:m |
| `TESTED_BY` | Hypothesis → Experiment | 1:n |
| `USES_CORPUS` | Experiment → Corpus | n:1 |
| `AGAINST_BASELINE` | Experiment → Baseline | n:1 |
| `PRODUCED` | Experiment → RunManifest | 1:n |
| `YIELDS` | RunManifest → Verdict | 1:1 |
| `ABOUT` | Verdict → Hypothesis | n:1 |
| `SUPERSEDES` | Verdict → Verdict | 1:1 |
| `REPORTED_IN` | Verdict → Publication | 1:1 |
| `JUSTIFIES` | Verdict → Calibration | 1:n |
| `CHANGES` | Calibration → Policy | n:1 |
| `SIGNED_BY` | Policy → Actor | n:1 |
| `GOVERNS` | Policy → Decision | 1:n |
| `REALIZED_BY` | Decision → Trade | 1:1 |
| `EMITS` | Trade → Event | 1:n |
| `IMPLEMENTS` | Commit → Policy | n:1 |
| `DERIVES_FROM_EXPERIMENT` | Commit → Experiment | n:1 |
| `DECIDED_IN` | Policy → ADR | n:1 |
| `CITES` | ADR → Verdict | n:m |
| `PRODUCED_BY` | Contribution → Actor | n:1 |
| `ARBITRATED_IN` | Contribution → Arbitration | n:1 |
| `UPDATES` | Verdict → Knowledge | n:1 |
| `USES_CALIBRATION` | Module → Calibration | n:m |
| `BELONGS_TO` | * → Epoch | n:1 |

### Invariants d'arête

| ID | Règle |
|---|---|
| **G-01** | Toute arête porte `created_at` et la provenance de son établissement |
| **G-02** | Une arête n'est jamais supprimée ; elle est marquée `INVALIDATED` avec sa raison |
| **G-03** | `JUSTIFIES` est obligatoire pour toute `Calibration` — aucune calibration orpheline |
| **G-04** | `DERIVES_FROM_EXPERIMENT` est obligatoire pour tout commit modifiant une `Policy` |
| **G-05** | Le sous-graphe `SUPERSEDES` est acyclique |

---

## 5. Les requêtes de gouvernance

Ces requêtes **définissent** le graphe : tout élément de schéma qui n'en sert
aucune est à supprimer du modèle.

### Q1 — Hypothèses réfutées encore utilisées

```
Hypothesis(status = REFUTED)
  ← ABOUT ← Verdict
             → JUSTIFIES → Calibration(status = APPLIED)
                             → CHANGES → Policy(status = ACTIVE)
```
**Sortie.** Liste des paramètres actifs reposant sur une hypothèse réfutée.
**Action.** Alerte de gouvernance (règle K-01), revue obligatoire.

> C'est la requête la plus importante du système. Elle rend impossible ce qui,
> aujourd'hui, est invisible : un seuil calibré sur une croyance depuis
> abandonnée.

### Q2 — Modules dépendant d'une calibration issue d'une hypothèse réfutée

```
Module → USES_CALIBRATION → Calibration → JUSTIFIES⁻¹ → Verdict → ABOUT → Hypothesis(REFUTED)
```
**Sortie.** Périmètre de code contaminé, avec le chemin de dépendance complet.

### Q3 — Commits issus d'une expérience validée

```
Commit → DERIVES_FROM_EXPERIMENT → Experiment → PRODUCED → RunManifest → YIELDS → Verdict(PASS)
```
**Sortie.** Part du code de production adossée à une preuve. Le complément
— commits sans expérience — est la **dette scientifique du code**, mesurable
en pourcentage.

### Q4 — Productivité par acteur

```
Actor ← PRODUCED_BY ← Contribution(type=hypothesis) → TESTED_BY → Experiment → Verdict
group by actor_id, actor_impl
```
**Sortie.** `validation_rate`, `calibration_error`, `citation_integrity` par rôle
et par modèle.
**Usage autorisé.** Affectation des rôles. **Jamais** la validation d'une
hypothèse.

### Q5 — Que mesurer en priorité

```
Knowledge(state ∈ {UNKNOWN, CONTESTED, UNMEASURABLE})
  ← UPDATES⁻¹ ... → data_gaps → required_instrumentation
order by nombre de questions débloquées
```
**Sortie.** Classement des investissements d'instrumentation par nombre de
questions qu'ils débloquent. **C'est la requête qui pilote la roadmap.**

### Q6 — Hypothèses zombies

```
Hypothesis(status = UNDER_TEST, created_at < now - 90j)
  sans Verdict associé
```
**Sortie.** Recherche ouverte mais abandonnée. Force la clôture explicite en
`INCONCLUSIVE` plutôt que l'oubli silencieux.

### Q7 — Intégrité de la chaîne de preuve

```
Verdict(PASS) sans RunManifest.determinism_proof
∪ Policy(ACTIVE) sans signed_by humain
∪ ADR citant un ADR inexistant
∪ Corpus(FROZEN) dont content_hash a changé
```
**Sortie.** Violations d'invariants. Devrait toujours être **vide**.
*(État actuel : ADR-0018 est cité par `tools/score_calibration_audit.py:675` et
n'existe pas — Q7 retournerait déjà une violation aujourd'hui.)*

### Q8 — Généalogie d'un trade

```
Trade → REALIZED_BY⁻¹ → Decision → GOVERNS⁻¹ → Policy
      → CHANGES⁻¹ → Calibration → JUSTIFIES⁻¹ → Verdict → ABOUT → Hypothesis
```
**Sortie.** Pour un trade donné : la chaîne complète jusqu'à l'hypothèse qui a
justifié le paramètre sous lequel il a été pris.

> C'est le test d'intégration du graphe entier. Le jour où Q8 répond sur un
> trade réel, le Research OS fonctionne. Aujourd'hui, cette chaîne est rompue en
> au moins trois endroits mesurés : les trades ne portent pas de
> `policy_version`, aucune `Calibration` n'existe, aucun `Verdict` n'existe.

---

## 6. Vues dérivées

| Vue | Contenu | Public |
|---|---|---|
| **État de connaissance** | chaque `Question` avec son état et ses preuves | opérateur |
| **Carte d'incertitude** | ce qui est `UNKNOWN` / `CONTESTED` / `UNMEASURABLE` | priorisation |
| **Dette scientifique** | code sans preuve, calibrations orphelines, ADR manquants | gouvernance |
| **Frontière de recherche** | questions testables maintenant, ordonnées par gain/coût | conseil |
| **Journal d'époques** | ce qui a changé, quand, pourquoi, comparabilité préservée ou rompue | audit |

Toutes sont **dérivées et reconstructibles**. Aucune n'est écrite à la main.

---

## 7. Ce que le graphe ne fera pas

**7.1 Il ne raisonnera pas.** C'est un index de relations enregistrées, pas un
moteur d'inférence. Une relation non enregistrée à la création n'existera jamais.

**7.2 Il ne remplacera pas la lecture.** Q1 dit *qu'un* paramètre repose sur une
hypothèse réfutée. Elle ne dit pas si c'est grave. Cela reste un jugement.

**7.3 Il ne peut pas être construit rétroactivement.** Les 359 commits, les 19
ADR et les 139 trades existants n'ont pas de relations enregistrées. **Le graphe
commence au premier objet créé sous le nouveau protocole.** Toute tentative de
reconstruire l'historique produirait des arêtes inventées — c'est-à-dire de la
fausse provenance, le défaut le plus grave possible dans ce système.

**7.4 Il est inutile en dessous de son seuil.** À 0 verdict, ce document décrit
un index vide. Il est écrit maintenant pour que les objets créés à partir de la
phase 2 portent **dès l'origine** les relations dont le graphe aura besoin —
c'est sa seule utilité immédiate, et elle est réelle.
