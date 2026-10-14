# Plan de gate — publishers passifs runtime-service, storage et event-center
Statut : **source pour revue, rien d'installé ni d'exécuté**. #286 reste actif ; les gates ci-dessous sont des demandes distinctes. Fusionner ce document ne déploie rien.
Base : main@452a630, API servie = release `1728b3ad952b87d903ccb7442579000da292b848`. Observations VPS du 2026-10-14 19:13–19:40Z (lecture seule, `chatgpt-ro`).

## 1. Constat qui motive le plan
`GET /runtime-service`, `/storage`, `/events` répondent 503 `*_MISSING` : le fichier est absent à l'emplacement lu par l'API. Aucun timer/service n'existe pour ces trois publishers (seuls market-radar, market-observer, market-horizons sont planifiés). Le chemin lu est correct (unité API = WEB-01F, `WorkingDirectory=/home/mathieu/crypto_ai_terminal`, défauts relatifs `databases/...`).

## 2. Ce que chaque publisher fait réellement (vérifié dans le code et par test)
| | runtime-service | storage | event-center |
|---|---|---|---|
| Module | `observability.runtime_service_snapshot` | `observability.storage_snapshot` | `observability.event_center_snapshot` |
| Entrées lues | **une** commande fixe `/usr/bin/systemctl show --property=<7 propriétés> -- crypto-advisor.service` (timeout 3 s, sortie ≤ 4 096 o, env minimal, `shell=False`) ; preuve de déploiement facultative (absente = `NOT_AVAILABLE/NO_EVIDENCE`) | **métadonnées** des enfants directs de `databases/` : 2 `scandir` + `stat` des seuls `decision_packets_*.jsonl`, plafond 10 000 entrées (au-delà : statut `OUTPUT_LIMIT`). **Aucun fichier de packet n'est ouvert** | lecture bornée (≤ 2 MiB chacune, `O_NOFOLLOW`, régulière, rejet si modifiée pendant la lecture) de `cache/startup/alerts.jsonl` (P12) et de `databases/burn_in_status_snapshot.json` (projection burn-in) ; supervision non configurée |
| Coût mesuré | processus Python + 1 `systemctl show` | **91 ms** pour 9 500 entrées dont 500 packets (banc local) | lecture ≤ 4 MiB au total, parse JSON borné à 10 000 enregistrements |
| Écritures | 1 fichier temporaire `mkstemp` dans le dossier de sortie puis `os.replace` | idem + `fsync` | idem + `fsync` |
| Écriture dans les données burn-in | aucune (testé : arbre source identique octet par octet, mtimes et dossier inclus) | aucune (idem) | aucune (idem) |
| Garde-fou source/sortie | `OUTPUT_SOURCE_COLLISION` | `OUTPUT_WITHIN_SOURCE` | `OUTPUT_IS_SOURCE` |
| Seuil de fraîcheur API | 90 s | 90 s | 90 s (et 90 s par source datée) |
| Cadence retenue | **30 s** : un run manqué reste FRAIS (age ≤ 60 s) | **60 s** : un run manqué passe STALE, honnêtement | **60 s** : idem |
| Échec | exit ≠ 0, **fichier précédent intact** (testé), l'âge croît jusqu'à STALE, jamais de faux FRAIS | idem | idem |

