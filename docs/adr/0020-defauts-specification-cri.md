# ADR-0020 — Défauts de spécification du CRI : plancher PSI et dénominateur de couverture

- **Statut** : **Proposé — non signé.** Aucune option n'est retenue par cet ADR.
- **Date** : 2026-08-11
- **Auteur** : rédigé par assistance, à valider par l'opérateur
- **Contexte** : Deux composantes du Calibration Readiness Index défini par
  l'ADR-0011 rendent le gate `CRI >= 90` structurellement inatteignable, pour
  des raisons indépendantes de la qualité du système de trading.

---

## Contexte

Mesure du 2026-08-11 sur le dataset de production
(`python3 tools/cri_calculator.py --provenance`) :

```json
{
  "cri": 40.05,
  "gate_ready": false,
  "n_clean": 251,
  "n_regrets_clean": 55074,
  "clean_data_since": "2026-07-17T01:30:00+00:00",
  "sub_scores": {
    "n_score": 50.2, "coverage_score": 40.0,
    "drift_score": 0.0, "balance_score": 70.0
  },
  "validity": "OK"
}
```

Le CRI est la moyenne non pondérée des quatre sous-scores (poids 25/25/25/25,
ADR-0011). Une composante à zéro coûte donc 25 points sur 100, et plafonne
mécaniquement le total à 75.

L'enquête menée pour identifier le facteur limitant a établi que **deux des
quatre composantes ne mesurent pas ce qu'elles prétendent mesurer**.

---

## Le problème de méthode, à traiter avant toute correction

L'ADR-0011 a **pré-enregistré** la définition du CRI :

> Les quatre sous-scores et leurs poids sont définis et gelés **avant** que le
> dataset propre n'atteigne un effectif significatif (N=24 au moment de cet
> ADR) — condition nécessaire pour que la définition ne soit pas influencée
> par la valeur qu'elle produirait.

Modifier cette définition maintenant, après avoir constaté qu'elle produit 40
et bloque le gate, est **exactement ce que le pré-enregistrement interdit**.
Le nier serait malhonnête ; l'ignorer viderait l'ADR-0011 de son sens.

La ligne de partage proposée est la suivante :

> Une correction est légitime si et seulement si le défaut se démontre
> **sans référence à la valeur produite sur les données réelles** — c'est-à-dire
> sur des données synthétiques, ou par lecture du code seul.

Les deux constats ci-dessous satisfont ce critère : le premier se reproduit
sur des distributions fabriquées, le second se lit dans le code sans ouvrir
le moindre fichier de données. Aucun des deux n'a été identifié en cherchant
« comment faire monter le CRI ».

Toute correction qui ne satisferait pas ce critère relèverait du p-hacking et
doit être refusée, y compris si elle paraît raisonnable.

---

## Constat 1 — `drift_score` : plancher epsilon dans `_psi`

### Mécanisme

`tools/cri_calculator.py` calcule le PSI entre la première et la seconde
moitié du dataset, sur 5 cases de largeur égale bornées par le min et le max
globaux. Les cases vides sont plancherées :

```python
return [max(c, 1e-6) / total for c in counts]
```

Une case vide d'un côté vaut donc `1e-6/125 ≈ 8e-9` au lieu de 0. Si la même
case est correctement peuplée de l'autre côté, le rapport de logarithmes
explose : `log(0,111 / 8e-9) ≈ 16,4`.

### Démonstration indépendante des données réelles

Sur distributions synthétiques, avec le code de `_psi` inchangé :

