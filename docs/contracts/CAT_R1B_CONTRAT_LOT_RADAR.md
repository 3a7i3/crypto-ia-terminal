# CAT R1-B — Contrat du lot d'observations du Radar (`radar-batch/1.0.0`)

Statut : **source seule, hors réseau**. Code : `observability/radar_selection/`
(`batch.py`, `adapter_scanner.py`, `adapter_bbo.py`, `refs.py`,
`batch_build.py`, constantes dans `contract.py`). Ce contrat amende le contrat
R0 ([CAT_R0_CONTRAT_RADAR.md](CAT_R0_CONTRAT_RADAR.md), section 9). Il
n'autorise ni collecte, ni rejeu d'un corpus réel, ni déploiement, ni PAPER,
ni admission C2-C ou C2-D.

Décisions opérateur appliquées (2026-11-24) :

- **D1** : catalogues Scanner passés en octets bruts, vérifiés par SHA-256
  avant `parse_all` ; jamais re-sérialisés ; nombres fractionnaires jamais
  convertis ; résolution sûre des références.
- **D2** : `HISTORICAL` admis seulement comme entrée hors ligne à provenance
  vérifiée. `LIVE` interdit. `HISTORICAL` n'est pas une admission.
- **D3** : statut `VERIFIED_TOP_N` ; pour Kraken, 10 niveaux attestés par
  CRC32 sur les instants valides seulement ; `depth_levels`, portée et limites
  publiées ; jamais « carnet complet » ; profondeur ±10 bps UNKNOWN si non
  couverte.
- **D4** : `VERIFIED_TOP_N` = 40 points, état `PARTIAL`, preuve
  `PROVEN_TOP_N`. Aucun producteur R1-B ne publie `VERIFIED`. Les 40 points
  sont une pondération transitoire de classement, pas une preuve de fiabilité
  égale ; toute hausse exige un protocole de calibration séparé.

## 1. Objet et autorité

Le lot transmet au Radar les informations minimales de son évaluation et les
références de preuve de ces informations. Il n'a **aucune autorité**.

- Aucune donnée brute de marché n'est recopiée dans le lot : elle reste chez
  son producteur (passage Scanner, fenêtres BBO rejouées et ancre scellée).
- Toute évaluation d'un lot porte `dataset.admission = "NONE"`.
- La référence `kraken:spot:BTC/USDT` reste hors classement
  (`in_ranking: false`, `NOT_YET_HISTORICALLY_ADMITTED`), y compris en
  `HISTORICAL`.

## 2. Nature de la preuve

| `evidence_kind` du lot | Admis | Nature exigée de chaque source BBO (`bbo_pilot`) |
|---|---|---|
| `SYNTHETIC` | oui | `SYNTHETIC` (transport simulé) |
| `HISTORICAL` | oui, hors ligne | `OBSERVATION` (corpus collecté puis scellé), relu hors ligne |
| `LIVE`, autre, absent | **non** : `EVIDENCE_KIND_NOT_ALLOWED` | — |

Un lot a une seule nature. Une source dont l'ancre ou le manifeste de journal
ne porte pas la nature exigée est refusée (`EVIDENCE_KIND_MIXED`) ; `MIXED`
n'est jamais accepté. Une observation sans source (`source_id: null`) n'est
admise qu'en `SYNTHETIC` (`HISTORICAL_OBSERVATION_WITHOUT_SOURCE`).
`radar-fixture/1.0.0` reste inchangé : `SYNTHETIC` seulement, fractionnaires
refusés.

## 3. Structure

Clés de premier niveau, ensemble fermé : `batch_schema`, `adapter_version`,
`dataset_id`, `description`, `evidence_kind`, `evaluation_time_ms`, `policy`,
`catalogue_manifest`, `catalogue_refs`, `source_access`, `previous_universe`,
`sources`, `observations`.

- `batch_schema = "radar-batch/1.0.0"`, `adapter_version = "radar-adapter/1.0.0"`.
- `policy`, `source_access` et `previous_universe` ont la forme de
  `radar-fixture/1.0.0`.
- Temps en millisecondes époque UTC (entiers) ; valeurs en chaînes décimales ;
  JSON strict (pas de fractionnaire, de clé dupliquée, de NaN/Infinity).
- `dataset.sha256` porte sur la forme canonique R0 du lot (clés triées,
  séparateurs compacts, UTF-8).
