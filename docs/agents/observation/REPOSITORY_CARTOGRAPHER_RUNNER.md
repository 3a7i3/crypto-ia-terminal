# Runner `repository-cartographer` — fiche d'installation (NON INSTALLÉE)

Statut : **proposition**. Ce lot ne crée ni runner, ni unité systemd, ni utilisateur, ni
répertoire sur le VPS. Aucune commande de ce document n'a été exécutée sur un hôte.
Contrat : [AGENT_OBSERVATION_MISSION_V1](../../contracts/AGENT_OBSERVATION_MISSION_V1.md) §6 bis.
Registre : `runner_id` reste `null`, `wiring_status` reste `NOT_WIRED` (#597).

## 1. Identité du runner

| Élément | Valeur proposée |
|---|---|
| `runner_id` | `obs-repo-cartographer-ro-01` (à enregistrer seulement après décision humaine) |
| Profil | `repository-cartographer`, `.github/agents/repository-cartographer.agent.md`, blob `dd414cad0c9b73c5106d6593dd603966db14ec83` (vérifié à `e387318`) |
| Banc | `repository-cartographer.bench.v1` · entrée `cat.observation.mission.v1` · sortie `cat.observation.report.v1` |
| Utilisateur système | `cat-obs-ro` : sans shell de connexion, sans appartenance aux groupes qui lisent `/opt/cat-app`, les données ou les `.env` |
| Forme d'exécution | commande **ponctuelle**, lancée par mission. Pas de service, pas de timer, pas de cron |

## 2. Permissions de lecture et d'écriture

- **Source** : un checkout git **séparé** du runtime gelé (`116634be…`), à
  `/srv/cat-obs/checkout/<sha>/`, en lecture seule (`chmod -R a-w`, ou bind-mount `ro`). Le SHA
  est celui de `analyzed_ref`.
- **Périmètre** : uniquement `scope.read_paths` de la mission, au plus **30** fichiers, seuls
  les `.py` sont analysés. Refusés : `.env*`, clés, `secrets/`, liens symboliques, chemins hors
  périmètre (contrôlés par `contract.path_violation` et `ScopedReader`).
- **Sortie** : écriture **uniquement** dans `/srv/cat-obs/reports/` (append-only ; un rapport
  n'est jamais écrasé). Aucun droit sur `/opt/cat-app`, `/var/lib/` des services, les JSONL,
  les bases ou les données PAPER/PPL/FIN.
- **Réseau** : aucun. Exécution dans un espace réseau sans route (`unshare -n`) ou règles
  sortantes refusées.
- **Environnement** : `env -i` ; aucun secret, aucune clé d'API, aucun jeton.
- **Privilèges** : aucun `sudo`, aucune capacité Linux.
- **Accès exclus** : API de marché, exchange, VPS en direct, bases de production.

## 3. Preuve d'activité attendue (pour la gate #597)

Une invocation produit un fichier `/srv/cat-obs/reports/runs/<mission_id>/<started_utc>.json` :

```text
runner_id, agent_id, profile.blob_sha1, mission_id, analyzed_ref,
started_utc, ended_utc, exit_code, status (COMPLETE|PARTIAL|BLOCKED|FAILED),
content_sha256, report_sha256, sha256 du script et du checkout, version Python
```

- **Corrélation** : `content_sha256` doit être recalculable par le banc depuis le checkout
  nommé (`bench cartographer --repo-sha <sha>`). Un écart = invocation non probante.
- **Statut Système** : `ACTIF_OBSERVÉ` seulement après une invocation datée et non refusée,
  corrélée à son rapport. `BLOCKED` compte comme invocation refusée, pas comme activité.
  Sans preuve : `NON_ATTESTÉ` (valeur par défaut). Un test vert n'allume rien.
- **Exposition** : une API GET distincte, non créée dans ce lot. Un runner ponctuel n'a pas
  de heartbeat ; cette limite est à trancher par la gate.

## 4. Procédure d'installation (à exécuter seulement après décision humaine)

1. Créer `cat-obs-ro` sans shell ni groupe sensible ; créer `/srv/cat-obs/{checkout,reports}`.
2. Cloner le dépôt au SHA de la mission dans `/srv/cat-obs/checkout/<sha>/`, puis le rendre en lecture seule.
3. Porte : `pytest -q tests/agent_bench` et `bench cartographer-matrix` doivent passer sur ce checkout ; noter leur sortie.
4. Lancer une mission de test : `env -i unshare -n python3 -m agent_bench.observation.bench cartographer --repo-sha <sha> --out /srv/cat-obs/reports/<id>.json`.
5. Vérifier que le fichier de preuve est écrit et que `content_sha256` est recalculé à l'identique.
6. Ne créer ni unité systemd, ni timer, ni cron.

## 5. Procédure de désactivation (retour arrière)

1. Aucune unité ni timer à arrêter. Vérifier : `systemctl list-units | grep -i cat-obs` ne retourne rien.
2. Vérifier qu'aucun processus ne tourne : `pgrep -af repository_cartographer` ne retourne rien.
3. Retirer le checkout : `chmod -R u+w /srv/cat-obs/checkout/<sha>` puis `rm -rf` de ce seul répertoire.
4. Révoquer l'utilisateur : `userdel cat-obs-ro` (après vérification qu'il ne possède aucun fichier hors de `/srv/cat-obs`).
5. **Conserver** `/srv/cat-obs/reports/` : ce sont des preuves (CLAUDE.md §5). Ne pas supprimer.
6. Registre : `runner_id` reste `null` ; aucun voyant à modifier.

## 6. Limites de ce runner

- Il ne prouve pas que la cartographie est juste : il prouve qu'une règle du banc a été appliquée au SHA nommé.
- Une invocation prouve l'exécution, pas la qualité du rapport ; la qualité relève de la revue humaine et du banc.
- Aucune observation runtime : le fait qu'un module tourne sur l'hôte n'est jamais déduit du code.
