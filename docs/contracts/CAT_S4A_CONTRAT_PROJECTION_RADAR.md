# CAT S4-a — Contrat de projection Radar `radar-projection/1.0.0`

Mission S4-a (GO opérateur du 2026-11-25, base `main@592ec4e`). Code :
`observability/radar_projection/` (`contract.py`, `verifier.py`,
`projection.py`). Tests : `tests/radar_projection/`. Statut : **source seule,
SYNTHETIC, hors réseau**.

Ce contrat définit deux choses :
- un **vérificateur indépendant** des exports Radar figés ;
- la **projection** `radar-projection/1.0.0`, qui sera l'entrée de la future
  Operator API (S4-b) et, par elle, de l'interface mobile CAT (S4-c).

Ce n'est pas un nouveau moteur scientifique. La projection ne recalcule aucun
score, aucune décision et aucun rang. **Une projection valide n'est ni une
admission scientifique ni une autorisation runtime.** Ce contrat n'ouvre
aucune route API, aucun écran, aucune collecte et aucun déploiement.

## 1. Chaîne et frontière

```text
Radar (moteur, hors ligne) ─export─▶ octets figés ─▶ vérificateur S4-a ─▶ projection radar-projection/1.0.0
                                                         │ refus typé
                                                         ▼
                                                 aucune projection
```

Le vérificateur reçoit des **octets**. Il ne lit aucun fichier, n'ouvre aucune
connexion et ne lit aucune horloge. S4-b décidera comment ces octets sont lus
et servis (lecteur borné du type `market_flow_reader`, route GET).

## 2. Phase A : composants réutilisés

| Composant | Origine | Usage dans S4-a |
|---|---|---|
| `strict_loads` | `radar_selection/fixture.py` | lecture JSON stricte et bornée : UTF-8, clés dupliquées, flottants, `NaN`/`Infinity` refusés |
| `canonical` | `radar_selection/fixture.py` | **forme canonique unique** : celle qui a produit le sceau ; aucune seconde implémentation |
| `sha256_hex` | `radar_selection/fixture.py` | empreintes de l'export et de la projection |
| `RadarRefusal` | `radar_selection/fixture.py` | base des erreurs typées ; `ProjectionRefusal` en hérite (même forme `CODE` ou `CODE:chemin`) |
| codes de refus de lecture | `strict_loads` | `INPUT_EMPTY`, `INPUT_MALFORMED`, `DUPLICATE_KEY`, `FLOAT_NOT_ALLOWED`, `NONFINITE_NUMBER` repris tels quels |
| motif de lecteur borné | `operator_api/market_flow_reader.py` | modèle pour S4-b (taille bornée avant lecture, échec typé, jamais de population vide) ; non importé ici |
| vocabulaire et versions | `radar_selection/contract.py`, contrats R0 §4, §7, §10 et R1-B | **recopiés en littéraux** dans `radar_projection/contract.py`, épinglés par test |

Pourquoi recopier les versions au lieu de les importer : si le moteur passe un
jour à une nouvelle version, le vérificateur doit continuer à **refuser** ses
exports tant que ce contrat n'a pas été révisé. Le test
`test_SA1_supported_source_is_pinned_to_the_current_engine` échoue à toute
divergence et force une révision délibérée.

Modules **non** importés : `engine`, `selection`, `surveillance`, `universe`,
`batch`, `terminal`, `manual`. Le test `test_SA9_the_engine_is_never_loaded`
le vérifie dans un processus séparé.

## 3. Source acceptée et versions (SA4)

| Source | Règle | Code |
|---|---|---|
| `radar-evaluation/1.2.0` + `radar-rules/1.2.0` + `radar-ranking/1.3.0` | **seule combinaison acceptée** | — |
| `radar-evaluation/1.0.0`, `1.1.0` ou toute version < 1.2 | refus (D-P2) | `PRE_RREF_EVALUATION` |
| autre `radar-evaluation` (1.2.1, 1.3.0, 2.0.0…) ou autre schéma | refus | `UNSUPPORTED_EVALUATION_SCHEMA` |
| 1.2.0 avec d'autres règles ou un autre classement | refus | `UNSUPPORTED_VERSION_COMBINATION` |
| `schema_version` absent ou non textuel | refus | `EVALUATION_SCHEMA_MISSING` |
| `schema_version` de plus de 64 caractères, ou numéro de plus de 6 chiffres | refus **avant** toute conversion numérique (S4A-RV-04) | `UNSUPPORTED_EVALUATION_SCHEMA` |

Les versions sont contrôlées **avant** le sceau. Les 27 sorties de l'archive
D-R1 (`docs/research/radar_rref/archive/`, R0 `ca0354f` et R1-B `77bd30e`)
sont toutes refusées avec `PRE_RREF_EVALUATION`. Elles restent archivées et
vérifiables par leur manifeste ; elles ne sont pas compatibles avec la
projection courante, et aucun convertisseur n'est fourni.

