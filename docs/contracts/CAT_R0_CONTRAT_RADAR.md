# CAT R0 — Contrat du Radar de sélection des marchés

Gate R0-2. Contrat `radar-evaluation/1.0.0`, règles `radar-rules/1.0.0`,
classement `radar-ranking/1.1.0` (amendés par R1-B, section 9, puis par R-REF,
section 10 : versions courantes `radar-evaluation/1.2.0`, `radar-rules/1.2.0`,
`radar-ranking/1.3.0`). Code : `observability/radar_selection/`
(constantes dans `contract.py`). Statut : **source seule, SYNTHETIC, hors
réseau**. Ce contrat n'autorise ni collecte, ni déploiement, ni expérience.

## 1. Rôle et frontière d'autorité

Le Radar est le premier étage de l'observatoire :

```text
RADAR → Admission scientifique → Collecte L2 autorisée → Reconstruction → Intelligence de marché → …
```

Il s'arrête à la **décision de candidature**. Il ne commande aucun étage
suivant.

| Le Radar peut | Le Radar ne peut pas |
|---|---|
| lire un catalogue et des observations minimales fournis en entrée | ouvrir une connexion réseau, un carnet L2, une collecte |
| évaluer chaque marché de l'univers autorisé | créer un job d'observation approfondie, un replay, une expérience |
| classer et proposer au plus trois marchés | passer un ordre PAPER/LIVE, toucher PPL, FIN, Advisor, Risk |
| enregistrer des préférences opérateur dans un dossier explicite | écrire hors de ce dossier, démarrer un service |

Chaque évaluation publie `authority = {execution_authority: false,
collection_authority: false, experiment_authority: false, proposal_status:
PROPOSED_NOT_AUTHORIZED}`, `mode = {evidence: SYNTHETIC, network: DISABLED,
l2_collection: DISABLED, paper: DISABLED, deep_observation: DISABLED}` et
`deep_observation_jobs = []`. En R0, une entrée dont `evidence_kind` n'est pas
`SYNTHETIC` est refusée.

Le mode hors réseau est **imposé** par la CLI : un hook d'audit Python,
installé avant tout travail, refuse sockets, sous-processus, fork/exec et toute
écriture hors de `--state-dir`. Sans `--state-dir`, rien n'est écrit.

## 2. R0-A — Univers autorisé et identité

### 2.1 Découverte

Les quatre catalogues publics officiels (formats de `scanner_universe`) sont
fournis comme octets d'entrée et lus par `scanner_universe.catalogues.parse_all`.
Aucun parseur n'est dupliqué. La validité des métadonnées suit
`scanner_universe.universe.source_status` (35 min, tolérance de 5 s dans le
futur).

### 2.2 Identité minimale d'un marché

| Champ | Exemple |
|---|---|
| `market_id` | `kraken:spot:BTC/USDT`, `mexc:perp:BTC/USDT`, `kraken:perp-inv:BTC/USD` |
| `venue` | `kraken`, `mexc` |
| `market_type` | `SPOT`, `PERPETUAL` |
| `contract_type` | `SPOT`, `LINEAR_PERPETUAL`, `INVERSE_PERPETUAL`, `FIXED_MATURITY`, `UNKNOWN` |
| `base`, `quote` | actifs canoniques (alias Kraken `XBT→BTC`, `XDG→DOGE` seulement) |
| `native_symbol` | symbole publié (`XBTUSDT`, `PF_XBTUSD`, `BTC_USDT`) |
| `settlement_asset` | devise de règlement du contrat, `null` en Spot |
| `catalogue.source_market`, `native_status`, `exclusion`, `collected_ms`, `metadata_current`, `metadata_reason`, `raw_sha256`, `provenance` | preuve du catalogue |

Règles : Kraken BTC/USDT Spot ≠ MEXC BTC/USDT Spot ; BTC/USD ≠ BTC/USDT ;
Spot ≠ Perpétuel ; linéaire ≠ inverse. Deux instruments natifs qui donnent le
même identifiant sur une plateforme sont conservés tous les deux, suffixés
`~NATIF`, et refusés (`CATALOGUE_DUPLICATE_KEY`). Un instrument sans base ou
cotation canonique reçoit `venue:type:?NATIF`, autorisation `UNKNOWN`,
décision `UNKNOWN` (`IDENTITY_INSUFFICIENT`).

### 2.3 Chaîne de qualification (cinq états distincts)

