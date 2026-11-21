# MARKET-DERIVATIVES-POSITIONING-01 — Plateformes & levier, lot 1 : stockage VPS des observations

Statut : **SOURCE_ONLY / NON_DEPLOYED**. Ce lot livre un module, ses migrations, sa CLI de
vérification, une configuration d'exemple et des tests synthétiques. Il ne crée ni service,
ni route API, ni collecteur, ni purge, et n'appelle aucune plateforme. #286 ACTIVE : aucune
modification runtime, epoch, stratégie ou configuration active.

Empilé sur [MARKET-DERIVATIVES-STRESS-01](MARKET_DERIVATIVES_STRESS_01.md) (PR #590, `6f9c12a6`) :
ce produit fournit la **persistance historique** qui manquait au builder pur (`samples` fournis par
l'appelant). Il réutilise `market_stress.metrics` (décimal exact, prime, base, funding, OI notionnel),
les vocabulaires `VENUE_ID`, `NATIVE_SYMBOL`, `OI_UNITS`, `DERIVATIVE_KINDS` et les fenêtres
pré-enregistrées 1 h / 4 h / 24 h.

## Frontière GitHub / VPS

| GitHub | VPS uniquement |
|---|---|
| `observability/derivatives_positioning/` (code, migrations), `tests/derivatives_positioning/` (fixtures inventées), `config/derivatives_positioning.example.json`, `scripts/derivatives_positioning_capacity.py`, cette documentation et la procédure VPS | `/var/lib/cat-derivatives-positioning/positioning.sqlite3` et ses fichiers `-wal`, `-shm`, `-journal` ; tout historique, toute copie ou export |

`.gitignore` exclut `*.sqlite3`, `*.sqlite3-wal`, `*.sqlite3-shm`, `*.sqlite3-journal` (vérifié par
`test_data_files_are_excluded_from_git`). Aucun workflow CI, artefact, télémétrie ou sauvegarde distante
ne lit ce répertoire. Les tests écrivent uniquement dans `tmp_path`. Le script de capacité refuse un
répertoire situé dans le dépôt.

Hors périmètre : carnet, cadence et transmission (Flux & rythmes) ; Footprint et profils par prix
(Microstructure). Aucun score, signal, seuil de trading ni interprétation de signe.

## Contrat d'entrée 1.0.0

Point d'entrée d'un futur collecteur : `PositioningStore(data_dir).ingest(mapping)` ou
`ingest_batch([...])`, ou la CLI `ingest`. Le collecteur fournit un objet JSON ; il ne connaît pas
le format de stockage.

```json
{
  "contract_version": "1.0.0",
  "venue": "exchange_a", "native_symbol": "BTC_USDT", "contract_type": "PERPETUAL_LINEAR",
  "quote_currency": "USDT", "base_currency": "BTC",
  "source_time_utc": "2026-11-21T12:00:00Z", "received_at_utc": "2026-11-21T12:00:01Z",
  "capture_id": null,
  "provenance": {"source": "…", "payload_sha256": "…", "mapping_id": "…", "mapping_sha256": "…",
                 "collector_run_id": "…"},
  "measures": {
    "mark_price": {"value": "65000.5"},
    "index_price": {"value": "64990.0"},
    "spot_reference": {"value": "64980.25", "qualification": "QUALIFIED", "venue": "…",
                       "native_symbol": "…", "qualification_ref": "…"},
    "open_interest": {"value": "1250000", "unit": "CONTRACTS", "contract_size_base": "0.0001"},
    "funding_rate": {"value": "0.0001", "interval_s": 28800, "interval_attested_by": "…",
                     "next_funding_utc": "…"}
  }
}
```

- **Résultat partiel** : chacune des cinq mesures est obligatoire, soit `{"value": …}`, soit
  `{"unavailable": "MOTIF_EN_MAJUSCULES"}`. Une mesure absente est refusée (`MEASURE_MISSING`) :
  l'absence n'est jamais silencieuse ni un zéro.
- **Décimal exact** : chaînes ou entiers ; un `float` est refusé (`FLOAT_NOT_EXACT`). Forme canonique
  normalisée (`65000.50` ≡ `65000.5`), stockée en texte, jamais en flottant.
- **Unités** : prix dans `quote_currency` ; OI dans son unité native `BASE | QUOTE | CONTRACTS`
  (taille de contrat obligatoire et seulement pour `CONTRACTS`) ; funding en fraction par intervalle,
  intervalle de 60 s à 24 h **attesté** par une source déclarée (`interval_attested_by`).
- **Référence spot** : admise seulement `qualification = QUALIFIED` avec sa référence de qualification.
- **Temps** : ISO-8601 avec fuseau explicite ou millisecondes epoch. L'heure source est facultative ;
  l'heure de réception est obligatoire.
- Tout champ inconnu est refusé. Les refus sont typés (`ContractError.code`).

## Identité, doublons, conflits, retard

- `observation_key` = SHA-256 canonique de `(venue, native_symbol, contract_type, quote_currency,
  source_time_ms)`.
- **Sans heure source** : `(venue, native_symbol, contract_type, quote_currency, payload_sha256,
  capture_id)` ; `payload_sha256` devient obligatoire (`IDENTITY_UNRESOLVED` sinon). Limite assumée :
  deux réponses identiques sans heure source ni `capture_id` distinct sont la même observation (la
  première réception est conservée). Un collecteur qui veut deux points distincts fournit un
  `capture_id` déterministe (créneau de collecte).
- `content_sha256` couvre tout le document normalisé **sauf** `received_at_utc` et
  `collector_run_id`. Un rejeu reçu plus tard ou par un autre run reste donc un **doublon** (testé).
- Même clé, même contenu → `DUPLICATE`, rien n'est écrit. Même clé, contenu différent →
  `CONFLICT` : l'original est conservé ; le contenu divergent est journalisé **une fois par contenu
  distinct** (`conflicts`, clé primaire `(observation_key, content_sha256)`) ; une nouvelle tentative
  du même conflit incrémente `attempts` et `last_seen_ms` sans ajouter de ligne.
- **Tardive** : acceptée. À l'écriture, le fait `out_of_order` (une observation plus récente du même
  instrument existait déjà) est enregistré. À la lecture, `lateness = LATE` si
  `réception − source > late_after_ms` ; `UNDETERMINED` sans heure source.

## Écriture durable

SQLite (stdlib), `journal_mode=WAL`, `synchronous=FULL`, `busy_timeout=5000`. Une transaction
`BEGIN IMMEDIATE` par appel ; `ingest_batch` est tout-ou-rien (testé : volume plein au milieu d'un lot →
aucune ligne du lot). Une interruption du processus en pleine transaction ne laisse rien
(`test_interrupted_write_leaves_nothing_behind`, `os._exit` puis `integrity_check = ok`).

Le module **ne crée pas** son répertoire : il doit exister (sur le VPS, créé par systemd
`StateDirectory`). Il crée la base au premier démarrage. Erreurs observables (`StorageError.code` ou
résultat `NOT_WRITTEN` avec `code`) :

| Situation | Code | Lecture de l'historique |
|---|---|---|
| répertoire absent | `STORAGE_DIRECTORY_MISSING` | impossible, erreur explicite |
| chemin non répertoire / lien | `STORAGE_NOT_A_DIRECTORY`, `STORAGE_INVALID_PATH` | impossible |
| lecture seule sans base | `STORAGE_EMPTY_NOT_INITIALISED` | impossible |
| volume plein | `STORAGE_FULL` | possible, données intactes |
| base ou volume en lecture seule | `STORAGE_READ_ONLY` | possible |
| verrou | `STORAGE_BUSY` | possible |
| base corrompue | `STORAGE_CORRUPT` | refusée |
| migration modifiée / base plus récente | `STORAGE_MIGRATION_TAMPERED`, `STORAGE_SCHEMA_NEWER` | refusée (échec fermé) |

## Migrations

`migrations.py` : liste numérotée, append-only. Chaque migration s'applique dans sa propre
transaction et enregistre son SHA-256 dans `schema_migrations`. À chaque ouverture, une migration
appliquée dont le SQL a changé est refusée ; une base de version supérieure au code est refusée. Une
ouverture en lecture seule n'applique jamais de migration. `store_identity.store_id` (UUID créé à
la migration 1) prouve qu'un redémarrage relit la même base.

