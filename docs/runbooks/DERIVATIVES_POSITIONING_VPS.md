# Procédure VPS — Plateformes & levier, stockage des observations (lot 1)

> **Ne pas exécuter sans GO de mise en service.** Ce document prépare la mise en service ; il ne
> l'autorise pas. Le lot 1 ne crée ni service, ni route API, ni collecteur. #286 ACTIVE.

Contrat : [MARKET_DERIVATIVES_POSITIONING_01](../contracts/MARKET_DERIVATIVES_POSITIONING_01.md).

## 0. Prérequis bloquant : snapshots et sauvegardes externes

Constat du 2026-11-21 : `crypto-restore-01` est une VM GCE avec **un seul disque persistant**
(`sda`, 100 Go, ext4, monté sur `/`, 58 Go libres). Aucun outil de sauvegarde local (restic, borg,
rclone absents ; seul `dpkg-db-backup.timer`). La politique de snapshots GCP n'a pas pu être lue
(métadonnées refusées, `gcloud` sans droits suffisants).

Avant toute écriture d'**observation réelle**, depuis un compte GCP autorisé (lecture seule) :

```bash
gcloud compute instances describe crypto-restore-01 --zone <ZONE> --format='value(disks[].source)'
gcloud compute disks describe <DISQUE> --zone <ZONE> --format='value(resourcePolicies)'
gcloud compute resource-policies list
gcloud compute snapshots list --filter='sourceDisk~<DISQUE>' --limit=5
```

- Aucune politique ni snapshot : consigner la preuve datée, puis continuer.
- Disque couvert : **ne pas modifier** la politique du disque système. Proposer un disque dédié sans
  planning de snapshots, monté par exemple sur `/var/lib/cat-derivatives-positioning` (fstab par UUID,
  `nofail` interdit : le service doit échouer si le volume manque). Décision explicite requise.

## 1. Chemin persistant et permissions

| Élément | Valeur |
|---|---|
| Répertoire | `/var/lib/cat-derivatives-positioning` |
| Base | `/var/lib/cat-derivatives-positioning/positioning.sqlite3` (+ `-wal`, `-shm`) |
| Propriétaire | `lecanada26:lecanada26` (même utilisateur que l'Operator API et le web) |
| Mode | `0700` répertoire, `0600` fichiers (`UMask=0077`) |
| Création | systemd `StateDirectory=cat-derivatives-positioning`, `StateDirectoryMode=0700` |

`StateDirectory` est compatible avec `ProtectSystem=strict` (précédent : `cat-paper-balance` de
`crypto-operator-web`). Ne pas utiliser `DynamicUser=` (le répertoire passerait sous
`/var/lib/private`). Le module ne crée jamais le répertoire : s'il manque, il répond
`STORAGE_DIRECTORY_MISSING`.

## 2. Installation du code (sans service)

Le code fait partie d'une release CAT habituelle (`/home/lecanada26/crypto-install/releases/<sha>`,
Python 3.11.17, SQLite 3.53.1 constatés). Aucune dépendance hors stdlib.

```bash
REL=/home/lecanada26/crypto-install/releases/<SHA>
PY=$REL/.venv/bin/python
cd "$REL" && $PY -m pytest -q tests/derivatives_positioning   # synthétique, tmp_path uniquement
```

## 3. Premier démarrage (vérification à vide, sans observation réelle)

Création du répertoire (root, une fois) — équivalent manuel de `StateDirectory` :

```bash
sudo install -d -o lecanada26 -g lecanada26 -m 0700 /var/lib/cat-derivatives-positioning
```

Vérification (utilisateur `lecanada26`) :

```bash
cd "$REL" && $PY -m observability.derivatives_positioning \
  --data-dir /var/lib/cat-derivatives-positioning status
```

Attendu : `observations: 0`, `schema_versions: [1]`, un `store_id`, `purge_enabled: false`,
`volume.free_bytes`. Noter le `store_id` : il doit rester identique après chaque redémarrage.

Une future unité écrivain (lot collecteur) contiendra au minimum :

```ini
[Service]
User=lecanada26
StateDirectory=cat-derivatives-positioning
StateDirectoryMode=0700
UMask=0077
ProtectSystem=strict
NoNewPrivileges=yes
PrivateTmp=yes
```

## 4. Vérification après redémarrage

```bash
$PY -m observability.derivatives_positioning --data-dir /var/lib/cat-derivatives-positioning status
$PY -m observability.derivatives_positioning --data-dir /var/lib/cat-derivatives-positioning --read-only \
  latest --venue <v> --symbol <s> --contract-type PERPETUAL_LINEAR
```

Contrôles : même `store_id`, `observations` non décroissant, `conflicts.distinct` stable,
`store_bytes` comparé à `budget.disk_budget_bytes` (hypothèse, rien n'est purgé).

Diagnostic d'intégrité (lecture seule, si le binaire `sqlite3` est installé) :

```bash
sqlite3 'file:/var/lib/cat-derivatives-positioning/positioning.sqlite3?mode=ro' 'PRAGMA integrity_check;'
```

## 5. Exploitation

| Situation | Comportement |
|---|---|
| historique vide | base créée, `observations: 0`, prête à écrire |
| répertoire absent | `STORAGE_DIRECTORY_MISSING`, code de sortie 3 |
| disque plein | `NOT_WRITTEN` / `STORAGE_FULL`, lot entier annulé, historique lisible |
| volume en lecture seule | `STORAGE_READ_ONLY`, historique lisible |
| redémarrage, même disque | historique retrouvé, nouvelles écritures acceptées |
| perte ou suppression du disque | historique perdu (règle de conservation acceptée) |

Budget prévisionnel 5 Go, aucune purge active. Capacité mesurée (synthétique, 60 instruments à 300 s) :
base ≈ 26 Mo/jour, WAL ≤ ≈ 5 Mo (replié à la fermeture) ; suivre `files_bytes` (base, WAL, shm séparés)
dans `status`. À réévaluer avant activation.

## 6. Retour arrière applicatif (préserve les données)

1. Arrêter seulement le futur écrivain (`systemctl stop <unité>`), jamais les autres services CAT.
2. Retirer son drop-in ou revenir à la release précédente.
3. **Ne jamais** supprimer `/var/lib/cat-derivatives-positioning`, ni lancer
   `systemctl clean --what=state` sur l'unité, ni `rm` des fichiers `-wal`/`-shm` (ils peuvent contenir
   des transactions validées non encore reportées dans la base).
4. Une release plus ancienne refuse une base de schéma plus récent (`STORAGE_SCHEMA_NEWER`) au lieu de
   l'altérer : rester sur la version de code qui a migré, ou restaurer la release correspondante.

## 7. Interdits

Aucun export, copie, `scp`, `rsync`, artefact CI, télémétrie ou sauvegarde hors VPS. Une copie à
froid éventuelle reste sur le VPS (après `wal_checkpoint`), sur décision explicite.