Jeux de données qu'une évaluation 1.2.0 peut citer :
`radar-fixture/1.0.0` (sans `inputs`) et `radar-batch/1.0.0` (avec `inputs` et
`adapter_version = radar-adapter/1.0.0`). Tout autre schéma :
`DATASET_SCHEMA_NOT_SUPPORTED`. Une fixture avec `inputs` :
`INPUTS_NOT_ALLOWED_FOR_FIXTURE`.

## 4. Lecture stricte et bornée (SA2)

Ordre des contrôles : taille, UTF-8 et JSON strict, versions, forme
canonique, sceau, structure, preuves, autorité, marchés, scores, candidats,
préférences, compteurs, budgets.

| Contrôle | Règle | Code |
|---|---|---|
| type | des octets (`bytes` ou `bytearray`) | `INPUT_NOT_BYTES` |
| vide | refusé | `INPUT_EMPTY` |
| taille | ≤ `MAX_EXPORT_BYTES` = 1 000 001 octets, vérifiée **avant** l'analyse | `INPUT_TOO_LARGE` |
| encodage, syntaxe, imbrication | UTF-8 strict sans BOM ; JSON valide ; imbrication excessive ou entier hors limite de l'interpréteur | `INPUT_MALFORMED` |
| clés dupliquées | à toute profondeur | `DUPLICATE_KEY` |
| nombres | aucun flottant ; aucun `NaN`, `Infinity` ou `-Infinity` | `FLOAT_NOT_ALLOWED`, `NONFINITE_NUMBER` |
| racine | un objet JSON | `OBJECT_EXPECTED` |
| forme canonique | octets égaux à `canonical(doc)`, suivis au plus d'un `\n` | `NOT_CANONICAL` |
| message de refus | `CODE` suivi d'au plus 120 caractères de détail ; jamais un morceau non borné de l'entrée (S4A-RV-04) | — |

Toute erreur d'analyse, de canonicalisation ou de validation devient un
`ProjectionRefusal` : un entier hors limite de l'interpréteur, une récursion
excessive ou un surrogate isolé donnent `INPUT_MALFORMED`. Le filet de
sécurité de la validation couvre `TypeError`, `KeyError`, `AttributeError`,
`ValueError`, `ArithmeticError` et `RecursionError` (`STRUCTURE_INVALID`).
`project` enveloppe aussi sa construction interne.

La borne vient du moteur : il refuse une évaluation de plus de
`max_output_bytes` = 1 000 000 octets (profil `TEST_FIXTURES`), et la commande
`export` ajoute un saut de ligne.

L'exigence de forme canonique ferme une porte : un même contenu ne peut pas
circuler sous plusieurs encodages (espaces, ordre des clés, échappements
`\uXXXX`) qui auraient tous un sceau valide.

## 5. Sceau : intégrité, pas authenticité (SA3)

Le vérificateur recalcule `evaluation_sha256` = SHA-256 de `canonical(doc)`
sans le champ `evaluation_sha256`, avec la canonicalisation du Radar. Il
exige 64 caractères hexadécimaux minuscules.

| Contrôle | Code |
|---|---|
| sceau absent ou mal formé | `SEAL_FORMAT` |
| sceau différent du contenu | `SEAL_MISMATCH` |

**Ce que le sceau prouve :** l'intégrité du contenu. Les octets sont ceux qui
ont été scellés, et toute modification non rescellée est détectée.

**Ce que le sceau ne prouve pas :** l'authenticité du producteur. N'importe
qui peut modifier un export et recalculer un SHA-256 correct. Le sceau ne dit
donc pas *qui* a produit l'évaluation. Prouver l'authenticité demanderait une
signature ou un canal de confiance ; c'est hors S4-a. La projection l'écrit
explicitement : `integrity = {seal: VERIFIED, proves: CONTENT_INTEGRITY,
producer_authenticity: NOT_PROVEN}`.

C'est pourquoi tous les invariants des sections 6 et 7 sont vérifiés
**après** le sceau, pour eux-mêmes. Les tests adversariaux modifient un export
réel puis **recalculent son sceau** : la validation ne repose jamais sur
l'empreinte seule.

## 6. Structure et cohérence (SA5)

Le vérificateur contrôle la forme exacte de `radar-evaluation/1.2.0` : jeux de
clés exacts, types, vocabulaires fermés et empreintes au format SHA-256. Il
contrôle aussi la cohérence entre marchés, compteurs et candidats. Il ne
recalcule ni score, ni décision, ni classement. Il vérifie que les valeurs
publiées sont **cohérentes entre elles**.

