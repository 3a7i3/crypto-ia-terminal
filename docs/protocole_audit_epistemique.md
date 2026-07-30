# Protocole d'audit épistémique

- **Version** : 4.5 — GEL avant campagne empirique
- **Statut** : Draft
- **Auteur** : Mathieu (opérateur du projet), en co-conception assistée
- **Date** : 2026-07-24
- **Objectif** : rendre un audit technique lui-même auditable, en empêchant
  **structurellement** un mot de porter une charge de preuve que les données ne portent pas.
- **Portée d'usage** : audits logiciels, revues de conception, rapports d'ingénierie ou
  scientifiques, analyses de sécurité, décisions d'investissement. Générique — non lié au
  moteur de trading de ce dépôt.
- **Historique** (détail en § 16) :
  - **v1.0** (2026-07-23) — format d'audit à quatre catégories + maillon faible + portée +
    source/couverture + double falsificateur + double filtre lexical + proportionnalité.
  - **v2.0** (2026-07-23) — grammaire de raisonnement : composition/fermeture (DAG),
    graphe de dépendances avec défaiteurs, rétracter ≠ nier, voir/croire/vouloir (Hume),
    révisabilité mécanique.
  - **v3.0** (2026-07-24) — contrôle-qualité du *processus* : représentativité de
    l'observation, plafond « état mutable », dette épistémique relative à une décision,
    indice de robustesse méthodologique, principe de symétrie.

> Règle méta : **le protocole lui-même est soumis au protocole.** Toute règle ci-dessous
> est révisable ; chacune énonce, quand c'est possible, ce qui la ferait tomber. Les ajouts
> v3 déclarent chacun leur **domaine de validité, leur mode d'échec et leur falsificateur** —
> v3 n'est pas « meilleure » que v2, c'est une hypothèse méthodologique plus riche, ouverte
> à révision.

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

**Les trois niveaux gouvernés (v3.1).**

> Un protocole d'audit n'est complet que s'il gouverne **les conclusions**, **les observations qui
> les soutiennent**, et **les instruments qui rendent ces observations possibles**.

| Niveau | Objet | Ce que produit son absence |
|---|---|---|
| 1 | les **conclusions** | de la prudence rhétorique, sans traçabilité |
| 2 | les **observations** | de la traçabilité, mais aveugle à ses propres angles morts |
| 3 | les **instruments** | — |