| Scénario | PSI | `drift_score` |
|---|---|---|
| Deux tirages de la même loi (bruit d'échantillonnage seul) | 0,02 – 0,18 | 82 – 98 |
| Une valeur aberrante redéfinissant les bornes des cases | 0,11 | 89 |
| Déplacement réel du centre de +5 points | 9,5 | **0** |
| Resserrement net de la dispersion | 14,9 | **0** |

Le bruit ne produit pas zéro. Une case vide correctement peuplée en face, si.

### Constat sur les données de production

Décomposition mesurée le 2026-08-11 (bornes `[64,0 ; 82,0]`, cases de 3,60) :

| Case | 1re moitié | 2e moitié | Contribution PSI |
|---|---|---|---|
| [64,0 – 67,6) | 14 | 7 | 0,040 |
| [67,6 – 71,2) | 25 | 25 | 0,000 |
| [71,2 – 74,8) | 61 | 41 | 0,066 |
| [74,8 – 78,4) | 25 | 45 | 0,091 |
| **[78,4 – 82,0)** | **0** | **8** | **1,009** |
| | | **total** | **1,205** |

**Huit trades sur 251**, dans une case vide de l'autre côté, produisent 84 %
du PSI et mettent à zéro un quart du CRI.

Sans le terme de la case vide, PSI = 0,197 — zone « décalage modéré » selon la
convention usuelle (0,10 – 0,25) — soit `drift_score ≈ 80`.

Les statistiques descriptives confirment l'absence de dérive réelle :

| | n | min | q1 | médiane | q3 | max | σ |
|---|---|---|---|---|---|---|---|
| 1re moitié (07-17 → 07-30) | 125 | 64,0 | 71,0 | **72,0** | 73,0 | 77,0 | 2,82 |
| 2e moitié (07-30 → 08-11) | 126 | 64,0 | 71,0 | **72,0** | 75,0 | 82,0 | 3,33 |

Minimum, premier quartile et médiane identiques. Seule la queue haute s'est
étendue — le système a trouvé quelques configurations mieux notées, ce qui
est vraisemblablement une amélioration, et qui est comptabilisé comme une
instabilité catastrophique.

---

## Constat 2 — `coverage_score` : dénominateur incluant des cellules interdites

### Mécanisme

`coverage_score` compte les cellules `régime × palier de score` ayant au moins
5 observations, sur un dénominateur `régimes_observés × 5`. Les paliers sont
fixes : `["<50", "50-59", "60-69", "70-79", "80+"]`.

Or le collecteur de regret écarte à la source toute observation sous un seuil :

```python
observability/regret_scheduler.py:47   _MIN_SCORE = float(os.getenv("REGRET_MIN_SCORE", "60"))
observability/regret_scheduler.py:293  if obs.score < _MIN_SCORE:
```

Valeur en production : **65** (`.env` du VPS ; défaut du code : 60 — écart
documenté par ailleurs, sans justification connue à ce jour).

**Les paliers `<50` et `50-59` ne peuvent donc jamais être peuplés, pour aucun
régime.** Ils comptent pourtant au dénominateur. Ce constat se lit dans le
code seul, sans ouvrir aucune donnée.

### Constat sur les données de production

```
régime                     <50   50-59   60-69   70-79    80+
bear_trend                   .       .   21057   16254      6
bull_trend                   .       .       .    8426    335
high_volatility_regime       .       .    6997       1      .
sideways                     .       .    2250      12      .
unknown                      .       .       5      13      .

cellules >= 5 observations : 10/25  ->  coverage_score = 40,0
```

Les deux premières colonnes sont vides sur les cinq régimes : **10 cellules
sur 25 sont structurellement invidables**. Avec 55 074 enregistrements de
regret, ce n'est pas un problème de volume.

Plafond mathématique de `coverage_score` : **60/100**.

Les 5 cellules atteignables non couvertes sont par ailleurs peu prometteuses
(`bull_trend`/60-69 : 0 ; `high_volatility`/70-79 : 1 ; `high_volatility`/80+ :
0 ; `sideways`/80+ : 0 ; `unknown`/80+ : 0). Un signal à 80+ en marché plat est
intrinsèquement rare : un plafond pratique autour de 50 est plus vraisemblable
que 60.

Note secondaire : le régime `unknown` totalise 18 observations et occupe
néanmoins 5 cellules du dénominateur. C'est une défaillance de classification
qui dilue la métrique.

---

## Conséquence combinée : le gate est inatteignable

| Scénario | n_score | coverage | drift | balance | CRI |
|---|---|---|---|---|---|
| Mesuré le 2026-08-11 | 50,2 | 40,0 | 0,0 | 70,0 | **40,05** |
| + 500 trades, rien d'autre corrigé | 100 | 40,0 | 0,0 | 100 | **60,0** |
| + PSI corrigé | 100 | 40,0 | 80,3 | 100 | **80,1** |
| + toutes cellules atteignables couvertes | 100 | 60,0 | 80,3 | 100 | **85,1** |
| Optimum absolu (PSI rigoureusement nul) | 100 | 60,0 | 100 | 100 | **90,0** |

Le gate `CRI >= 90` n'est atteint que dans la dernière ligne, laquelle exige un
PSI **rigoureusement nul** entre deux moitiés de dataset — c'est-à-dire deux
distributions strictement identiques, ce qui n'arrive pas en marché réel.

**Aucun volume de collecte ne peut ouvrir ce gate en l'état.** C'est un défaut
de spécification, pas une insuffisance de données.

---

## Options soumises à l'opérateur

Aucune n'est retenue par cet ADR.

### Défaut 1 — `_psi`

| Option | Effet | Compromis |
|---|---|---|
| **1A** — plancher epsilon conventionnel (`0,0001`, ou Laplace `0,5/n`) | `drift` 0 → ~80 | Correctif minimal, mais garde des cases de largeur égale sur min/max, sensibles aux valeurs extrêmes |
| **1B** — cases par quantiles de la distribution de référence | supprime le problème à la racine | Change davantage la définition ; pratique standard en PSI |
| **1C** — ne rien changer | — | Acte que le CRI est inexploitable dès qu'une queue de distribution évolue |

### Défaut 2 — `coverage_score`

| Option | Effet | Compromis |
|---|---|---|
| **2A** — aligner les paliers sur `REGRET_MIN_SCORE` (supprimer du dénominateur les paliers inatteignables) | plafond 60 → 100 | Le dénominateur devient dépendant d'une variable d'environnement ; tout changement de `REGRET_MIN_SCORE` redéfinit la métrique |
| **2B** — abaisser `REGRET_MIN_SCORE` pour peupler réellement les paliers bas | paliers atteignables | **Change l'époque** : les observations d'avant et d'après ne forment plus une population unique (cf. ADR-0017). Coûteux |
| **2C** — dénominateur fondé sur les cellules **observables**, calculé à partir du seuil actif et consigné dans le rapport | plafond 100, traçable | Demande de journaliser le seuil actif dans la sortie du CRI |
| **2D** — ne rien changer | — | Le gate reste inatteignable |

### Question annexe — régime `unknown`

Le fusionner, l'exclure du dénominateur, ou corriger la classification en
amont. Effet sur `coverage_score` : neutre à l'instant T (10/25 et 8/20 valent
tous deux 40), non neutre ensuite.