- Un défaut de forme refuse tout le lot avec un code stable ; un lot n'est
  jamais lu à moitié.

## 4. Catalogues (D1)

- `catalogue_manifest = {ref, sha256}` désigne le `manifest.json` d'un passage
  Scanner (`scanner_universe.collect`), épinglé par l'opérateur.
- `catalogue_refs` contient exactement les cinq documents du Scanner, chacun
  `{ref, sha256, bytes, received_ms, error}`. `ref`/`sha256`/`bytes` et
  `error` s'excluent (`REF_XOR_ERROR`). Chaque entrée doit égaler celle du
  manifeste (`CATALOGUE_REF_NOT_IN_MANIFEST`) ; un manifeste non vérifié rend
  les cinq catalogues `REFUSED` (`CATALOGUE_MANIFEST_*`).
- Le Radar reçoit les **octets d'origine**, vérifie taille et empreinte
  (`REF_SIZE_MISMATCH`, `REF_SHA_MISMATCH`), puis appelle
  `scanner_universe.catalogues.parse_all` sur ces octets, qui lit les
  fractionnaires en `Decimal`. Plafond : `MAX_RAW_BYTES` du Scanner.
- Un document absent, en erreur ou non vérifié rend sa source de catalogue
  `UNAVAILABLE`, visible ; ses marchés ne deviennent pas une liste vide.
- Un code d'erreur Scanner hors de la grammaire de `parse_all` est transmis
  comme `SCANNER_ERROR_NOT_CANONICAL` ; le texte d'origine reste dans
  `inputs.catalogues`.
- Les marchés issus du lot portent `catalogue.provenance =
  "SCANNER_RAW_CATALOGUE"` (fixture : `SYNTHETIC_FIXTURE_CATALOGUE`).

## 5. Résolution des références

Seule la CLI lit des fichiers (`refs.py`) ; le cœur reçoit `{ref: octets}`.

- Une seule racine `--evidence-root`, répertoire réel, pas un lien
  (`EVIDENCE_ROOT_MISSING`, `EVIDENCE_ROOT_NOT_A_DIRECTORY`).
- Grammaire d'une `ref` : `[A-Za-z0-9._-]{1,80}(/[A-Za-z0-9._-]{1,80}){0,7}`,
  sans composant `.` ni `..` (`REF_SYNTAX`).
- Chaque composant est vérifié par `lstat` (pas de lien : `REF_SYMLINK`) ; la
  cible est un fichier régulier (`REF_NOT_REGULAR`), sous la racine
  (`REF_OUTSIDE_ROOT`), dans son plafond (`REF_TOO_LARGE`), ouvert avec
  `O_NOFOLLOW` et du même inode que celui vérifié
  (`REF_CHANGED_DURING_READ`). Une référence absente (`REF_MISSING`) est
  signalée par la vérification, pas ignorée.
- Le hook d'audit refuse toute lecture hors de `--evidence-root` et
  `--state-dir` (`RADAR_READ_OUTSIDE_EVIDENCE_ROOT`), sauf les fichiers de
  code Python des répertoires d'import ; tout réseau et sous-processus ; toute
  écriture hors de `--state-dir`.

## 6. Sources BBO et observations

**Source** : `{source_id, kind, producer_module, producer_commit, corpus_id,
pair, anchor{ref, sha256}, manifest{ref, sha256}, artifacts[{ref, sha256,
bytes}], coverage{start_ms, end_ms}}`, `kind = "BBO_REPLAY_WINDOWS"`,
`source_id = "bbo:<corpus_id>"`.

Vérification d'une source (un échec rend la source `REFUSED` et ses
observations UNKNOWN avec le code ; le reste du lot est évalué) :

- ancre `bbo-composite-history/1.0.0` valide (`ANCHOR_INVALID`), paire
  présente ; `corpus_id + ".tar.gz"` = `archive_name` (`CORPUS_ID_MISMATCH`) ;
  `producer_commit` = `collection_commit` (`PRODUCER_COMMIT_MISMATCH`) ;
- manifeste de journal lié à l'ancre par ses empreintes scellées,
  `COMPLETED`, de même nature (`MANIFEST_NOT_BOUND_TO_ANCHOR`,
  `EVIDENCE_KIND_MIXED`) ; ses `bindings` donnent le symbole natif par venue ;
