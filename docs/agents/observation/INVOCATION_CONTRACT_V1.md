# Contrat d'invocation `cat.observation.invocation.v1` — branchement Repository Cartographer

Statut : **code et banc en PR brouillon (#599), non installés, non activés**. Aucun service, timer ou
cron n'est créé ; le registre garde `NOT_WIRED` et `runner_id: null`, donc le voyant du profil reste
gris ; la présentation est derrière `VITE_CARTOGRAPHER_INVOCATION` (désactivé par défaut).
Base : PR #598 (code `52db9887`, zone `e387318e`). Les rapports réels et preuves runtime restent sur le
VPS : ils ne sont pas publiés dans GitHub, même expurgés, sans autorisation spécifique.

Ce document décrit le code **après** la correction de la revue de `33b1ec03`. Les écarts corrigés et
leurs tests sont dans la PR #599 (tableau « défaut → correction → test → résultat »).

## 1. Audit initial (lecture seule, conservé)

| Point | Constat (avant ce lot) | Suite |
|---|---|---|
| Rapports réels | Sur le VPS seulement ; inventaire non vérifié d'ici. | Inchangé : non publiés. |
| Preuves d'invocation | Le rapport ne porte ni runner, ni SHA de code, ni code de sortie, ni limites. | Enveloppe dédiée (§2) ; les anciens rapports ne sont pas complétés. |
| Écriture de la CLI `bench.py` | `write_text`, sans garantie contre l'écrasement. | L'exécuteur publie par `os.link` ; `bench.py` reste inchangé. |
| Registre Système | `RUNTIME_EVIDENCE_SOURCE = NOT_CONNECTED`. | Inchangé dans le registre livré (§6). |
| Compte API | `lecanada26` (UID 1001), sans accès au dossier des rapports. | Accès en lecture à décider (procédure). |

## 2. Contrat d'invocation (fichier unique)

Une invocation est publiée comme **un seul fichier JSON** : l'enveloppe contient le rapport scellé et
le bloc `verification`. Un fichier incomplet n'est jamais une preuve.

Champs obligatoires (`ENVELOPE_KEYS`) : `contract`, `contract_version`, `invocation_id` (32 hex),
`agent_id`, `runner_id`, `mission_id`, `profile_blob_sha1`, `code_sha`, `analysed_sha`, `started_utc`,
`ended_utc` (format `AAAA-MM-JJThh:mm:ssZ`, secondes entières), `state`, `exit_code`,
`interruption_reason`, `result_status`, `report_sha256`, `content_sha256`, `limits`, `report`,
`verification`.

Deux SHA distincts : **`code_sha`** = code exécuté (HEAD du checkout, et chaque module
`agent_bench.observation.*` réellement chargé a le blob de ce commit) ; **`analysed_sha`** = sources
analysées (chaque fichier du périmètre a, sur disque, le blob qu'il a à ce commit).
`verification` consigne `checkout_head`, `executed_modules`, `scope_blobs`, `profile_source_path`,
`profile_blob_sha1`.

Trois niveaux à ne pas confondre : **profil** (`agent_id` + `profile_blob_sha1`) ; **exécution**
(`state` ∈ `COMPLETED`, `FAILED`, `TIMEOUT`, `INTERRUPTED`, `ABANDONED`) ; **résultat scientifique**
(`result_status` ∈ `COMPLETE`, `PARTIAL`, `BLOCKED`, `FAILED`). `COMPLETED` + `PARTIAL` est normal.

Validation (`validate_envelope`) — les empreintes recalculées ne remplacent pas les comparaisons :

- identité attendue ↔ enveloppe : agent, runner, mission ; profil qualifié attendu (côté API) ;
- état ↔ code de sortie (`COMPLETED` ⇒ 0, échec ⇒ ≥ 1) ; limites dans les bornes ;
- `verification` ↔ enveloppe : HEAD vérifié = `code_sha`, profil vérifié = `profile_blob_sha1` ;
- enveloppe ↔ contenu du rapport : agent, mission, SHA analysé, chemin de profil, statut, et
  sources consultées incluses dans le périmètre vérifié ;
- chronologie : dates valides, fin ≥ début, pas dans le futur (tolérance 60 s) ;
- `ABANDONED` : aucun rapport, résultat, empreinte, vérification ni limite (rien n'est inventé).

Nom de fichier : `runs/<mission_id>/<AAAAMMJJThhmmssZ>_<invocation_id>.json` ; le lecteur exige que
le nom corresponde à l'enveloppe.

## 3. Exécuteur ponctuel (`agent_bench/observation/executor.py`)

Point d'entrée documenté et testé de bout en bout :

```
python3 -m agent_bench.observation.executor \
  --mission <mission.json> --checkout <checkout git au code_sha> --reports <dossier des rapports> \
  --runner-id obs-repo-cartographer-ro-01 --code-sha <sha> --analysed-sha <sha> [--max-run-s N]
```

Sortie : une ligne JSON (`PUBLISHED`, `REFUSED` ou `PUBLICATION_FAILED`, avec code et motif).
Codes de sortie : `0` publié `COMPLETED` ; `2` refusé avant exécution ; `3` publié mais non
`COMPLETED` ; `4` échec de publication.

- **Refus avant exécution** (rien n'est publié) : mission invalide, agent non qualifié, git
  indisponible ou HEAD non vérifiable (`GIT_UNAVAILABLE`, `HEAD_UNVERIFIABLE`), HEAD ≠ `code_sha`,
  SHA analysé absent, fichier du périmètre modifié ou absent au SHA analysé (`CHECKOUT_MODIFIED`,
  `SCOPE_ABSENT_AT_ANALYSED_SHA`), profil différent, module exécuté différent du commit déclaré
  (`CODE_MISMATCH`), dossier de preuves non sûr ou trop peuplé. Aucun mode synthétique : les tests
  construisent de vrais dépôts git.
- **Bornes** : durée `min(120 s, budget de mission, --max-run-s)` — un argument ne peut que
  l'abaisser ; fichiers ≤ 30 ; bail ≤ 600 s. La CLI applique aussi `RLIMIT_CPU`, `RLIMIT_AS` (1 Gio),
  `RLIMIT_NOFILE` (256), `RLIMIT_FSIZE` (16 Mio).
- **Exclusion mutuelle** : `flock(LOCK_EX | LOCK_NB)` sur `locks/<runner_id>.lock`. Le noyau libère
  le verrou à la mort du processus (y compris `SIGKILL`) : pas de verrou orphelin, pas de reprise par
  `rename`, et un exécuteur ne peut jamais supprimer le verrou d'un autre (le fichier n'est jamais
  supprimé). Un second candidat reçoit `ALREADY_RUNNING`.
- **Reprise** : sous verrou, si le contenu du verrou désigne une invocation jamais publiée (arrêt
  brutal), l'exécuteur publie d'abord son `ABANDONED`, puis nettoie les `.partial`. Deux reprises
  simultanées : une seule obtient le verrou, une seule enveloppe `ABANDONED` est publiée.
- **Interruption contrôlée** (`SIGTERM`) : publication `INTERRUPTED`, verrou libéré.
- **Publication** : `.<nom>.partial` en `O_EXCL` + `fsync`, puis `os.link` vers le nom définitif
  (atomique, sans écrasement : `NAME_EXISTS`), puis `fsync` du dossier (durabilité). Chaque niveau
  de chemin est ouvert en `O_NOFOLLOW` : un lien symbolique dans un parent est refusé. Échec de
  publication : `PUBLICATION_FAILED` explicite, aucun fichier partiel visible, verrou libéré.

## 4. Lecteur (`agent_bench/observation/invocation_reader.py`) — strictement passif

Aucun fichier créé, modifié ou verrouillé ; le lecteur ne prend jamais de verrou.

**Attestation de l'activité réelle.** Un bail valide seul ne prouve pas qu'un processus vit. Le
lecteur lit `/proc/locks` et exige qu'un `FLOCK WRITE` soit tenu sur l'inode du fichier de verrou
**par le PID déclaré dans le verrou**. `EN_COURS` = verrou noyau tenu + contenu de verrou valide
(schéma, agent, runner, mission, `invocation_id`, chronologie, bail ≤ 600 s non expiré). Un PID
réutilisé par un autre processus ne tient pas le verrou : refus. `/proc/locks` illisible, verrou tenu
par un autre PID, contenu invalide : `INDETERMINE`, jamais vert.

Sortie :

- **connexion et preuve** : `AVAILABLE`, `ABSENT`, `ACCESS_DENIED`, `UNREADABLE`, `INCOMPLETE`, `INVALID` ;
- **activité** : `EN_COURS`, `TERMINE` (dernière enveloppe valide), `INDETERMINE` ;
- **dernier résultat** scientifique, séparé ; `life_observed`, `lease_until_utc` ;
- **`server_observed_at_utc`** (instant de la lecture) distinct de **`last_activity_utc`** (fin
  consignée de la dernière mission) : relire un ancien rapport ne le rajeunit jamais ;
- **règle des 36 h (implémentée et testée)** : `last_mission_age_s`, `mission_overdue` ; le libellé
  rouge devient « … · aucune mission depuis plus de 36 h » ;
- **`display`** (contrat d'affichage partagé, §6).

Lecture bornée : 2 Mio par fichier ; énumération par `scandir` arrêtée à 200 entrées avec refus
explicite (pas de `listdir` puis découpe) ; `O_NOFOLLOW` à chaque niveau ; noms conformes seulement ;
la plus récente invalide rend `INVALID`, sans repli sur une plus ancienne.

## 5. Comportement après arrêt brutal, délais

| Événement | Serveur | Interface |
|---|---|---|
| `SIGKILL` de l'exécuteur | Le noyau libère le verrou immédiatement ; la lecture suivante ne voit plus de détenteur → `TERMINE` (dernière enveloppe) ou `INDETERMINE`. L'`ABANDONED` est publié par l'invocation suivante. | Vert retiré à la réponse suivante (≤ 30 s + requête), et au plus tard à l'échéance `valid_until_utc` (≤ 90 s). |
| Exécuteur figé (verrou tenu) | `EN_COURS` jusqu'à la fin du bail (≤ 600 s) au plus ; la durée d'exécution est bornée à 120 s par l'alarme et `RLIMIT_CPU`. | Vert tant que le serveur l'atteste, renouvelé par les réponses. |
| API coupée ou lente | — | Requête abandonnée à 10 s → gris « Coupure ». Sans aucune réponse, la couleur s'éteint à l'échéance locale. |

## 6. Route, présentation et contrat d'affichage partagé

- **Route** : `GET /api/operator/v1/agent-invocations/repository-cartographer`, `Cache-Control:
  no-store`, liste fermée de cibles avec identité attendue (agent, runner, mission, profil qualifié
  `dd414cad…`). Le chemin des rapports (`AGENT_INVOCATION_REPORTS_PATH`, défaut
  `/srv/cat-obs/reports`) n'est jamais renvoyé. Toute exception devient `UNREADABLE` gris.
- **`display`** décidé par le serveur : `GREEN` seulement si identité, preuve, observation de vie et
  fraîcheur sont valides (échéance = min(bail, maintenant + 90 s)) ; `RED` « Inactif · fin normale » ou
  « Inactif · échec » pour une fin attestée (échéance + 90 s) ; `GRAY` sinon (échéance nulle).
- **Interface** : valide la réponse à l'exécution (aucun cast aveugle), ne recalcule aucun verdict,
  peut seulement rétrograder en gris (identité inattendue, date invalide ou future, vert sans vie
  observée, rouge sans fin attestée, échéance absente ou échue). L'échéance est mesurée sur
  l'horloge du navigateur depuis la réception (`reçu + min(valid_until − observé, 90 s)`) et un
  minuteur éteint la couleur à cet instant, sans nouvelle réponse.
- **Interrogation** : une seule requête en vol ; suivante planifiée 30 s après la réponse ; abandon
  à 10 s ; réponse d'une requête remplacée ou plus ancienne que la dernière affichée rejetée ;
  annulation complète au démontage.
- **Registre** : `NOT_WIRED` dans le registre livré → voyant du profil gris quelle que soit la preuve ;
  seule la carte de preuve montre l'état, et seulement avec le drapeau.
- **Captures mobile** (iPhone 13, clair/sombre, harnais synthétique
  `frontend/vite.cartographer-proof.config.ts`) : `screenshots/invocation-mobile/` et `results.json`.

## 7. Installation

Procédure préparée, **non exécutée** : `CARTOGRAPHER_INSTALL_PROCEDURE.md`. Campagne : préparée, non
démarrée (`CARTOGRAPHER_CAMPAGNE_7J.md`).

## 8. Tests

- `tests/agent_bench/test_invocation_contract.py` : verrou (identités, invocation manquante, bail
  excessif, dates incohérentes, processus arrêté, PID réutilisé, `/proc/locks` illisible) ;
  cohérence (rapport d'un autre agent, SHA différent, profil incohérent, git indisponible, checkout
  modifié, code exécuté ≠ référence) ; vrais processus concurrents synchronisés, deux reprises
  simultanées après `SIGKILL`, `SIGTERM`, échec de publication ; CLI de bout en bout ; liens
  symboliques, énumération bornée, nom ↔ enveloppe, `.partial`, règle des 36 h.
- `tests/agent_bench/test_agent_invocation_api.py` : route, vert seulement avec verrou noyau, profil
  attendu, chemin jamais exposé.
- `tests/agent_bench/test_observation_bench.py` : non-régression du pilote (périmètre figé au SHA
  pilote, et périmètre courant avec écarts revus).
- Front : `frontend/src/test/invocationEvidence.test.tsx` (validation, contrat d'affichage,
  interrogation, expiration page ouverte).
