# AGENT OBSERVATION — Contrat commun de mission V1

Statut : **BANC ISOLÉ / CONTRACT V1 / NON DÉPLOYÉ / AUCUN RUNNER**.
Identifiants : entrée `cat.observation.mission.v1`, sortie `cat.observation.report.v1`,
identité `cat.observation.mission-identity.v1`.
Implémentation de référence : [`agent_bench/observation/contract.py`](../../agent_bench/observation/contract.py)
(validateur fermé) et [`provenance_auditor.py`](../../agent_bench/observation/provenance_auditor.py) (pilote).
Base source analysée : `857404f8ebfbcf9df4a3f36052ab5357ea9b8d7b` (PR #597).

Ce contrat est **subordonné** à [A0](AGENT_ECON_A0_FOREST_MAINTENANCE_CONTRACT.md) et
[A1](AGENT_ECON_A1_AGENT_REGISTRY_CONTRACT.md) ; il n'en modifie aucune règle. Il ne
crée ni `AgentSpec`, ni événement de registre, ni worker, ni scheduler, ni provider,
ni credential. Une mission Observation est un acte **F0 (SENSOR)** au sens A0 §4 :
lecture, recherche et analyse statique, rapport transitoire rendu à l'invocateur.

```text
TEST PASSÉ        != RUNNER QUALIFIÉ
RAPPORT PRODUIT   != RAPPORT VALIDE
VOYANT SYSTÈME    reste gris tant qu'aucun runner serveur relié et prouvé (#597)
```

## 1. Familles et profils

| Profil | Exécutable au banc | Fiche |
|---|---|---|
| `data-provenance-auditor` | **oui (pilote, `DATASET_PROVENANCE_CHAIN`, v1)** | ce contrat + [fiches](../agents/observation/MISSION_SHEETS.md) |
| `observability-cartographer` | **oui (banc v2, `METRIC_SURFACE_MAP`)** | [agents v2](../agents/observation/AGENTS_V2_ET_STOCKAGE.md) |
| `repository-cartographer` | **oui (lot 2, question `REPOSITORY_MAP`, v1)** | [fiche](../agents/observation/MISSION_SHEETS.md) · [runner](../agents/observation/REPOSITORY_CARTOGRAPHER_RUNNER.md) · [résultat](../agents/observation/CARTOGRAPHER_RESULT.md) |
| `repo-architect` | **oui (banc v2, `CHANGE_IMPACT`)** | [agents v2](../agents/observation/AGENTS_V2_ET_STOCKAGE.md) |

Tout autre `agent_id` ⇒ `BLOCKED AGENT_UNKNOWN`. Le type de question doit correspondre
au profil : `DATASET_PROVENANCE_CHAIN` pour `data-provenance-auditor`, `REPOSITORY_MAP`
pour `repository-cartographer`, `METRIC_SURFACE_MAP` pour `observability-cartographer`,
`CHANGE_IMPACT` pour `repo-architect` (sinon `MISSION_SCHEMA_VIOLATION`). Les deux types v2
exigent `contract = cat.observation.mission.v2` ; les types v1 restent sous `…mission.v1`
(identités et `mission_id` inchangés). Banc v2 ≠ runner installé : aucun des deux nouveaux
profils n'a de runner sur le VPS.

## 6 bis. Cartographie de zone (`REPOSITORY_MAP`, lot 2)

| Champ | Contenu |
|---|---|
| `question` | `kind=REPOSITORY_MAP`, `zone_id` (slug), `text` |
| `capture` | `null` (aucune capture ; toute autre valeur est refusée) |
| `budget.max_files` | au plus **30** (`REPOSITORY_MAP_MAX_FILES`) ; au-delà ⇒ `FILE_BUDGET_EXCEEDED` |
| `scope.read_paths` | même grammaire ; seuls les fichiers `.py` sont analysés, les autres sont listés dans `skipped_non_python` |

Règles de classement (module `agent_bench/observation/repository_cartographer.py`) :

- un **import** n'est jamais un appel. `IMPORT_ONLY` : aucun appel de la même module ne
  s'en réclame (peut servir à un attribut ou une constante) ; `IMPORT_USED` ; `IMPORT_TEST_SCOPE` :
  un module de test importé par du code de production ;
- un **appel** dans un fichier de test est `TEST_CALL` ; un appel à un nom importé depuis un
  module de test est `TEST_SCOPE_CALL` ; ni l'un ni l'autre n'est une preuve d'activité de production ;
- un appel de secours (`except`) est `CONDITIONAL_PRODUCTION_CALL` (`EXCEPT_HANDLER`) ; un appel
  sous `if`, ternaire ou court-circuit est aussi conditionnel (`BRANCH`) ;
- une cible d'appel non nommable (`handlers[k]()`) est `DYNAMIC_CALL_TARGET`, niveau `INCONCLUSIVE`, jamais un appel ;
- deux écritures candidates vers le même fichier ⇒ `MULTIPLE_PRODUCER_CANDIDATES`, avec chaque référence ;
- un flag lu sur un seul couple (fichier, fonction) ⇒ `FLAG_SINGLE_PATH` attribué à ce couple,
  niveau `SUPPORTED` (attribution limitée à la zone) ; sinon `FLAG_MULTI_PATH` ;
- chaque constat cite fichier, ligne, symbole et `sha256` de la source.

## 2. Entrée obligatoire (`cat.observation.mission.v1`)

Toutes les clés sont obligatoires ; une clé inconnue ou absente ⇒ `MISSION_SCHEMA_VIOLATION`.

| Champ | Contenu | Contrôle |
|---|---|---|
| `contract` | `cat.observation.mission.v1` | constante |
| `agent_id` | identifiant du registre #597 | §1 |
| `profile.source_path`, `profile.blob_sha1` | version **exacte** du profil = blob git SHA-1 du `.agent.md` (même valeur que `agentIdentityRegistry.v1.json`) | recalcul ⇒ `PROFILE_VERSION_MISMATCH` |
| `mission_id` | `sha256(canonical_json(identité))` (§4) | recalcul ⇒ `MISSION_ID_MISMATCH` |
| `analyzed_ref` | `{"kind":"GIT_COMMIT","sha":<40 hex>}` ou `{"kind":"FIXTURE_TREE","sha":<64 hex>}` | vérifié par le **harnais** (git diff vide sur le périmètre, ou empreinte d'arbre de fixture) |
| `scope.read_paths` | chemins relatifs exacts ou préfixes de dossier finissant par `/` ; triés, uniques | grammaire A1 §4 : pas de glob, d'absolu, `..`, `//`, `\`, `.env*`, clés, `secret(s)/` ⇒ `SCOPE_PATH_INVALID` / `SECRET_PATH_REQUESTED` / `SCOPE_ARRAY_NOT_CANONICAL` |
| `question` | `kind=DATASET_PROVENANCE_CHAIN`, `dataset_id`, `text`, `as_of_utc` (instant d'évaluation explicite), `max_source_age_ms` (entier ou `null`), pointeurs `source_ts`/`write_ts`, `units`, `join_checks`, `observation_key` | fermé |
| `budget` | `max_files`, `max_bytes`, `max_wall_ms` | dépassement ⇒ `BUDGET_EXCEEDED` (§5) |
| `capture` | `capture_id`, `path` (dans le périmètre), `sha256`, `kind` ∈ `FIXTURE`, `COMMITTED_FIXTURE`, `AUTHORIZED_CAPTURE` | empreinte ⇒ `CAPTURE_FINGERPRINT_MISMATCH` ; hors périmètre ⇒ `CAPTURE_OUT_OF_SCOPE` |

Pointeurs : `a.b[*].c` (`[*]` parcourt un tableau). Unités fermées : `EPOCH_MS`,
`DURATION_MS`, `UTC_ISO_SECONDS`, `DECIMAL_STRING_BPS`, `COUNT`. Relations de jointure :
`EQUALS`, `CONTAINED_IN`, `SAME_LENGTH`, alignées élément par élément sur le premier
tableau commun.

## 3. Sortie obligatoire (`cat.observation.report.v1`)

```text
{ "content": {...},            # déterministe
  "content_sha256": sha256(canonical(content)),
  "run": {started_utc, ended_utc, duration_ms, peak_traced_bytes, sources_read, bytes_read},
  "report_sha256": sha256(canonical({content, content_sha256, run})) }
```

`content` porte : `agent_id`, `profile`, `mission_id`, `analyzed_ref`, `status`,
`chain` (un maillon par saut, §6), `findings`, `inferred_links`, `freshness`,
`capture`, `observations`, `unknowns`, `runtime_measurements_required`,
`sources_consulted` (chemin, octets, sha256 — profil inclus), `refused_paths`,
`errors`, `limits`.

Chaque constat : `finding_id` (hash de catégorie, code et preuves), `category`,
`code`, `claim` (affirmation en français), `level` ∈ `PROVEN | SUPPORTED | INFERRED |
INCONCLUSIVE | NOT_FOUND`, `confidence` ∈ `HIGH | MEDIUM | LOW`, `evidence[]`
(`path`, `line`, `symbol`, `evidence_type` ∈ `CODE | CALL_SITE | IMPORT | LITERAL |
CAPTURE_FIELD | FILE_STAT | MISSION_INPUT`, `file_sha256`).

Les métadonnées temporelles sont **séparées** : deux exécutions identiques ont le même
`content_sha256` et des `report_sha256` différents. Le `mtime` d'une capture est un fait
du système de fichiers et reste dans `content.freshness` (il est fixé par `setup.json`
dans les fixtures ; pour un checkout git, il vaut l'heure du checkout).

## 4. Identité de mission

```text
mission_id = SHA256(canonical_json({
  "mission_identity_schema": "cat.observation.mission-identity.v1",
  "agent_id", "profile", "analyzed_ref", "scope", "question", "budget", "capture" }))
```

Sérialisation canonique de A1 §3.1. Aucun horodatage d'exécution n'entre dans l'identité ;
`question.as_of_utc` y entre car il change la réponse.

## 5. Statuts de mission

| Statut | Condition | Ce qu'il **ne** signifie **pas** |
|---|---|---|
| `BLOCKED` | entrée refusée avant lecture du périmètre (schéma, profil, chemin, secret, empreinte) | — aucune source du périmètre n'est lue |
| `FAILED` | erreur interne, ou budget épuisé avant tout maillon prouvé | jamais « vide » ni « sain » |
| `PARTIAL` | au moins un maillon non `PROVEN`, capture illisible, budget épuisé après des preuves ou source non analysable | les maillons prouvés restent publiés |
| `COMPLETE` | les 7 maillons `PROVEN`, capture analysée, aucun budget épuisé | **pas** « dataset sain » : une source périmée, une jointure contradictoire ou une unité incompatible restent des constats d'une mission COMPLETE |

## 6. Règles de preuve statique V1 (pilote)

| Maillon | PROVEN si (dans le périmètre) | Sinon |
|---|---|---|
| `PRODUCER` | un seul module Python porte la littérale `dataset_id` **et** écrit un fichier | `NOT_FOUND` ; plusieurs ⇒ constat `MULTIPLE_PRODUCERS` |
| `SOURCE_TO_PRODUCER` | un autre module écrit un nom de fichier (gabarit f-string inclus) que le producteur nomme | `NOT_FOUND` / `INCONCLUSIVE` |
| `PRODUCER_TO_STORAGE` | le chemin écrit vient d'un argument `--x` (argparse) ou d'un `getenv` dans la même fonction | `INCONCLUSIVE` (chemin dynamique) |
| `STORAGE_TO_READER` | lecteur (résolu depuis la route) et producteur partagent la même liaison (`ENV:`/`CLI:`) | `INFERRED` si le lecteur importe le schéma du producteur ou porte l'identifiant mais lit une autre liaison ; `INCONCLUSIVE` si aucun lien ; lecteur hors périmètre ⇒ `INCONCLUSIVE` + `READER_OUT_OF_SCOPE_NOT_READ` |
| `READER_TO_API` | une route (`@app.get`) sert l'endpoint du client, et son corps appelle `X.read()` où `X = Classe()` importée | `INCONCLUSIVE` / `NOT_FOUND` |
| `API_TO_CLIENT` | un fichier TS porte `dataset_id` **et** la même littérale d'endpoint `/api/...` | `NOT_FOUND` |
| `CLIENT_TO_VIEW` | une vue importe une fonction exportée du client ; l'hôte qui importe la vue est cité | `NOT_FOUND` |

Analyse statique uniquement (`ast` pour Python, motifs pour TS) : aucun module n'est
importé ni exécuté. Indirection au-delà d'un saut ⇒ non prouvée, jamais supposée.

Capture : JSON strict (clé dupliquée, `NaN`, troncature ⇒ `CAPTURE_MALFORMED`) ;
fraîcheur (`FRESHNESS_CANONICAL | FRESHNESS_PARTIAL | MTIME_ONLY | NO_FRESHNESS_CONTRACT`,
verdict `SOURCE_WITHIN_THRESHOLD | SOURCE_STALE | AGE_REPORTED_NO_THRESHOLD |
INCONCLUSIVE`) ; le `mtime` n'est **jamais** une preuve (`mtime_used_as_evidence=false`)
et un mtime récent sur source périmée produit `MTIME_RECENT_SOURCE_STALE` ; unités
(`UNIT_MISSING`, `UNIT_INCOMPATIBLE`) ; jointures (`JOIN_KEY_CONTRADICTION`) ; rejeu :
un enregistrement identique pour la même clé est compté **une** fois
(`IDENTICAL_REPLAY_COUNTED_ONCE`), une même clé au contenu différent est une
contradiction conservée (`OBSERVATION_KEY_CONFLICT`).

## 7. Règles constitutionnelles

1. Lecture seule des sources autorisées, par un lecteur unique qui inventorie chaque
   fichier lu ; lien symbolique, nom de secret ou chemin hors périmètre ⇒ consigné dans
   `refused_paths`, jamais ouvert.
2. Aucun accès réseau ; aucune API de marché ; aucun VPS. Le banc tourne hors ligne.
3. Aucun ordre, aucune décision de trading, aucune modification de gate, aucune écriture
   de production ni d'aucun fichier : l'auditeur n'a pas de chemin d'écriture.
4. Preuve manquante ⇒ `INCONCLUSIVE` ou `NOT_FOUND`, jamais une valeur inventée.
5. Le rapport ne s'auto-certifie pas (`REPORT_IS_NOT_SELF_CERTIFYING`) ; ni `valid`, ni
   `PASS`, ni `CERTIFIED`. Les verdicts `*_COMPLETE` des profils legacy (A0 §16 I7) ne
   sont pas repris.
6. Un test réussi n'allume aucun voyant : `wiring_status` reste `NOT_WIRED`,
   `runner_id = null` dans `agentIdentityRegistry.v1.json` (inchangé par ce lot).

## 8. Exemples

- Entrée pilote : [`pilot_mission.json`](../agents/observation/examples/pilot_mission.json)
- Sortie pilote : [`pilot_report.json`](../agents/observation/examples/pilot_report.json)
- Fixtures A–I : `tests/agent_bench/fixtures/observation/*/{mission,expected,setup}.json`
  (`FIXTURE_ONLY · NOT_REGISTRY_DATA · NOT_OPERATOR_DATA · NOT_DEPLOYED`).

## 9. Évolution

Toute nouvelle règle de preuve, unité, relation ou profil exécutable = nouvelle version
(`…v2`), revue humaine, nouveaux cas de banc. Un profil n'est exécutable au banc qu'après
une fiche acceptée, des fixtures à résultat attendu prédéfini et une matrice verte.

## 10. Version 2 (`cat.observation.mission.v2`, 2026-11-22)

Ajoute deux types de question, sans changer les règles communes (§2–§7) :
`METRIC_SURFACE_MAP` (observability-cartographer) et `CHANGE_IMPACT` (repo-architect). Champs,
règles de preuve, matrices et dossiers de stockage : [AGENTS_V2_ET_STOCKAGE](../agents/observation/AGENTS_V2_ET_STOCKAGE.md).

