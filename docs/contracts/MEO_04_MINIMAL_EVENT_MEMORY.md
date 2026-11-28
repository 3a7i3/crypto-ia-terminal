# MEO-04 — Mémoire événementielle minimale (V0.1)

**Décisions opérateur.** Ordre de mission MEO-04 du 2026-11-28 (04:26Z) et arbitrage
MEO04-D01 (04:29Z) : mémoire dans `observability/meo_memory/`, hors `market_flow`,
dépendance à sens unique mémoire → moteur scientifique, consommateur déclaré dans les
tests d'architecture.

**Cadre.**
- Contrat scientifique B02 v0.2 (`5b639caa…`) ; lecture MEO-03 `meo-03-reading/0.1`.
- `INSTRUMENT_ADMISSION` = PROBATION pour TRADE_FLOW. Aucune revendication ADMITTED_PARTIAL.
- Mémoire locale, hors ligne, un seul écrivain. Aucun service, aucune route HTTP, aucune UI.
- B04-A sert de référence d'invariants ; ses exigences de qualification B04-LAB ne sont pas
  transposées (voir le tableau d'adaptation).

## 1. Objets logiques

| Objet | Contenu | Identité logique |
| --- | --- | --- |
| Session (import) | Tous les champs de la lecture sauf `windows` et `divergent_windows` : `flow`, `corpus_ref`, `evidence_kind`, `source_evidence_kind`, `admission`, `quality`, `axis`, `time_basis`, `qualification`, `rule`, `limits`, `subscription_acknowledged_receipt_ns`, `first_desalignment_by_segment`, `first_desalignment` | type `SESSION` |
| Fenêtre d'observation | La fenêtre de la lecture, recopiée telle quelle avec toutes ses minutes, ses exclusions, ses `null` | type `WINDOW`, portée segment + bornes natives |
| Référence d'événement divergent | `window_id`, `start_ns`, `segment`, `eligible_for_first_desalignment`, `exclusion_reason`, `first_in_segment`. Aucune mesure dupliquée | type `DIVERGENT_EVENT`, portée segment + début |

- Toutes les fenêtres sont gardées : UNKNOWN, exclues, non couvertes.
- `eligible_for_first_desalignment` qualifie seulement la recherche. Le premier désalignement
  par segment est gardé tel que MEO-03 le publie.
- La lecture d'origine se recompose à l'octet près depuis ses objets. C'est vérifié à l'import,
  à la reconstruction et à chaque lecture.

**Identité.** `SHA-256` du préimage canonique suivant :
- `schema = meo-memory-identity/1` ;
- partition de provenance ;
- identité complète de l'instrument :
  - venue, instrument, base, quote, `market_kind`, `id_domain`, base du côté ;
  - `contract_identity` et `settlement_asset_id` du manifeste ;
- session de capture : SHA-256 du manifeste vérifié, sceaux `events_sha256` et `frames_sha256`, pilote ;
- version de contrat (`meo-03-reading/0.1`) et règle (`DESALIGN-1` v1) ;
- type et portée (segment natif, bornes de fenêtre).

Elle ne contient ni chemin local, ni instant d'import, ni hash de la lecture entière. Le
hash de contenu (`content_sha256`, canonique de l'objet) est un champ distinct.

**Conflits.**
- Même identité, contenu différent : refus `CONFLICT` ; rien n'est écrit.
- Captures distinctes qui se chevauchent : sessions distinctes, jamais dédupliquées ni additionnées.

**Statuts préservés.**
- HISTORICAL avec provenance OBSERVATION ; SYNTHETIC reste SYNTHETIC.
- PROBATION, DEGRADED, UNATTESTED, NATIVE, qualification CONDITIONAL.
- Aucune promotion. Aucun STATE_5M.

**Trois ordres distincts.**
- Axe natif : `start_ns`, `end_ns`, entiers 64 bits dans l'index, jamais triés comme du texte.
- Réception : `receipt_bounds_ns`, horloge murale de l'hôte de capture, base `CAPTURE_HOST_RECEIPT_WALL_UNATTESTED`.
- Connaissance locale : `knowledge_seq`, ordre d'import.

## 2. Stockage durable

Racine privée explicite :
- créée par `init` ;
- absolue et canonique ;
- mode 0700, propriétaire courant ;
- hors du dépôt ;
- aucun chemin par défaut ;
- rien n'est écrit à l'import Python.

| Élément | Rôle |
| --- | --- |
| `meo-memory-root.json` | Partition unique de la racine (HISTORICAL ou SYNTHETIC) et budget d'octets |
| `proofs/<hh>/<sha256>` | Preuves immuables adressées par contenu, mode 0400, une seule copie par hash |
| `journal/<seq>.json` | Enregistrements d'import immuables et chaînés (`predecessor_sha256`), autorité |
| `index/memory.sqlite` | Index dérivé, reconstructible. Les anciens index sont renommés `retired-…`, jamais supprimés |
| `tmp/` | Temporaires sur le même système de fichiers ; un reste est un orphelin, jamais une observation |
| `writer.lock` | Verrou `flock` exclusif d'écrivain |

**Preuves conservées.**
- Membres scellés : `manifest.json`, `events.jsonl`, `frames.bin`, rapports, `preflight.json`, `SHA256SUMS`.
- L'archive elle-même, si elle est fournie.
- Le rapport de rejeu (`replay-report`).
- La lecture d'origine (`reading`).

**Vérification à l'import.**
- Lecture bornée sans lien symbolique, chemin par chemin (`bounded_file`).
- Archive plate de membres réguliers connus, sceau `SHA256SUMS`.
- Sceau du journal (`verify_journal`).
- Nouveau rejeu (`replay_journal`) et nouvelle lecture (`read_report`).
- Les octets d'un rapport ou d'une lecture fournis doivent être identiques au rejeu ; sinon `PROOF_CORRUPT`.
- JSON strict : UTF-8, sans BOM, clés dupliquées, flottants, NaN ou Infinity.

**Ordre de publication.**
1. Preuves : temporaire → fsync → lien sans remplacement → fsync du répertoire.
2. Enregistrement : même procédure.
3. Index : une transaction SQLite (`synchronous=FULL`).
4. Acquittement.

Un échec de fsync de répertoire donne `PUBLICATION_UNCERTAIN` : aucun acquittement. Une
preuve existante n'est jamais réécrite ; ses octets sont revérifiés.

**Frontière de visibilité.**
- Un import est visible quand son enregistrement est dans le journal vérifié ET que la tête
  de l'index égale la tête du journal.
- Sinon, les lectures sont refusées `INDEX_INCONSISTENT` : jamais de vue partielle.
- `recover` (écrivain) :
  - refait le fsync du journal ;
  - vérifie les enregistrements en attente et leurs preuves ;
  - applique ces enregistrements, ou reconstruit l'index.
- La reconstruction conserve `knowledge_seq`.

**Idempotence.**
- Ré-import identique : `NO_OP`, mêmes identifiants, aucun octet écrit.
- Une seconde archive aux membres identiques mais aux octets différents donne aussi `NO_OP`.
  Ce second conteneur n'est pas conservé ; il est seulement non enregistré.

**Limites par défaut** (`store.Limits`) :
- manifeste : 64 Kio ;
- journal et trames : 64 Mio chacun ;
- petits membres et lecture : 8 Mio ;
- archive : 128 Mio, 16 membres au plus ;
- un import : 192 Mio ;
- enregistrement : 4 Mio ;
- journal : 10 000 enregistrements ;
- racine : 200 000 entrées ;
- budget de racine : 1 Gio par défaut, 2 Gio au plus, réserve 16 Mio. Il inclut index, journaux SQLite et temporaires ;
- page : 20 par défaut, 100 au plus ;
- 256 sessions revérifiées par lecture.

Chaque dépassement donne un refus typé, jamais une troncature.

## 3. Lectures locales

Module `observability.meo_memory.reads.Reader` ; CLI `python3 -m observability.meo_memory`.

Chaque lecture :
- épingle sa borne de connaissance K (tête du journal) ;
- prend l'ordre dans l'index ;
- prend chaque valeur dans la preuve de lecture, revérifiée : hash, recomposition, accord de l'index.

| Lecture | Contenu |
| --- | --- |
| `now` (Maintenant) | Dernier import selon `knowledge_seq`, puis plus grand `start_ns` natif dans cette capture. Fournit la fenêtre, la provenance, le marquage et les limites. `freshness.state = NOT_FRESH_HISTORICAL` (ou `NOT_FRESH_SYNTHETIC`), `age = UNKNOWN` |
| `events` (Événements) | Divergences éligibles, ordre `knowledge_seq, start_ns, event_id`, pagination bornée par curseur lié à K. Avec `--include-excluded`, les fenêtres exclues sont données à titre documentaire, avec leur motif. `--first-only` donne le premier par segment |
| `summary` (Bilan) | Par session : comptes par alignement, statut et motif d'exclusion ; événements (total, éligibles, exclus) ; premier désalignement ; références. Les chevauchements natifs sont listés (conditionnels), `totals_across_sessions = null` |

**Résultats et erreurs.**
- `EMPTY` est un résultat.
- Les erreurs sont distinctes : `NOT_CONFIGURED`, `PROOF_UNAVAILABLE`, `PROOF_CORRUPT`, `CONFLICT`, `INDEX_INCONSISTENT`.
- Autres refus typés : `INPUT_REFUSED`, `BUDGET_EXCEEDED`, `WRITER_BUSY`, `PUBLICATION_UNCERTAIN`, `INVALID_REQUEST`.
- Codes de sortie de la CLI : 0, 4 refus, 5 publication incertaine.

## 4. Adaptation B04-A → MEO-04

B04-A a été écrit pour BOOK_AT_RECEIPT B03 CERTIFIED. MEO-04 porte une lecture TRADE_FLOW
en PROBATION. Rien n'est transposé automatiquement.

| Exigence B04-A | MEO-04 | Statut |
| --- | --- | --- |
| Preuves adressées par contenu, une copie par hash, pas d'écrasement | `proofs/<hh>/<sha256>`, lien sans remplacement, revérification si présente | Conservé |
| Partitions HISTORICAL / SYNTHETIC distinctes en racine, chaîne et identité | Une partition par racine, partition dans l'identité, refus du mélange | Conservé |
| `logical_id` distinct de `revision_id` ; préimage sans chemin | Identité logique distincte du hash de contenu, sans chemin ni instant | Conservé (pas de `revision_id`, voir révisions) |
| Journal append-only chaîné, numéro monotone K | `journal/<seq>.json` chaîné, `knowledge_seq` | Conservé |
| Index SQLite dérivé, reconstructible ; il ne crée ni ne retire une publication | Idem ; tête vérifiée contre le journal ; reconstruction testée | Conservé |
| Temporaire → fsync → publication sans remplacement → fsync répertoire ; `COMMIT_UNCERTAIN` | Idem, nommé `PUBLICATION_UNCERTAIN`, sans acquittement | Conservé |
| Reprise : chaîne vérifiée, orphelins ignorés, pas de réparation par écrasement | `recover`, orphelins listés par `verify`, index retirés conservés | Conservé |
| Ré-import identique `NO_OP` | Idem | Conservé |
| `PROOF_UNAVAILABLE` distinct de `PROOF_CORRUPT` | Idem | Conservé |
| Aucun STATE_5M ni UTC fictif | Fenêtres natives seulement, UNATTESTED | Conservé |
| Segments JSONL de 256 lignes / 4 Mio, descripteurs | Un enregistrement JSON par import ; les fenêtres restent dans la preuve de lecture | Simplifié |
| Lecture à deux bornes (R, K) | K seulement (tête du journal), épinglée par lecture et par curseur ; R est la fenêtre native | Simplifié |
| Manifeste `meo-commit/1` séparé des segments | L'enregistrement d'import est le commit | Simplifié |
| Lecture de plage vérifiée (`BYTE_RANGE`) | Preuves entières seulement (fichiers < 1 Mio) | Simplifié |
| Révisions, `supersedes`, `REVISION_CONFLICT` à deux enfants | Contradiction refusée `CONFLICT` ; pas de correction ni de branche | Reporté |
| Concurrence multi-auteurs (M06) | Un seul écrivain, verrou exclusif `WRITER_BUSY` | Reporté |
| Ancre externe de la tête du journal | Tête publiée dans chaque réponse et acquittement ; pas d'ancre externe | Reporté (MEO-05) |
| Broker d'E/S, cgroup v2, quota de volume, isolement réseau (§8, M10) | Budget logique de racine et limites d'octets en code ; aucun confinement OS revendiqué | Reporté (pas une exigence en PROBATION) |
| Plafonds CPU/mémoire de campagne | Mesurés et rapportés, non imposés | Reporté |
| Registre d'artefacts et localisateurs du dépositaire | Les preuves sont copiées dans la racine | Reporté |
| Certificat, binding scellé, OBSERVATION_QUALITY par reçu | Marquage MEO-03 conservé tel quel | Propre à BOOK_AT_RECEIPT |
| 13 mesures du carnet, conciliation 29 557 lignes (M01), reçus et sous-index | Sans objet pour TRADE_FLOW | Propre à BOOK_AT_RECEIPT |
| Chaîne PENDING → CERTIFIED, RV01 | Sans objet (PROBATION) | Propre à BOOK_AT_RECEIPT |

Ni B04-A ni B02 ne sont déclarés complets ou certifiés par MEO-04.

## 4 bis. Contre-revue RV01-R1 (correctifs)

**RV01-01 — Index dérivé.** Chaque lecture, `verify` et `recover` comparent l'index entier à
l'autorité, dans un seul instantané SQLite ouvert pour toute la lecture :
- le schéma (`sqlite_master`) ;
- les métadonnées ;
- toutes les lignes et toutes les colonnes de `sessions`, `windows` et `events`, y compris
  `eligible`, `first_in_segment`, `start_ns`, `segment`, `alignment`, `exclusion_reason` et les liens
  `window_id`, `session_id`, `knowledge_seq`.

Les lignes attendues viennent d'une seule définition (`_rows`), utilisée pour écrire et pour
vérifier. Une ligne manquante, parasite ou modifiée donne `INDEX_INCONSISTENT`, jamais `EMPTY`.
`recover` reconstruit alors l'index, uniquement depuis le journal et les preuves.

**RV01-02 — Preuves.**
- Obligatoires dans tout enregistrement : `manifest.json`, `events.jsonl`, `frames.bin`,
  `replay-report`, `reading`.
- Toute autre preuve enregistrée (archive, `SHA256SUMS`, `preflight.json`, rapports source)
  devient obligatoire une fois enregistrée.
- Politique bornée : chaque lecture, `verify`, `recover`, `rebuild` et chaque import (donc
  aussi un `NO_OP`) vérifient intégralement, pour toutes les sessions de K, la présence, la
  taille et le SHA-256 de chaque preuve. Limites : 256 sessions et 512 Mio de preuves par passe ;
  au-delà, refus `BUDGET_EXCEEDED`.
- Liens vérifiés :
  - le manifeste et les sceaux de l'identité égalent les preuves `manifest.json`, `events.jsonl` et `frames.bin` ;
  - `corpus_ref` de la lecture égale ces sceaux et le rapport de rejeu ;
  - `reading_sha256` égale la preuve `reading` ;
  - les rapports source égalent le rapport de rejeu.
- Une preuve absente donne `PROOF_UNAVAILABLE`, une preuve altérée `PROOF_CORRUPT`. Aucun
  `NO_OP` ni aucune récupération n'est acquitté dans ces cas. Rien n'est réparé
  automatiquement : la remise en place des octets exacts par l'opérateur rend l'état valide.

**RV01-03 — Budget.**
- La reconstruction est refusée avant écriture si l'estimation (index actuel, ou schéma vide
  plus une marge par ligne) dépasse l'espace restant. L'espace restant tient compte des index
  actifs et retirés, des temporaires, des journaux SQLite et de la réserve.
- Pendant l'écriture, le fichier temporaire est plafonné (`max_page_count`, journal en mémoire
  pour ce fichier non publié).
