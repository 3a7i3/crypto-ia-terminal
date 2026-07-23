# Protocole d'audit épistémique

- **Version** : 2.0
- **Statut** : Draft
- **Auteur** : Mathieu (opérateur du projet), en co-conception assistée
- **Date** : 2026-07-23
- **Objectif** : rendre un audit technique lui-même auditable, en empêchant
  **structurellement** un mot de porter une charge de preuve que les données ne portent pas.
- **Portée d'usage** : audits logiciels, revues de conception, rapports d'ingénierie ou
  scientifiques. Générique — non lié au moteur de trading de ce dépôt.
- **Historique** :
  - **v1.0** (2026-07-23) — format d'audit à quatre catégories (Observation / Inférence /
    Hypothèse / Décision) + règle du maillon faible + portée + source/couverture +
    double falsificateur + double filtre lexical + règle de proportionnalité.
  - **v2.0** (2026-07-23) — passage d'un format de rédaction à une **grammaire de
    raisonnement** : composition/fermeture (DAG de dépendances), graphe de dépendances avec
    défaiteurs, distinction rétracter ≠ nier, triade voir/croire/vouloir (guillotine de Hume),
    critère de validité par révisabilité mécanique.

> Règle méta : **le protocole lui-même est soumis au protocole.** Toute règle ci-dessous
> est révisable ; chacune énonce, quand c'est possible, ce qui la ferait tomber.

---

## 1. Principe fondateur

**Chaque phrase appartient à UNE catégorie épistémique unique.**
Une phrase qui en mélange plusieurs n'est pas auditable — on la scinde avant tout.

Les trois verbes que le protocole rend **non-interchangeables** :

| Catégorie | Verbe | Interdit structurel |
|---|---|---|
| Observation | **voir** | — |
| Inférence / Hypothèse | **croire** | un *croire* ne devient jamais un *voir* par répétition |
| Décision | **vouloir** | on ne dérive jamais un *vouloir* d'un *voir* seul (guillotine de Hume) |

« J'ai vu X, donc Y est vrai, donc il faut Z » devient impossible à écrire d'un trait.
Le protocole force : *j'ai vu X ; je crois que cela implique Y (portée…) ; si mon objectif
est G, alors je recommande Z.*

**Critère de validité (formulation forte) :**
> Un audit est valide lorsqu'un lecteur peut supprimer n'importe quelle observation,
> hypothèse ou inférence, puis déterminer **mécaniquement** quelles conclusions cessent
> d'être justifiées.

Corollaire du prix à payer : la révisabilité mécanique **exige zéro prémisse implicite**.
Toute arête de dépendance doit être déclarée, sinon la suppression d'un nœud ne révèle pas
que la conclusion aurait dû tomber.

---

## 2. Les quatre catégories et leurs champs

### 2.1 Observation — un fait lu à une source (voir)
- **Énoncé** : factuel, sans qualificatif fort.
- **Source** : `inspection directe` | `échantillon de fichiers` | `log` | `documentation` | `mémoire de conversation`.
- **Couverture** : `complète` | `partielle` | `inconnue`.
- *Pas de champ « confiance ».* La force probante est portée par **Source × Couverture**.

### 2.2 Inférence — déduite d'observations (croire)
- **Énoncé**
- **Confiance** : `certain` | `très probable` | `probable` | `spéculatif` | `non démontré` | `faux`
- **Portée** : le domaine EXACT où l'énoncé vaut.
- **Supports / Dépend de** : identifiants des nœuds parents (voir § 5).
- **Falsificateur logique** : l'observation qui détruirait le raisonnement.

### 2.3 Hypothèse — plausible mais non vérifiée (croire)
- **Énoncé** · **Confiance** (même échelle) · **Source de plausibilité**
- **Falsificateur expérimental** : l'expérience qui départagerait d'une rivale.

### 2.4 Décision — recommandation de gouvernance (vouloir)
- **Énoncé** (la recommandation)
- **Autorité / fonction de risque** : au nom de qui, sous quel appétit au risque.
- **Prémisse de coût/valeur** : le jugement de valeur explicite.
- *Une Décision n'a pas de ligne Observation.* Si elle en a besoin, c'est une Inférence déguisée.

---

## 3. Règle de propagation — maillon faible (locale)

Une **Inférence ne peut jamais être plus forte que sa plus faible observation-support.**
Observation `source: mémoire` ou `couverture: inconnue` ⇒ inférence plafonnée à `probable`.

---

## 4. Règle de composition / fermeture (globale)

Un rapport n'est pas une collection d'affirmations : c'est une conclusion qui les **compose**.
La confiance se propage le long du **DAG de dépendances** (§ 5) :

- **Nœud conjonctif** (la conclusion exige A ET B ET C) :
  `confiance ≤ min(parents)`, et *strictement plus bas* si les parents sont indépendants
  (le produit est inférieur au minimum). Plusieurs prémisses indépendantes **diminuent**.
- **Nœud disjonctif / corroboratif** (A, B, C pointent indépendamment vers la conclusion) :
  la confiance **peut dépasser** tout parent (consilience) — **mais seulement si** les
  ensembles d'ancêtres des parents sont **disjoints** dans le graphe.
  Ancêtre commun ⇒ traiter comme conjonctif sur la part commune / plafonner à cet ancêtre.

> Anti-pattern nommé — **l'illusion de convergence** : deux affirmations « probables »
> qui semblent se renforcer alors qu'elles héritent de la **même** observation.
> La conclusion ne repose que sur une observation ; la montée disjonctive est illégitime.
> Le graphe la détecte automatiquement (ancêtre commun ≠ disjoint).