- chaque fenêtre figure dans l'ancre avec la même empreinte et à sa position
  (`ARTIFACT_NOT_IN_ANCHOR`, `SOURCE_ARTIFACT_SHA_MISMATCH`,
  `WINDOW_NOT_AT_ANCHOR_POSITION`), est valide (`WINDOW_INVALID`), contiguë et
  au même pas (`WINDOW_GRID_MISMATCH`), dans la couverture déclarée
  (`SOURCE_COVERAGE_MISMATCH`, `WINDOW_BEYOND_COVERAGE`) ;
- chaque observation publiée est **re-dérivée** des fenêtres vérifiées et doit
  lui être égale (`OBSERVATION_NOT_DERIVED_FROM_SOURCE`).

**Observation** : clés R0, plus `source_id` et `unknown_reasons`.

- `price_kind = "MID_BBO"`, unique dans la série (`PRICE_KIND_MIXED`).
- `price` est le `mid` publié, recopié sans correction ; si
  `mid ≠ (bid+ask)/2` en `Decimal` exact, l'observation est refusée
  (`MID_REPRESENTATION_MISMATCH`).
- Seuls les instants évalués, éligibles, `SYNCED`, avec bid et ask donnent un
  échantillon (`t_ms = instant_ms`). Les autres sont **omis** et listés dans
  `l2.scope.excluded_instants` avec leur motif (`NOT_EVALUATED`, `STATE_*`,
  `CONTINUITY_*`, `BBO_VALUE_MISSING`). Aucun `t_ms` n'est nul.
- `unknown_reasons`, objet fermé (`activity`, `depth`, `cost`), donne le motif
  d'une mesure absente : `TRADE_CHANNEL_NOT_CAPTURED`,
  `DEPTH_LEVELS_NOT_IN_ARTIFACT`, `COST_NOT_MEASURED`. Un motif pour une
  valeur présente est refusé (`UNKNOWN_REASON_FOR_PRESENT_VALUE`). UNKNOWN ≠ 0.
- `cost.basis = "MEASURED"` est refusé pour une observation de source.
- L'identité est jointe par `(venue, market_type, native_symbol)` au catalogue
  référencé ; une observation sans marché correspondant reste visible dans
  `orphan_observations`. Une base ou quote déclarée contraire au catalogue
  donne `IDENTITY_CONFLICT_*` (R0).

## 7. Intégrité L2 (D3, D4)

| Statut | Sens | Critère `l2_quality` | Points (`radar-ranking/1.2.0`) |
|---|---|---|---|
| `VERIFIED` | carnet complet vérifié (fixture SYNTHETIC seulement) | `AVAILABLE`, `PROVEN` | 100 |
| `VERIFIED_TOP_N` | `depth_levels` premiers niveaux attestés par checksum natif, sur les instants valides | `PARTIAL`, `PROVEN_TOP_N`, motif `L2_VERIFIED_TOP_N_ONLY` | **40** (transitoire) |
| `TECHNICALLY_COMPATIBLE` | carnet reconstruit sans checksum | `PARTIAL`, `TO_QUALIFY` | 40 |

- `VERIFIED` venant d'une source est refusé
  (`L2_VERIFIED_NOT_ALLOWED_FROM_SOURCE`).
- `VERIFIED_TOP_N` exige `depth_levels` (`L2_TOP_N_DEPTH_LEVELS_REQUIRED`) et
  `scope = {verified_by, valid_instants, grid_instants, excluded_instants}`
  (`L2_TOP_N_SCOPE_REQUIRED`) avec `valid + exclus = grille`
  (`L2_SCOPE_COUNTS`) ; une portée sur un autre statut est refusée
  (`L2_SCOPE_ONLY_FOR_TOP_N`). Kraken Spot : `verified_by = "KRAKEN_CRC32"`,
  `depth_levels = 10` (`KRAKEN_DEPTH_NOT_CHECKSUM_DEPTH`). MEXC :
  `TECHNICALLY_COMPATIBLE`, sans portée.
- Mission `L2_DEPTH_STUDY` : `VERIFIED_TOP_N` donne `A_QUALIFIER`
  (`L2_VERIFIED_TOP_N_ONLY`).
- La profondeur ±10 bps reste UNKNOWN : les fenêtres rejouées ne portent que
  le premier niveau.