**Types et formes** : `KEYS_MISMATCH`, `OBJECT_EXPECTED`, `LIST_EXPECTED`,
`STRING_EXPECTED`, `BOOLEAN_EXPECTED`, `INTEGER_EXPECTED`, `CODE_EXPECTED`,
`SHA256_EXPECTED`, `VALUE_NOT_ALLOWED`, `DUPLICATE_VALUE`, `CRITERION_SHAPE`.
Filet de sécurité : toute forme non prévue qui ferait lever une exception
Python devient `STRUCTURE_INVALID`. Aucune autre exception ne sort du
vérificateur, ce que vérifie un test de mutations aléatoires rescellées.

| Invariant | Code |
|---|---|
| `market_id` uniques et triés (ordre du moteur) | `DUPLICATE_MARKET`, `MARKETS_NOT_ORDERED` |
| mission connue ; besoins (`needs_bbo`, `needs_l2_verified`) conformes à la mission | `MISSION_RULES_MISMATCH` |
| chaque marché évalué pour la mission de l'évaluation | `MISSION_MISMATCH` |
| motifs uniques, triés par sévérité puis code ; décision = motif le plus sévère, `ADMISSIBLE` si aucun motif | `REASONS_NOT_ORDERED_OR_DUPLICATED`, `DECISION_REASONS_MISMATCH` |
| `lifecycle.scientific` = décision | `DECISION_LIFECYCLE_MISMATCH` |
| score présent **si et seulement si** la décision est `ADMISSIBLE` | `SCORE_ON_NON_ADMISSIBLE`, `ADMISSIBLE_WITHOUT_SCORE` |
| poids = poids publiés de `radar-ranking/1.3.0` | `WEIGHTS_MISMATCH` |
| composantes connues ; `missing` = composantes absentes ; `quality` = `COMPLETE` si rien ne manque | `SCORE_COMPONENTS`, `SCORE_MISSING_MISMATCH`, `SCORE_QUALITY_MISMATCH` |
| score et plafond : chaîne à deux décimales, sans zéro de tête, entre `0.00` et `100.00` (S4A-RV-01) | `SCORE_DECIMAL_EXPECTED` |
| plafond = 100 − poids des composantes manquantes ; score ≤ plafond (aucun score recalculé) | `SCORE_CEILING_MISMATCH`, `SCORE_ABOVE_CEILING` |
| entiers stricts partout : un booléen n'est ni un rang, ni un compteur, ni une composante (S4A-RV-01) | `INTEGER_EXPECTED` |
| un marché admissible a une observation | `ADMISSIBLE_WITHOUT_OBSERVATION` |
| au plus 3 candidats, rangs entiers 1..n, sans doublon | `CANDIDATES_TOO_MANY`, `RANK_SEQUENCE`, `DUPLICATE_CANDIDATE` |
| critères disponibles et manquants du candidat = ceux de son marché (S4A-RV-02) | `CANDIDATE_CRITERIA_MISMATCH` |
| coût du candidat = copie des champs `collection_cost` de son marché (S4A-RV-02) | `CANDIDATE_COST_MISMATCH` |
| chaque candidat existe, a la même identité, est `ADMISSIBLE` et n'est pas exclu par l'opérateur | `CANDIDATE_NOT_IN_MARKETS`, `CANDIDATE_IDENTITY_MISMATCH`, `CANDIDATE_NOT_ADMISSIBLE`, `CANDIDATE_EXCLUDED_BY_OPERATOR` |
| score, qualité et régime du candidat = ceux de son marché | `CANDIDATE_SCORE_MISMATCH`, `CANDIDATE_REGIME_MISMATCH` |
| critères disponibles et manquants forment une partition des six critères | `CANDIDATE_CRITERIA_PARTITION` |
| ordre de présentation cohérent avec les valeurs publiées (qualité, score décroissant, `market_id`) | `CANDIDATES_NOT_ORDERED` |
| autant de candidats que possible, dans la limite de 3 | `CANDIDATES_INCOMPLETE` |
| motif d'absence de candidat : nul s'il y a des candidats ; sinon le motif exact du moteur | `EMPTY_REASON_WITH_CANDIDATES`, `EMPTY_REASON_MISMATCH` |
| listes `manual` et drapeaux des marchés concordants ; présence, décision et `presented_as_admissible` exacts | `MANUAL_FLAG_MISMATCH`, `MANUAL_PRESENCE_MISMATCH`, `MANUAL_DECISION_MISMATCH` |
| compteurs = dénombrement des marchés, candidats et orphelins ; `evaluated` ≤ `authorized` | `COUNTS_MISMATCH` |
| usage des budgets = nombre de marchés, `evaluated` et taille du jeu de données | `BUDGET_USAGE_MISMATCH` |
| limites de budget : clés exactes, entiers stricts, profil identique à `budgets.profile` | `BUDGET_PROFILE_MISMATCH` |
| références d'un lot : état `VERIFIED` sans motif, ou `REFUSED` avec motif ; commit producteur sur 40 caractères hexadécimaux | `REF_STATE_REASON`, `COMMIT_EXPECTED` |

