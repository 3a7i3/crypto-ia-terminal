# ADR-0011 — Borne canonique du dataset propre et pré-enregistrement du CRI

- **Statut** : Accepté
- **Date** : 2026-07-05
- **Contexte** : Correction d'une lecture statistique erronée (N=487 contaminé
  confondu avec N=24 propre) et absence de définition opérationnelle du
  Calibration Readiness Index (CRI) malgré son seuil de gate (CLAUDE.md).

## Contexte

Une demande de bilan des données collectées a d'abord été répondue avec
N=487 trades fermés (2026-06-13 → 2026-07-05), un Profit Factor de 0,459 et
un intervalle de confiance calculé sur cet effectif. Vérification faite via
`scripts/data_quality.py` (déjà committé sur `main`) : **463 de ces 487
trades sont antérieurs au 2026-06-25**, la borne officielle de démarrage
propre (`experiments/EXP-001.yaml`, `commit_start: ff49c2a` — blacklist de
tokens toxiques). Le N réellement exploitable est **24**, avec un intervalle
de confiance bien plus large (Wilson 95 % sur 7/24 ≈ [14 %, 50 %]) —
insuffisant pour conclure à un edge négatif réel.

Une mémoire de session antérieure (2026-06-21, commit `6ce7fc2`, correctif
anti-synthétique) documentait une consigne différente : "recalculer
uniquement sur les trades ouverts après `6ce7fc2`", avec 20 trades
synthétiques identifiés comme contamination du dataset pré-21/06. Les deux
bornes (21/06 et 25/06) n'ont jamais été formellement réconciliées dans
`CLAUDE.md`.

En parallèle, `docs/blueprint_v2.md` (lignes 106-111) spécifie la formule de
haut niveau du CRI (`CRI = (w1·N_score + w2·coverage_score + w3·drift_score
+ w4·balance_score) / 100`, gate `≥ 90/100`) sans jamais définir les poids
ni le calcul de chaque sous-score. `tools/cri_calculator.py` n'existe pas.

## Décision

### 1. Borne canonique unique : `CLEAN_DATA_SINCE = 2026-06-25`

Le 25/06 (`ff49c2a`) **contient strictement** le 21/06 (`6ce7fc2`) : tout ce
que la consigne du 21/06 excluait est également exclu par celle du 25/06.
Adopter le 25/06 comme borne unique satisfait les deux exigences sans
conflit, et correspond au code actuellement committé et actif
(`scripts/data_quality.py`, `analysis/regime_audit.py`). La consigne du
21/06 est remplacée, pas contredite. Ajouté dans `CLAUDE.md` § Règle du
statisticien.

### 2. Pré-enregistrement du CRI — définition gelée avant tout calcul réel

Les quatre sous-scores et leurs poids sont définis et gelés **avant** que
le dataset propre n'atteigne un effectif significatif (N=24 au moment de
cet ADR) — condition nécessaire pour que la définition ne soit pas
influencée par la valeur qu'elle produirait. Implémentation :
`tools/cri_calculator.py`.

| Sous-score | Formule | Justification |
|---|---|---|
| `N_score` | `min(100, 100 × N_clean / 500)` | Progression linéaire vers le seuil de calibration, sans palier intermédiaire arbitraire |
| `coverage_score` | % des cellules (régime observé × score_bin) avec ≥ 5 observations (trades fermés + regrets confondus) | Détecte un sur-échantillonnage d'un seul régime — voir note taxonomie ci-dessous |
| `drift_score` | `100 × (1 − PSI)`, borné [0,100] ; PSI entre 1ʳᵉ et 2ᵉ moitié du dataset propre sur la distribution des scores | Calibrer sur un mélange de deux régimes temporels distincts n'a pas de sens |
| `balance_score` | `100 × min(winners, losers, 150) / 150` | Rend explicite le goulot actuel (7 winners au 2026-07-05) |

**Pondération** : `w1 = w2 = w3 = w4 = 25`. Égalité choisie en l'absence de
toute donnée justifiant de privilégier une composante — choisir des poids
asymétriques après avoir observé les sous-scores serait exactement la
faute que la règle du statisticien interdit. Les poids sont gelés avec la
définition ; toute révision ultérieure doit être un nouvel ADR, jamais un
ajustement silencieux.

**Note sur `coverage_score`** : au moins trois taxonomies de régime
coexistent dans le code (`global_risk_gate._CANONICAL_REGIMES` — majuscules,
`TREND_BULL/TREND_BEAR/RANGE/VOLATILE/UNKNOWN` ; `tools/dataset_certifier._VALID_REGIMES`
— minuscules, `bull_trend/bear_trend/sideways/volatile/unknown` ; et un
régime `flash_crash` observé en production dans les rapports Telegram,
absent des deux listes). Plutôt que choisir arbitrairement l'une de ces
énumérations théoriques — risquant d'omettre un régime réel ou d'inclure un
régime jamais observé — `coverage_score` construit sa grille à partir des
**régimes réellement présents dans le dataset propre**, croisés avec les 5
`score_bin` déjà établis dans `scripts/burnin_calibration_v3.py`
(`<50, 50-59, 60-69, 70-79, 80+`). Ce choix est documenté ici pour éviter
qu'il soit relu plus tard comme une omission.

**`drift_score` à faible N** : le PSI est calculé uniquement si N ≥ 10 par
moitié (sinon `drift_score = 0`, N_score étant de toute façon très bas à ce
stade) — le PSI sur des échantillons trop petits produit des valeurs
instables sans information réelle.

## Alternatives rejetées

| Alternative | Raison du rejet |
|---|---|
| Garder deux bornes distinctes (21/06 pour un usage, 25/06 pour un autre) | Ambiguïté documentaire exactement de la nature qui invaliderait une calibration après coup |
| Choisir une taxonomie de régime théorique fixe pour `coverage_score` | Au moins un régime réel (`flash_crash`) n'apparaît dans aucune des taxonomies théoriques trouvées — risque d'omission |
| Pondérer le CRI en fonction de l'importance perçue de chaque sous-score | Introduit un jugement non justifié par des données, contraire à la règle du statisticien |
| Attendre d'avoir plus de données avant de définir le CRI | Défait l'objectif même du pré-enregistrement — la définition doit précéder le résultat |

## Conséquences

**Positives :**
- Le CRI est calculable dès aujourd'hui (score bas, cohérent avec N=24) et
  restera calculable sans interruption jusqu'au franchissement des gates —
  pas de improvisation de définition au moment critique.
- La borne de dataset est désormais unique et documentée dans la
  constitution du projet, pas seulement dans le code.

**Négatives / compromis :**
- `coverage_score` fondé sur les régimes observés plutôt qu'une taxonomie
  théorique signifie qu'un régime qui n'apparaîtrait qu'une fois pourrait
  artificiellement peser sur le score — accepté comme compromis raisonnable
  face à l'absence de taxonomie de référence fiable.
- Le chemin `governance/science/cri_calculator.py` mentionné ailleurs dans
  `docs/blueprint_v2.md` (tableau de gouvernance, ligne G-07) diverge du
  chemin `tools/cri_calculator.py` retenu ici (spec principale du blueprint,
  lignes 106-111) — à réconcilier si besoin, non bloquant.

**Règles induites :**
- Toute référence future à "N trades propres" ou aux seuils du tableau
  statisticien doit filtrer par `CLEAN_DATA_SINCE = 2026-06-25`.
- Toute révision des poids ou sous-scores du CRI est un nouvel ADR, jamais
  une modification silencieuse de `tools/cri_calculator.py`.