## Lecture

- `latest(venue, symbol, type, as_of)` : dernière observation à `as_of` au plus tard, avec heure
  source, réception, base temporelle (`SOURCE | RECEIPT`), latence, retard, fraîcheur
  (`FRESH | STALE | FUTURE_OR_INCONSISTENT_CLOCK`), unités, provenance, champs indisponibles et
  dérivés descriptifs : **prime vs indice** (`(marque − indice)/indice`), **base vs spot qualifié**
  (`(marque − spot)/spot`), funding avec équivalent 8 h linéaire, OI notionnel exact si l'unité le
  permet.
- `history(…, start, end, limit, cadence_s)` : borné par `history_max_rows` (indicateur `truncated`),
  couverture (observations, attendues si la cadence est déclarée, ratio, champs indisponibles par
  champ, retards).
- `oi_change(…, as_of, cadence_s)` : fenêtres 1 h / 4 h / 24 h. Les deux extrémités suivent **la même
  règle** : l'observation la plus proche de l'instant visé dans `max(min_tolerance_ms, cadence)`, avec
  OI disponible. Elles doivent partager unité, taille de contrat, type de contrat et base temporelle.
  La couverture (points compatibles dans la fenêtre / points attendus) doit atteindre `min_coverage`.
  Sinon `NOT_AVAILABLE` avec motif : `CADENCE_UNKNOWN`, `NO_COMPARABLE_POINT_AT_START|END`,
  `OPEN_INTEREST_UNITS_DIFFER`, `CONTRACT_SIZES_DIFFER`, `TIME_BASES_DIFFER`,
  `INSUFFICIENT_COVERAGE`, `REFERENCE_OPEN_INTEREST_ZERO`.