Le contrôle d'ordre des candidats ne refait pas le classement : il vérifie
seulement que l'ordre publié suit les scores publiés. Le choix par régime et
par diversité de base n'est pas recalculé.

## 6 bis. Sous-structures scientifiques (S4A-RV-02)

Chaque sous-structure publiée par `radar-rules/1.2.0` a une forme définie par
état, reprise du moteur (`surveillance.py`, `selection.criteria`) : clés
exactes, types et vocabulaires. Règle générale : le motif d'un critère ou
d'une mesure est `null` **si et seulement si** son état est `AVAILABLE`
(`REASON_ON_AVAILABLE`, `UNKNOWN_WITHOUT_REASON`). Les décimaux sont des
chaînes sans exposant (`DECIMAL_STRING_EXPECTED`) ; un ratio s'écrit avec
quatre décimales entre `0.0000` et `1.0000` (`RATIO_EXPECTED`).

| Sous-structure | Formes acceptées | Concordances vérifiées | Codes |
|---|---|---|---|
| `l2_quality` | `UNKNOWN` : `{state, reason, proof: UNKNOWN}` ; sinon `{state, reason, proof, status, evidence_ref, depth_levels}` (+ `scope` pour `VERIFIED_TOP_N`) | preuve = fonction du statut (`PROVEN`, `PROVEN_TOP_N`, `TO_QUALIFY`) ; état et motif fixés par le statut ; `VERIFIED` exige une référence de preuve ; périmètre : vérificateur `KRAKEN_CRC32`, instants valides ≤ instants de la grille, au plus 256 exclusions | `L2_PROOF_MISMATCH`, `L2_STATE_MISMATCH`, `L2_SCOPE_BOUNDS` |
| `continuity` | `UNKNOWN`/`INVALID` : `{state, reason, time}` ; `AVAILABLE`/`PARTIAL` : 11 clés (classe, ratio, couverts, attendus, trous, fraîcheur, âge) | `time` = état de l'heure de l'observation ; `INVALID` ⇔ heure incohérente ou contradictions ; couverts ≤ attendus ; `FRESH` ⇔ `AVAILABLE`, `STALE` ⇔ `PARTIAL` + `SOURCE_STALE` | `CONTINUITY_TIME_MISMATCH`, `CONTINUITY_INVALID_MISMATCH`, `CONTINUITY_BOUNDS`, `FRESHNESS_STATE_MISMATCH` |
| `spread_depth` | `{state, spread, depth, reason}` ; `spread` BBO ou inconnu ; `depth` L2 ou inconnue | état agrégé : `INVALID` si la continuité l'est, `AVAILABLE` si les deux parties le sont, `UNKNOWN` si les deux sont inconnues, sinon `PARTIAL` | `AGGREGATE_STATE_MISMATCH` |
| `activity_volatility` | `{state, activity, volatility, reason}` ; activité `TRADE_COUNT_WINDOW` ; volatilité avec régime et nature de prix | même règle d'agrégation | `AGGREGATE_STATE_MISMATCH` |
| `collection_cost` | `UNKNOWN` : `{state, reason, basis: null}` ; sinon 11 clés | `missing` = champs nuls, dans l'ordre du moteur ; `AVAILABLE` ⇔ rien ne manque, sinon `PARTIAL` + `COST_FIELDS_MISSING` | `COST_MISSING_MISMATCH`, `COST_STATE_MISMATCH` |
| `diversity` | `AVAILABLE` : `{state, regime, reason: null}` ; `UNKNOWN` : `{state, regime: null, reason}` | régime = régime publié par la volatilité, ou `null` | `DIVERSITY_REGIME_MISMATCH` |
| `observation` | présente : référence, nature de prix, fenêtre de 4 entiers, nombre d'échantillons ; absente : tout cela `null`, heure `UNKNOWN`, aucune contradiction | fin de fenêtre = début + (points − 1) × pas ; une observation absente rend les six critères `UNKNOWN` avec son propre motif ; `recent_data` = `ABSENT` (`NO_OBSERVATION`) ou `UNKNOWN`, et pour un marché observé = fraîcheur de sa continuité | `WINDOW_BOUNDS`, `ABSENT_OBSERVATION_WITH_DATA`, `CRITERION_WITHOUT_OBSERVATION`, `RECENT_DATA_MISMATCH` |
| `catalogue` et `sources[]` | catalogue : 11 clés typées ; sources triées et uniques, 10 clés typées | la place et le type de la source correspondent au marché ; `raw_sha256`, `collected_ms` et `metadata_current` du catalogue = ceux de sa source | `CATALOGUE_SOURCE_MISMATCH`, `CATALOGUE_SOURCE_UNKNOWN`, `SOURCES_NOT_ORDERED_OR_DUPLICATED` |
| identité | `market_id` = `place:type:BASE/QUOTE`, ou `place:type:?NATIF` si l'identité est insuffisante, avec un suffixe `~NATIF` éventuel ; `previous` : 4 clés | identifiant cohérent avec la place, le type de contrat, la base, la devise et le symbole natif | `MARKET_ID_IDENTITY_MISMATCH` |