### Qualification « passif »
- **runtime-service** : passif vérifié en source et en test. Réserve hôte : la requête D-Bus sous `PrivateNetwork=true`, à valider en G1.
- **storage** : passif vérifié (pas d'ouverture, pas de verrou, descripteur `O_RDONLY|O_DIRECTORY`). Réserve : la mise à jour éventuelle de l'`atime` du dossier `databases/` dépend des options de montage (à relever en G0, `relatime` n'écrit qu'une fois par jour).
- **event-center** : lecture seule vérifiée. Réserves : (a) `alerts.jsonl` est un fichier vivant : une modification pendant la lecture donne `INVALID` sur ce run (le suivant corrige) ; (b) au-delà de 2 MiB le statut devient `OUTPUT_LIMIT` en permanence ; (c) la source burn-in n'a aucun producteur planifié, donc `MISSING` tant qu'une gate distincte n'en admet pas un. Aucun de ces états n'est converti en zéro.
- **Découverte reproduite** : un horodatage à la seconde entière rend le snapshot `INVALID_METADATA` dès qu'un packet est modifié dans la même seconde (`latest ≤ observed` exigé). Les units passent un horodatage sous-seconde (`%6N`) ; testé.

## 3. Dossier de sortie, utilisateur, permissions
- Sortie : `/home/mathieu/operator_presentation/` (hors de l'arbre runtime gelé, jamais dans `databases/`). Chemins exacts : `.../runtime_service_snapshot.json`, `.../storage_snapshot.json`, `.../event_center_snapshot.json`.
- Choix et alternative : écrire dans `databases/` (défauts de l'API, sans redémarrage) exigerait un droit d'écriture sur le répertoire des données burn-in : refusé. Un dossier séparé exige que l'API le lise via trois variables (drop-in), donc un redémarrage API (§4, G4, isolé).
- Utilisateur `mathieu` (comme les publishers existants ; un utilisateur dédié exigerait des ACL sur `/home/mathieu`). Durcissement : `ProtectSystem=strict`, `ReadWritePaths` = le seul dossier de sortie, `ProtectHome=read-only`, `PrivateNetwork`, `PrivateTmp`, `CapabilityBoundingSet=` vide, `NoNewPrivileges`, `MemoryMax=128M`, `TasksMax=16`, `Nice=19`, I/O idle, `UMask=0077`. Code exécuté = release déjà en place `staging-src/1728b3ad…` avec son venv : aucune nouvelle copie de code, aucun `git`.
- Prévention du chevauchement : `Type=oneshot` (systemd ne relance pas une unité active), `TimeoutStartSec` 20–30 s, pas de `Restart`, `Persistent=false` (pas de rafale après arrêt). Test de 6 exécutions concurrentes : jamais de fichier partiel ni temporaire.

## 4. Gates proposées (aucune exécutée)
| Gate | Contenu | Exécutant | Critère d'arrêt |
|---|---|---|---|
| **G0** relevés lecture seule | taille et mtime de `cache/startup/alerts.jsonl` ; nombre d'entrées de `databases/` ; `findmnt -no OPTIONS` du montage de `/home` ; espace disque ; lecture de `systemctl cat crypto-advisor.service` (intervalle Advisor) | `mathieu` (le compte `chatgpt-ro` ne traverse pas `/home/mathieu`) | `alerts.jsonl` > 2 MiB, entrées > 10 000, disque insuffisant |
| **G1** préparation | `mkdir -m 0700 /home/mathieu/operator_presentation` ; `systemd-analyze verify` et `systemd-analyze security` des 6 fichiers ; **un** essai manuel de chaque commande vers un dossier temporaire, comparé à la sortie des tests | `mathieu` + root pour `systemd-analyze` | tout écart avec les tests, tout fichier créé hors du dossier temporaire |
| **G2** installation | copie des 6 fichiers dans `/etc/systemd/system/`, `daemon-reload`, **sans** `enable` | root | échec de `verify` |
| **G3** activation des timers | `systemctl enable --now` des 3 timers ; observer ≥ 10 cycles : fichiers valides (validateurs du dépôt), âges < 90 s, aucune unité en échec, PID/NRestarts d'Advisor et de l'API inchangés | root puis `mathieu` | unité en échec répété, charge visible, écart Advisor |
| **G4** bascule API (**seul changement de configuration + redémarrage**) | copier `API_DROPIN_30-presentation-paths.conf` dans `crypto-operator-api.service.d/`, `daemon-reload`, `restart crypto-operator-api.service`. Nécessaire car l'API lit des chemins fixés par variables d'environnement ; sans cela elle continue de lire `databases/` où ces fichiers n'existent pas | root | non-200 attendu sur une des trois routes, Advisor touché |
| **G5** vérification | les neuf routes, codes et métadonnées ; comparaison des âges | `chatgpt-ro` | — |
Advisor n'est jamais redémarré ni reconfiguré. Aucun publisher burn-in, Research, FIN ni market n'est concerné.

## 5. Rollback
1. `systemctl disable --now` des trois timers puis `systemctl stop` des services ; `rm` des 6 fichiers d'unité ; `daemon-reload`.
2. Retirer le drop-in 30 et `restart crypto-operator-api.service` : l'API retrouve ses défauts et répond de nouveau `*_MISSING` (état antérieur, honnête).
3. Les artefacts de sortie sont régénérables et peuvent rester ou être supprimés (`rm -r` du seul dossier dédié). Aucune donnée burn-in, aucun journal, aucun dataset n'est touché à aucun moment.

## 6. Questions ouvertes
1. Intervalle réel d'Advisor (période observée du snapshot ≈ 1 060 s, voir §7) : `systemctl cat crypto-advisor.service`, à nommer.
2. Taille réelle de `alerts.jsonl` et nombre d'entrées de `databases/` (G0).
3. Chemin de l'audit de supervision (`alerts_audit.jsonl`, relatif au processus qui l'écrit) : non configuré dans les units tant qu'il n'est pas prouvé.
4. Producteur de `burn_in_status_snapshot.json` : chantier distinct ; l'événement `ppl_lifecycles` reste `MISSING` jusque-là.
5. `MemoryDenyWriteExecute` et `PrivateNetwork` avec `systemctl` : à valider en G1 sur l'hôte.

## 7. Cadence du snapshot Advisor (hors publishers)
Code : `OperatorSnapshotWriter.maybe_refresh` n'écrit au plus qu'une fois par 30 s (`DEFAULT_MIN_REFRESH_INTERVAL_S`), appelé une fois par cycle d'`advisor_loop` ; le cycle dort `--interval` (défaut 300 s) puis recommence. Période effective = intervalle + durée du cycle. Lectures datées de `/system-health` : cycle 1709 généré 19:14:37Z, cycle 1710 généré 19:32:16Z, soit **1 059 s** ; le cycle précédent (18:56:57Z → 19:14:37Z) avait **1 060 s**. Six lectures espacées de 90 s (19:31:19Z → 19:38:49Z) : le champ `generated_at_utc` saute une fois (19:14:37Z → 19:32:16Z, cycle 1709 → 1710) et l'âge croît ensuite de 90 s par lecture, sans rafraîchissement intermédiaire. Même `process_instance_id`, compteur +1 à chaque fois : un âge de 16,6 min est le milieu d'une période de 17,7 min, **pas une panne**. La cause de la période (intervalle configuré ≈ 1 000 s ou cycles de ≈ 760 s) n'est pas établie.
