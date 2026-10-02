# APP-UNIFY U2b — RuntimeServiceSnapshot

Issue : #330
Parent : #323
Freeze : #286 ACTIVE
Baseline source : `e16856e860467b3b8fb629bcb16e8cba5bdd1061`

## Besoin et autorité

U0 a identifié l'absence d'une preuve host indépendante du service Advisor.
Le manifest déclare une succession de processus ; `/healthz` décrit le
transport API ; `system_health.boot_alive` garde sa sémantique existante.
Aucun de ces éléments ne devient une preuve systemd.

U2b fournit une observation du gestionnaire de services, à la capture :

```text
systemctl show crypto-advisor.service (propriétés fixes)
              ↓
producteur host externe READ-ONLY
              ↓
runtime_service_snapshot.json atomique
              ↓
reader strict, sans subprocess / Advisor / PPL
              ↓
GET /api/operator/v1/runtime-service
              ↓
Direction + PAPER LIVE / Système
```

Autorité : `HOST_SYSTEMD_OBSERVATION`. Mode : `READ_ONLY`.
Un service `active/running` ne certifie ni la santé du cycle Advisor, ni sa
progression scientifique, ni une permission de trade. Aucun booléen global
`alive` ou `healthy` n'est fabriqué. Direction reste fédérée/non atomique
avec six sources indépendantes.

## Collecte fermée

Unité unique : `crypto-advisor.service`, conformément au catalogue source
`scripts/claude-service-matrix.py`. Aucun argument CLI ne permet de choisir
une autre unité ou une commande arbitraire.

Commande absolue `/usr/bin/systemctl show --no-pager`, sans shell.
Propriétés autorisées exclusivement :

- `LoadState`, `ActiveState`, `SubState` ;
- `MainPID`, `NRestarts` ;
- `ExecMainStartTimestamp`, `InvocationID`.

Locale C et timezone UTC ; délai total de trois secondes ; lecture bornée
à 4096 octets (+ un octet pour constater le dépassement). Stderr est envoyé
à DEVNULL, jamais lu ni publié. Le processus de collecte est tué/récolté
en cas de timeout ou dépassement ; il n'est jamais le processus Advisor.

Aucune lecture de journal, Environment, EnvironmentFiles, ExecStart,
ExecStop, `/proc/environ`, manifest Advisor ou JSONL/PPL. Aucune commande
start/stop/restart/reload/enable/daemon-reload. Aucun import trading.

## Contrat fermé v1.0.0

Champs racine exacts : `schema_version`, `product`, `domain`, `authority`,
`mode`, `generated_at_utc`, `observed_at_utc`, `host_id`, `service`,
`deployment`. Product : `RuntimeServiceSnapshot`. Domaine : `runtime_service`.

| Famille | Champs / sémantique |
|---|---|
| Temps | UTC strict ; observation ≤ génération ; capture après la lecture host |
| Host | hostname local borné à 128 caractères ; label d'hôte, pas attestation cryptographique |
| Service | unité, query_status, load_state, active_state, sub_state, main_pid, restart_count, exec_main_started_at_utc, invocation_id |
| Query OK | états systemd validés, compteurs entiers sûrs ≥ 0 ; zéro réellement observé conservé |
| active/running | MainPID positif, démarrage et invocation obligatoires ; contradiction => INVALID_PROPERTIES |
| Query non OK | états/PID/redémarrages/démarrage/invocation null ; jamais de faux zéro |
| NOT_FOUND | uniquement LoadState=not-found avec une sortie admissible ; état active inconnu |
| Deployment | status, reason, source_code_sha, evidence_ref, observed_at_utc, artifact_sha256, host_id, invocation_id |

Query states : `OK`, `NOT_FOUND`, `TIMEOUT`, `COMMAND_UNAVAILABLE`,
`COMMAND_FAILED`, `INVALID_PROPERTIES`, `OUTPUT_LIMIT`.
Tout état systemd non supporté reste `INVALID_PROPERTIES`, pas une nouvelle
interprétation silencieuse.

## Preuve de source/déploiement

Le producteur ne prend jamais son propre git HEAD pour le code Advisor.
Il peut lire un artifact explicitement fourni via `--deployment-evidence` :

```json
{
  "schema_version": "1.0.0",
  "product": "RuntimeServiceDeploymentEvidence",
  "host_id": "host-label",
  "unit": "crypto-advisor.service",
  "invocation_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "source_code_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "evidence_ref": "deployment-proof-reference",
  "observed_at_utc": "2026-10-01T00:00:01Z"
}
```

Le document doit être fermé, régulier, non symlink, borné à 16 KiB, sans
clés dupliquées ni constantes JSON non finies. Host, unité et invocation
doivent correspondre à la capture systemd ; son temps doit se situer entre
le démarrage de cette invocation et l'observation host.

`PRESENT` signifie **preuve fournie et liée**, pas code chargé vérifié par
U2b. La création/certification de cet artifact de preuve appartient à une
future gate runtime ; U2b ne le génère pas depuis un PID, un manifest ou un
checkout. Le digest SHA-256 identifie les octets exacts de la preuve fournie.
Les host/invocation projetés sont aussi validés par les readers Python/TS.

Absence, corruption ou désaccord => `NOT_AVAILABLE`, avec une raison
fermée et tous les champs de preuve null. La collecte du service reste
indépendante de la présence de cette preuve.

## Publication, API et fraîcheur

Publication one-shot externe uniquement : temporaire unique dans le même
répertoire puis `os.replace`. Échec => ancien artifact conservé, sans
touches au service ni remontée d'erreur dans Advisor. Le chemin de sortie
ne peut pas écraser le document source de preuve de déploiement.

Le reader consomme seulement l'artifact, en lecture bornée avec O_NOFOLLOW.
Missing, malformed, duplicate, oversized, non-regular, symlink ou contrat
invalide => HTTP 503 avec code d'erreur fermé, sans erreur brute ni secret.
Temps futur => `RUNTIME_SERVICE_FUTURE_TIMESTAMP`.

L'API ajoute uniquement `snapshot_age_s` et `freshness_classification`.
L'âge part de `observed_at_utc`, pas de la date de republication.
Seuil source par défaut : 90 secondes. Aucune configuration runtime n'est
modifiée dans cette PR. Une preuve STALE conserve ses valeurs historiques,
mais l'UI indique `ÉTAT ACTUEL · INCONNU`. Les erreurs de source, transport
ou contrat n'utilisent aucun fallback Advisor/API health.

Système affiche cette carte indépendamment de la présence du snapshot
Advisor. Le domaine system_health existant reste inchangé. Les détails
host/déploiement sont repliables ; les cartes sont lisibles sur mobile.

## Certification source et frontière #286

Preuves : commande fixe et capture réellement bornée ; success/inactive/
failed/transition/not-found/errors ; zéro versus null ; preuve de déploiement
liée/désaccord ; atomicité ; strict readers ; GET-only ; contrats frontend ;
cross-stack réel producer → artifact → API → React ; desktop/mobile avec
stale/missing/invalid/network et indépendance du snapshot Advisor.

Les tests injectent uniquement le transport systemd : aucune observation
réelle du VPS ou de l'Advisor n'est prétendue par ces preuves source.

Verdict cible : `APP_UNIFY_U2B_RUNTIME_SERVICE_SOURCE_READY`.

Aucun déploiement/publisher/service/timer/systemd installés par U2b.
Aucun restart Advisor, changement PPL/FIN/epoch/config/risk/sizing,
PB_MAX_POSITIONS, Watchdog ou exchange. #286 reste ACTIVE.
Le déploiement ultérieur du collecteur exige une gate séparée.