`ADMISSIBLE_WITHOUT_OBSERVATION` reste en défense : une observation absente
est désormais refusée plus tôt par les concordances ci-dessus.

**Propriétés volontairement non vérifiées.** Les vérifier reviendrait à refaire
le travail du moteur :
- la valeur du score à partir des composantes et des poids, et les points de
  chaque composante à partir des mesures (barèmes du classement) ;
- les règles d'admissibilité : quels motifs une mission impose au vu des
  mesures ; seule la cohérence entre la décision et ses motifs publiés est
  vérifiée ;
- la sélection : places par régime et diversité de base. Seuls l'ordre publié
  et la complétude du nombre de candidats sont vérifiés ;
- les valeurs numériques mesurées : ratio = couverts / attendus, médiane du
  spread, RMS des rendements, âge. Seuls leurs types, formats et bornes sont
  vérifiés ;
- l'autorisation de chaque marché au regard de la politique, et la détection
  des observations orphelines ;
- le sens des textes libres : motifs en clair des candidats, limites,
  libellés, provenance.

## 7. Séparation des preuves et autorité (SA7, Phase D)

**Capacités réelles du moteur actuel**

| Entrée | Preuves acceptées par le moteur | Projetées par S4-a |
|---|---|---|
| `radar-fixture/1.0.0` | `SYNTHETIC` seulement | oui |
| `radar-batch/1.0.0` | `SYNTHETIC` ou `HISTORICAL` (artefacts hors ligne scellés) | `SYNTHETIC` seulement |
| LIVE | **n'existe pas** dans le Radar | jamais |

| Règle | Code |
|---|---|
| `HISTORICAL` non pris en charge par S4-a (décision E3) | `EVIDENCE_HISTORICAL_NOT_SUPPORTED` |
| `LIVE` toujours refusé | `EVIDENCE_LIVE_REFUSED` |
| toute autre nature | `EVIDENCE_KIND_UNKNOWN` |
| nature incompatible avec le schéma du jeu de données (défensif, inatteignable tant que seul SYNTHETIC est projeté) | `EVIDENCE_SCHEMA_COMBINATION_REFUSED` |
| `mode.evidence`, `dataset.evidence_kind` et l'`evidence_kind` de chaque observation identiques | `EVIDENCE_MIXED` |
| `dataset.admission = NONE` : aucune admission historique | `ADMISSION_INVARIANT` |
| `authority` exactement `{execution_authority: false, collection_authority: false, experiment_authority: false, proposal_status: PROPOSED_NOT_AUTHORIZED}` | `AUTHORITY_INVARIANT` |
| `mode` : réseau, collecte L2, PAPER et observation approfondie `DISABLED` | `AUTHORITY_INVARIANT` |
| `deep_observation_jobs` vide ; chaque candidat `PROPOSED_NOT_AUTHORIZED` | `AUTHORITY_INVARIANT` |
| budgets de production `{status: NOT_MEASURED, values: null}` | `PRODUCTION_BUDGETS_INVARIANT` |

Ces égalités sont **strictes** sur la forme canonique : `0` n'est pas
`false`, et `1` n'est pas `true`. Un export rescellé avec
`execution_authority: 0` est refusé.

## 8. Document `radar-projection/1.0.0`

La projection réorganise l'évaluation vérifiée ; elle ne calcule rien. Elle
ajoute seulement :
- les empreintes de l'export source ;
- la liste des contrôles effectués ;
- des énoncés fixes d'intégrité et d'autorité ;
- le rang publié recopié sur chaque instrument.

