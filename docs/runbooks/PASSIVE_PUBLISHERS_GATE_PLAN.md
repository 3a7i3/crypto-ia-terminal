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
| Coût mesuré (banc local) | processus Python + 1 `systemctl show` | **91 ms** pour 9 500 entrées dont 500 packets (le coût réel dépend de G0) | **≈ 0,27–0,36 s** processus compris, pour le pire cas P12 : 10 000 lignes, 1,77 MiB. Budget de lecture **global** : au plus `len(SOURCE_IDS) × (2 MiB + 1 o)` = 3 × 2 MiB ≈ 6 MiB par exécution (la liste des sources est fixe ; ajouter une source change ce chiffre et fait échouer le test qui l'épingle) |
| Écritures | 1 fichier temporaire `mkstemp` dans le dossier de sortie puis `os.replace` | idem + `fsync` | idem + `fsync` |
| Écriture dans les données burn-in | aucune (testé : arbre source identique octet par octet, mtimes et dossier inclus) | aucune (idem) | aucune (idem) |
| Garde-fou source/sortie | `OUTPUT_SOURCE_COLLISION` | `OUTPUT_WITHIN_SOURCE` | `OUTPUT_IS_SOURCE` |
| Seuil de fraîcheur API | 90 s | 90 s | 90 s (et 90 s par source datée) |
| Cadence retenue | **30 s** | **30 s**, *sous réserve de G0* (nombre d'entrées et durée de listage ; sinon allonger, jamais au-delà de ce que 2 × cadence + timeout < 90 s permet) | **30 s** |
| Échec | exit ≠ 0, **fichier précédent intact** (testé), l'âge croît jusqu'à STALE, jamais de faux FRAIS | idem | idem |
| Marge de panne | `TimeoutStartSec=20s` pour les trois ; 2 × 30 s + 20 s = **80 s < 90 s** : un run échoué ou bloqué jusqu'au timeout laisse l'artefact FRAIS ; deux échecs consécutifs le font passer STALE, honnêtement | idem | idem |

### Qualification « passif »
- **runtime-service** : passif vérifié en source et en test. Réserve hôte : la requête D-Bus sous `PrivateNetwork=true`, à valider en G1.
- **storage** : passif vérifié (pas d'ouverture, pas de verrou, descripteur `O_RDONLY|O_DIRECTORY`). Réserve : la mise à jour éventuelle de l'`atime` du dossier `databases/` dépend des options de montage (à relever en G0, `relatime` n'écrit qu'une fois par jour).
- **event-center** : lecture seule vérifiée. Réserves : (a) `alerts.jsonl` est un fichier vivant : une modification pendant la lecture donne `INVALID` sur ce run (le suivant corrige) ; (b) au-delà de 2 MiB la source P12 devient `OUTPUT_LIMIT` (voir « Limite 2 MiB » ci-dessous) ; (c) la source burn-in n'a aucun producteur planifié, donc `MISSING` tant qu'une gate distincte n'en admet pas un. Aucun de ces états n'est converti en zéro.
- **Limite 2 MiB et lecture bornée (`alerts.jsonl`)** : G0 a mesuré `alerts.jsonl` à 2 013 413 o (96 % du plafond). En contrat 1.0.0 la source P12 passerait en `OUTPUT_LIMIT` durablement (aucun enregistrement ni compteur publié). **Lecture bornée préparée en source (contrat 1.1.0, `docs/contracts/APP_EVENTS_01_CONTRACT.md`)** : au-delà de 2 MiB ou de 10 000 lignes, la source JSONL devient `PARTIAL_TAIL` : fin du journal seulement (1 MiB, coupé sur un début de ligne), `coverage`/`source_bytes`/`window_bytes` explicites, enregistrements antérieurs inconnus et non comptés, jamais `PRESENT`. Fichier modifié pendant la lecture, fenêtre sans ligne complète ou dernière ligne non terminée : `INVALID`, sans ligne partielle. Les autres sources restent publiées (testé). Le nombre de lignes de `alerts.jsonl` est inconnu (G0 n'a relevé que les octets) : sous ~201 o/ligne il dépasse déjà 10 000 lignes, cas que seule la lecture bornée traite sans `OUTPUT_LIMIT`. Une API/un frontend/un publisher 1.0.0 déployés ne lisent pas 1.1.0 : la lecture bornée exige une release commune, hors de ce plan source.
- **Source burn-in absente** : `ppl_lifecycles` reste `MISSING` et n'empêche pas la publication des autres sources (testé). Elle ne devient jamais un zéro ni une liste vide.
- **Course avec les écritures (horodatage)** : l'horodatage sous-seconde est pris **avant** le balayage. Une écriture entre l'horodatage et le balayage est détectée (mtime > observé → `INVALID_METADATA`, ou `FUTURE_*` côté events), jamais acceptée silencieusement (testé). `observed_at` est donc une borne **inférieure** : « rien de plus récent que cet instant n'a été accepté ». La précision sous-seconde réduit la fenêtre d'échec (donc les instantanés INVALID spurieux) sans supprimer la course ; l'échec est visible et le run suivant (30 s) corrige. Supprimer la course exigerait d'horodater après le balayage, donc une nouvelle version du code publié : hors de ce plan.
- **Découverte reproduite** : un horodatage à la seconde entière rend le snapshot `INVALID_METADATA` dès qu'un packet est modifié dans la même seconde (`latest ≤ observed` exigé). Les units passent un horodatage sous-seconde (`%6N`) ; testé.

## 3. Dossier de sortie, utilisateur, permissions
- Sortie : `/home/mathieu/operator_presentation/` (hors de l'arbre runtime gelé, jamais dans `databases/`). Chemins exacts : `.../runtime_service_snapshot.json`, `.../storage_snapshot.json`, `.../event_center_snapshot.json`.
- Choix et alternative : écrire dans `databases/` (défauts de l'API, sans redémarrage) exigerait un droit d'écriture sur le répertoire des données burn-in : refusé. Un dossier séparé exige que l'API le lise via trois variables (drop-in), donc un redémarrage API (§4, G4, isolé).
- Utilisateur `mathieu` (comme les publishers existants ; un utilisateur dédié exigerait des ACL sur `/home/mathieu`). Durcissement : `ProtectSystem=strict`, `ReadWritePaths` = le seul dossier de sortie, `ProtectHome=read-only`, `PrivateNetwork`, `PrivateTmp`, `CapabilityBoundingSet=` vide, `NoNewPrivileges`, `MemoryMax=128M`, `TasksMax=16`, `Nice=19`, I/O idle, `UMask=0077`. Code exécuté = release déjà en place `staging-src/1728b3ad…` avec son venv : aucune nouvelle copie de code, aucun `git`.
- Prévention du chevauchement : `Type=oneshot` (systemd ne relance pas une unité active), `TimeoutStartSec` 20–30 s, pas de `Restart`, `Persistent=false` (pas de rafale après arrêt). Test de 6 exécutions concurrentes : jamais de fichier partiel ni temporaire.

## 4. Gates proposées (aucune exécutée)
| Gate | Contenu | Exécutant | Critère d'arrêt |
|---|---|---|---|
| **G0** relevés lecture seule | exécution de `deploy/passive_publishers/g0_readonly_checks.sh` (stat, listages bornés à 1–2 niveaux, `findmnt`, `df`, aucun fichier de donnée ouvert ; **un seul** parcours de `databases/` borné à 10 000 entrées (au-delà : `INCOMPLETE`, compteurs = bornes basses, aucune troncature par `head`), statut et timeout de chaque commande conservés (jamais de résultat partiel présenté comme complet), durée du parcours distinguée du coût du publisher (celui-ci n'est mesuré qu'en G1) ; `G0B=1` ajoute la lecture de trois champs de `live_snapshot.json`, ≤ 1 MiB) : taille et mtime de `alerts.jsonl`, nombre d'entrées de `databases/` et temps de listage, montage, espace, droits du futur dossier de sortie | `mathieu` (le compte `chatgpt-ro` ne traverse pas `/home/mathieu`) | `alerts.jsonl` > 2 MiB, entrées > 10 000, disque insuffisant |
| **G1** préparation | **G1-a** (`docs/runbooks/PASSIVE_PUBLISHERS_G1_REVIEW.md`, aucune écriture persistante) : `verify` et `security --offline` sur une copie temporaire des 6 fichiers ; mesure du coût réel de chaque publisher (5 exécutions vers un dossier temporaire, validées par les validateurs du dépôt) ; nettoyage vérifié. **G1-b** : le seul `mkdir -m 0700` du dossier de sortie, séparé et reporté à G2 | `mathieu` + root pour `systemd-analyze` | tout écart avec les tests, tout fichier créé hors du dossier temporaire |
| **G2** installation inactive | **Remplacé par [PASSIVE_PUBLISHERS_G2_G5_PLAN.md](PASSIVE_PUBLISHERS_G2_G5_PLAN.md) après G1 (résultats : [G1_RESULTS](PASSIVE_PUBLISHERS_G1_RESULTS.md)).** Nouvelle numérotation : G2 = installation inactive (unités + dossier de sortie, aucun enable/start) ; G3 = essais ponctuels sous systemd, un publisher à la fois, timers désactivés ; G4 = drop-in API à deux variables + redémarrage de l'API seule ; G5 = timers + observation. Périmètre runtime-service et storage ; events séparé (options A/B) | opérateur, root | voir le plan |

**Résultats G0 (Mathieu, 2026-10-14)** : parcours `databases/` COMPLETE, 49 entrées, 8 packets, 380 366 419 o, 0,012 s ; aucune contrainte de volume pour le listage, donc **cadence storage 30 s retenue** (le coût réel du publisher reste à mesurer en G1). `burn_in_status_snapshot.json` reste `MISSING` : aucune source de substitution. Les deux audits anciens ne sont pas sélectionnés automatiquement (pas de découverte dans le publisher ; `supervision_alerts` reste `NOT_CONFIGURED`).

Advisor n'est jamais redémarré ni reconfiguré. Aucun publisher burn-in, Research, FIN ni market n'est concerné.

## 5. Rollback
(Historique : cette section décrit l'ancien découpage G2–G5 ; le rollback par gate, qui ne supprime que ce que la gate a créé, est dans [PASSIVE_PUBLISHERS_G2_G5_PLAN.md](PASSIVE_PUBLISHERS_G2_G5_PLAN.md).)
1. `systemctl disable --now` des trois timers puis `systemctl stop` des services ; `rm` des 6 fichiers d'unité ; `daemon-reload`.
2. Retirer le drop-in 30 et `restart crypto-operator-api.service` : l'API retrouve ses défauts et répond de nouveau `*_MISSING` (état antérieur, honnête).
3. Les artefacts de sortie sont régénérables et peuvent rester ou être supprimés (`rm -r` du seul dossier dédié). Aucune donnée burn-in, aucun journal, aucun dataset n'est touché à aucun moment.

## 6. Questions ouvertes
1. Durée de traitement du cycle Advisor : lecture de `cycle_duration_ms` (G0-b). Intervalle configuré = 300 s (défaut de l unité), voir §7.
2. Taille réelle de `alerts.jsonl` et nombre d'entrées de `databases/` (G0).
3. Chemin de l'audit de supervision (`alerts_audit.jsonl`, relatif au processus qui l'écrit) : non configuré dans les units tant qu'il n'est pas prouvé.
4. Producteur de `burn_in_status_snapshot.json` : chantier distinct ; l'événement `ppl_lifecycles` reste `MISSING` jusque-là.
5. `MemoryDenyWriteExecute` et `PrivateNetwork` avec `systemctl` : à valider en G1 sur l'hôte.

## 7. Cadence du snapshot Advisor (hors publishers)
**Intervalle configuré** (unité lue, valeurs sensibles masquées) : `ExecStart=… core/advisor_loop.py` **sans** `--interval`, donc défaut de **300 s** ; MainPID 882633 démarré le 2026-09-27 03:03:57 UTC, NRestarts 0. Les `EnvironmentFile` (drop-ins `90-ppl-02e-authority.conf`, `95-burn-in-admission.conf`) n'ont pas été lus : une surcharge par variable d'environnement ne peut pas être exclue.
**Code** : `OperatorSnapshotWriter.maybe_refresh` n'écrit au plus qu'une fois par 30 s, appelé une fois par cycle ; le cycle dort l'intervalle puis recommence. Période effective = intervalle + durée de traitement.
**Observé** (lectures datées de `/system-health`) : cycle 1709 généré 19:14:37Z, cycle 1710 à 19:32:16Z, soit **1 059 s** ; le cycle précédent avait **1 060 s**. Même `process_instance_id`, compteur +1.
**Inférence, non mesure** : 1 059 s − 300 s ≈ **759 s** de traitement par cycle si l'intervalle est bien 300 s. Cette durée est un reste calculé, pas une mesure. La mesure directe est `cycle_duration_ms` dans `databases/live_snapshot.json` (G0-b, lecture de trois champs). Tant qu'elle n'est pas lue, la période de 17,7 min n'est **ni qualifiée de normale ni de panne** : elle est cohérente avec un cycle long, et un cycle de ~12,6 min reste à expliquer ou à confirmer.
