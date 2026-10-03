# APP-STORAGE-01 — Stockage DecisionPackets

Mission #368, parent #323, roadmap #285 ; #286 ACTIVE. Base source `8aad0ac4`.
Tranche source/UI, aucun déploiement ou accès VPS. Le stockage était un reliquat
explicite de l’inventaire app après APP-EVENTS-01 #361/#364.

## Source, parité et limites

L’ancien `scripts/dashboard_api.py:/api/status` expose `dp_files` et
`dp_total_gb` depuis `DP_DIR.glob("decision_packets_*.jsonl")`. La nouvelle
projection reprend la population de fichiers et le volume **logique en octets**,
sans arrondi ; pas les blocs alloués, la capacité ou l’espace libre du disque.
`packets_today` et `last_packet` restent aux projections de packets existantes :
aucun nombre de records ou timestamp d’événement déduit du filesystem.

Répertoire choisi explicitement ; enfants directs correspondant au pattern
fixe, sans récursion. Maximum 10 000 entrées examinées, y compris non pertinentes.
Seuls les fichiers réguliers sont admissibles. Un symlink/fifo/répertoire
correspondant invalide la capture entière. Le répertoire final est ouvert sans
suivre un symlink ; stats relatives au descripteur, sans ouvrir de journal.
Deux inventaires et signatures du répertoire doivent correspondre, y compris
la liaison chemin/descripteur. Une mutation détectée produit SOURCE_CHANGED ;
aucun lock, écriture source ou arrêt du producteur. C’est une observation
stable entre contrôles, pas une transaction filesystem ni une preuve scientifique.

Les chemins, noms de fichiers, inodes et contenus privés ne sont pas exportés.
`inventory_sha256` porte sur la liste ordonnée des métadonnées (nom privé,
device/inode, taille, mtime/ctime nanosecondes), **jamais le contenu**. Aucune
empreinte de provenance des packets n’est prétendue. `latest_file_modified_at_utc`
est un mtime, pas `last_packet` ni un heartbeat ; futur/non représentable :
INVALID_METADATA sans compteurs partiels. Un fichier peut changer après capture.

## Contrat fermé 1.0.0

`StorageSnapshot`, domain `storage`, autorité `FILESYSTEM_METADATA_OBSERVATION`,
mode READ_ONLY, category DECISION_PACKET_LOGS, scope DIRECT_CHILDREN_PATTERN.

| Champs | Contrainte |
|---|---|
| schema_version/product/domain/authority/mode/category/scope/pattern | littéraux fermés |
| generated_at_utc/observed_at_utc | ISO UTC Z explicite, observation ≤ génération |
| source_status | PRESENT/NOT_CONFIGURED/MISSING/READ_ERROR/INVALID_PATH/OUTPUT_LIMIT/SOURCE_CHANGED/INVALID_METADATA |
| entries_observed | entier sûr JS, 0–10 000, toute entrée examinée |
| matched_file_count | entier sûr JS, ≤ entries_observed |
| total_bytes | entier sûr JS non négatif, volume logique exact |
| latest_file_modified_at_utc | UTC explicite ≤ observation, null seulement si aucun fichier |
| inventory_sha256 | SHA-256 hexadécimal 64 caractères |

Si source non PRESENT : les cinq champs de métadonnées sont **null**, jamais
zéro. PRESENT avec zéro fichier impose total_bytes=0 et dernier mtime=null.
Un fichier vide reste un fichier connu avec 0 octets. Aucun champ supplémentaire,
float/bool substitué à un compteur ou sévérité de santé dérivée.

Capture CLI passive → artifact atomique isolé → reader borné/strict → GET
`/api/operator/v1/storage` → carte `/paper-live/system`. Aucun module Advisor,
PPL/FIN, moteur marché, dashboard historique ou filesystem scan dans l’API.
`STORAGE_SNAPSHOT_PATH` choisit seulement l’artifact transport (défaut
`databases/storage_snapshot.json`). Lecture artifact régulière sans symlink,
16 KiB maximum ; duplicats JSON et constantes non finies rejetés. Écriture
atomique même dossier, fsync ; destination dans le répertoire source interdite.

```bash
python -m observability.storage_snapshot \
  --out /tmp/operator-artifacts/storage_snapshot.json \
  --source-directory /tmp/decision-packet-fixture \
  --generated-at-utc 2027-01-15T08:06:40Z
```

Cette commande illustre une capture de fixtures autorisées ; aucune sélection
de sources Machine réelle ou tâche/runtime ajoutée par cette mission.

## API, UX et admission

GET valide : 200 + snapshot_age_s (âge de l’observation) et classification
FRESH/STALE, seuil 90 s. Cette fraîcheur ne certifie jamais l’activité Advisor.
Artifact absent/invalide/futur : 503, code fermé STORAGE_MISSING,
STORAGE_INVALID_ARTIFACT, STORAGE_INVALID_SCHEMA ou STORAGE_FUTURE_TIMESTAMP.
POST/PUT/PATCH/DELETE : 405 ; aucune commande de purge/nettoyage.

Carte indépendante de l’Advisor et du service host ; absent, source invalide,
capture vide et STALE distincts. Valeurs exactes, provenance repliable et limites
visibles ; STALE décrit l’observation historique. Lecture GET commune avec Events,
sérialisée, timeout réponse/JSON 10 s, abort à la fermeture. Erreur/timeout retire
les anciens chiffres ; aucun fallback sur /healthz ou l’ancien dashboard.

Tests Python/API/TS avec vrai producteur de fixtures, permissions, symlinks,
bornes, changement concurrent, atomicité, source préservée, schéma/future dates,
GET-only, independence/timeout et captures 1440/390. Les captures synthétiques
ne prouvent pas un volume réel ni une publication Machine.

Ménage source : MOVE du script `capture_app_events_visual.mjs` vers
`capture_app_passive_visual.mjs`, étendu aux deux surfaces ; consommateur CI
cross-stack mis à jour et recherche de références actives à l’ancien chemin
vide. KEEP des contrats/vues Events, lecture HTTP INTEGRATE dans un helper
commun testé. Aucun script runtime, source métier ou preuve historique retiré.

Rollback : revert source de la PR. Aucun déploiement/systemd/restart, changement
burn-in/PPL/FIN/epoch/config/risk/sizing/Watchdog/exchange. CryptoRadar et ses
consommateurs restent inchangés ; sa parité globale et son retrait non certifiés.
