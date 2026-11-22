# Revue d'installation pilote — Repository Cartographer (#599)

Statut : **revue et préparation documentaire uniquement**. Rien n'a été installé, créé ou modifié sur
le VPS : ni verrou, ni dossier, ni compte, ni groupe, ni permission, ni service ; le cartographe n'a pas
été lancé. Registre `NOT_WIRED`. Campagne de sept jours non démarrée.
Procédure ordonnée : [`CARTOGRAPHER_INSTALL_PROCEDURE.md`](CARTOGRAPHER_INSTALL_PROCEDURE.md).

## 1. SHA audité

- HEAD de #599 vérifié au début de la revue : `57b4ee005fa4e1ec34edb9bc73747949b2d602e9` (= référence annoncée).
- Ce dossier est ajouté par un commit **documentaire** au-dessus (`docs/agents/observation/` seulement) :
  code exécuté, tests et frontend identiques à `57b4ee00`. Le SHA retenu pour l'installation est le HEAD
  qui contient ce dossier (noté `<SHA_RETENU>` ; voir la PR).
- Base #598 (`52db9887`) inchangée.

## 2. Relecture des corrections

| Ancien défaut | Correction observée (code) | Test associé | Résultat disponible | Limite restante |
|---|---|---|---|---|
| Verrou par `rename`, reprise concurrente non sûre | `executor.RunnerLock` : `flock(LOCK_EX\|LOCK_NB)`, fichier jamais supprimé, libération noyau à la mort (même `SIGKILL`) | `test_two_concurrent_processes_only_one_runs`, `test_hard_kill_then_two_simultaneous_resumptions`, `test_lock_file_is_never_deleted` | vert, 5 répétitions ; vrais processus | `flock` local : ne vaut pas sur NFS (ici ext4 `/dev/root`, vérifié) |
| Bail valide = « en cours » sans processus | `invocation_reader.read_lock` : FLOCK WRITE tenu sur l'inode d'après `/proc/locks` **et** détenteur = PID déclaré | `test_stopped_process_releases_lock_and_is_not_en_cours`, `test_valid_lock_held_by_live_process_is_en_cours_bounded` | vert ; répété en local sous deux comptes distincts | vert réel non encore observé dans l'API servie (§3, niveau 3) |
| Réutilisation de PID | PID déclaré doit **détenir** le verrou ; un PID réutilisé ne le détient pas | `test_pid_reuse_cannot_fake_activity` | vert | un processus qui hériterait du fd de verrou (fork) serait vu détenteur ; l'exécuteur ne forke que `git` (fd `O_CLOEXEC`) |
| Identité de verrou non vérifiée | `validate_lock` : schéma fermé, agent/runner/mission, id 32 hex, chronologie, bail ≤ 600 s | `test_lock_held_but_invalid_is_never_en_cours` (9 cas) | vert | — |
| Cohérence code / sources / profil / mission / rapport | `verify_checkout` (HEAD = `code_sha`, blobs du périmètre au SHA analysé, profil, modules exécutés au `code_sha`) ; `validate_envelope` compare enveloppe ↔ rapport ↔ identité attendue | `test_valid_run_records_distinct_code_and_scope_verification`, `test_resealed_report_inconsistent_with_envelope_is_invalid`, `test_executed_code_not_matching_declared_reference_is_refused`, `test_expected_profile_blob_is_enforced` | vert ; **exécution réelle** de la mission de zone sur un checkout propre de `57b4ee00` : `COMPLETED`/`PARTIAL`, `content_sha256` `67bdcc05…` (= attendu de campagne) | les modules exécutés vérifiés sont ceux d'`agent_bench.observation` ; la bibliothèque standard de l'interpréteur n'est pas vérifiée |
| Git ou références invérifiables acceptés | refus `GIT_UNAVAILABLE`, `HEAD_UNVERIFIABLE`, `ANALYSED_SHA_UNAVAILABLE`, `CHECKOUT_MODIFIED`, `CODE_MISMATCH` avant exécution | `test_git_unavailable_is_refused`, `test_checkout_without_git_is_refused`, `test_modified_scope_file_is_refused`, `test_head_different_…` | vert ; `safe.directory` par variable d'environnement **vérifié sur le git 2.34.1 du VPS** (lecture `rev-parse` du checkout root existant) | — |
| Voyant figé, délais réseau, réponses désordonnées | serveur : `display` + `valid_until_utc` ; UI : validation runtime, échéance locale, 1 requête en vol, abandon 10 s, rejet des réponses obsolètes | `invocationEvidence.test.tsx` (37), `test_invalid_proof_with_live_lock_is_gray` | vert ; navigateur : vert → gris à 41 s serveur bloqué ; échéance seule : gris à 90 s | refus de date future compare horloges serveur/navigateur (tolérance 60 s) |
| Publication écrasante, partielle ou silencieuse | `.partial` `O_EXCL` + `fsync` → `os.link` (`NAME_EXISTS`) → `fsync` dossier ; `O_NOFOLLOW` à chaque niveau ; `PUBLICATION_FAILED` (code 4) | `test_existing_name_is_preserved`, `test_publication_failure_is_explicit_…`, `test_parent_symlink_…`, `test_partial_file_is_ignored_then_cleaned` | vert | — |
| Énumération non bornée | `scandir` arrêté à 200 entrées, refus explicite (lecteur et exécuteur) | `test_directory_enumeration_is_really_bounded`, `test_executor_refuses_an_unbounded_reports_directory` | vert | > 200 invocations par mission → refus : très au-delà d'une campagne d'une invocation/jour |
| Lecteur exigeant le listage de la racine | `O_PATH` pour la racine et les niveaux intermédiaires | `test_reader_needs_only_traverse_right_on_reports_root` | vert sous compte non root | — |
| Retour arrière | procédure : retrait des drop-ins, accès ajoutés retirés, rapports conservés | — (procédure) | non exécuté | à exécuter seulement si un contrôle échoue |