| Champ | Contenu | Pourquoi |
|---|---|---|
| `schema` | `radar-projection/1.0.0` | contrat versionné |
| `source` | `evaluation_schema`, `rules_version`, `ranking_version`, `evaluation_sha256`, `export_sha256`, `export_bytes` | versions et sceau de l'évaluation ; empreinte et taille des octets reçus |
| `integrity` | `seal`, `proves`, `producer_authenticity: NOT_PROVEN`, `checks` | distinction intégrité / authenticité (section 5) |
| `evidence` | `kind` et `mode` | nature des preuves (SYNTHETIC) et modes désactivés |
| `dataset` | identifiant, schéma, empreinte, taille, nature, `admission`, description, adaptateur | identité et provenance du jeu de données |
| `inputs` | références du lot (manifeste, catalogues, sources, observations refusées) ou `null` pour une fixture | provenance vérifiable d'un lot R1-B |
| `scanner_universe` | `sha256: null`, `state: NOT_AVAILABLE`, `reason`, `catalogue_sources` | E1 : voir section 11 ; on donne les empreintes brutes des catalogues, seule provenance réellement portée |
| `evaluation_time_ms` | instant de l'évaluation (donnée de l'entrée) | horodatage de l'évaluation, jamais l'heure de projection |
| `mission` | `id`, `label`, `needs_bbo`, `needs_l2_verified` | mission scientifique |
| `policy` | politique d'univers (places, types, devises, refus) | délimite la population |
| `population` | `counts`, `orphan_observations` | population et compteurs, observations sans marché visibles |
| `instruments[]` | voir ci-dessous, un par marché, dans l'ordre de l'évaluation | admissibilité, critères, scores |
| `candidates`, `candidates_empty_reason` | copiés tels quels | candidats, rangs, règle de sélection, motifs, critères manquants, coût, limites |
| `preferences` | `preferences_sha256`, listes `manual` | préférences opérateur pertinentes, présentées sans effet |
| `budgets` | profil, limites, production `NOT_MEASURED`, usage | budgets |
| `authority` | autorité de l'évaluation, `admission`, `deep_observation_jobs`, `projection_status` | autorité nulle ; une projection n'est ni une admission ni une autorisation |
| `projection_sha256` | SHA-256 de la forme canonique du reste | reproductibilité vérifiable |

**`instruments[]`**

| Champ | Contenu |
|---|---|
| `identity` | `market_id`, `venue`, `market_type`, `contract_type`, `base`, `quote`, `native_symbol`, `settlement_asset` |
| `catalogue`, `change`, `previous` | provenance du catalogue, empreintes brutes, cycle de vie, changement d'identité |
| `lifecycle` | découverte, autorisation, accès source, `recent_data`, décision scientifique |
| `observation` | présence, motif, nature, fenêtre, heure, contradictions (fraîcheur d'observation, E2) |
| `admissibility` | mission, décision, motifs, troncature |
| `criteria` | les six critères, avec état, base et motif, copiés tels quels |
| `score` | valeur, composantes, poids, manquants, qualité, plafond ; `null` hors `ADMISSIBLE` |
| `rank` | rang publié si candidat, sinon `null` ; jamais recalculé |
| `manual` | drapeaux sélection, épinglage, exclusion |

**Champs omis.** Aucun champ scientifique de l'évaluation n'est omis : chaque
champ d'un marché est porté par exactement un champ de son instrument (test
`check_faithful`). Le champ `reference` n'existe plus depuis R-REF.
L'évaluation ne contient ni échantillons bruts ni carnets L2, donc la
projection non plus.

**Champs volontairement absents de la projection**, pour rester
déterministe :
- heure de projection ;
- heure de publication (`published_at`) ;
- âge maximal (`max_age`) ;
- chemin du fichier ;
- identifiant de machine.

La fraîcheur de publication (E2) appartient à la couche qui sert la
projection (S4-b), hors du document.

### Frontière de publication (S4A-RV-03)

| Interface publique | Entrée | Sortie |
|---|---|---|
| `projection.project(raw)` | octets d'un export | projection vérifiée (`dict`) |
| `projection.project_bytes(raw)` | octets d'un export | projection vérifiée, forme canonique + `\n` |
| `verifier.verify_export(raw)` | octets d'un export | document vérifié **sans** déclaration `VERIFIED` (contrôle seul) |

`project(raw)` est le seul point d'entrée qui produit une projection
vérifiée. Les deux interfaces de projection partent d'**octets** et appellent
le vérificateur dans le même appel. La construction est privée
(`_build_projection`). Elle ne reçoit que le résultat de `verify_export(raw)`
obtenu dans `project`, et travaille sur une copie profonde. Aucune interface
publique n'accepte un document : un `dict` passé à `project` ou à
`project_bytes` est refusé avec `INPUT_NOT_BYTES`. Modifier le résultat d'un
`verify_export` antérieur n'a aucun effet sur une projection.

**Pour S4-b** : la route lit les octets de l'export, appelle
`project_bytes(raw)` et sert ces octets tels quels. Elle ne doit jamais
construire, compléter ou réécrire une projection, ni servir un document qui
ne sort pas de `project_bytes`. La fraîcheur de publication (E2) va dans
l'enveloppe de service, hors de ces octets.

## 9. États inconnus (SA6)

- Un `null` de l'évaluation reste `null` à la même place ; le test compare
  l'ensemble des chemins `null` de chaque marché et de son instrument.
- `UNKNOWN ≠ 0` : la comparaison stricte distingue `null`, `0` et `false`.
- Un critère `UNKNOWN` ou `INVALID` porte toujours un motif
  (`UNKNOWN_WITHOUT_REASON`). Une observation absente porte toujours un motif
  et ne peut pas être `FRESH` ou `STALE` (`FRESHNESS_WITHOUT_OBSERVATION`).
