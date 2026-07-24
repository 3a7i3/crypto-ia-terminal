# Protocole d'audit épistémique

- **Version** : 3.0
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

**Biais** : chaque biais nommé indique sa **direction** — *gonfle l'inférence* ou *réduit
l'inférence*. Jamais « biais possibles » sans direction (une liste sans direction est
infalsifiable). Une représentativité insuffisante plafonne la confiance aval (§ 3).

> Domaine : toute observation servant de support à une inférence porteuse.
> Mode d'échec : exiger un dénominateur là où la population est légitimement inconnue —
> il faut alors écrire `NON ÉVALUABLE`, pas bloquer l'audit.
> Falsificateur : une inférence porteuse tenue pour valide alors que son échantillon ne
> couvre pas une population pourtant connue.

---

## 13. Dette épistémique *(v3)*

Un `NON OBSERVÉ` n'a **pas de gravité absolue** ; sa gravité dépend de **la décision
concernée**. Une même inconnue peut être critique pour une décision et nulle pour une autre.

Échelle : **Critique / Majeure / Mineure / Nulle**. Format :
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

## 16. Historique des versions

| Version | Date | Nouveaux concepts |
|---|---|---|
| **v1.0** | 2026-07-23 | quatre catégories (Observation/Inférence/Hypothèse/Décision) ; maillon faible ; portée ; source/couverture ; double falsificateur ; double filtre lexical ; proportionnalité |
| **v2.0** | 2026-07-23 | composition/fermeture (DAG) ; graphe de dépendances + défaiteurs ; rétracter ≠ nier ; voir/croire/vouloir (guillotine de Hume) ; révisabilité mécanique |
| **v3.0** | 2026-07-24 | représentativité (échantillon/population, `NON ÉVALUABLE`, biais directionnels) ; plafond « état mutable » ; dette épistémique relative à une décision ; indice de robustesse méthodologique (3 garde-fous) ; principe de symétrie (parité d'effort de recherche) |

Compatibilité : v3 est **additive**. Aucune section v1/v2 n'a été supprimée ni renommée ;
les nouveaux champs (§ 2.1) et sections (§ 12–§ 15) s'ajoutent sans casser un rapport v2.

---

## 17. Pourquoi cette évolution existe (auto-audit de l'évolution)

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