Le niveau 3 est ce qui permet de distinguer « je n'ai pas observé » de « je ne **peux pas** observer »
(§ 16). Sans lui, un angle mort se lit comme une simple négligence.

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
- **Source** : `inspection directe` | `échantillon de fichiers` | `log` | `documentation` | `mémoire de conversation` | `état externe mutable`.
- **Couverture** : `complète` | `partielle` | `inconnue`.
- **Échantillon / Population** *(v3)* : ce qui a été effectivement observé / la cible réelle si connue, sinon `inconnue` (voir § 12).
- **Représentativité** *(v3)* : dérivée si la population est connue, sinon `NON ÉVALUABLE` — jamais « faible » sans dénominateur.
- **Biais** *(v3)* : chaque biais nommé indique sa **direction** (*gonfle* ou *réduit* l'inférence).
- *Pas de champ « confiance ».* La force probante est portée par **Source × Couverture × Représentativité**.

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

**Extensions v3 :**
- Une **représentativité insuffisante** (ou `NON ÉVALUABLE`) plafonne la confiance exactement comme `mémoire`, `couverture` ou `source` (§ 12).
- Toute inférence dont un support observe un **état externe mutable** (champ d'API, ref distante type `origin/main`, working tree, service tiers) est plafonnée à `très probable` — jamais `certain`, car un snapshot d'état mutable admet désync/lag/évolution post-requête (proba faible, non nulle). `certain` est réservé aux **objets immuables** (contenu d'un commit content-addressed, invariant logique).

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

**Arêtes ajoutées en v3 :**
```
Dette (§13)          ──bloque──►  Décision Dx
Représentativité(§12)──plafonne─►  Confiance d'une Inférence
Symétrie (§15)       ──impose───►  { recherche des supports , recherche des réfutateurs }
```

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
  Énoncé          :
  Source          : inspection directe | échantillon | log | doc | mémoire | état mutable
  Couverture      : complète | partielle | inconnue
  Échantillon/Pop : <observé> / <cible ou "inconnue">        (v3)
  Représentativité: dérivée | NON ÉVALUABLE                  (v3)
  Biais           : <nom> → gonfle | réduit l'inférence      (v3)

INFÉRENCE  I#
  Énoncé      :
  Confiance   : certain … faux   (≤ maillon faible ; ≤ composition ; ≤ représentativité ; état mutable ⇒ ≤ très probable)
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

NON OBSERVÉ  N#                                               (v3)
  Dette       : critique | majeure | mineure | nulle POUR <décision>
  Bloque      : D#
```

---

## 10. Exemple complet (recast d'une affirmation porteuse)

```
OBSERVATION  O1
  Énoncé          : grep "from src.(domain|paper|backtest|engine|risk|events)"
                    sur core/** → aucune correspondance.
  Source          : inspection directe
  Couverture      : partielle (imports statiques seulement)
  Échantillon/Pop : imports statiques de core/ / tous les modes d'import (statique+dynamique)
  Représentativité: dérivée — partielle (les imports dynamiques ne sont pas couverts)
  Biais           : angle mort import dynamique → gonfle "découplé"

INFÉRENCE  I1
  Énoncé      : les piles core/ (live) et src/ sont découplées.
  Confiance   : très probable  (plafonné par couverture ET représentativité partielles)
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

---

## 12. Représentativité de l'observation *(v3)*

Une observation peut être **exacte** tout en étant **peu représentative**. Exemple :
`grep "TODO"` → 12 000 résultats est vrai, mais n'autorise pas « le projet est mal maintenu ».

La représentativité **n'est pas une observation** — elle est **dérivée**. L'observation ne
porte que deux quantités brutes :
- **Échantillon** : ce qui a été effectivement observé (ex. 137 lignes lues) ;
- **Population** : la cible réelle si connue (ex. le chemin réel traverse 18 modules), sinon `inconnue`.

La représentativité en découle :
- population **connue** → dérivée (l'échantillon couvre-t-il la cible ?) ;
- population **inconnue** → **NON ÉVALUABLE**. Écrire « faible » sans dénominateur est
  lui-même un surclaim.

**Biais** : chaque biais nommé indique sa **direction**, parmi **trois** valeurs seulement —
*gonfle l'inférence* · *réduit l'inférence* · *effet inconnu*. Jamais « biais possibles » sans
direction : une liste sans direction est infalsifiable.

`effet inconnu` est une valeur **légitime et informative** : elle dit qu'un biais est identifié
mais que son sens ne l'est pas. C'est différent de ne pas l'avoir nommé — et cela plafonne
l'inférence au même titre qu'une couverture partielle. Une représentativité insuffisante plafonne la confiance aval (§ 3).

> Domaine : toute observation servant de support à une inférence porteuse.
> Mode d'échec : exiger un dénominateur là où la population est légitimement inconnue —
> il faut alors écrire `NON ÉVALUABLE`, pas bloquer l'audit.
> Falsificateur : une inférence porteuse tenue pour valide alors que son échantillon ne
> couvre pas une population pourtant connue.

---

## 13. Dette épistémique *(v3)*

Un `NON OBSERVÉ` n'a **pas de gravité absolue** ; sa gravité dépend de **la décision
concernée**. Une même inconnue peut être critique pour une décision et nulle pour une autre.

**Échelle NORMATIVE (v3.1)** — définitions, non plus simples étiquettes. Trois échelles
divergentes coexistaient (ce document : sans « moyenne » ; le manifeste d'implémentation : avec).
Réconciliation retenue — **cinq niveaux définis** :

| Niveau | Définition normative |
|---|---|
| **critique** | empêche une décision **irréversible** |
| **majeure** | empêche la validation d'un objectif de campagne, mais pas une décision réversible |
| **moyenne** | réduit significativement la confiance **sans** bloquer la décision |
| **mineure** | affecte seulement la précision ou la compréhension |
| **nulle** | sans effet sur la décision considérée |

Toute autre valeur est **invalide**. Sans ces définitions, deux personnes classent selon leur
intuition et l'échelle ne mesure rien.

**Dette critique — DÉMONTRABLE, jamais déclarée (v3.1).** Affirmer « critique » affirme qu'une
décision **irréversible** est bloquée. Cette irréversibilité exige sa propre justification :

```
debt: critique
critical_justification:
  decision:         <id de la decision bloquee>
  why_irreversible: <pourquoi un revert NE SUFFIT PAS>
  falsifier:        "montrer que la decision est reversible"
  max_acceptable_cost: <effort au-dela duquel on renonce a lever la dette>
```

`max_acceptable_cost` est **obligatoire**. Une dette critique peut coûter une heure ou dix-huit mois ;
sans ce champ, le protocole sait qu'une décision est bloquée mais ne sait pas **arbitrer** entre
lever la dette et renoncer à la décision. Au-delà de ce coût, la décision elle-même doit être
reconsidérée.

Une dette critique sans ces trois champs est **refusée**. La gravité elle-même reste auditée.

Format d'usage :
```
NON OBSERVÉ : <inconnu>
  Dette   : critique POUR <décision A> | majeure POUR <décision B> | nulle POUR <décision C>
  Bloque  : D<x>        (le nœud de décision du graphe que l'inconnu bloque)
```
Exemple : « protection GitHub » = mineure pour merger un document, potentiellement critique
pour une décision de durcissement sécurité. Le lecteur sait où concentrer son attention.

> Domaine : chaque item `NON OBSERVÉ` relié à au moins une décision nommée.
> Mode d'échec : noter une dette « en absolu » sans nommer la décision → recrée la gravité
> universelle qu'on cherche à éviter.
> Falsificateur : une même inconnue notée d'une seule gravité pour deux décisions d'enjeu
> manifestement différent.

---

## 14. Indice de robustesse méthodologique *(v3)*

Score de **qualité du processus**, **pas de vérité**. Il résume la solidité méthodologique
d'un rapport (observations par couverture, inférences par confiance, surclaims retirés,
présence de dette critique).

Trois garde-fous **obligatoires** — sans eux, l'indice devient un anti-indicateur (même
forme qu'un score de capacité Goodharté) :
- **A — Plafonnement par le pire** : une seule dette **critique** borne la note. Jamais de
  moyenne simple, qui masquerait le trou.
- **B — Dimension « couverture de la question »** : a-t-on cherché ce qui manque, ou seulement
  compté ce qu'on avait ? Un rapport peut être propre et répondre à la mauvaise question.
- **C — Jamais un critère de GO** : l'indice **informe**, il n'**autorise** aucune décision.
  Une décision découle des observations, pas de l'indice.

**Contraintes renforcées (v3.1)** — l'indice doit intégrer la **qualité**, pas seulement le nombre :
complétude · couverture · qualité des observations · **couverture de la question**.
Une dette **critique** interdit toute note supérieure à **C**, quel que soit le reste.
Jamais un gate, jamais une autorisation de décision.

> **Deux rapports de même note ne sont pas comparables s'ils répondent à des questions
> différentes.** L'indice mesure la qualité d'un processus, jamais l'importance de ce qu'il
> examine. Un `A` sur une question triviale vaut moins qu'un `C` sur une question décisive.
> Tout classement entre rapports est donc un **abus d'usage**.

> Domaine : rapports comportant plusieurs inférences.
> Mode d'échec : optimiser l'indice (empiler des observations triviales « complètes ») au
> lieu de l'épistémique — loi de Goodhart.
> Falsificateur : un rapport noté haut alors qu'une dette critique reste ouverte, ou que la
> question centrale n'a pas été couverte.

---

## 15. Principe de symétrie *(v3, normatif)*

Une preuve **favorable** et une preuve **défavorable** sont tenues au **même standard** de
couverture, de portée et de représentativité. C'est l'antidote structurel au biais de
confirmation.

Deux précisions :
- **Même standard ≠ même poids.** Une preuve défavorable faible et une preuve favorable
  faible sont discréditées **également** ; cela n'oblige pas à douter de tout à parts égales
  (ce serait de la fausse balance / « teach the controversy »).
- **Parité d'effort de recherche** : l'effort consacré à **chercher les réfutations** doit
  être comparable à celui consacré à **chercher les confirmations**. *Ne pas chercher* un
  réfutateur est déjà une asymétrie. Se branche sur le champ « falsificateur logique » : le
  test devient *« ai-je cherché mon falsificateur aussi fort que ma confirmation ? »*.

> Domaine : toute inférence porteuse d'un rapport.
> Mode d'échec : dérive en fausse balance (traiter une preuve faible comme égale à une forte).
> Falsificateur : une inférence dont les supports ont été cherchés mais dont le réfutateur
> nommé n'a fait l'objet d'aucune recherche.

---

## 16. UNKNOWN vs BLIND_SPOT — l'inconnue et l'angle mort *(v3.1)*

Deux absences d'observation, **deux actions différentes**. Les confondre conduit à chercher une
observation que rien ne peut produire.

| | **UNKNOWN** | **BLIND_SPOT** |
|---|---|---|
| Définition | l'observation **manque**, mais elle est observable avec l'instrumentation existante | l'observation est **impossible** : aucun instrument ne la produit |
| Action | **aller observer** | **construire l'instrument** |
| Champ requis en plus | — | `instrument_required` |

### Cycle de vie — construire l'instrument ne produit **jamais** une observation

```
BLIND_SPOT / NON_OBSERVABLE
      │  construire l'instrument
      ▼
BLIND_SPOT / OBSERVABLE          ← l'instrument existe, RIEN n'est encore observe
      │  reclassement OBLIGATOIRE
      ▼
UNKNOWN / NON_OBSERVE
      │  produire l'observation
      ▼
UNKNOWN / OBSERVE                = levee
```

**Le saut direct `BLIND_SPOT → OBSERVE` est INTERDIT.** Construire un instrument crée la
*possibilité* d'observer, jamais l'observation. L'état intermédiaire `OBSERVABLE` existe pour
rendre ce glissement causal impossible à écrire.

Statuts admis : `BLIND_SPOT` → `NON_OBSERVABLE | OBSERVABLE` · `UNKNOWN` → `NON_OBSERVE | OBSERVE`.
Tout autre couple est invalide.

> Domaine : toute absence d'observation portant sur une affirmation porteuse.
> Mode d'échec : classer en `UNKNOWN` ce qui est un angle mort — on cherche alors indéfiniment
> une observation qu'aucun instrument ne peut produire.
> Falsificateur : un `BLIND_SPOT` dont l'observation s'avère produite par un instrument existant.

---

## 17. Chapitre obligatoire — Dette épistémique résiduelle *(v3.1)*

Tout rapport porte ce chapitre. Une inconnue mentionnée dans un texte n'est **pas gouvernée** ;
une inconnue avec un identifiant, un genre, une dette, une décision bloquée et un moyen de
l'observer, l'est.

```
UNK-xxx
  kind                : UNKNOWN | BLIND_SPOT
  description         : ce qui manque
  status              : (selon le kind, cf. § 16)
  decision_blocked    : quelle decision, ou "aucune"
  how_to_observe      : l'action concrete qui leverait l'inconnue
  debt                : critique | majeure | moyenne | mineure | nulle
  reason              : pourquoi ce niveau de dette
  instrument_required : OBLIGATOIRE si kind = BLIND_SPOT
  critical_justification : OBLIGATOIRE si debt = critique (cf. § 13)
```

Un chapitre **vide** doit être justifié explicitement : « aucune inconnue résiduelle » est une
affirmation forte, rarement vraie.

---

## 18. Surface de garantie *(v3.1)*

Ce que le protocole — et son validateur — garantit, et ce qu'il ne garantit **pas**. Sans cette
frontière, on lui délègue une confiance qu'il ne porte pas.

| ✓ Garanti | ✗ Non garanti | **Comment augmenter cette garantie** |
|---|---|---|
| **classification** | la **vérité** d'un énoncé | confrontation à une source indépendante |
| **traçabilité** (supports, dépendances) | l'**absence d'erreur** | relecture adversariale ; audit croisé |
| **complétude structurelle** | la **cohérence sémantique** des champs | lint sémantique ; revue humaine |
| **graphe** (cycles, références) | la **qualité** des observations | exiger source + couverture + représentativité |
| **maillon faible** mécanique | la **qualité** du `how_to_observe` | bibliothèque d'exemples ; revue par un pair |
| `TERMINE` sans preuve → refusé | qu'une preuve soit *convaincante* | red-team sur les preuves |
| `BLIND_SPOT` sans instrument → refusé | que l'instrument soit *le bon* | valider l'instrument indépendamment |

La troisième colonne rend le protocole **évolutif** et non seulement descriptif : chaque non-garantie
nomme le chemin qui la réduirait.

**Conséquence.** Le protocole déplace le contrôle de la vigilance vers le mécanisme **pour tout ce
qui est structurel — et seulement pour cela**. Le jugement reste humain là où il compte.

---

## 19. Invariants opérationnels *(v3.1)*

Quatre règles nées d'échecs constatés, non d'anticipations théoriques. Chacune porte son précédent.

| ID | Règle | Précédent |
|---|---|---|
| **INV-ROI-001** | Tout travail doit rapprocher de l'objectif de campagne **ou** rendre sa mesure valide. Sinon : différé. | un outil de maintenance construit pendant un gel, dont le retour arrivait après la campagne |
| **INV-TRACE-001** | Le diff doit égaler **exactement** le contrat annoncé. | un ticket annonçant 1 fichier en ayant emporté 43 |
| **INV-HEALTH-001** | La santé de la suite de tests est un **état de référence mesuré**, pas un caveat. `observé > attendu` → FAIL. | une suite dont la collecte échouait, rendant tout « vert » non comparable |
| **INV-RESTORE-001** | Toute expérimentation destructive exige un point de restauration **vérifiable** (commit, stash vérifié, branche). La confiance dans le working tree n'est pas acceptée. | **deux** pertes de travail par le même mécanisme dans une même session |
| **INV-COVERAGE-001** *(v4.2)* | Toute **couverture** publiée porte son **plafond de confiance** mécanique. Un rapport plus affirmatif que son plafond contredit ses propres données. | deux couvertures déjà présentes dans le dépôt (composante `coverage` du CRI, `coverage_pct` du burn-in) citées comme des scores, sans qu'aucune conséquence n'en soit tirée ; puis un « 3 mesurées sur 234 » relégué en note de bas de page |
| **INV-POWER-001** *(v4.1)* | Toute conclusion d'**absence** d'effet est plafonnée tant que l'**effet minimal détectable** n'est pas publié. La puissance se lit **avant** la significativité. Une exigence de **volume** ne vaut pas une puissance. | **sept** instruments d'un même dépôt concluant sans publier ce qu'ils pouvaient détecter — dont un indice de préparation bâti sur quatre seuils de volume et aucune puissance |

> `INV-RESTORE-001` illustre la règle de formation : **une occurrence est un accident, deux sont une
> propriété du processus.** Une règle écrite après un incident unique est de la superstition.
>
> `INV-POWER-001` a été formé selon la même règle, mais par **inventaire** plutôt que par
> répétition temporelle : l'instance déclenchante était unique (un coefficient de corrélation nul
> lu comme une absence d'effet, sur un échantillon dont 45 % des observations partageaient une
> seule valeur et dont la résolution était de 0.25) ; c'est le balayage des dix-neuf instruments
> du dépôt qui a établi la propriété. **Sept instances mesurées en une passe valent deux
> occurrences séparées dans le temps** — et coûtent une journée de moins à constater.
>
> Corollaire lexical : « non significatif » et « pas d'effet » ne sont pas synonymes. Le premier
> est un résultat de test, le second une affirmation sur le monde. Le double filtre lexical (§ 7)
> doit refuser le second quand la puissance n'est pas publiée.

---

## 20. La couche TRANSFORMATION *(v4.0)*

Le protocole gouvernait les **conclusions**, les **observations** et les **instruments**.
Il ne gouvernait pas ce qui se passe **entre** une observation et une décision.

```
Observation ──► nettoyage ──► agregation ──► normalisation ──► metrique ──► Decision
                    ▲             ▲               ▲              ▲
                    └─────────────┴───────────────┴──────────────┘
                       CINQ transformations, jusqu'ici INVISIBLES
```

L'histoire des erreurs scientifiques est faite de transformations qui **changent le sens** des
données sans que rien ne le signale : un filtre qui écarte les valeurs « aberrantes » et supprime
précisément le phénomène étudié, une moyenne qui masque une bimodalité, une normalisation qui
détruit l'unité dans laquelle la décision se prend.

Une transformation n'est ni une observation (elle ne constate rien) ni une inférence (elle ne
déduit rien) : **c'est une opération qui altère ce sur quoi tout le reste repose.**

### Champs d'une transformation

```
TRANSFORMATION  T#
  operation              : ce que fait l'etape, en une phrase
  input / output         : ce qui entre, ce qui sort (avec leurs unites)
  information_loss       : ce qui devient IRRECUPERABLE apres cette etape
  assumptions_introduced : ce que l'etape SUPPOSE vrai sans le verifier
  reversibility          : reversible | partiellement | irreversible
  falsifier              : quelle observation montrerait que la transformation
                           trahit ses entrees
```

### Règles

1. **Toute chaîne observation → décision déclare ses transformations.** Une chaîne qui n'en déclare
   aucune affirme implicitement que la donnée n'a pas été touchée — affirmation forte, rarement vraie.
2. **Le maillon faible traverse les transformations.** Une transformation `irreversible` ou porteuse
   d'`assumptions_introduced` non vérifiées **plafonne** la confiance de tout ce qui est en aval,
   au même titre qu'une observation à couverture partielle (§ 3).
3. **Une perte d'information est un `UNKNOWN` par construction.** Ce qui est détruit à l'étape *k*
   n'est plus observable en aval : si la décision en dépend, c'est un `BLIND_SPOT` (§ 16), et
   l'instrument requis est *conserver la donnée avant transformation*.
4. **Les hypothèses introduites sont des Hypothèses au sens du § 2.3** — avec source de plausibilité
   et falsificateur expérimental. Une transformation en introduit souvent plus que son auteur ne croit.

### Exemple

```
TRANSFORMATION  T2
  operation   : agregation des PnL par trade en un PnL total
  input       : liste de PnL par trade (USD)   output : PnL total (USD)
  information_loss       : la DISTRIBUTION. Apres T2, impossible de distinguer
                           "10 petits gains" de "1 gros gain et 9 pertes"
  assumptions_introduced : que la somme est la statistique pertinente pour la
                           decision — faux si la decision porte sur le risque
  reversibility          : irreversible (la somme ne se decompose pas)
  falsifier              : exhiber deux distributions de meme somme menant a des
                           decisions opposees
```

> Domaine : toute chaîne où une observation ne sert pas directement de support, mais transite.
> Mode d'échec : déclarer les transformations triviales et manquer celle qui change le sens.
> Falsificateur : une décision invalidée par une transformation non déclarée en amont.

### 20.1 Type de transformation : PROJECTION entre populations *(v4.1)*

Les cinq transformations du § 20 (nettoyage, agrégation, normalisation, métrique, filtrage)
opèrent **à l'intérieur** d'une population. Il en existe une sixième, plus discrète, qui opère
**entre deux populations** : conclure sur A en s'appuyant sur ce qu'on a mesuré sur B.

```
Observation A                        Observation B
     │                                    │
     ▼                                    ▼
candidats non exécutés                trades exécutés
rendement à 24 h                      PnL réalisé sur ~6 h
     │                                    │
     └──────────────► PROJECTION ◄────────┘
                          │
                    ═════════════
                    RAPPROCHEMENT
                    ═════════════
                          │
                          ✗  ne devient PAS une preuve causale
```

Une projection n'est ni une observation (rien n'a été constaté sur la population cible) ni une
inférence ordinaire (le pas logique n'est pas déductif) : **c'est une hypothèse de transport**.
Elle introduit toujours au moins une supposition supplémentaire — que les deux populations sont
comparables sur la dimension qui porte la conclusion — et cette supposition est presque toujours
tacite.

```
TRANSFORMATION  P#   (type : PROJECTION)
  operation              : conclure sur la population CIBLE a partir de la population SOURCE
  source / cible         : les deux populations, avec leurs criteres de selection
  selection_difference   : ce qui distingue les deux ECHANTILLONNAGES, pas les deux mesures
  assumptions_introduced : "transportable sur la dimension X" — a enoncer, jamais a supposer
  information_loss       : aucune donnee n'est detruite ; c'est la GARANTIE qui est perdue
  reversibility          : sans objet — une projection ne se defait pas, elle se teste
  falsifier              : une mesure sur la population CIBLE elle-meme, meme petite
```

**Règles.**

1. **Une projection plafonne la conclusion au niveau `HYPOTHESE`**, quel que soit le volume de la
   population source. Dix-huit mille observations sur B ne produisent pas une observation sur A.
2. **La différence de sélection doit être écrite**, pas la différence de mesure. « Candidats
   bloqués » vs « trades exécutés » n'est pas une nuance de protocole : c'est deux populations
   choisies par des mécanismes différents, dont l'un est précisément le mécanisme étudié.
3. **Le falsificateur d'une projection est toujours disponible** : mesurer la cible. S'il n'est pas
   exécuté, la raison doit être écrite (coût, gel, autorité) — jamais implicite.
4. **Une projection non déclarée est le mode d'échec le plus coûteux du § 20**, parce qu'elle ne
   modifie aucune donnée : rien dans le pipeline ne la signale, et le lecteur voit deux mesures
   solides encadrant une conclusion qui n'appartient à aucune des deux.

**Exemple (précédent réel, 2026-07-29).**

```
TRANSFORMATION  P1   (type : PROJECTION)
  operation   : conclure que la politique de sortie tronque le signal d'entree
  source      : 18 716 candidats BLOQUES, rendement signe a 24 h, hors frais
  cible       : 121 trades EXECUTES, PnL realise, duree moyenne 5.92 h
  selection_difference   : la source est selectionnee par le blocage (meta/gate),
                           la cible par le passage des gates — le mecanisme de
                           selection EST l'objet de l'etude
  assumptions_introduced : que le rendement forward d'un candidat bloque est
                           transportable au trade execute correspondant
  falsifier              : rejouer les 121 executes contre le rendement a 24 h de
                           la MEME paire au MEME instant (population unique)
  statut                 : HYPOTHESE. Falsificateur disponible, NON execute
                           (gel scientifique + autorite operateur)
```

> Domaine : tout audit disposant de deux jeux de données pour une seule question.
> Mode d'échec : présenter un rapprochement quantifié comme une mesure, parce que les deux
> observations qui l'encadrent sont, elles, rigoureuses.
> Falsificateur de la règle elle-même : une projection dont le transport serait démontré par
> construction (échantillonnage aléatoire commun) — auquel cas ce n'en est plus une.

### 20.2 Le principe général : la garantie se détruit sans la donnée *(v4.2)*

Le § 20.1 est un cas particulier d'un énoncé plus large, et c'est probablement l'idée la plus
généralisable de ce protocole :

> **Une transformation non déclarée détruit la garantie attachée à une donnée sans détruire la
> donnée.**

C'est ce qui rend cette famille d'erreurs si difficile à voir : il n'y a **rien à constater**. Le
fichier est là, les nombres sont exacts, les tests passent. Ce qui a disparu est la chaîne qui
rendait ces nombres interprétables — la population dont ils viennent, la date à laquelle ils
valaient, l'unité dans laquelle ils se lisent, la question à laquelle ils répondaient.

Le principe ne dépend ni de ce dépôt ni du trading. Il vaut pour :

| Opération | Donnée conservée | Garantie détruite |
|---|---|---|
| agrégation | la somme, la moyenne | la distribution, donc le risque |
| filtrage | les lignes restantes | la représentativité de l'échantillon |
| sélection | les cas retenus | l'absence de biais de sélection |
| réduction dimensionnelle | les axes principaux | l'interprétabilité des axes d'origine |
| projection entre populations | les deux mesures | la validité du transport de l'une à l'autre |
| visualisation | la forme visible | l'échelle, l'incertitude, les cas écartés |
| résumé par un LLM | les phrases produites | la traçabilité vers la source, et ce qui a été omis |

Dans chaque ligne, un lecteur de bonne foi voit une donnée correcte et en tire une conclusion que
la donnée ne porte plus. **La garantie ne laisse pas de trou en partant** : c'est pourquoi elle doit
être déclarée en amont, jamais reconstituée en aval.

Conséquence opérationnelle : la déclaration ne suffit pas longtemps. Une transformation déclarée
reste une phrase ; une transformation **prouvée** porte des empreintes vérifiables.

```
TRANSFORMATION  T#   (champs de preuve, v4.2 — facultatifs mais recommandes)
  proof.input_sha256      : empreinte de chaque entree AU MOMENT de la lecture
  proof.tool_sha256       : empreinte du script qui a produit la sortie
  proof.output_sha256     : empreinte du corps produit, hors bloc de provenance
  proof.population        : loader, N, borne d'epoque
  proof.generated_at      : date de production, pour la fraicheur
```

Ce que ces empreintes prouvent : l'**identité des octets** et l'identité du producteur. Ce qu'elles
ne prouvent pas : la **justesse de l'opération**. Une transformation fausse, reproductible et
parfaitement tracée reste fausse — la preuve déplace la charge, elle ne l'annule pas. C'est le même
saut que « les tests passent » → « voici l'observation qui montre que les tests passent » : on ne
gagne pas la vérité, on gagne la possibilité de la contester.

> Domaine : toute chaîne où un artefact est relu par un autre outil que celui qui l'a produit.
> Mode d'échec : produire des empreintes que personne ne vérifie — la preuve devient décorative.
> Falsificateur : un artefact dont les empreintes concordent et dont la conclusion est fausse ;
> il montrerait que le contrôle porte sur la forme et jamais sur le fond, ce qui est **attendu** et
> doit rester écrit.

---

## 21. Historique des versions

| Version | Date | Nouveaux concepts |
|---|---|---|
| **v1.0** | 2026-07-23 | quatre catégories (Observation/Inférence/Hypothèse/Décision) ; maillon faible ; portée ; source/couverture ; double falsificateur ; double filtre lexical ; proportionnalité |
| **v2.0** | 2026-07-23 | composition/fermeture (DAG) ; graphe de dépendances + défaiteurs ; rétracter ≠ nier ; voir/croire/vouloir (guillotine de Hume) ; révisabilité mécanique |
| **v4.5** | 2026-07-30 | § 25 **EPREUVE ET GEL**. N'ajoute aucun mecanisme : une regle qui RESTREINT la croissance (§ 25.1, orthogonalite des axes — tout nouvel axe doit exhiber un defaut reel qu'aucun axe existant ne capture), une limite qui REDUIT une garantie affichee (§ 25.2, un auto-test prouve la coherence interne, jamais la validite externe), une famille explicitement NON promue en axe (§ 25.3, PERTINENCE — zero instance observee), et le gel (§ 25.4 : aucune v5 avant mesure de l'efficacite reelle des regles). Premier releve : 6 regles productives sur 14, 3 axes sur 6 ne rendent jamais FAIL, faux negatifs non mesurables |
| **v4.4** | 2026-07-30 | § 24 **VALIDITE** — cinquieme question : le mecanisme qui applique le protocole FONCTIONNE-t-il ? **INV-VALIDITY-001** (auto-test a cas negatifs obligatoire ; garantie derivee INVALIDE tant qu'il n'est pas passe ; VALIDITE evaluee AVANT adoption) ; § 24.1 la **dependance entre garanties doit etre modelisee** — sinon une racine cassee se presente comme quatre coches concordantes ; § 24.2 **INV-LEXICAL-001** : un usage ne se conclut jamais d'une presence lexicale, trois instances ; § 24.3 la **decision devient un artefact de premiere classe**, persistee, prouvee, epinglant ses entrees |
| **v4.3** | 2026-07-30 | § 23 **ADOPTION**, quatrieme question et cinquieme axe : peut-on croire que le protocole a ete APPLIQUE ? **INV-ADOPTION-001** (tout mecanisme publie son taux d'adoption ; 0 % equivaut a l'absence), forme sur deux adoptions nulles mesurees (bloc de preuve 0/2, couche TRANSFORMATION 0 declaration) ; § 23.1 **deux plafonds** distincts (couverture vs maillon faible) avec l'action que chacun implique ; **INV-PROOF-001** : constructeur unique du bloc de preuve, extrapolation assumee d'une propriete de classe deja demontree deux fois |
| **v4.2** | 2026-07-30 | § 20.2 **principe général** : une transformation non déclarée détruit la garantie sans détruire la donnée (agrégation, filtrage, sélection, réduction, projection, visualisation, résumé par LLM) ; **champs de preuve** d'une transformation (empreintes entrée/outil/sortie + population + date) — la déclaration devient contestable ; **INV-COVERAGE-001** (§ 19) : toute couverture publiée porte son plafond de confiance mécanique ; propagation du maillon faible **entre critères d'audit**, pas seulement entre observations |
| **v4.1** | 2026-07-29 | type de transformation **PROJECTION entre populations** (§ 20.1) : conclure sur A en mesurant B est une *hypothèse de transport*, plafonnée à `HYPOTHESE`, dont le falsificateur est toujours disponible ; **INV-POWER-001** (§ 19) : la puissance se lit avant la significativité, et un seuil de volume n'est pas une puissance ; règle de formation étendue — *N instances mesurées en une passe* valent *deux occurrences séparées dans le temps* |
| **v4.0** | 2026-07-27 | couche **TRANSFORMATION** : les operations entre observation et decision deviennent gouvernees (perte d'information, hypotheses introduites, reversibilite, falsificateur) ; surface de garantie evolutive (3e colonne) ; `max_acceptable_cost` sur dette critique ; non-comparabilite des indices |
| **v3.1** | 2026-07-27 | trois niveaux gouvernés (conclusions/observations/instruments) ; `UNKNOWN` vs `BLIND_SPOT` + cycle de vie interdisant le saut direct ; échelle de dette **normative** réconciliée (5 niveaux définis) ; dette critique **démontrable** ; chapitre obligatoire de dette résiduelle ; surface de garantie ; 4 invariants opérationnels ; indice plafonné par la pire dette |
| **v3.0** | 2026-07-24 | représentativité (échantillon/population, `NON ÉVALUABLE`, biais directionnels) ; plafond « état mutable » ; dette épistémique relative à une décision ; indice de robustesse méthodologique (3 garde-fous) ; principe de symétrie (parité d'effort de recherche) |

Compatibilité : v3 est **additive**. Aucune section v1/v2 n'a été supprimée ni renommée ;
les nouveaux champs (§ 2.1) et sections (§ 12–§ 15) s'ajoutent sans casser un rapport v2.

---

## 22. Pourquoi cette évolution existe (auto-audit de l'évolution)

Le protocole s'applique à sa propre évolution. v2 **garantissait la qualité des affirmations**
mais pas celle des **observations** elles-mêmes : une observation exacte pouvait être peu
représentative (§ 12) ; les inconnues étaient traitées à gravité égale (§ 13) ; aucun résumé
de qualité de processus n'existait (§ 14) ; le biais de confirmation n'était pas interdit
explicitement (§ 15) ; et rien n'empêchait un `certain` sur un état mutable (§ 3).

Chaque ajout v3 est présenté comme une **hypothèse méthodologique**, avec son domaine, son
mode d'échec et son falsificateur — donc réfutable. v3 ne se déclare pas « meilleure » : elle
est plus riche **et** plus exposée à la critique, ce qui est la propriété recherchée. Si l'un
des cinq ajouts alourdit un audit sans réduire les surclaims, la règle de proportionnalité
(§ 6) impose de le retirer : le protocole reste, jusque dans son évolution, soumis à
lui-même.

---

## 23. ADOPTION — la quatrième question *(v4.3)*

Au début de cette campagne, le protocole répondait à une seule question : **peut-on croire cette
conclusion ?** Il en répond aujourd'hui à quatre, et la dernière n'existait pas il y a trois jours.

| # | Question | Ce qui y répond |
|---|---|---|
| 1 | Peut-on croire la **donnée** ? | population, provenance, borne d'époque |
| 2 | Peut-on croire l'**instrument** ? | puissance, résolution, unité d'échantillonnage |
| 3 | Peut-on croire la **transformation** ? | § 20, empreintes, projection déclarée |
| 4 | Peut-on croire que le **protocole a été appliqué** ? | **adoption** |

Les trois premières portent sur un objet de la chaîne de mesure. La quatrième porte sur le
protocole lui-même, et c'est ce qui la rend structurellement différente : elle mesure l'écart entre
ce qui est **défini** et ce qui est **utilisé**.

**INV-ADOPTION-001.** *Tout mécanisme défini par le protocole publie son taux d'adoption réel.*
Un mécanisme parfait avec 0 % d'adoption équivaut à son absence.

Précédent (deux instances mesurées le 2026-07-30, pas une anticipation) : le bloc de preuve
existait depuis la veille et **aucun** artefact ne le portait ; la couche TRANSFORMATION introduite
en v4.0 n'avait **aucune** déclaration dans le code trois jours après son écriture — ses champs
n'apparaissaient que dans ce document et dans le manifeste. Deux mécanismes, deux adoptions nulles,
et aucune règle ne l'avait signalé.

> **Risque de gouvernance que cet axe surveille** : multiplier les mécanismes plus vite que leur
> adoption. Un protocole qui grossit sans se diffuser produit exactement l'inverse de son but — il
> donne l'impression que les garanties existent, parce qu'elles sont *écrites*.

**Corollaire d'indépendance.** ADOPTION n'est jamais invalidé par la propagation (§ 3 généralisée
aux audits). « Ce producteur passe-t-il par l'API ? » reste une question sensée même si sa
population est mauvaise, alors que « quelle est sa puissance ? » ne l'est plus. C'est ce qui en fait
un cinquième axe et non une cinquième conséquence.

**Deux mesures d'adoption, jamais moyennées** : au niveau du **code** (le producteur a-t-il
l'intention de prouver) et au niveau de l'**artefact** (le fichier sur le disque est-il prouvé).
Elles divergent dès qu'un producteur corrigé n'a pas régénéré sa sortie — et cette divergence est
une information, pas un bruit.

### 23.1 Deux plafonds, deux actions *(v4.3)*

Un plafond de confiance unique cache l'information la plus utile : **que faire**.

| Plafond | Question | Action si c'est lui qui contraint |
|---|---|---|
| **couverture** | combien ai-je mesuré ? | **mesurer plus** — ce qui est mesuré est sain |
| **maillon faible** | quel est mon pire élément ? | **corriger** — mesurer plus n'aidera pas |

Le plafond final est le plus contraignant des deux (§ 3), mais il doit être publié **avec** les deux
composantes et avec la raison qui désigne le contraignant. Exemple réel du 2026-07-30 : couverture
MOYENNE, maillon faible AUCUNE, final AUCUNE — *contraint par le maillon faible, mesurer plus
n'aidera pas*. Sans la décomposition, un lecteur diligent aurait pu conclure qu'il fallait étendre
la couverture, c'est-à-dire exactement la mauvaise action.

> Domaine : tout rapport qui agrège plusieurs contrôles hétérogènes.
> Mode d'échec : publier une adoption élevée sur un dénominateur choisi après coup.
> Falsificateur : un mécanisme à 100 % d'adoption dont les défauts qu'il devait prévenir
> continuent d'apparaître — l'adoption serait alors mesurée sur la forme et non sur l'usage.

---

## 24. VALIDITÉ — le mécanisme mesure-t-il ce qu'il affirme mesurer ? *(v4.4)*

Le § 23 ajoutait une quatrième question : *le protocole a-t-il été appliqué ?* Une cinquième lui
manquait, et elle est plus dérangeante :

> **Le mécanisme qui applique le protocole fonctionne-t-il ?**

Un mécanisme peut être **adopté**, **exécuté**, **parfaitement traçable** — et incapable de détecter
ce qu'il prétend détecter. Ce n'est ni un problème de population, ni de puissance, ni de
transformation, ni d'adoption. C'est un problème de **validité de l'instrument**.

**Précédent (2026-07-30, trouvé par attaque adversariale).** Le mécanisme de preuve venait d'être
livré. `output_sha256` absent faisait sauter *silencieusement* le contrôle du corps, et l'audit de
chaîne certifiait « corps inchangé » avec un plafond COMPLETE ; un bloc forgé réduit à deux champs
obtenait `PREUVE = ok`. Pendant ce temps, l'axe ADOPTION annonçait **1/1 = 100 %**.

```
Coverage   ✓          ┐
Adoption   ✓          │  quatre coches vertes
Proof      ✓          │  une garantie nulle
Chain      ✓          ┘
```

**INV-VALIDITY-001.** *Tout mécanisme de garantie publie le résultat d'un auto-test comportant des
cas NÉGATIFS, et toute garantie qui en dérive est INVALIDE tant que cet auto-test n'est pas passé.*

Un auto-test uniquement composé de cas positifs valide un mécanisme qui ne détecte rien : il faut
des artefacts **dont on sait qu'ils sont altérés** et que le mécanisme doit refuser. Le test du test
est simple : casser volontairement le mécanisme doit faire **tomber** son auto-test.

### 24.1 La dépendance doit être modélisée, pas supposée

Plusieurs indicateurs peuvent afficher un statut positif alors qu'ils reposent tous sur le même
composant :

```
create_proof
      ↓
verify_provenance
      ↓
chain_audit
      ↓
adoption
```

Tant que cette dépendance n'est pas **écrite**, une défaillance de la racine se présente comme
quatre garanties indépendantes et concordantes — la pire configuration possible, parce que la
concordance est lue comme une corroboration (§ 4, *illusion de convergence*). Modélisée, la même
défaillance rend un seul verdict : `MÉCANISME_INVALIDE`, et **aucune** coche verte.

**Ordre d'évaluation normatif : VALIDITÉ avant ADOPTION.** Un taux d'adoption élevé d'un mécanisme
cassé est *pire* qu'une adoption nulle.

### 24.2 Usage ≠ mention *(INV-LEXICAL-001)*

> **Aucun audit ne peut conclure à un USAGE sur la seule présence d'un identifiant lexical.**

Trois occurrences de la même faute, sur le même outil, en deux jours : `json.dump` capturant
`json.dumps` ; un chemin de dataset *nommé* dans une déclaration compté comme une *lecture* ;
`attach_proof` mentionné dans une docstring — y compris dans une phrase qui **nie** l'usage —
comptant comme un appel.

La parade n'est pas un motif plus fin, c'est de **changer d'instrument** : un arbre syntaxique
distingue un appel d'un mot, une expression régulière jamais. Les critères qui cherchent une
*déclaration* (unité d'échantillonnage, population consommée) restent lexicaux à dessein — ils
mesurent une intention écrite, pas un comportement.

### 24.3 La décision devient un artefact de première classe *(v4.4)*

Dernier maillon : une chaîne pouvait être entièrement correcte et **perdre sa sortie**. « Quelle
preuve soutenait cette décision du 28 juillet ? » n'avait aucune réponse automatique — le verdict
partait sur la sortie standard.

```
Décision ──► artefact persisté ──► preuve ──► vérification
```

La preuve d'une décision **épingle les empreintes de ses entrées**. Relire une décision archivée,
c'est donc retrouver l'état exact des données qui la soutenaient — et toute altération ultérieure
de ces entrées devient visible à la relecture. Un journal en append conserve l'historique : sans
lui, la décision du 28 serait déjà écrasée par celle du 29.

> Domaine : tout système où plusieurs garanties dérivent d'un composant commun.
> Mode d'échec : un auto-test complaisant, composé de cas que le mécanisme passe par construction.
> Falsificateur : casser délibérément le mécanisme ; si l'auto-test passe encore, il ne teste rien.

---

## 25. Épreuve — et gel du protocole *(v4.5)*

Le protocole est passé de 17 à 25 sections en une semaine. Chaque ajout se
justifiait isolément par un incident constaté ; leur somme crée le risque inverse
de celui du départ : **que le protocole devienne plus complexe que les phénomènes
qu'il gouverne**.

Cette section n'ajoute donc aucun mécanisme. Elle en ajoute une règle qui en
**restreint** la croissance, une limite qui **réduit** une garantie affichée, et
une famille explicitement **non promue** en axe.

### 25.1 Règle d'orthogonalité des axes

> **Tout nouvel axe doit démontrer qu'il capture une famille de défaillances
> qu'aucun axe existant ne pouvait exprimer.**

La démonstration exige un **cas concret** : un défaut réel que les axes en place
laissent passer ou classent mal. Sans lui, l'axe proposé décrit une deuxième fois
un phénomène déjà couvert, et le protocole grossit sans gagner de pouvoir de
détection.

Précédent d'application (2026-07-30) : `output_sha256` absent n'était ni un
problème de population, ni de puissance, ni de transformation, ni d'adoption —
un mécanisme adopté, exécuté et traçable ne détectait rien. VALIDITY a été créé
sur ce cas, pas sur une intuition de complétude.

Contre-exemple (même jour) : « la pertinence de la question » n'a pas été promue
en axe, faute d'instance observée — voir § 25.3.

### 25.2 Ce qu'un auto-test ne prouve pas

`INV-VALIDITY-001` exige un auto-test à cas négatifs. C'est une avancée, et sa
portée doit être écrite avec elle :

> Un auto-test prouve une **cohérence interne**, jamais une **validité externe**.

```
create_proof  ──┐
verify_provenance ├── même modèle de preuve
self_test     ──┘        │
                         └─► une erreur PARTAGÉE par les trois passe inaperçue
```

Ce que l'auto-test élimine réellement : la **régression** — un composant qui
cesse de faire ce que les autres supposent. Ce qu'il ne peut pas éliminer : une
erreur conceptuelle commune. La seule parade connue est **extérieure au
système** : une attaque adversariale, qui a effectivement trouvé deux défauts que
l'auto-test n'aurait jamais vus, puisqu'il aurait été écrit avec le même angle
mort.

### 25.3 PERTINENCE — famille candidate, PAS un axe

Tous les instruments construits répondent à *« peut-on faire confiance à ce
résultat ? »*. Une question de niveau supérieur reste sans instrument :

> **Fallait-il mesurer cela ?**

Un outil peut être traçable, reproductible, statistiquement puissant, valide et
adopté à 100 % — et répondre à une question qui n'est pas celle du problème réel.
Ce n'est ni POPULATION, ni POWER, ni TRANSFORMATION, ni INDEPENDENCE, ni
VALIDITY, ni ADOPTION : cela relève du **choix de la question scientifique**.

**Statut : famille CANDIDATE.** Conformément au § 25.1 et à la règle de formation
(§ 19), elle n'est pas promue en axe : *zéro instance constatée et documentée*.
Ce qui la ferait promouvoir : un cas réel où un instrument irréprochable sur les
six axes a produit un travail sans valeur parce que la question était mal posée.

Note d'honnêteté : le projet a probablement déjà croisé cette famille sans
l'instruire — l'audit du score a mesuré une corrélation là où la question utile
portait sur l'horizon. Ce précédent est **cité mais non compté** : il a été
reconstruit après coup, et une instance reconstruite n'est pas une instance
observée.

### 25.4 Gel : aucune v5 avant l'épreuve

> **Le facteur limitant n'est plus la conception du protocole, mais son épreuve
> sur le terrain.**

Aucune version majeure ne sera ouverte avant d'avoir mesuré, sur des audits
réels : quelles règles détectent effectivement des défauts, lesquelles ne
produisent jamais d'information, quels faux positifs elles coûtent, et — le plus
difficile — quels faux **négatifs** elles laissent passer.

Le premier relevé (`tools/protocol_efficacy_audit.py`, 2026-07-30) est
inconfortable et doit le rester :

| Constat | Valeur |
|---|---|
| règles PRODUCTIVES (≥ 1 détection réelle) | 6 sur 14 |
| règles jamais liées | 4 |
| règles liantes n'ayant jamais rien détecté | 4 |
| axes ne rendant **jamais** FAIL | 3 sur 6 |
| décisions réellement changées | 7, par 5 règles |
| faux **négatifs** | **non estimés** — voir § 25.5 |

Un axe qui ne rend jamais FAIL ne sépare rien : il ne distingue pas un dépôt sain
d'un critère qui ne mord pas. Ces trois-là sont les premiers candidats au retrait
si la campagne empirique ne leur fait rien trouver.

### 25.5 Les faux négatifs sont non estimés, pas inobservables

Formulation corrigée le 2026-07-30. Écrire « inobservables » fermait
prématurément l'espace des méthodes — exactement la faute que ce protocole
cherche à empêcher ailleurs.

Ce qui est vrai : **aucun instrument ne les estime aujourd'hui.** Un défaut
qu'aucune règle n'a cherché ne laisse aucune trace dans le registre d'efficacité.

Ce qui est faux : qu'il n'existe aucun moyen d'en approcher le taux. Au moins
quatre pistes n'ont pas été essayées, et aucune n'est exclue :

| Méthode | Ce qu'elle bornerait | Coût pressenti |
|---|---|---|
| **injection contrôlée** de défauts connus dans un dépôt de test | taux de détection sur une famille choisie | faible, mais ne borne que les familles injectées |
| **jeux de cas synthétiques** couvrant chaque axe | sensibilité de chaque règle prise isolément | moyen ; risque de tester ce qu'on a déjà en tête |
| **audit indépendant ciblé** par un tiers | angles morts propres à l'auteur | élevé ; le seul à sortir du point de vue de l'auteur |
| **campagne adversariale** | défauts qu'aucune règle ne cherche | mesuré : 12 défauts en une passe |

Seule la dernière a produit quelque chose à ce jour. C'est un argument pour la
garder, **pas** pour déclarer les trois autres inutiles : une seule instance ne
départage pas quatre méthodes.

`UNKNOWN`, pas `BLIND_SPOT` (§ 16) : l'instrument requis n'existe pas encore,
mais rien ne montre qu'il ne peut pas exister.

### 25.6 Critère de sortie du gel

**Ni une date, ni un nombre d'itérations.** Le gel se lève quand le registre
d'efficacité porte assez d'observations pour que les décisions de retrait ou de
conservation soient fondées sur des données plutôt que sur des impressions.

Concrètement, trois conditions — aucune n'est une échéance :

1. les quatre règles `JAMAIS_LIÉE` ont **rencontré ou non** leur cas, et on sait
   dire lequel ;
2. les trois axes qui ne rendent jamais FAIL ont soit produit un FAIL, soit été
   éprouvés sur un dépôt où ils auraient dû en produire un ;
3. au moins une méthode d'estimation des faux négatifs (§ 25.5) a été essayée.

**Indicateur de maturité, à surveiller pendant la campagne :** si elle conduit
principalement à **retirer, simplifier ou fusionner** des règles plutôt qu'à en
ajouter, le protocole aura atteint une maturité réelle. Si elle produit surtout
de nouveaux axes, c'est le signe que la complexité croît encore — et que ce qui
est mesuré n'est pas ce qui manque.

> Domaine : tout protocole méthodologique qui grossit plus vite qu'il n'est éprouvé.
> Mode d'échec : mesurer l'activité d'une règle (combien de fois elle s'exécute)
> et la lire comme son utilité (combien de fois elle a évité une erreur).
> Falsificateur : une règle classée `JAMAIS_LIEE` qui, retirée, laisse passer un
> défaut réel — elle prouverait que l'absence de déclenchement était l'effet, et
> non l'inutilité.