| Étape | Champ | Valeurs |
|---|---|---|
| Instrument découvert | `lifecycle.discovered` | vrai si listé au cycle courant |
| Instrument autorisé | `lifecycle.authorized` | `true`, `false` + motif, `null` (identité insuffisante) |
| Source accessible | `lifecycle.source_access` | `ACCESSIBLE`, `DEGRADED`, `UNAVAILABLE`, `UNKNOWN` (non déclarée) |
| Données récentes | `lifecycle.recent_data` | `FRESH`, `STALE`, `ABSENT`, `UNKNOWN` |
| Données scientifiquement admissibles | `lifecycle.scientific` | décision de l'étape 1 (§4) |

### 2.4 Politique d'univers

`policy = {venues, market_types, quotes, asset_classes, deny}`. Motifs de
refus : `VENUE_NOT_AUTHORIZED`, `MARKET_TYPE_NOT_AUTHORIZED`,
`QUOTE_NOT_AUTHORIZED`, `ASSET_CLASS_NOT_AUTHORIZED` (classes de
`scanner_universe` : `CRYPTO`, `STABLECOIN`, `FIAT`), `DENIED_BY_POLICY`. Un
marché non autorisé n'est pas mesuré (`NOT_EVALUATED_OUTSIDE_AUTHORIZED_UNIVERSE`).

### 2.5 Évolutions entre cycles

`previous_universe` (identités du cycle précédent) donne `change` :
`BASELINE`, `ADDED`, `UNCHANGED`, `METADATA_CHANGED` (symbole natif, contrat ou
règlement différent), `RETIRED` (catalogue complet sans le marché ; décision
`NON_ADMISSIBLE`, `MARKET_RETIRED_FROM_CATALOGUE`), `SOURCE_NOT_CURRENT`
(catalogue indisponible : le marché reste visible, décision `UNKNOWN`,
`SOURCE_CATALOGUE_NOT_CURRENT`, jamais « retiré »). Un univers vide est un
résultat valide.

## 3. R0-B — Surveillance légère

### 3.1 Observation minimale (entrée)

Par marché, identifié par `(venue, market_type, native_symbol)` :

| Champ | Contenu |
|---|---|
| `evidence_ref` | référence de preuve (obligatoire) |
| `price_kind` | `LAST_TRADE`, `MID_BBO`, `MARK` (nature du prix) |
| `window` | `start_ms`, `step_ms`, `points` (grille) |
| `samples[]` | `t_ms`, `price`, `bid`, `ask` (décimaux en chaînes, `null` autorisé) |
| `activity` | `TRADE_COUNT_WINDOW` + valeur + référence, ou `null` |
| `l2` | `VERIFIED` (référence de preuve exigée) ou `TECHNICALLY_COMPATIBLE`, niveaux, profondeur à 10 bps par côté, ou `null` |
| `cost` | `basis` `MEASURED` ou `ESTIMATED`, `provenance`, réseau KiB/s, CPU %, mémoire MiB, stockage MiB/h, connexions, note de limite de débit |
| `declared_base`, `declared_quote` | identité déclarée par la source, comparée au catalogue |

Aucun journal brut n'est conservé : la sortie contient des compteurs, des
mesures bornées et des références.

### 3.2 Mesures