- `compare(legs, as_of)` : valeurs natives conservées ; indique `OPEN_INTEREST_UNITS_DIFFER`,
  `CONTRACT_SIZES_DIFFER`, `QUOTE_CURRENCIES_DIFFER`, `FUNDING_INTERVALS_DIFFER` au lieu de convertir.

## Politique (configurable, valeurs initiales de test)

`config/derivatives_positioning.example.json` → `PositioningPolicy` :

| Champ | Valeur initiale | Rôle |
|---|---|---|
| `late_after_ms` | 120000 | seuil de retard à la lecture |
| `min_coverage` | 0.8 | couverture minimale d'une fenêtre OI |
| `min_tolerance_ms` | 60000 | tolérance = max(cette valeur, cadence) |
| `max_age_ms` | 600000 | fraîcheur de la dernière observation |
| `history_max_rows` | 10000 | borne d'une lecture d'historique |
| `disk_budget_bytes` | 5000000000 | **hypothèse**, rapportée seulement |
| `retention_days` | 365 | **hypothèse**, rapportée seulement |
| `purge_enabled` | false | toute autre valeur est refusée dans ce lot |

Changer une valeur change la lecture, jamais les données stockées.

## Budget et capacité

**Budget prévisionnel : 5 Go. Aucune purge active** (`purge_enabled=false`, toute autre valeur refusée).
Le budget est seulement rapporté par `status` (`budget.used_ratio`), jamais appliqué.

Mesure synthétique (`scripts/derivatives_positioning_capacity.py`, 60 instruments, cadence 300 s,
7 jours, lots de 60, Python 3.11.18), base et WAL mesurés **séparément** :