---

## 5. Graphe de dépendances et défaiteurs

Chaque affirmation (nœud) déclare ses arêtes. Deux types, **positif ET négatif** :

```
Supports        : [O3, O8]      # nœuds qui soutiennent
Dépend de       : [I2]          # nœuds dont l'énoncé hérite
Sapé par        : [O5]          # undercut : affaiblit l'inférence sans la réfuter
Réfuté par      : [O9]          # rebut : contredit directement l'énoncé
```

Quand une observation tombe, **toute conclusion qui en hérite devient immédiatement suspecte**
(traçabilité d'ingénierie des exigences, étendue au raisonnement défaisable).

Deux opérations de révision, à propagation **différente** :
- **Rétracter** un nœud (on ne l'affirme plus) → l'aval perd son support.
- **Nier** un nœud (on affirme le contraire) → l'aval peut devenir *activement contredit* ;
  un défaiteur s'active et déclenche la règle **contradiction = obligation** (résolution forcée).

---

## 6. Règle de proportionnalité (anti-théâtre)

Remplir des cases simule la rigueur sans la produire. **Forme longue + arêtes explicites
seulement si** la phrase est (a) porteuse, (b) contestée, ou (c) déclenche un filtre lexical (§ 7).
Sinon : ligne taguée — `[OBS]`, `[INF: probable]`, `[HYP: spéculatif]`, `[DEC]`.

**Caveat dur :** un graphe de dépendances **périmé est pire que pas de graphe** — il affirme
une traçabilité qui n'est plus vraie. Le graphe ne doit exister que là où il reste
**peu coûteux à maintenir vrai**.

---

## 7. Double filtre lexical (avant de valider une phrase)

**Filtre 1 — mots forts :** `impossible, détruit, mort, prouve, définitivement, nécessairement,
toujours, jamais, seul, aucun, tout, garantit`.
→ *« Quelle observation autorise précisément ce mot ? »* Pas de réponse immédiate ⇒ requalifier.

**Filtre 2 — quantificateurs implicites :** une phrase sans adjectif fort peut cacher un
« tout / seul / toujours ». « le système écrit dans un fichier » sous-entend « un seul / toujours ».
→ rendre le quantificateur explicite, puis lui appliquer le Filtre 1.

**Corollaire unificateur :** une **Portée manquante EST un quantificateur universel caché.**

---

## 8. Deux types de falsificateur

| Type | Rôle | Exemple |
|---|---|---|
| **Logique** | remet en cause le *raisonnement* | montrer un import dynamique de `src` dans le runtime |
| **Expérimental** | remet en cause le *modèle* | backtest walk-forward OOS avec coût calibré |

Toute Inférence porte un falsificateur **logique** ; toute Hypothèse vise un falsificateur **expérimental**.

---

## 9. Gabarit copiable

```
OBSERVATION  O#
  Énoncé      :
  Source      : inspection directe | échantillon | log | doc | mémoire
  Couverture  : complète | partielle | inconnue

INFÉRENCE  I#
  Énoncé      :
  Confiance   : certain … faux   (≤ maillon faible ; ≤ composition)
  Portée      :
  Supports    : [O#, …]   Dépend de : [I#, …]
  Sapé/Réfuté : [O#, …]
  Falsif. log.:

HYPOTHÈSE  H#
  Énoncé      :   Confiance :   Source plaus. :
  Falsif. exp.:

DÉCISION  D#
  Énoncé      :
  Autorité    : au nom de qui / quel appétit au risque
  Dépend de   : [I#, H#, …]
  Prémisse c/v:
```

---

## 10. Exemple complet (recast d'une affirmation porteuse)

```
OBSERVATION  O1
  Énoncé      : grep "from src.(domain|paper|backtest|engine|risk|events)"
                sur core/** → aucune correspondance.
  Source      : inspection directe
  Couverture  : partielle (imports statiques seulement)

INFÉRENCE  I1
  Énoncé      : les piles core/ (live) et src/ sont découplées.
  Confiance   : très probable  (plafonné par couverture partielle)
  Portée      : chemin d'exécution inspecté uniquement — PAS "le projet entier".
  Supports    : [O1]
  Sapé par    : [un import dynamique de src, non observé]
  Falsif. log.: exhiber un import dynamique/plugin de src dans le runtime.

HYPOTHÈSE  H1
  Énoncé      : la migration ADR-0002 (src = SSoT) est inachevée.
  Confiance   : probable      Source plaus. : ADR-0002 + persistance de core/ en prod.
  Falsif. exp.: retracer l'historique git de la migration.

DÉCISION  D1
  Énoncé      : nommer la frontière (Context Map écrite), ne pas fusionner.
  Autorité    : architecte ; appétit au risque bas sur la dette de duplication.
  Dépend de   : [I1, H1]
  Prémisse c/v: coût d'onboarding d'une frontière tacite > coût d'un document —
                vrai si l'équipe s'agrandit ; à un seul mainteneur, discutable.
```

Note de composition : D1 dépend de I1 (`très probable`) ET H1 (`probable`) — nœud
conjonctif ⇒ la justification de D1 ne peut se réclamer mieux que `probable`. Si O1 est
rétractée, I1 perd son unique support et D1 devient non justifiée — mécaniquement.

---

## 11. Auto-application (le protocole s'audite lui-même)

Mode d'échec : devenir un rituel de remplissage de cases qui *simule* la rigueur.
Garde-fous : la règle de proportionnalité (§ 6) et le caveat « graphe périmé = pire que rien ».
Si un audit produit des gabarits complets et des graphes pour des évidences triviales,
il viole son propre principe.
