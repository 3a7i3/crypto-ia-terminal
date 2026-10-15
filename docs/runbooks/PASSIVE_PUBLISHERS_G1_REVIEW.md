# G1 — préparation et mesure des publishers passifs (pour revue, non exécuté)
Statut : **source pour revue**. Aucun lancement de G1, aucun dossier de sortie, aucun timer, aucune installation, aucun redémarrage API ou Advisor. #286 reste actif. Le script est `deploy/passive_publishers/g1_stage_verify_measure.sh` ; le bloc à coller est `g1_paste_block.sh` (il écrit le script dans un répertoire temporaire privé, **vérifie son sha256**, l'exécute, supprime ce répertoire et renvoie son statut). Les deux sont générés par `build_g1.py` depuis les six fichiers d'unité ; la dérive est testée octet par octet.

## 1. Ce que le bloc fait (G1-a, sans écriture persistante)
Exécutant : `mathieu`, sans sudo. Une seule zone d'écriture : un répertoire temporaire privé `mktemp -d /tmp/g1.XXXXXX` (mode 0700, `umask 077`), supprimé à la fin et sur interruption (`trap`).
1. **Écrit** les six fichiers d'unité (≈ 8 Kio) dans `<tmp>/units/` (copie exacte du dépôt, jamais dans `/etc`).
2. `systemd-analyze verify` sur ces fichiers, statut de sortie affiché (rien n'est chargé ni installé).
3. `systemd-analyze security --offline` par service si la version le supporte, sinon `SKIPPED` affiché.
4. **Mesure** chaque publisher : `RUNS` (5 par défaut, 1 à 10) exécutions de la commande `ExecStart` de l'unité, extraite du fichier d'unité, avec la sortie redirigée vers `<tmp>/out/`, environnement minimal, `timeout 20`, `nice -n 19`, `PYTHONDONTWRITEBYTECODE=1` (aucun `__pycache__` dans `staging-src`). Durées par exécution, min/médiane/max, nombre d'échecs (statut 124 = timeout), validité de l'artefact avec le validateur du dépôt, statuts de source. C'est le **coût réel du processus** (démarrage de l'interpréteur compris), distinct de la durée du listage de G0.
5. Empreintes `stat` avant/après de `alerts.jsonl`, `burn_in_status_snapshot.json` et `databases/` : `UNCHANGED` ou `CHANGED (informational)` (des écrivains vivants peuvent légitimement modifier `alerts.jsonl`).
6. **Statut de sortie** : 0 seulement si tout passe ; 1 si `systemd-analyze verify`, un publisher (statut ≠ 0, 124 = timeout), un artefact absent, un contrat invalide (le validateur sort 1) ou le nettoyage échoue. Les échecs sont agrégés, listés dans « summary (before cleanup) » avec les messages utiles, puis le nettoyage a lieu en dernier. Avant **chaque** exécution le dossier de sortie est recréé vide et l'artefact est validé immédiatement : un artefact d'un run précédent ne peut pas valider un run échoué.
7. **Signaux** : INT/TERM/HUP → le script arrête le processus enfant (TERM puis KILL), attend qu'aucun processus ne référence plus le répertoire de travail, puis le supprime et sort avec 130/143/129. S'il reste un processus, le répertoire est **conservé** (`CLEANUP REFUSED`) plutôt que supprimé sous un processus vivant.
8. **Code mesuré** : l'en-tête affiche si le code sous test contient `PARTIAL_TAIL`. Avec la release déployée `1728b3ad` : « no ». **G1 ne valide pas la nouvelle lecture PARTIAL_TAIL / schéma events 1.1.0**, testée uniquement en CI sur la source.

**Lectures sur la machine** : `alerts.jsonl` (≤ 2 MiB, jamais plus), métadonnées de `databases/` (jamais le contenu des packets), un `systemctl show crypto-advisor.service` (une propriété fixe, timeout 3 s). Aucune autre lecture. **Aucune écriture** hors du répertoire temporaire.

## 2. Limites et garde-fous
- Borne de temps : 3 publishers × `RUNS` × 20 s au pire (≤ 300 s pour 5 exécutions). Refus si moins de 64 MiB libres dans `/tmp`.
- `RUNS` hors 1–10 est ramené à 5. Variables `SHA`, `REL`, `RT`, `PYBIN`, `SRC` surchargeables (tests uniquement) ; par défaut, mêmes chemins que les unités.
- **Non validé par G1-a** : les propriétés de sandbox systemd (`PrivateNetwork`, `ProtectSystem`, `MemoryDenyWriteExecute`, `MemoryMax`, `CapabilityBoundingSet=`) ne sont pas appliquées à une exécution manuelle. La requête `systemctl show` sous ce sandbox et la mémoire réelle ne seront observées qu'à G3 (première activation), où un échec reste visible et honnête (`STALE`). `--offline` ne juge que les directives, pas l'exécution.
- Le publisher qui tourne est celui de la release **déjà déployée** (`1728b3ad`) : contrat events 1.0.0. La lecture bornée 1.1.0 de `alerts.jsonl` n'y est pas ; à > 2 MiB cette release publie `OUTPUT_LIMIT` (explicite, jamais un faux vide). Elle exige une release commune (API + publisher + frontend), hors de G1.

## 3. Résultats attendus (référence des tests)
- `verify exit status: 0` ; exposition offline ≈ 3,1 « OK » par service (valeur mesurée sur systemd 255 en bac à sable).
- runtime-service : `contract-valid=True`, `query_status OK`, `load_state loaded`.
- storage : `contract-valid=True`, `source_status PRESENT`, `entries_observed` = nombre d'entrées de `databases/` (49 à G0), `matched_file_count 8`, `total_bytes 380366419` (à la dérive près des écrivains vivants).
- events : `contract-valid=True`, schéma `1.0.0`, `p12_alerts PRESENT`, `supervision_alerts NOT_CONFIGURED`, `ppl_lifecycles MISSING`.
- Durées : de l'ordre de 0,05–0,3 s en bac à sable ; seules les valeurs de l'hôte comptent. Critère d'arrêt proposé : un échec, un artefact non valide, `CHANGED` autre que `alerts.jsonl`, ou une durée max > 5 s.

## 4. G1-b — l'unique écriture persistante (séparée, non exécutée)
```
mkdir -m 0700 /home/mathieu/operator_presentation && stat -c '%n %U:%G %a' /home/mathieu/operator_presentation
```
Écrit : un répertoire vide appartenant à `mathieu`, hors de l'arbre runtime gelé. **Nettoyage/rollback** : `rmdir /home/mathieu/operator_presentation` (échoue s'il n'est pas vide, par prudence). À ne demander qu'avec G2 (installation) puisque `ConditionPathIsDirectory` fait sauter les services tant qu'il n'existe pas.

## 5. Ce que G1 ne fait pas
Pas de `/etc/systemd/system`, pas de `daemon-reload`, pas d'`enable`/`start`, pas de drop-in API, pas de redémarrage, pas de lecture d'EnvironmentFile ou de secret, pas de modification de `staging-src`/`staging-envs`, pas de `git`.