| Fichier | Avant checkpoint | Après checkpoint |
|---|---|---|
| base `positioning.sqlite3` | 183 132 160 o | 183 218 176 o |
| WAL `positioning.sqlite3-wal` | 5 014 072 o (maximum observé pendant l'écriture) | 0 o |
| `positioning.sqlite3-shm` | 32 768 o | 32 768 o |

Soit ≈ 1 515 o par observation dans la base, ≈ 26,2 Mo/jour, ≈ 9,55 Go/365 jours ; le WAL reste borné
par l'auto-checkpoint SQLite (≈ 5 Mo) et est replié à la fermeture. À cette cadence, le budget de 5 Go
correspond à ≈ 190 jours ; cadence, nombre d'instruments ou rétention restent à arbitrer. Mesure locale
synthétique, non transposable telle quelle au VPS.

**Activation avec données réelles suspendue** tant qu'un compte GCP autorisé n'a pas vérifié que le
volume retenu est exclu des snapshots et sauvegardes hors VPS.

## Limites

- Aucune donnée réelle, aucune plateforme contactée ; fixtures `exchange_a`/`exchange_b` inventées.
- La politique de snapshots du disque VPS est **inconnue** (lecture GCP refusée). Prérequis bloquant
  avant toute écriture d'observation réelle : voir la procédure VPS.
- Un seul processus écrivain prévu. Pas de route API : l'exposition au frontend viendra après
  qualification des sources et des historiques.

## Lot 2 — API de lecture bornée et vue Comparaison

Route `GET /api/operator/v1/derivatives-positioning` (Operator API, GET seul, `Cache-Control: no-store`).
Le lecteur ouvre la base en lecture seule (`mode=ro`) et ne calcule rien que le stockage n'expose
déjà (dernier relevé, variation d'OI, comparaisons) ; le graphique ne fait que **filtrer** des points
stockés. Aucun score, signal ni autorité d'exécution (`execution_authority: false`).

Configuration (aucune valeur par défaut ; absente → 503 `DERIVATIVES_POSITIONING_NOT_CONFIGURED`) :

| Variable | Rôle |
|---|---|
| `OPERATOR_DERIVATIVES_POSITIONING_DIR` | répertoire de la base (lecture seule) |
| `OPERATOR_DERIVATIVES_POSITIONING_ROSTER` | JSON déclarant les jambes affichées et leur cadence (`venue`, `native_symbol`, `contract_type`, `cadence_s`), `evidence_kind`, `chart_window_s` ∈ {3600, 14400, 86400}, 20 jambes au plus |
| `OPERATOR_DERIVATIVES_POSITIONING_POLICY` | politique (facultatif, mêmes clés que le lot 1) |

Erreurs typées : `DERIVATIVES_POSITIONING_INVALID_CONFIGURATION`, `…_INVALID_READER_CLOCK`, puis les
codes du stockage préfixés (`…_STORAGE_DIRECTORY_MISSING`, etc.).

Graphique Prix + OI : une série n'est tracée que si, sur toute la fenêtre, chaque point a un prix de
marque et un OI dans l'unité, la taille de contrat et la base temporelle du dernier relevé, tombe sur
la grille de sa cadence déclarée (tolérance de la politique, un point par créneau), atteint la
couverture minimale, et partage cadence et base temporelle avec la première série admise. Sinon la
série est listée avec son motif (`INSUFFICIENT_COVERAGE`, `CONTRACT_SIZES_DIFFER`,
`OPEN_INTEREST_UNITS_DIFFER`, `TIME_BASES_DIFFER`, `POINTS_OFF_CADENCE_GRID`,
`NOT_ALIGNED_WITH_REFERENCE_LEG`, `NO_OBSERVATION`, …) et aucun point. Prix et OI restent en unités
natives sur des axes séparés.

Note d'exploitation : une ouverture `mode=ro` d'une base WAL a besoin du fichier `-shm` ; le
processus lecteur doit pouvoir le créer dans le répertoire ou un écrivain doit être actif. Les octets
de la base ne changent pas (vérifié par empreinte dans les tests).

Preuves : `tests/derivatives_positioning/test_read_api.py` (fixtures synthétiques : couverture
partielle, contrats non comparables, jambe sans observation),
`frontend/src/test/derivativesPositioning.compat.test.tsx`,
`frontend/scripts/capture_derivatives_positioning_visual.mjs` (1440 et 384 px, clair et sombre).