---

## Ce que cet ADR ne décide pas

- Il ne modifie aucun seuil, aucune formule, aucun fichier de code.
- Il ne justifie pas la valeur `REGRET_MIN_SCORE=65`, inconnue à ce jour.
- Il ne se prononce pas sur le maintien ou le déplacement de
  `CLEAN_DATA_SINCE_V4`.

---

## Conséquences

**Positives**

- Le facteur limitant du burn-in est identifié et chiffré : ce n'est ni le
  volume, ni la qualité du système de trading.
- Toute décision de calibration prise sur la foi du CRI actuel aurait reposé
  sur deux composantes fausses.

**Négatives / compromis**

- Corriger une métrique pré-enregistrée après avoir vu son résultat expose au
  soupçon de p-hacking, quelle que soit la qualité de la justification. Le
  critère de légitimité posé plus haut est une réponse à ce risque, pas une
  garantie.
- Tant qu'aucune option n'est retenue, le burn-in continue d'alimenter un
  indicateur dont deux composantes sur quatre sont invalides.

**Règles induites (si une option est retenue)**

- La sortie de `tools/cri_calculator.py` doit consigner le seuil
  `REGRET_MIN_SCORE` actif et le plafond de `coverage_score` qu'il implique.
- Toute modification ultérieure de `REGRET_MIN_SCORE` doit être traitée comme
  un changement d'époque, au même titre qu'un changement d'univers (ADR-0017).
- La correction retenue doit être datée, et le CRI d'avant et d'après ne doit
  jamais être comparé sans mention explicite du changement de définition.

---

## Limitations de cette rédaction

Établi par mesure directe sur le dataset de production et par lecture du code.
Non établi : la raison du choix de `REGRET_MIN_SCORE=65`, et la date à laquelle
cette valeur a été fixée — `.env` est gitignoré, jamais transféré par
`deploy_vps.sh`, et l'historique shell n'en porte pas trace. Il est en revanche
établi qu'aucun enregistrement sous 65 n'existe depuis le début de l'époque V4,
donc que ce seuil n'a pas changé pendant la fenêtre courante.