- Une composante de score n'est présente que si son critère est connu ; un
  export rescellé qui note une entrée inconnue est refusé (`UNKNOWN_SCORED`).
- Un marché `UNKNOWN`, `A_QUALIFIER` ou `NON_ADMISSIBLE` n'a ni score ni rang.
  Les compteurs `unknown` et les observations orphelines restent visibles.

## 10. Déterminisme (SA8) et isolation (SA9)

- La projection est une fonction pure des octets : mêmes octets, mêmes octets
  de projection (`project_bytes`), dans un même processus et entre
  processus avec des `PYTHONHASHSEED` différents.
- Aucune horloge n'est lue ; un test remplace `time` et `datetime` par des
  fonctions qui échouent.
- Seul `export_sha256` dépend du saut de ligne final ; tout le reste est
  identique.
- Imports autorisés : `__future__`, `copy`, `re`, `decimal`, `radar_selection.fixture` et
  le paquet lui-même. Il n'y a :
  - ni réseau, ni processus ;
  - ni `open`, ni `exec`, ni `eval` ;
  - aucun moteur Radar chargé.
- À l'exécution, `open` et `socket` sont interdits pendant la projection ;
  rien n'est écrit.
- Aucune route ajoutée à l'Operator API, aucun frontend, aucun collecteur.
- Aucun changement dans :
  - le moteur Radar, ses poids, ses seuils ou ses contrats ;
  - l'archive R-REF ;
  - PAPER, FIN, PPL ou Advisor ;
  - le VPS ;
  - C2-C ou C2-D.

## 11. Limites résiduelles et décisions ouvertes

1. **E1, empreinte de l'univers Scanner.** `radar-evaluation/1.2.0` ne porte
   pas `scanner_universe_sha256`. Le Scanner la calcule à partir de ses
   propres paires et actifs ; elle ne se déduit pas des données du Radar. La
   projection publie donc `scanner_universe.sha256 = null`, état
   `NOT_AVAILABLE`, motif `NOT_CARRIED_BY_RADAR_EVALUATION_1_2_0`, et le
   conserve. Elle donne à la place les empreintes brutes des catalogues
   sources (`catalogue_sources[].raw_sha256`). La contre-revue S4A-RV1
   recommande l'option 2 (relation de provenance par catalogues, section 13).
   Elle reste **soumise à l'acceptation explicite de l'opérateur** sur la
   sémantique d'E1 ; elle n'est pas implémentée dans S4-a.
2. **E2, fraîcheur de publication.** Elle n'est pas dans la projection, qui
   doit rester déterministe. S4-b devra la porter dans l'enveloppe de service,
   sans modifier la projection.
3. **Authenticité.** Le sceau prouve l'intégrité, pas le producteur. Une
   signature ou un canal de confiance relève d'une décision distincte.
4. **HISTORICAL.** Le moteur accepte des lots `HISTORICAL`, mais S4-a les
   refuse. Aucune projection HISTORICAL ne sera produite sans décision
   explicite et sans gates C2-C et C2-D.
5. **Textes libres.** Descriptions, libellés, provenance et motifs en clair
   sont contrôlés en type et en longueur, pas en sens.
6. **Budgets de production** : toujours `NOT_MEASURED`. La borne de
   1 000 001 octets est une borne de test, pas une capacité mesurée.
7. **Preuve SYNTHETIC.** Les preuves portent sur les fixtures R0 et le lot
   R1-B synthétique. Il n'y a aucune donnée réelle, aucun runtime et aucun
   déploiement. SOURCE PROOF ≠ RUNTIME PROOF.

## 13. E1 : relation de provenance Scanner ↔ Radar (préparation, non implémentée)

Statut : **définition documentaire seulement**. Aucune jointure n'est codée
dans S4-a, et la projection garde `scanner_universe.sha256 = null`.

**Ce que la relation compare.** Pour chacun des quatre marchés sources
(`MEXC_SPOT`, `MEXC_PERPETUAL`, `KRAKEN_SPOT`, `KRAKEN_PERPETUAL`), on compare
deux dictionnaires d'empreintes SHA-256 des octets bruts des catalogues :
- `scanner_universe.catalogue_sources[market].raw_sha256` de la projection
  Radar ;
- `sources[market].raw_sha256` de `scanner-universe/1.1.0`.

| État par marché source | Condition |
|---|---|
| `SAME_CATALOGUE_BYTES` | les deux dictionnaires existent, sont non vides et identiques |
| `DIFFERENT_CATALOGUE_BYTES` | les deux existent et diffèrent |
| `NOT_COMPARABLE` | un côté manque, est vide ou porte un catalogue `UNAVAILABLE` |

Relation globale, calculée seulement si les quatre marchés sont comparables :
`CATALOGUE_PROVENANCE_MATCH` si les quatre sont `SAME_CATALOGUE_BYTES`, sinon
`CATALOGUE_PROVENANCE_MISMATCH`. Si un marché n'est pas comparable :
`CATALOGUE_PROVENANCE_UNKNOWN`. Ce n'est jamais un succès par défaut.