- Un refus supprime seulement le temporaire créé par l'appel et laisse intact l'état antérieur.
- L'application d'imports en attente est aussi contrôlée avant écriture.
- `proofs/` est synchronisé (fsync) à chaque publication de preuve, même si le sous-répertoire
  existait déjà. `recover` synchronise `proofs/` et tous les `proofs/<hh>/` du journal avant
  d'appliquer quoi que ce soit.

## 5. Limites

- Mémoire descriptive : aucun détecteur, épisode, signal, prédiction ni ordre.
- Une lecture revérifie toutes les sessions de K et toutes leurs preuves, dans la limite de 256 sessions et 512 Mio. Au-delà, elle est refusée. MEO-05 devra fournir un cache vérifié.
- Le dernier enregistrement du journal n'a pas d'ancre externe : sa falsification est détectée par l'index, mais pas après une reconstruction.
- La lecture n'est pas incrémentale : chaque requête relit le journal.
- Aucune heure UTC n'est affirmée ; aucune comparaison entre captures n'est faite.

## 6. Tests

`tests/meo_04/` T01–T12 couvre :
- l'import ;
- le `NO_OP` ;
- les conflits ;
- les coupures à chaque frontière, y compris la mort réelle du processus ;
- la reconstruction ;
- les valeurs exactes ;
- les exclusions, les preuves, les limites et les partitions ;
- les lectures bornées ;
- l'architecture.

Les tests sur le corpus réel L3 ne s'exécutent que si `MEO04_L3_ARCHIVE` et
`MEO04_L3_READING` désignent les fichiers de référence (`4b06e032…`, `eade163d…`). Le corpus
reste hors de Git (D6). Toutes les autres entrées de test sont SYNTHETIC.
