# Contrat d'invocation `cat.observation.invocation.v1` — branchement Repository Cartographer

Statut : **banc et code en PR brouillon, non installés, non activés**. Aucun service, timer ou cron
n'est créé ; le voyant du registre reste gris ; `runner_id` reste `null` dans le registre déployé.
Base : PR #598 (code `52db9887`, zone `e387318e`).

## 1. Audit complémentaire (lecture seule)

| Point | Constat | Conséquence |
|---|---|---|
| Rapports réels | Sur le VPS seulement. Non accessibles depuis cet environnement. Seule la répétition `cartographer-rehearsal-20261122T010856Z.json` est signalée (taille, empreinte) par Mathieu. | Inventaire VPS **non vérifié** ici. |
| Preuves d'invocation | Aucune. Le rapport ne porte ni `runner_id`, ni SHA de code, ni code de sortie, ni limites. Son bloc `run` contient seulement `started_utc_ns`, `ended_utc_ns`, `duration_ms`, `sources_read`. | Une enveloppe dédiée est nécessaire ; les anciens rapports ne sont **pas** complétés. |
| Écriture de la CLI | `bench.py` écrit avec `write_text` (sans garantie contre l'écrasement). | L'exécuteur ajouté publie par `os.link` ; la CLI existante reste inchangée. |
| Registre Système | `frontend/src/agents/agentRegistry.ts` : `RUNTIME_EVIDENCE_SOURCE = NOT_CONNECTED`. `classifyActivity` ne donne vert/rouge qu'avec un runner vérifié et une preuve serveur fraîche. | Le branchement côté front n'est **pas** fait dans ce lot (voir §6). |
| Voyants | `classifyActivity` distingue déjà « Actif » (preuve récente) et « Inactif » (preuve attestée). Un rapport sans activité en cours n'est pas une panne. | Le nouveau lecteur respecte ces règles côté serveur. |
| Route API | Aucune route `agents` dans `observability/operator_api/app.py`. Les lecteurs existants suivent le motif `*_reader.py` + route `GET /api/operator/v1/...`. | Route non ajoutée dans ce lot (§6). |
| Compte API | L'API tourne sous `lecanada26` d'après l'audit précédent. Aucun accès au dossier des rapports. Non re-vérifié ici. | **Inconnue** : doit être confirmée sur l'hôte avant tout accès. |

## 2. Contrat d'invocation (fichier unique)

Une invocation est publiée comme **un seul fichier JSON** : l'enveloppe contient le rapport scellé.
Un fichier incomplet n'est donc jamais une preuve.

Champs obligatoires (`ENVELOPE_KEYS`) : `contract`, `contract_version`, `invocation_id` (32 hex),
`agent_id`, `runner_id`, `mission_id`, `profile_blob_sha1`, `code_sha`, `analysed_sha` (deux SHA
distincts quand ils diffèrent), `started_utc`, `ended_utc` (UTC ISO 8601 `Z`), `state`,
`exit_code`, `interruption_reason`, `result_status`, `report_sha256`, `content_sha256`, `limits`, `report`.

Trois niveaux à ne pas confondre :

- **profil** : `agent_id` + `profile_blob_sha1` (qualification) ;
- **exécution** : `state` ∈ `COMPLETED`, `FAILED`, `TIMEOUT`, `INTERRUPTED`, `ABANDONED` ;
- **résultat scientifique** : `result_status` ∈ `COMPLETE`, `PARTIAL`, `BLOCKED`, `FAILED`.

`COMPLETED` avec `PARTIAL` est normal. Un code de sortie 0 ne prouve pas la validité : seul le
recalcul des empreintes (`content_sha256`, `report_sha256`) et la cohérence des identités le fait.

Nom de fichier : `runs/<mission_id>/<AAAAMMJJThhmmssZ>_<invocation_id>.json` (début d'invocation).

Une invocation `ABANDONED` ne prouve pas ses SHA : `code_sha`, `analysed_sha`, `profile_blob_sha1`
restent `null`, jamais inventés.

## 3. Exécuteur ponctuel (`agent_bench/observation/executor.py`)

- Une invocation par appel explicite. Aucun démon, aucune relance automatique.
- Verrou `locks/<runner_id>.lock` créé en `O_EXCL`, avec bail (`lease_until_utc`, 10 min).
- Bail dépassé : le verrou est repris (`rename` puis création), et l'invocation précédente est
  consignée `ABANDONED` avec un motif. Aucun état « en cours » permanent.
- Publication : écriture dans `.<nom>.partial`, `fsync`, puis `os.link` vers le nom définitif.
  `os.link` échoue si le nom existe : l'ancien fichier est préservé (refus `NAME_EXISTS`).
- Le lecteur ignore les fichiers cachés (`.partial`) : une publication interrompue n'est jamais acceptée.
- Limite de durée : `min(120 s, budget.max_wall_ms)` via signal d'alarme (`TIMEOUT` si dépassée).
  Limite de fichiers : budget de la mission, plafonné à 30.
- Refus avant verrou : mission invalide, agent non qualifié, SHA analysé différent de la mission,
  checkout git dont le HEAD diffère de `code_sha`.
- Verrou libéré dans un `finally` après publication.

Non traité par l'exécuteur : isolation réseau, permissions de système de fichiers, identité
Unix. Elles restent des contrôles d'environnement (procédure §5), pas du code.

## 4. Lecteur (`agent_bench/observation/invocation_reader.py`)

Sortie séparée pour Système :

- **connexion et preuve** : `AVAILABLE`, `ABSENT`, `ACCESS_DENIED`, `UNREADABLE`, `INCOMPLETE`,
  `INVALID` (avec motif : empreinte altérée, mauvais runner, date future, etc.) ;
- **activité** : `EN_COURS` (bail valide), `TERMINE` (dernière invocation terminée), `INDETERMINE`
  (aucune preuve, ou bail expiré). `INACTIF` n'est jamais déduit de l'absence ;
- **dernier résultat** : `COMPLETE`, `PARTIAL`, `BLOCKED`, `FAILED`, ou `null`.

Règles :

- `last_activity_utc` = fin consignée de l'invocation, jamais la date de lecture : relire un
  ancien rapport ne le rajeunit pas ;
- l'invocation la plus récente invalide rend `INVALID` ; pas de repli silencieux sur une plus ancienne ;
- lecture bornée : 2 Mo par fichier, 50 fichiers listés, `O_NOFOLLOW` (lien symbolique refusé),
  seuls les fichiers réguliers aux noms conformes sont lus.

## 5. Procédure d'installation (non exécutée) et retour arrière

Préalables, à décider séparément : confirmer le compte `cat-obs-ro` et son appartenance ; confirmer le
compte API ; décider du chemin de publication.

Installation proposée (à faire seulement après décision) :

1. Copier `executor.py`, `invocation.py`, `invocation_reader.py` dans le checkout `/srv/cat-obs/checkout/<code_sha>/` (lecture seule).
2. Le lanceur ponctuel est `python3 -m agent_bench.observation.executor` (à ajouter comme point d'entrée
   minimal dans une étape ultérieure ; non fourni dans ce lot).
3. Permissions : `cat-obs-ro` en écriture **uniquement** sur `/srv/cat-obs/reports/` ; le lecteur API
   a un accès en lecture sur `runs/` et `locks/`, sans écriture et sans accès au reste du dossier.

Retour arrière : retirer le lanceur et le checkout de l'invocation ; **conserver** `/srv/cat-obs/reports/`
(preuves, CLAUDE.md §5). Aucun `rm -rf` sur `reports`.

## 6. Ce qui n'est pas fait dans ce lot

- Route API `GET /api/operator/v1/agent-invocations/...` et son branchement dans
  `AgentRegistryView` : **non fait**. La présentation Système (trois états séparés, vieillissement
  pendant que la page est ouverte, coupure API → gris) reste à implémenter.
- Captures mobile clair/sombre : **non faites**.
- Campagne de 7 jours : **non préparée**.
- Accès réel au VPS, inventaire des rapports, identité de l'API : **non vérifiés**.

## 7. Tests

`tests/agent_bench/test_invocation_contract.py` : 22 tests, couvrant le tableau d'acceptation
(PARTIAL valide, EN_COURS limité, interruption, lancements concurrents, nom existant, publication
interrompue, empreinte altérée, mauvais runner, date future, rapport absent, illisible, lien symbolique,
relecture sans rajeunissement, invocation abandonnée, refus avant verrou). Ils sont **unitaires et
d'intégration locale** (fichiers temporaires). Les preuves sous identité isolée relèvent de la PR.