**Ce que la relation ne dit pas.** Une concordance des catalogues n'est
**jamais** une identité des univers. Les deux produits appliquent des règles
différentes aux mêmes octets :
- le Scanner garde l'intersection des quatre marchés par BASE/QUOTE, groupée
  par actif ;
- le Radar applique sa politique par instrument (places, types, devises,
  classes d'actifs, refus) et conserve les marchés retirés.

`CATALOGUE_PROVENANCE_MATCH` signifie seulement : « le Radar a évalué à partir
des mêmes octets de catalogue que ceux du Scanner ». Il ne doit jamais être
affiché comme « même univers », ni remplacer `scanner_universe_sha256`. La
jointure des instruments reste une étape distincte, par l'identité exacte
(`market_id`, `native_symbol`, `contract_type`, `quote`, `settlement_asset`).
Un instrument sans entrée reste « Non évalué ».

**Limites.** Les catalogues des fixtures R0 sont reconstruits par
canonicalisation (`canonical(body)`), donc leurs empreintes ne correspondront
jamais à des octets réels du Scanner. Seul un lot R1-B, qui garde les octets
d'origine, peut produire `SAME_CATALOGUE_BYTES`. La relation ne prouve pas
non plus l'authenticité des deux côtés (section 5).

**Avant toute implémentation (S4-b ou ultérieur)**, l'opérateur doit accepter
explicitement cette sémantique. Le nom des états, leur affichage et la place de
la relation (projection versionnée ou enveloppe de service) relèvent de cette
décision.

## 12. Gates SA1 à SA10

| Gate | Exigence | Preuve |
|---|---|---|
| SA1 | Contrat versionné et documenté | ce document ; `test_s4a_a_contract.py` (`SA1_*`) : schéma, versions épinglées au moteur, chaque code de refus documenté |
| SA2 | Lecture stricte et bornée | `test_s4a_b_strict_read.py` (`SA2_*`) : taille, UTF-8, BOM, JSON, clés dupliquées, flottants, non-finis, imbrication, forme canonique |
| SA3 | Empreinte vérifiée | `test_s4a_b_strict_read.py` (`SA3_*`) : recalcul, format, absence, changement d'un caractère, sceau rescellé insuffisant |
| SA4 | Refus des versions incompatibles | `test_s4a_a_contract.py` (`SA4_*`) : 27 sorties archivées refusées `PRE_RREF_EVALUATION`, versions futures, combinaisons mixtes |
| SA5 | Fidélité des champs scientifiques | `test_s4a_c_fidelity.py` (`SA5_*`) : 15 cas différentiels, préférences, sortie réelle de `export` |
| SA6 | Préservation des états inconnus | `test_s4a_c_fidelity.py` (`SA6_*`) et cas adversariaux `UNKNOWN_*` |
| SA7 | Séparation des preuves | `test_s4a_d_adversarial.py` (`SA7_*`) : HISTORICAL, LIVE, nature inconnue, mélange, autorité rescellée |
| SA8 | Reproductibilité déterministe | `test_s4a_c_fidelity.py` (`SA8_*`) : pureté, entre processus et graines, aucune horloge |
| SA9 | Isolation opérationnelle | `test_s4a_e_isolation.py` (`SA9_*`) |
| SA10 | Non-régression et CI verte | suites Radar existantes inchangées ; CI au HEAD de la PR |

Contre-revue S4A-RV1 : `test_s4a_f_rv1.py`, avec des exports rescellés.

| Constat | Correctif | Tests |
|---|---|---|
| RV-01 types numériques | rangs entiers stricts (un booléen est refusé) ; scores et plafonds en chaînes à deux décimales, sans zéro de tête, entre 0.00 et 100.00 ; plafond cohérent avec les poids manquants ; ratios et décimaux formatés | `test_RV01_*` |
| RV-02 cohérence structurelle | sous-structures définies par état (section 6 bis) ; concordance des critères et du coût des candidats avec leur marché ; catalogue ↔ source ; identité ↔ `market_id` ; limites de budget, entrées de lot et notes fermées | `test_RV02_*` |
| RV-03 frontière de publication | `project(raw)` seul point d'entrée vérifié ; `_build_projection` privé ; `project_bytes(raw)` remplace la sérialisation d'un document | `test_RV03_*` |
| RV-04 refus typés | `schema_version` borné avant toute conversion ; détail de refus borné ; `RecursionError` et erreurs de canonicalisation typées | `test_RV04_*` |

Les cas adversariaux rescellés (`test_resealed_incoherent_export_is_refused`)
et le test de mutations aléatoires rescellées démontrent que la validation ne
repose pas sur l'empreinte seule.
