# Procédure d'installation — Repository Cartographer (préparée, NON exécutée)

Statut : **à relire, non exécutée**. Rien ici n'autorise une installation, un changement de permissions,
un démarrage de service, l'activation du registre ou la campagne. Chaque étape marquée **[GO]** demande
une autorisation explicite de Mathieu ; les commandes `sudo` sont exécutées par lui.

`<FINAL_SHA>` = SHA final de la PR #599 après revue. Les rapports réels restent sur le VPS.

## 0. Faits hôte (fournis par Mathieu, 2026-11-22) et inconnues

| Élément | Valeur |
|---|---|
| Compte API | `lecanada26`, UID 1001 ; API opérateur active (port 8090) ; web actif |
| Compte runner | `cat-obs-ro`, UID 996, sans shell de connexion |
| Rapports | `/srv/cat-obs/reports`, 0750, `cat-obs-ro:cat-obs-ro` ; `runs/` et `locks/` absents |

À vérifier sur l'hôte avant l'étape 4 (non vérifiable d'ici) : prise en charge des ACL POSIX sur le
système de fichiers de `/srv` ; correspondance `st_dev` ↔ `/proc/locks` (vérifiée à l'étape 6) ; que
l'API et le runner partagent le même espace de PID (pas de `PrivatePIDs=`) ; chemin et unité exacts de
l'API déployée.

## 1. Checkout complet au SHA final [GO]

```
sudo install -d -o root -g cat-obs-ro -m 0750 /srv/cat-obs/checkout
sudo git clone --no-checkout https://github.com/3a7i3/crypto-ia-terminal /srv/cat-obs/checkout/<FINAL_SHA>
sudo git -C /srv/cat-obs/checkout/<FINAL_SHA> checkout --detach <FINAL_SHA>
sudo git -C /srv/cat-obs/checkout/<FINAL_SHA> rev-parse HEAD        # doit afficher <FINAL_SHA>
sudo chown -R root:cat-obs-ro /srv/cat-obs/checkout/<FINAL_SHA>
sudo chmod -R g+rX,g-w,o-rwx /srv/cat-obs/checkout/<FINAL_SHA>
```

Le checkout appartient à root, en lecture seule pour `cat-obs-ro` : le runner ne peut pas modifier le
code qu'il exécute. Pas de `__pycache__` : le lancement utilise `PYTHONDONTWRITEBYTECODE=1`.
Le commit analysé de la mission de zone (`e387318e…`) doit être présent dans ce clone (clone complet).

## 2. Mission

La mission est `docs/agents/observation/examples/cartographer_zone_mission.json` du checkout
(`mission_id` `02e0f78f…`, `analyzed_ref` `e387318e…`). Aucune copie modifiable n'est utilisée.

## 3. Commande de lancement exacte (ponctuelle) [GO]

Une invocation = une commande explicite, unité transitoire isolée, sans timer :

```
sudo systemd-run --unit=cat-obs-cartographer-$(date -u +%Y%m%dT%H%M%SZ) --wait --collect \
  --uid=cat-obs-ro --gid=cat-obs-ro \
  -p WorkingDirectory=/srv/cat-obs/checkout/<FINAL_SHA> \
  -p Environment=PYTHONDONTWRITEBYTECODE=1 -p Environment=HOME=/nonexistent -p UMask=0027 \
  -p PrivateNetwork=yes -p RestrictAddressFamilies=AF_UNIX \
  -p ProtectSystem=strict -p ReadWritePaths=/srv/cat-obs/reports \
  -p ProtectHome=yes -p PrivateTmp=yes -p PrivateDevices=yes -p NoNewPrivileges=yes \
  -p CapabilityBoundingSet= -p ProtectKernelTunables=yes -p ProtectKernelModules=yes \
  -p ProtectControlGroups=yes -p RestrictSUIDSGID=yes -p LockPersonality=yes \
  -p MemoryMax=1G -p TasksMax=16 -p CPUQuota=100% -p RuntimeMaxSec=180 \
  /usr/bin/python3 -m agent_bench.observation.executor \
    --mission docs/agents/observation/examples/cartographer_zone_mission.json \
    --checkout /srv/cat-obs/checkout/<FINAL_SHA> \
    --reports /srv/cat-obs/reports \
    --runner-id obs-repo-cartographer-ro-01 \
    --code-sha <FINAL_SHA> \
    --analysed-sha e387318eeaed81d4e6dc90228d46943a65a5b73c
```

- Pas de `PrivatePIDs=` : le PID inscrit dans le verrou doit être celui que voit l'API dans
  `/proc/locks`, sinon l'activité reste grise (sûr, mais inutile).
- `git` est appelé par l'exécuteur (lecture seule, `safe.directory` limité au checkout).
- Bornes internes non modifiables par argument : 120 s, 30 fichiers, bail 600 s ; `RuntimeMaxSec=180`
  est un filet systemd au-delà.
- Codes de sortie : 0 publié `COMPLETED` · 2 refusé avant exécution · 3 publié non `COMPLETED` ·
  4 échec de publication. La ligne JSON de sortie est dans le journal de l'unité.

## 4. Accès en lecture de l'API, sans accès plus large [GO]

Objectif : `lecanada26` lit `runs/` et `locks/`, rien d'autre, sans écriture, **sans changer ses groupes**
(donc sans redémarrage de l'API pour ce seul droit). Proposition par ACL POSIX :

```
sudo install -d -o cat-obs-ro -g cat-obs-ro -m 0750 /srv/cat-obs/reports/runs /srv/cat-obs/reports/locks
sudo setfacl -m u:lecanada26:--x /srv/cat-obs/reports                  # traverser, ne pas lister
sudo setfacl -m u:lecanada26:r-x  -m d:u:lecanada26:r-x /srv/cat-obs/reports/runs
sudo setfacl -m u:lecanada26:r-x  -m d:u:lecanada26:r-x /srv/cat-obs/reports/locks
getfacl /srv/cat-obs/reports /srv/cat-obs/reports/runs /srv/cat-obs/reports/locks
```

Les fichiers sont créés par l'exécuteur en 0640 (masque ACL `r--`) et les dossiers en 0750 : l'ACL par
défaut donne la lecture seule à `lecanada26`, jamais l'écriture. Le lecteur traverse la racine en
`O_PATH` : le seul droit `x` sur `/srv/cat-obs/reports` suffit (pas de listage). Si `runs/` ou `locks/`
existaient déjà avec du contenu, ajouter `setfacl -R -m u:lecanada26:r-X` sur ces deux dossiers.

Répétition locale (conteneur, deux comptes système distincts `obsro`/`apiro`, mêmes commandes ACL) :
écriture du runner et lecture de l'API vérifiées ; sans `O_PATH`, le lecteur obtenait `ACCESS_DENIED`
(défaut trouvé par cette répétition et corrigé). Ce n'est pas une preuve sur l'hôte. Le lecteur ne prend aucun verrou : la
lecture seule suffit. `/proc/locks` est lisible par tout compte ; à confirmer si l'API tourne avec
`ProtectProc=`/`hidepid` (dans ce cas l'activité restera grise, jamais verte).

Alternative si ACL indisponible : groupe dédié `cat-obs-read` (membre `lecanada26`) avec `runs/`,
`locks/` en 2750 — impose un redémarrage de l'API pour prendre le groupe : à décider séparément.

## 5. Intégration API et frontend en préservant les fonctions déployées [GO distinct]

- **API** : la route et le lecteur sont dans le code source à `<FINAL_SHA>`. Les servir exige une
  nouvelle release de l'API opérateur et son redémarrage : gate runtime distincte, non couverte ici.
  Avant : liste des routes servies (`/openapi.json`) ; après : mêmes routes + la seule route
  `GET /api/operator/v1/agent-invocations/repository-cartographer` ; réponses inchangées sur les routes
  existantes (échantillon comparé). `AGENT_INVOCATION_REPORTS_PATH=/srv/cat-obs/reports`.
- **Frontend** : build avec `VITE_CARTOGRAPHER_INVOCATION=1` seulement après la décision de branchement.
  Le registre reste `NOT_WIRED` (voyant du profil gris) jusqu'à une décision séparée.

## 6. Vérification sous identités réelles, après autorisation

1. `sudo -u cat-obs-ro test -w /srv/cat-obs/reports/runs && echo OK` ;
   `sudo -u cat-obs-ro test -w /srv/cat-obs/checkout/<FINAL_SHA> || echo LECTURE_SEULE_OK`.
2. Lancer l'étape 3 une fois : code 0 ou 3, une ligne `PUBLISHED`.
3. Sous `lecanada26`, lecture passive :
   `python3 -c 'from agent_bench.observation import invocation_reader as r; import json,time; print(json.dumps(r.read_status(__import__("pathlib").Path("/srv/cat-obs/reports"), mission_id="02e0f78f43d1062ee0efed015ad9fe37329dbe480062f02c53e32c82e19fdece", agent_id="repository-cartographer", runner_id="obs-repo-cartographer-ro-01", now_ts=time.time(), expected_profile_blob="dd414cad0c9b73c5106d6593dd603966db14ec83"), indent=1))'`
   (depuis le checkout) → `connection AVAILABLE`, `activity TERMINE`, `display.light RED`.
4. Pendant une invocation (seconde session), même lecture → `EN_COURS`, `life_observed true` ; sinon
   noter le motif (`/proc/locks`, PID, `st_dev`) : gris attendu en cas de doute.
5. `sudo -u lecanada26 touch /srv/cat-obs/reports/runs/x` doit échouer (lecture seule).
6. Aucun flux réseau : `PrivateNetwork=yes` ; vérifier dans le journal de l'unité qu'aucune erreur
   réseau n'est attendue (l'agent n'en fait aucun).

Les sorties de ces vérifications restent sur le VPS ; seul un résumé est rapporté.

## 7. Retour arrière (conserve tous les rapports)

1. Ne plus lancer l'étape 3 (aucun timer n'existe à retirer).
2. API : redéployer la release précédente si l'étape 5 a été faite (gate runtime).
3. Retirer l'accès : `sudo setfacl -x u:lecanada26 /srv/cat-obs/reports` puis
   `sudo setfacl -R -x u:lecanada26 -x d:u:lecanada26 /srv/cat-obs/reports/runs /srv/cat-obs/reports/locks`.
4. Retirer le checkout `/srv/cat-obs/checkout/<FINAL_SHA>` (code seulement).
5. **Conserver** `/srv/cat-obs/reports/` entier (`runs/`, `locks/`, enveloppes) : aucune suppression,
   aucun `rm -rf` (CLAUDE.md §5). Un fichier de verrou restant est inerte (aucun détenteur).