| Mesure | Règle | Absente ou non calculable |
|---|---|---|
| Horodatage | `CERTIFIED` si tous présents, strictement croissants, ≤ évaluation + 5 s | `UNCERTIFIED` (manquant) ; `INCOHERENT` (désordre, futur) |
| Continuité | instant `g` couvert si un échantillon avec prix tombe dans `(g − pas, g]` ; ratio couvert/attendu ; classes `GOOD` ≥ 0,95, `VIABLE` ≥ 0,80, `PARTIAL` ≥ 0,50, sinon `INSUFFICIENT` (classes des pilotes `radar_composite`) ; nombre et longueur des trous | `UNKNOWN` |
| Fraîcheur | `FRESH` si dernier échantillon ≤ 2 pas | `STALE` |
| Spread | médiane de `(ask − bid)/mid` en bps sur les instants couverts avec BBO ; base `BBO` ; `AVAILABLE` si ≥ 80 % des instants couverts ont un BBO, sinon `PARTIAL` | `UNKNOWN` `BBO_NOT_PROVIDED` (jamais 0) |
| Profondeur | lue **uniquement** dans un bloc L2 fourni (base `L2`) ; un côté manquant = `PARTIAL` ; L2 non vérifié = `PARTIAL` | `UNKNOWN` (jamais dérivée d'un BBO) |
| Volatilité | RMS des rendements entre instants consécutifs couverts, en bps par pas ; ≥ 10 rendements | `UNKNOWN` `TOO_FEW_CONSECUTIVE_RETURNS` |
| Activité | compteur de trades de fenêtre ; 0 est une mesure | `UNKNOWN` (`ACTIVITY_NOT_PROVIDED`, type non supporté) |
| Coût | recopié avec sa base et sa provenance | `UNKNOWN` ; `PARTIAL` si champs manquants |

Contradictions (refus) : prix/bid/ask ≤ 0, carnet croisé ou verrouillé
(`bid ≥ ask`), `MID_BBO` différent de `(bid+ask)/2` ou sans BBO, horodatage
incohérent, identité déclarée différente du catalogue, observation en double.
Une observation sans marché correspondant est publiée dans
`orphan_observations`, jamais rattachée.

## 4. R0-C — Sélection scientifique

### 4.1 Six critères

Chaque critère porte `state ∈ {AVAILABLE, PARTIAL, UNKNOWN, INVALID}`, ses
valeurs, sa base et son motif.

1. **Qualité L2** : `proof = PROVEN` (L2 `VERIFIED` avec référence),
   `TO_QUALIFY` (compatibilité technique), `UNKNOWN`. Compatibilité technique
   ≠ intégrité prouvée.
2. **Continuité** : horodatage, ratio, classe, trous, fraîcheur.
3. **Spread et profondeur** : spread (base `BBO`) et profondeur (base `L2`)
   séparés. La base `GENERAL` (ticker 24 h) n'est pas supportée en R0.
4. **Activité et volatilité** : compteur et régime `CALM` (< 5 bps/pas),
   `ACTIVE` (5–20), `VOLATILE` (≥ 20). Seuils = hypothèses, dépendantes du pas.
5. **Coût de collecte** : réseau, CPU, mémoire, stockage, connexions, limites,
   avec `MEASURED` ou `ESTIMATED` et provenance.
6. **Diversité** : régime du marché, utilisé au moment de la sélection.

### 4.2 Étape 1 — Admissibilité par mission

| Mission | Exige |
|---|---|
| `PRICE_STUDY` | identité, autorisation, source, horodatage certifié, continuité ≥ 0,80, fraîcheur |
| `DEEP_OBSERVATION` (défaut) | idem + spread BBO disponible ; L2 peut rester `TO_QUALIFY` |
| `L2_DEPTH_STUDY` | idem + L2 `PROVEN` et profondeur complète |

Motifs et décision (le plus grave l'emporte ; tous les motifs sont publiés) :

| Décision | Motifs |
|---|---|
| `NON_ADMISSIBLE` | non autorisé ; exclusion catalogue ; retiré ; source `UNAVAILABLE` ; horodatage incohérent ; valeurs contradictoires ; conflit d'identité ; observation en double ; continuité `INSUFFICIENT` |
| `UNKNOWN` | identité insuffisante ; accès source non déclaré ; catalogue non courant ; pas d'observation ; horodatage manquant ; BBO absent (mission BBO) ; L2 non prouvé (mission L2) ; marché non évalué faute de budget |
| `A_QUALIFIER` | métadonnées anciennes ; source `DEGRADED` ; données `STALE` ; continuité `PARTIAL` ; BBO partiel ; L2 `TO_QUALIFY` ou profondeur incomplète (mission L2) |
| `ADMISSIBLE` | aucun motif |

### 4.3 Étape 2 — Classement (`radar-ranking/1.1.0`)

Seuls les marchés `ADMISSIBLE` reçoivent un score sur 100 :

| Composante | Poids | Points |
|---|---|---|
| Continuité | 30 | ratio ≥ 0,95 → 100 ; ≥ 0,80 → 60 |
| Spread (BBO) | 25 | ≤ 2 bps → 100 ; ≤ 5 → 80 ; ≤ 10 → 60 ; ≤ 25 → 30 ; sinon 10 |
| Activité | 20 | ≥ 1000 trades → 100 ; ≥ 100 → 70 ; ≥ 10 → 40 ; ≥ 1 → 20 ; 0 → 0 |
| L2 | 15 | `VERIFIED` → 100 ; `TECHNICALLY_COMPATIBLE` → 40 |
| Coût réseau | 10 | ≤ 50 KiB/s → 100 ; ≤ 200 → 70 ; ≤ 1000 → 40 ; sinon 10 |

`score = Σ poids × points / 100`, décimal exact arrondi à 0,01. Une composante
inconnue **ne marque rien et son poids n'est pas redistribué** : elle apparaît
dans `missing`, la qualité devient `INCOMPLETE` et `max_reachable` baisse.
Aucun score n'est produit pour un marché non `ADMISSIBLE`.

### 4.4 Sélection et diversité

Pool = marchés notés, non exclus manuellement (R0 à R1-B : « hors référence » ;
supprimé par R-REF, section 10). Tri : scores
`COMPLETE` avant scores `INCOMPLETE`, puis score décroissant, puis `market_id`
(1.1.0 : une composante inconnue ne fait jamais perdre de rang face à un
marché complet ; `UNKNOWN ≠ 0`). Règles dans l'ordre :

1. `REGIME_SLOT` : le meilleur de chaque régime, `CALM`, puis `ACTIVE`, puis
   `VOLATILE` ;
2. `BASE_DIVERSITY` : le meilleur restant d'un autre actif de base ;
3. `SCORE` : le meilleur restant.

Au plus trois candidats, présentés par score, chacun avec : instrument exact,
plateforme, type, contrat, régime, règle et motif, score et qualité, critères
disponibles et manquants, coût (base, provenance), limites, statut
`PROPOSED_NOT_AUTHORIZED`. Liste vide justifiée par
`NO_ADMISSIBLE_MARKET_FOR_MISSION` ou
`ADMISSIBLE_MARKETS_ALL_EXCLUDED` (R0 à R1-B :
`ADMISSIBLE_MARKETS_ALL_EXCLUDED_OR_REFERENCE`). Le résultat ne dépend pas de
l'ordre de lecture.

## 5. R0-D — Contrôle manuel et référence

- `select`, `pin`, `exclude` (et `unselect`, `unpin`, `include`, `reset`)
  écrivent `preferences.json` (`radar-preferences/1.0.0`) dans `--state-dir`,
  atomiquement, avec un journal borné à 50 actions.
- `select` et `pin` refusent un marché inconnu (`UNKNOWN_MARKET`) ou hors
  univers autorisé (`MARKET_NOT_AUTHORIZED`).
- `exclude` retire un marché des propositions automatiques sans changer sa
  décision.
- Un marché choisi ou épinglé garde sa décision réelle ;
  `presented_as_admissible` n'est vrai que pour `ADMISSIBLE`. Aucun choix ne
  lance de collecte.
- **Référence (R0 à R1-B, retirée par R-REF, section 10).** `kraken:spot:BTC/USDT`, publiée à part (`in_ranking: false`),
  avec sa décision Radar et `historical_admission:
  NOT_YET_HISTORICALLY_ADMITTED`. Elle reste soumise à l'intégrité de ses
  données et aux gates C2-C, C2-D et suivantes ; aucun passage PAPER n'en
  découle.

## 6. Budgets

| Plafond | Valeur de test (fixtures) | Production |
|---|---|---|
| Instruments examinés par cycle | 200 (au-delà : `UNKNOWN BUDGET_NOT_EVALUATED`, visible) | `NOT_MEASURED` |
| Taille d'une observation | 32 768 octets | `NOT_MEASURED` |
| Échantillons par observation | 256 | `NOT_MEASURED` |
| Taille totale de l'entrée | 2 000 000 octets (refus `INPUT_TOO_LARGE`) | `NOT_MEASURED` |
| Évaluations conservées | 20 (`history.json`, les plus anciennes sortent) | `NOT_MEASURED` |
| Mémoire (pic `tracemalloc`) | 64 MiB | `NOT_MEASURED` |
| Durée d'un cycle | 2 000 ms | `NOT_MEASURED` |
| Taille de sortie | 1 000 000 octets (refus `OUTPUT_TOO_LARGE`) | `NOT_MEASURED` |
| Fréquence future d'évaluation | non fixée (`null`) | à justifier par mesure |

Les valeurs de production restent absentes tant qu'aucun benchmark
représentatif n'existe. `bench` mesure localement temps, mémoire et taille.

## 7. Sortie `radar-evaluation/1.0.0`

Clés : `schema_version`, `rules_version`, `ranking_version`, `mode`,
`authority`, `dataset` (id, sha256, octets, nature), `mission`,
`evaluation_time_ms`, `preferences_sha256`, `policy`, `sources`, `counts`,
`reference` (absent depuis `radar-evaluation/1.2.0`, section 10), `candidates`,
`candidates_empty_reason`, `manual`,
`orphan_observations`, `markets[]`, `budgets`, `deep_observation_jobs`,
`evaluation_sha256` (SHA-256 du JSON canonique sans ce champ).

Déterminisme : aucune horloge, `evaluation_time_ms` vient de l'entrée ;
décimaux exacts ; JSON canonique (clés triées, séparateurs compacts). Même
entrée + mêmes préférences + même mission ⇒ mêmes octets.

## 8. Limites connues

- Toutes les données sont SYNTHETIC ; aucun seuil n'est calibré.
- Pas de source réelle de surveillance légère multi-marché sur main.
- Régimes estimés sur une seule fenêtre.
- Coûts comparés sur le réseau seulement ; quotes USD et USDT non converties.
- Vocabulaire à aligner avec CH1-01 lorsque #604 sera fusionnée.

## 9. Amendement R1-B (2026-11-24)

Contrat associé : [CAT_R1B_CONTRAT_LOT_RADAR.md](CAT_R1B_CONTRAT_LOT_RADAR.md)
(décisions opérateur D1 à D4). Les sections 1 à 8 restent la référence de la
version R0 ; les changements suivants s'y ajoutent.

| Élément | R0 | R1-B |
|---|---|---|
| Évaluation | `radar-evaluation/1.0.0` | `radar-evaluation/1.1.0` : `mode.evidence`, `dataset` (`schema`, `admission: NONE`, `adapter_version` pour un lot), `inputs` (vérification des références), `source_id` et `evidence_kind` par observation, portée L2 |
| Règles | `radar-rules/1.0.0` | `radar-rules/1.1.0` : statut `VERIFIED_TOP_N` (preuve `PROVEN_TOP_N`, état `PARTIAL`, motif `L2_VERIFIED_TOP_N_ONLY`), nature `HISTORICAL` réservée à `radar-batch`, motifs d'absence `unknown_reasons` |
| Classement | `radar-ranking/1.1.0` | `radar-ranking/1.2.0` : entrée L2 `VERIFIED_TOP_N → 40`, rien d'autre ne change |
| Entrées | `radar-fixture/1.0.0` | inchangée (SYNTHETIC seulement) ; nouvelle entrée `radar-batch/1.0.0` (`SYNTHETIC` ou `HISTORICAL`, jamais `LIVE`) |

- Les 40 points de `VERIFIED_TOP_N` sont une **pondération transitoire**. Ils
  n'affirment pas une fiabilité égale à `TECHNICALLY_COMPATIBLE` et ne peuvent
  être relevés sans protocole de calibration et validation séparés.
- Une évaluation `HISTORICAL` n'est pas une admission : `dataset.admission`
  vaut toujours `NONE`, la référence reste `NOT_YET_HISTORICALLY_ADMITTED`, et
  chaque candidat porte la limite « Données HISTORICAL hors ligne ».
- Équivalence scientifique : une fixture R0 et le même contenu passé en lot
  donnent les mêmes critères, décisions, scores et candidats, à version
  identique (test T17). Seuls l'identité du jeu de données, `inputs` et
  l'étiquette de provenance du catalogue diffèrent.

## 10. Amendement R-REF (2026-11-25)

Décisions opérateur D-R1 (option A renforcée) et D-R2. Base :
`main@77bd30e2888a11207c2c0dbce19eaa62fd4421ac`.

**Sémantique.** Le Radar n'a plus de marché de référence obligatoire. Aucun
marché n'est exclu du classement, ni publié hors classement, en raison de son
identité (`market_id`, plateforme ou actif de base). Chaque marché passe par
les mêmes critères, la même admissibilité et le même classement. Seule une
préférence opérateur `exclude` retire un marché des candidats, sans changer sa
décision. Un marché sans preuve reste `UNKNOWN` ou `A_QUALIFIER` et n'est jamais
admissible d'office. Aucun poids ni aucun seuil ne change.

| Élément | R1-B | R-REF |
|---|---|---|
| Évaluation | `radar-evaluation/1.1.0` | `radar-evaluation/1.2.0` : le champ `reference` disparaît ; motif vide `ADMISSIBLE_MARKETS_ALL_EXCLUDED_OR_REFERENCE` renommé `ADMISSIBLE_MARKETS_ALL_EXCLUDED` ; tout le reste est identique |
| Règles | `radar-rules/1.1.0` | `radar-rules/1.2.0` : plus de constante `REFERENCE` ni de statut `NOT_YET_HISTORICALLY_ADMITTED` ; aucune règle ne cite un marché par son nom |
| Classement | `radar-ranking/1.2.0` | `radar-ranking/1.3.0` : le pool ne retire plus la référence (`select_candidates(entries, excluded)`) ; poids, paliers, tri et diversité inchangés |
| Entrées | `radar-fixture/1.0.0`, `radar-batch/1.0.0` | inchangées |
| Terminal | écran « Référence » | supprimé |

**Effet mesuré sur les entrées SYNTHETIC** (tests différentiels
`tests/radar_selection/test_h_rref.py`) : marchés, critères, décisions,
scores et motifs sont identiques octet pour octet aux sorties archivées
`radar-evaluation/1.1.0`. Le classement ne change que pour la fixture
`r0_syn_04_incoherent` en missions `PRICE_STUDY` et `DEEP_OBSERVATION` :
`kraken:spot:BTC/USDT` remplace `mexc:spot:BTC/USDT` : même base BTC, même
régime CALM, mais 88.00 `COMPLETE` contre 82.00 `INCOMPLETE` (composante L2
manquante). Il l'emporte par la qualité et le score, pas par son identifiant.
Exclure manuellement `kraken:spot:BTC/USDT` reproduit exactement les candidats
archivés dans les 15 cas.

**Privilège fixe et départage des ex æquo.** R-REF retire tout privilège fixe
lié à l'identité : aucun marché n'est mis de côté, ni placé d'office, parce
qu'il s'appelle `kraken:spot:BTC/USDT` ou parce que sa base est BTC. Le tri
reste en revanche entièrement déterministe : qualité `COMPLETE` avant
`INCOMPLETE`, puis score décroissant, puis `market_id` croissant. Entre deux
marchés de même qualité, même score, même régime et même base, le
`market_id` départage donc les ex æquo, quel que soit l'ordre de lecture. Ce
départage lexicographique s'applique de la même façon à tous les marchés,
l'ancienne référence comprise (elle gagne ou perd un ex æquo selon l'ordre
alphabétique des identifiants) ; il ne constitue pas un privilège et n'est
jamais appliqué avant une différence réelle de qualité ou de score (tests
`test_RR1_*`).

**Archive (D-R1).** Les sorties des moteurs antérieurs sont conservées sans
réécriture dans `docs/research/radar_rref/archive/` : R0 au commit
`ca0354f99b2ec2c8fa5ec8ba61c21280f91ed823` (`radar-evaluation/1.0.0`,
12 sorties : 4 fixtures × 3 missions) et R1-B au commit
`77bd30e2888a11207c2c0dbce19eaa62fd4421ac` (`radar-evaluation/1.1.0`,
15 sorties : 4 fixtures et 1 lot × 3 missions). `MANIFEST.json` donne pour
chaque sortie son schéma et ses versions, son SHA-256, sa source (chemin et
empreinte de la fixture ou du lot), le commit du moteur, la commande de
production et la nature SYNTHETIC. Le moteur courant n'émet que les nouvelles
versions ; aucun moteur historique n'est maintenu actif. Vérifier une sortie
archivée (empreintes, sceau `evaluation_sha256`) n'est pas rejouer son calcul :
un rejeu exige un checkout séparé du commit moteur cité.

## Frontière Radar → Admission scientifique → Observation approfondie

Les gates C2-C (admission scientifique) et C2-D (observation approfondie) ne
sont pas définies dans le dépôt ; leur état est `UNKNOWN`. Ce contrat ne les
définit pas. Il fixe seulement ce que le Radar leur doit :

1. L'entrée d'un étage suivant est un export Radar figé, identifié par son
   `evaluation_sha256`, jamais un appel au Radar.
2. Aucune transition automatique : chaque passage exige une décision humaine
   traçable ; `deep_observation_jobs` reste vide.
3. Un critère `UNKNOWN` au Radar reste `UNKNOWN` en entrée d'admission.
4. Aucun marché n'est admis historiquement par le Radar. Depuis R-REF
   (section 10), aucun marché n'a de statut de référence ; `kraken:spot:BTC/USDT`
   est évalué comme les autres, et son admission éventuelle relève de C2-C.
