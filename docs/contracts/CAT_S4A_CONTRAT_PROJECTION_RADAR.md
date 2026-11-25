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
| score et plafond au format décimal `0.00` à `100.00` | `SCORE_DECIMAL_EXPECTED` |
| un marché admissible a une observation | `ADMISSIBLE_WITHOUT_OBSERVATION` |
| au plus 3 candidats, rangs 1..n, sans doublon | `CANDIDATES_TOO_MANY`, `RANK_SEQUENCE`, `DUPLICATE_CANDIDATE` |
| chaque candidat existe, a la même identité, est `ADMISSIBLE` et n'est pas exclu par l'opérateur | `CANDIDATE_NOT_IN_MARKETS`, `CANDIDATE_IDENTITY_MISMATCH`, `CANDIDATE_NOT_ADMISSIBLE`, `CANDIDATE_EXCLUDED_BY_OPERATOR` |
| score, qualité et régime du candidat = ceux de son marché | `CANDIDATE_SCORE_MISMATCH`, `CANDIDATE_REGIME_MISMATCH` |
| critères disponibles et manquants forment une partition des six critères | `CANDIDATE_CRITERIA_PARTITION` |
| ordre de présentation cohérent avec les valeurs publiées (qualité, score décroissant, `market_id`) | `CANDIDATES_NOT_ORDERED` |
| autant de candidats que possible, dans la limite de 3 | `CANDIDATES_INCOMPLETE` |
| motif d'absence de candidat : nul s'il y a des candidats ; sinon le motif exact du moteur | `EMPTY_REASON_WITH_CANDIDATES`, `EMPTY_REASON_MISMATCH` |
| listes `manual` et drapeaux des marchés concordants ; présence, décision et `presented_as_admissible` exacts | `MANUAL_FLAG_MISMATCH`, `MANUAL_PRESENCE_MISMATCH`, `MANUAL_DECISION_MISMATCH` |
| compteurs = dénombrement des marchés, candidats et orphelins ; `evaluated` ≤ `authorized` | `COUNTS_MISMATCH` |
| usage des budgets = nombre de marchés, `evaluated` et taille du jeu de données | `BUDGET_USAGE_MISMATCH` |
| références d'un lot : état `VERIFIED` sans motif, ou `REFUSED` avec motif | `REF_STATE_REASON` |

Le contrôle d'ordre des candidats ne refait pas le classement : il vérifie
seulement que l'ordre publié suit les scores publiés. Le choix par régime et
par diversité de base n'est pas recalculé.

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
  de projection (`projection_bytes`), dans un même processus et entre
  processus avec des `PYTHONHASHSEED` différents.
- Aucune horloge n'est lue ; un test remplace `time` et `datetime` par des
  fonctions qui échouent.
- Seul `export_sha256` dépend du saut de ligne final ; tout le reste est
  identique.
- Imports autorisés : `__future__`, `copy`, `re`, `radar_selection.fixture` et
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
   `NOT_AVAILABLE`, motif `NOT_CARRIED_BY_RADAR_EVALUATION_1_2_0`. Elle
   donne à la place les empreintes brutes des catalogues sources
   (`catalogue_sources[].raw_sha256`), comparables à `sources[].raw_sha256`
   de `scanner-universe/1.1.0`.
   **Décision opérateur requise avant S4-b**, entre deux options :
   - porter l'empreinte de l'univers dans une future version du moteur, ce qui
     exige une nouvelle version et donc une décision ;
   - accepter la jointure par empreintes de catalogues.
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

Les cas adversariaux rescellés (`test_resealed_incoherent_export_is_refused`)
et le test de mutations aléatoires rescellées démontrent que la validation ne
repose pas sur l'empreinte seule.
