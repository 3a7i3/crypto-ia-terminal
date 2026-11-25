# CAT R1-B — Rapport de validation

**Portée : SOURCE PROOF, données SYNTHETIC, hors réseau.** Ce rapport ne
prouve aucun comportement runtime, aucune donnée réelle et aucune admission.
Base : `main` à `ca0354f` (fusion de #607 vérifiée). Date : 2026-11-24.

## 1. Ce qui a été livré

| Lot du plan | Contenu |
|---|---|
| L1 | Contrat [CAT_R1B_CONTRAT_LOT_RADAR.md](../../contracts/CAT_R1B_CONTRAT_LOT_RADAR.md) ; amendement section 9 du contrat R0 |
| L2 | `contract.py` : `radar-evaluation/1.1.0`, `radar-rules/1.1.0`, `radar-ranking/1.2.0`, `VERIFIED_TOP_N = 40` (D4), natures `SYNTHETIC`/`HISTORICAL`, plafonds |
| L3 | `adapter_scanner.py` (manifeste Scanner → références épinglées), `batch.py` (chargement strict et vérification), `refs.py` (résolution sûre) |
| L4 | `adapter_bbo.py` (ancre, manifeste de journal, fenêtres → observations MID_BBO), `batch_build.py` (constructeur CLI) |
| L5 | `engine.evaluate_batch`, terminal `--batch` / `--evidence-root`, garde de lecture |
| L6 | Arbre de preuves SYNTHETIC et générateur `tests/radar_selection/build_batches.py`, tests `test_g_batch.py`, ce rapport et le [guide](CAT_R1B_GUIDE_LOT.md) |

## 2. Résultats des contrôles

Exécutés localement dans l'environnement isolé. Aucune CI lancée.

| Contrôle | Python 3.13.18 | Python 3.11 |
|---|---|---|
| `tests/radar_selection` (72 R0 inchangés + 68 R1-B) | 140 réussis | 140 réussis |
| `radar_selection` + `scanner_universe` + `radar_composite` + `market_flow` | 485 réussis, 3 ignorés | 485 réussis, 3 ignorés |
| Gate ruff du dépôt (`scripts/ci/ruff_baseline_gate.py check`, ruff 0.15.8) | 0 nouvelle violation | — |
| `build_batches --check` (reproductibilité octet pour octet) | aucune différence | — |

Les 3 tests ignorés dépendent de `fastapi`, absent de l'environnement ; ils
sont étrangers à R1-B.

## 3. Critères d'acceptation

| Id | Critère | Test |
|---|---|---|
| T01 | même lot ⇒ mêmes octets et empreintes | `test_T01_*` |
| T02 | octets bruts et fractionnaires des catalogues jusqu'à `parse_all`, sans conversion | `test_T02_*` |
| T03 | catalogue ou manifeste falsifié ⇒ `UNAVAILABLE`/`REFUSED`, jamais inventé | `test_T03_*` |
| T04 | fenêtre altérée ⇒ seule sa source est refusée | `test_T04_*` |
| T05 | `PRICE_KIND_MIXED` | `test_T05_*` |
| T06–T07 | quote ou type de contrat contraire ⇒ non admissible, jamais fusionné | `test_T06_*`, `test_T07_*` |
| T08–T09 | activité et profondeur UNKNOWN avec motif, jamais 0 | `test_T08_*`, `test_T09_*` |
| T10 | instants invalides omis et cités | `test_T10_*` |
| T11–T12 | couverture dépassée, référence absente ⇒ marchés UNKNOWN visibles | `test_T11_*`, `test_T12_*` |
| T13 | chaque plafond refuse avec un code stable | `test_T13_*` (3 tests) |
| T14 | aucun import réseau/runtime ; garde réseau, écriture et lecture | `test_T14_*` |
| T15 | référence BTC hors classement, même en HISTORICAL ; `admission: NONE` | `test_T15_*` |
| T16 | `LIVE` et natures inconnues refusés | `test_T16_*` |
| T17 | même science à version identique, fixture ou lot (4 univers) | `test_T17_*` |
| T18 | écriture interrompue ne laisse rien ; jamais de remplacement | `test_T18_*` |
| R02–R14 | non-régressions du plan (fixture R0 inchangée, portée TOP_N, aucun `VERIFIED` depuis une source, 40 points, mid non corrigé, fenêtres non contiguës, ancre, références, codes Scanner, reproductibilité, terminal) | `test_R*` |

## 4. Décisions et écarts constatés pendant l'implémentation

- **Nature HISTORICAL ↔ OBSERVATION.** `bbo_pilot` et `bbo_history`
  n'emploient pas `HISTORICAL` : un corpus collecté y porte `OBSERVATION`. Un
  lot `HISTORICAL` exige donc des sources `OBSERVATION` ; un lot `SYNTHETIC`
  exige des sources `SYNTHETIC` ; `MIXED` est refusé. Aucun autre producteur
  n'est modifié.
- **Garde de lecture.** `sys.path` contient le répertoire courant ; sous les
  répertoires d'import, seuls les fichiers de code Python sont lisibles, pour
  que le répertoire courant n'ouvre pas tous ses fichiers de données.
- **Plafond des instants exclus.** Code distinct `EXCLUDED_INSTANTS_BOUND`,
  séparé de l'incohérence `L2_SCOPE_COUNTS`.
- **Codes d'erreur Scanner.** Le Scanner produit des codes en majuscules
  (`TRANSPORT_<NOM>` est mis en majuscules), compatibles avec `parse_all`. Le
  lot traduit par précaution un code hors grammaire en
  `SCANNER_ERROR_NOT_CANONICAL`, en gardant le texte d'origine visible.
- **Affichage des critères PARTIAL.** Comme en R0, la ligne « Critères
  disponibles » d'un candidat ne liste que les critères `AVAILABLE` ; les
  critères `PARTIAL` (L2 TOP_N, spread sans profondeur) apparaissent dans
  « manquants », avec leur détail dans `inspect`. Comportement R0 conservé.

## 5. Contre-revue du 2026-11-24 (L2 sécurité, L3 à L6)

### 5.1 Défaut bloquant corrigé : sortie de la racine par course sur un parent

`refs.read_ref` vérifiait chaque composant par `lstat` sur le chemin joint, puis
ouvrait le chemin complet avec `O_NOFOLLOW`, qui ne protège que le dernier
composant. Un test de concurrence isolé (un processus remplace en boucle
`root/sub` par un lien vers un dossier extérieur contenant un fichier de même
nom) a montré que le lecteur **renvoyait le contenu du fichier extérieur** :
132 lectures sur 200 000, et 12 040 ouvertures de descripteurs hors racine.
Le contrôle d'inode ne suffisait pas : le `lstat` du fichier passait lui-même
par le parent remplacé.

Correction minimale : traversée par descripteurs de répertoire. La racine est
ouverte (`O_DIRECTORY | O_NOFOLLOW`) et comparée à l'identité relevée par
`evidence_root` ; chaque composant est examiné et ouvert relativement au
descripteur de son parent avec `O_NOFOLLOW`, puis comparé par inode. Plafonds,
codes de refus, contrôle d'inode et SHA-256 sont conservés ; nouveau code
`REF_PLATFORM_UNSUPPORTED` si l'ouverture relative n'existe pas. Le garde
d'audit replace les noms relatifs sous le répertoire parcouru
(`refs.WALK`) pour continuer à refuser toute lecture hors racine.

Après correction, même sonde : 0 contenu extérieur, 0 descripteur extérieur.
Tests ajoutés : `test_R10_parent_swapped_during_read_never_leaves_the_root`
(échoue sur l'ancien code, passe sur le nouveau) et
`test_R10_evidence_root_replaced_after_resolution_is_refused`.

### 5.2 Défaut mineur corrigé

`EXCLUDED_INSTANTS_BOUND` (refus de forme) sortait en code `2` au lieu de `3`
dans le terminal. Corrigé ; test
`test_R14_every_batch_shape_refusal_exits_as_input_refused`.

### 5.3 Points de revue L3 à L6

| # | Point | Constat | Preuve |
|---|---|---|---|
| 1 | Catalogues en octets bruts | conformes : octets d'origine vérifiés (taille, SHA-256, entrée du manifeste) puis `parse_all` ; aucune re-sérialisation ; fractionnaires lus en `Decimal` par le Scanner | T02, T03, R11 |
| 2 | Ancrage SHA-256 BBO | conforme : ancre épinglée, manifeste lié par ses empreintes scellées, chaque fenêtre présente dans l'ancre à sa position | T04, R09, T12 |
| 3 | Provenance par observation | conforme : `source_id`, `evidence_ref` `bbo:<corpus>#<venue>`, commit producteur égal à `collection_commit`, observation re-dérivée et comparée | R13, T04 |
| 4 | Kraken/MEXC, Spot/Perp, USD/USDT | conforme : symbole natif tiré des `bindings` du journal, type `SPOT` exigé, jointure par `(venue, type, symbole natif)`, conflit base/quote non admissible | T06, T07 |
| 5 | MID_BBO exact | conforme : égalité `Decimal` exacte, refus `MID_REPRESENTATION_MISMATCH`, aucune correction | R07 |
| 6 | Instants invalides | conformes : omis, cités avec motif dans la portée | T10 |
| 7 | Activité, profondeur absentes | UNKNOWN avec motif, jamais 0 | T08, T09 |
| 8 | `VERIFIED_TOP_N = 40` | conforme, avec `depth_levels`, `scope` et motif ; jamais `VERIFIED` depuis une source | R03 à R06 |
| 9 | Lecture, mémoire, stockage | plafonds par référence et par lot appliqués ; écriture atomique et bornée à `--state-dir`. Réserve levée le 2026-11-25 : budget agrégé de 1 000 000 octets, références répétées refusées, pic mesuré au plafond 45,7 MiB (section 6) | T13, T18, R14, R15 |
| 10 | Réseau, collecte, rejeu, PAPER, autorité | aucun import réseau ni producteur ; garde d'audit en sous-processus ; `admission: NONE` ; aucun job lancé | T14, T15 |

## 6. Réserve « budget mémoire agrégé » (2026-11-25)

Avant cette réserve, un lot pouvait faire lire jusqu'à environ 99 Mo : cinq
catalogues de 8 Mo et 59 références de 1 Mo, chacune dans son propre plafond.
Correction minimale, sans toucher aux adaptateurs ni à la sélection :

- `contract.MAX_BATCH_REF_BYTES = 1 000 000` ;
- `batch.load_batch` refuse un lot dont les tailles déclarées dépassent ce
  total, avant toute lecture (`REFS_BYTES_BOUND`), ainsi que toute référence
  répétée (`DUPLICATE_REF`). Une ancre reste partageable par plusieurs
  sources avec la même empreinte ;
- `refs.read_all(..., total=...)` compte les octets réels, y compris ceux des
  manifestes et des ancres qui ne déclarent pas de taille, et refuse le lot
  au dépassement. Le terminal et `batch_build` lui passent ce total ;
- les deux codes produisent un refus d'entrée global (sortie `3`).

Mesures et lecture : contrat § 8. Au plafond, le pic est de 45,7 MiB, sous le
budget mémoire de test de 64 MiB. Au-delà, le lot est refusé avant lecture
(0,15 MiB), alors que sans le plafond le pic aurait été de 73,5 MiB. Outil
reproductible : `python -m tests.radar_selection.measure_batch_memory`. Tests :
`test_R15_*`, qui couvrent le dépassement déclaré, le dépassement réel en
lecture, cinq formes de répétition et le pic mesuré.

Limite qui demeure : la mémoire croît avec le nombre de marchés, et le plafond
de sortie R0 limite l'évaluation à quelques centaines de marchés. Aucune
capacité de production n'est certifiée.

## 7. Limites

- Toutes les preuves du dépôt sont SYNTHETIC (transport simulé `FakeVenues`,
  catalogues inventés). Aucune valeur n'est calibrée.
- Les fenêtres BBO ne portent que le premier niveau : profondeur toujours
  UNKNOWN. Activité et coût ne sont pas mesurés par ces sources.
- Les 40 points de `VERIFIED_TOP_N` sont transitoires (D4).
- Plafonds de production : `NOT_MEASURED`.
- Aucun lot HISTORICAL réel n'a été construit : cela exigerait un corpus
  scellé existant et une décision séparée.