Versions Python : `tests/agent_bench` 136 passés / 1 sauté sous 3.10, 3.11 et 3.13 (la 3.10 est
l'interpréteur système du VPS prévu pour le runner).

### Tests compensant le pilote historique

`test_pilot_on_frozen_scope_reproduces_committed_report` et
`test_pilot_on_current_scope_differs_only_by_reviewed_changes` exigent le commit `857404f8` :

- **En CI : exclusion signalée, non résolue.** Le job `tests` fait `actions/checkout@v4` sans
  `fetch-depth` (profondeur 1) : les deux tests se sautent avec le motif « commit pilote … absent du
  clone (historique superficiel) ». La CI de #599 elle-même n'exécute pas ce job (PR empilée).
- **Proposition pour les rendre obligatoires** (non appliquée, changement source distinct à décider) :
  1. dans `ci.yml`, avant `pytest`, `git fetch --no-tags --depth=1 origin 857404f8ebfbcf9df4a3f36052ab5357ea9b8d7b` ;
  2. une variable `CAT_REQUIRE_PILOT_COMMIT=1` posée dans ce job transforme le saut en échec.
- **D'ici là, contrôle obligatoire à l'installation** : la procédure (étape 1) exécute les deux tests sur
  le clone complet du VPS ; un saut y est un échec de précondition.

## 3. Constats VPS (lecture seule, 2026-11-22 ~04:10Z, compte `lecanada26`, sans sudo)

Trois niveaux de preuve distingués : **N1** session shell ; **N2** compte Unix de l'API ; **N3**
contexte d'isolation réel du service. La session shell *est* `lecanada26` (UID 1001) : N1 et N2
coïncident pour l'identité, mais **pas** pour les groupes (le shell a en plus 1001 `google-sudoers`)
ni pour l'isolation.

| Fait | Valeur | Niveau |
|---|---|---|
| Unité API | `crypto-operator-api.service`, actif depuis 2026-11-20 08:54Z, 0 redémarrage | N1 (`systemctl show`) |
| Processus | PID 1658422, UID/GID 1001/1002, groupes 4 20 24 25 29 30 44 46 118 119 1000 1002, CapEff 0, NoNewPrivs 1, seccomp actif (16 filtres) | N3 partiel (`/proc/<pid>/status`) |
| Release API exécutée | `/home/lecanada26/crypto-install/releases/85376c5e7725c9fa45f8d05fb0051f25a127aba4` (cwd du processus ; `git rev-parse` = ce SHA ; arbre propre) ; venv CPython 3.11.17 | N1 + cwd N3 |
| Contenu | **pas d'`agent_bench`** dans cette release : la route ne peut pas y être servie telle quelle | N1 |
| Isolation API | `ProtectSystem=strict`, `ProtectHome=tmpfs`, `PrivateTmp`, `PrivateDevices`, `ProtectProc=default`, `ProcSubset=all`, `SupplementaryGroups=` vide, `IPAddressAllow=localhost` ; systemd 249 (pas de `PrivatePIDs`) | N1 (`systemctl show`) |
| Espaces de noms | mnt propre au service ; **pid, user, net partagés** avec l'hôte | N3 (`/proc/<pid>/ns`) |
| Vue de `/srv` par le service | `/` monté `ro` ; `/srv/cat-obs` présent, même périphérique (`801`) et inode (4180531) que l'hôte | N3 partiel (`/proc/<pid>/root`, mes identifiants) |
| `/proc` du service | procfs `rw,nosuid,nodev,noexec`, sans `hidepid` ; `/proc/<pid>/root/proc/locks` lisible ; format `08:01:<inode>` = `st_dev` 0x801 | N3 partiel |
| `/srv/cat-obs` | `root:root 0755` ; `checkout/` `root:root 0755` contenant `52db9887…` (répétition #598, `dr-xr-xr-x root`) ; `reports/` `cat-obs-ro:cat-obs-ro 0750`, illisible pour `lecanada26` ; `runs/`, `locks/` non observables (absents d'après Mathieu) | N1 |
| ACL | aucun attribut étendu sur `/srv/cat-obs`, `reports`, `checkout` ; **`getfacl`/`setfacl` non installés** | N1 |
| Compte runner | `cat-obs-ro` 996:996, groupes {996}, shell `nologin`, pas de home | N1 |
| Outils | git 2.34.1 ; `/usr/bin/python3` = 3.10.12 ; node 24.22.2 ; 2 vCPU, 16 Go | N1 |
| Frontend servi | `crypto-operator-web.service` (PID 1772807, `lecanada26`), serveur de `CAT-FOOTPRINT-FINANCE-V6-RC1/frontend`, `dist` remplacé par bind `ro` de `/opt/cat-app/releases/CAT-SYSTEM-AGENTS-597-857404f8/dist` (vu dans `/proc/1772807/mountinfo`) ; proxy `GET /api/*` → `127.0.0.1:8090` | N1 + N3 partiel |
| Empreinte du `dist` servi | 12 fichiers, manifeste `55a0eedf…` = **build local de `857404f8` à l'identique** | N1 + local |
| Session PAPER | `ExecStartPre` `CAT-paper-session.py` : ne crée une session que si `/run/cat/current` manque ; `RuntimeDirectoryPreserve=yes` ; `current` → `PAPER-1582…` | N1 |
| Unités/timers cartographe | aucun | N1 |

**Ce qui manque pour N3 complet.** Mes lectures via `/proc/1658422/root` se font avec les
identifiants de ma session, hors seccomp et avec un groupe en plus : elles montrent que le chemin, le
périphérique et `/proc/locks` sont visibles **dans l'espace de montage du service**, pas que le
processus API peut les lire. N3 n'est démontrable sans modifier le service qu'**après** l'installation,
par la route elle-même (code exécuté dans le service) : étape 4 de la procédure (`ABSENT` attendu, puis
`/proc/locks` exercé dès qu'un fichier de verrou existe : motif « aucun processus ne détient le verrou »
et non « /proc/locks illisible »).

**Anomalie préexistante signalée, non corrigée** : l'environnement effectif de l'API garde
`PYTHONPATH=…/releases/1da73768…` (drop-in 538), chemin non monté dans le service ; sans effet
(`sys.path[0]` = répertoire de travail). Non modifié par ce pilote.

## 4. Configuration proposée (unique)

| Élément | Choix | Justification |
|---|---|---|
| Runner | `cat-obs-ro` (996) inchangé, aucun groupe ajouté | existe, sans shell ; seul compte à écrire dans `reports/` |
| Compte API | `lecanada26` **inchangé** | l'accès passe par l'unité, pas par le compte |
| Lecture | nouveau groupe système **`cat-obs-read`, sans membre** ; donné au **seul service API** par `SupplementaryGroups=cat-obs-read` | ACL impossibles sans installer `acl` ; le groupe sur l'unité n'élargit ni le compte ni les autres services ; le redémarrage API est de toute façon requis pour la release |
| Python runner | `/usr/bin/python3.10` (3.10.12, bibliothèque standard seule) | lisible par `cat-obs-ro` ; la CPython 3.11 est sous `/home/lecanada26` (0750) : y donner accès élargirait le runner ; suite verte sous 3.10 |
| Checkout runner | `/srv/cat-obs/checkout/<SHA_RETENU>`, clone **complet** (contient `e387318e`), détaché, `root:root`, dossiers 0555 / fichiers 0444 | immuable pour le runner ; même modèle que `52db9887` (conservé) |
| Point d'entrée | `python3.10 -m agent_bench.observation.executor` | CLI testée (codes 0/2/3/4) |
| Release API | **`85376c5e` + correctif minimal** de 7 fichiers (`agent_bench/__init__.py`, `agent_bench/observation/{__init__,contract,invocation,invocation_reader}.py`, `observability/operator_api/agent_invocation_reader.py`, route ajoutée dans `app.py`), arbre attendu **`c1ecc3b436e8a9617004ca0c8f142ec9e7ff7012`**, correctif [`pilot/api-85376c5e-agent-invocation.patch`](pilot/api-85376c5e-agent-invocation.patch) (sha256 `6a73ea3b…41fc`) | n'embarque **pas** les 385 autres fichiers changés depuis `85376c5e` (dont la route BBO non déployée) ; tests API existants : **mêmes 10 échecs préexistants** (`test_operator_snapshot_builder`) qu'à `85376c5e`, 364 passés ; route servie sur un vrai rapport : `AVAILABLE/TERMINE/RED`, chemin non exposé, cible inconnue 404 |
| venv API | celui de `85376c5e` réutilisé (aucune dépendance nouvelle ; aucun `.pth` pointant vers une release) | évite une reconstruction réseau |
| Release frontend | build de `<SHA_RETENU>` avec `VITE_CARTOGRAPHER_INVOCATION=1` ; diff frontend cumulé depuis `857404f8` = **#599 seulement** (10 fichiers dont tests/harnais) ; manifeste local attendu `2d59c533…` (12 fichiers ; seuls le JS, le CSS et `index.html` diffèrent de `55a0eedf…`) | même base que la release servie, vérifiée à l'identique |
| Registre | `NOT_WIRED` | voyant du profil gris ; seule la carte de preuve montre l'état |

### Matrice des permissions

| Chemin | Propriétaire:groupe | Mode | Runner `cat-obs-ro` | Service API (`lecanada26` + `cat-obs-read`) |
|---|---|---|---|---|
| `/srv/cat-obs` | root:root | 0755 (inchangé) | traverse | traverse |
| `/srv/cat-obs/checkout/<SHA_RETENU>/**` | root:root | 0555 / 0444 | lecture | lecture (inutile) |
| `/srv/cat-obs/reports` | cat-obs-ro:**cat-obs-read** | **0710** (au lieu de 0750) | lecture/écriture | **traverse seulement** (pas de listage) |
| `reports/runs`, `reports/locks` | cat-obs-ro:cat-obs-read | **2750** (setgid) | lecture/écriture | lecture |
| `runs/<mission_id>/` (créé par l'exécuteur) | cat-obs-ro:cat-obs-read (hérité) | 2750 (0750 demandé, setgid hérité) | lecture/écriture | lecture |
| enveloppes `runs/<mission_id>/*.json`, `locks/<runner>.lock` | cat-obs-ro:cat-obs-read (hérité) | **0640** (mode explicite de l'exécuteur, `UMask=0027`) | lecture/écriture | **lecture seule** |
| `.<nom>.partial` (transitoire) | idem | 0640 | écriture | ignoré par le lecteur |

Le runner n'obtient aucun droit sur les données d'autres composants : écriture limitée à
`/srv/cat-obs/reports` (`ReadWritePaths`), réseau coupé, `ProtectHome=yes`.

### Commande d'invocation (ponctuelle, manuelle)

```
sudo systemd-run --unit=cat-obs-cartographer-$(date -u +%Y%m%dT%H%M%SZ) --wait --collect --pipe \
  --uid=cat-obs-ro --gid=cat-obs-ro \
  -p WorkingDirectory=/srv/cat-obs/checkout/<SHA_RETENU> \
  -p Environment=PYTHONDONTWRITEBYTECODE=1 -p Environment=HOME=/nonexistent -p Environment=LC_ALL=C -p UMask=0027 \
  -p PrivateNetwork=yes -p IPAddressDeny=any -p RestrictAddressFamilies=AF_UNIX \
  -p ProtectSystem=strict -p ReadWritePaths=/srv/cat-obs/reports -p ProtectHome=yes \
  -p PrivateTmp=yes -p PrivateDevices=yes -p ProtectProc=invisible -p NoNewPrivileges=yes \
  -p CapabilityBoundingSet= -p ProtectKernelTunables=yes -p ProtectKernelModules=yes \
  -p ProtectControlGroups=yes -p RestrictSUIDSGID=yes -p LockPersonality=yes \
  -p MemoryMax=1G -p TasksMax=16 -p CPUQuota=100% -p RuntimeMaxSec=180 \
  /usr/bin/python3.10 -m agent_bench.observation.executor \
    --mission docs/agents/observation/examples/cartographer_zone_mission.json \
    --checkout /srv/cat-obs/checkout/<SHA_RETENU> \
    --reports /srv/cat-obs/reports \
    --runner-id obs-repo-cartographer-ro-01 \
    --code-sha <SHA_RETENU> \
    --analysed-sha e387318eeaed81d4e6dc90228d46943a65a5b73c
```

`RestrictSUIDSGID=yes` interdit de *poser* un bit setgid, pas d'en hériter : à confirmer à l'étape 5
(mode `2750` de `runs/<mission_id>`). Bornes internes non modifiables par argument : 120 s, 30 fichiers,
bail 600 s, `RLIMIT_AS` 1 Gio.

## 5. Contrôles restant après installation

1. **N3 réel** : réponse de la route dans le service (`ABSENT`, puis motif « aucun processus ne détient
   le verrou » après invocation, preuve que `/proc/locks` est lu dans le contexte réel).
2. **Vert réel** : non démontrable de façon déterministe au pilote (invocation ≈ 1 s) ; lecture en boucle
   pendant l'invocation, au mieux ; sinon reporté à la campagne. Jamais simulé par un faux verrou.
3. Héritage setgid malgré `RestrictSUIDSGID=yes` ; mode 0640 et groupe des fichiers produits.
4. Non-régression : routes API identiques + 1, codes de réponse inchangés, session PAPER inchangée, vues web.
5. CI : rendre obligatoires les deux tests pilote (§2) — décision source distincte.

## 6. Verdict

**Prêt pour décision d'installation pilote**, sous réserve des préconditions vérifiées à l'étape 1 de la
procédure (SHA, tests pilote sur clone complet, tests sous Python 3.10.12 de l'hôte). Aucun blocage
identifié ; deux points restent ouverts et sont contrôlés dans la procédure : N3 réel et vert réel.