- Affichage : « carnet vérifié sur N niveaux (KRAKEN_CRC32), X instants
  valides sur Y », jamais « carnet vérifié » seul.

## 8. Plafonds

Plafonds de test R0 (`TEST_BUDGETS`), plus :

| Plafond | Valeur | Code |
|---|---|---|
| Sources par lot | 16 | `SOURCES_BOUND` |
| Références par lot | 64 | `REFS_BOUND` |
| Octets par artefact BBO / ancre / manifeste | 1 000 000 | `REF_TOO_LARGE` |
| Octets par catalogue | `MAX_RAW_BYTES` du Scanner | `REF_TOO_LARGE` |
| Fenêtres par source | 8 (240 points ≤ 256 échantillons) | `ARTIFACTS_BOUND` |
| Instants exclus listés | 256 | `EXCLUDED_INSTANTS_BOUND` |

Les plafonds de production restent `NOT_MEASURED`.

## 9. Refus global et dégradation locale

Règle : un défaut qui empêche de savoir **ce que le lot affirme** refuse tout
le lot ; un défaut qui touche **une preuve** dégrade seulement ce qu'elle
porte, et reste visible avec son code. Rien n'est jamais remplacé, corrigé ou
compté comme zéro.

| Niveau | Déclencheur | Effet |
|---|---|---|
| **Refus global** (sortie `3`, aucune évaluation, rien n'est écrit) | forme du lot (clé, type, version, nature, `LIVE`, plafond de taille ou de nombre, grammaire d'une `ref`) ; racine de preuves invalide ; référence présente mais dangereuse ou hors plafond (`REF_SYMLINK`, `REF_OUTSIDE_ROOT`, `REF_NOT_REGULAR`, `REF_TOO_LARGE`, `REF_CHANGED_DURING_READ`) ; lecture hors racine ; spécification ou construction d'un lot (`batch_build`) en échec | le lot n'est pas lu à moitié |
| **Dégradation : catalogues** | manifeste Scanner absent, altéré ou mal formé | les cinq catalogues `REFUSED` (`CATALOGUE_MANIFEST_*`) ; marchés de ces sources `UNAVAILABLE` ; évaluation produite |
| **Dégradation : un catalogue** | document absent, empreinte ou taille fausse, entrée différente du manifeste, erreur Scanner | ce catalogue seul `REFUSED` ou `UNAVAILABLE` avec son code |
| **Dégradation : une source** | ancre, manifeste de journal, fenêtre absente ou altérée, nature, commit ou corpus incohérents | source `REFUSED` ; toutes ses observations écartées, leurs marchés UNKNOWN avec le code ; autres sources intactes |
| **Dégradation : une observation** | `PRICE_KIND_MIXED`, `WINDOW_BEYOND_COVERAGE`, `MID_REPRESENTATION_MISMATCH`, `KRAKEN_DEPTH_NOT_CHECKSUM_DEPTH`, `OBSERVATION_NOT_DERIVED_FROM_SOURCE` | cette observation seule écartée (`inputs.refused_observations`), son marché UNKNOWN avec le code |
| **Instant** | instant non évalué, non synchronisé, sans BBO | omis de la série, cité dans `l2.scope.excluded_instants` |

Une référence simplement absente (`REF_MISSING`) n'est pas un refus global :
elle dégrade la preuve qui la cite. Les compteurs de découverte ne changent
pas : un marché dégradé reste listé.

## 10. Construction d'un lot

`python -m observability.radar_selection.batch_build --evidence-root DIR
--spec REF --state-dir DIR --out NAME` lit une spécification
`radar-batch-spec/1.0.0` (identité, nature, temps d'évaluation, politique,
passage Scanner et empreinte de son manifeste, et pour chaque source BBO :
ancre, manifeste et fenêtres épinglés). Le constructeur référence et projette ;
il ne parse aucun catalogue, ne rejoue aucun journal, n'ouvre aucune
connexion. Le lot est contrôlé par le vérificateur du Radar avant d'être écrit
(`BUILD_SELF_CHECK`), atomiquement, sans jamais remplacer un fichier.

## 11. Hors contrat

Collecte, rejeu d'un corpus réel, déploiement, PAPER, PPL, FIN, Advisor,
observation approfondie, C2-C, C2-D, `LIVE`.
