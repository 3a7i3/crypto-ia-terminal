# Plan G2 → G5 — raccorder runtime-service et storage, puis events
Statut : **source pour revue. Rien n'est installé, activé ni lancé.** #286 reste actif ; chaque gate ci-dessous est une demande distincte, avec son autorisation runtime propre. Fusionner ce document ne déploie rien. Suite de [G1](PASSIVE_PUBLISHERS_G1_RESULTS.md) et du [plan de gate](PASSIVE_PUBLISHERS_GATE_PLAN.md) (dont la numérotation G2–G5 est remplacée par celle-ci).

Périmètre : **runtime-service et storage d'abord**. Events est traité à part (§6) et n'est ni installé ni câblé par G2–G5. Limites permanentes : aucun changement Advisor, burn-in, FIN ni admission Research ; droits de `chatgpt-ro` inchangés ; **aucun sudo n'est exécuté par un agent** (l'opérateur lance chaque bloc) ; l'ancienne exception frontend (`GOV-286-WEB-FRONTEND-bdca77f`) est consommée.

## 0. Vue d'ensemble et autorisations runtime à demander
| Gate | Action sur l'hôte | Exécutant | Pourquoi c'est nécessaire | Arrêt |
|---|---|---|---|---|
| **G2** installation inactive | crée `/var/lib/crypto-publishers-g2/` (état, manifeste, sauvegardes), `/home/mathieu/operator_presentation` (0700, `mathieu`) si absent, 4 fichiers d'unité dans `/etc/systemd/system/`, puis `daemon-reload`. Rien d'activé ni lancé | opérateur, root via sudo | les fichiers d'unité et le dossier de sortie doivent exister pour tout essai sous systemd ; sans eux les routes restent `*_MISSING` | `NeedDaemonReload=yes` sur Advisor/API/web, vérification refusée, dossier existant au mauvais mode |
| **G3** essais ponctuels | `systemctl start` de **chaque service une fois ou trois**, un publisher à la fois ; écrit l'artefact dans le dossier de sortie ; timers toujours désactivés | opérateur, root pour `start` et le journal | seul moyen d'exercer le sandbox, le bus systemd et l'écriture atomique réels ; G1 n'a rien de tout cela | statut ≠ 0, artefact invalide, écart Advisor/API/web |
| **G4** raccordement API | un drop-in de 2 variables + `daemon-reload` + `restart crypto-operator-api.service` **seul** | opérateur, root | le lecteur ne lit pas le dossier de sortie par défaut ; les chemins sont lus à l'import (redémarrage inévitable) | API non `active`, code HTTP inattendu, Advisor touché |
| **G5** timers et observation | `systemctl enable --now` de **2 timers** ; observation ≥ 5 périodes | opérateur, root | seule la planification produit une fraîcheur continue (< 90 s) | échec répété, run > 10 s, charge visible |
Chaque gate demande une autorisation de Mathieu **distincte**, publiée sur #286 comme l'exception précédente (proposition de noms : `GOV-286-PUBLISHERS-G2` … `-G5`), et se consomme à l'usage. Aucune ne couvre la suivante.

## 1. G1 consigné
Voir [PASSIVE_PUBLISHERS_G1_RESULTS.md](PASSIVE_PUBLISHERS_G1_RESULTS.md) : provenance opérateur, script `166caedb…` vérifié, bloc extérieur non vérifié, sandbox non exercé, `security --offline` ignoré, `stat` avant/après inchangés (indice, pas preuve de contenu). G1 n'est pas relancé sans raison nouvelle.

## 2. G2 — installation inactive (préparée)
### Paquet
| Fichier | Rôle | sha256 |
|---|---|---|
| `deploy/passive_publishers/g2_install_inactive.sh` | script G2 (modes `plan`, `verify`, `apply`, `rollback`), généré par `build_g2.py` depuis les unités revues | `9ad589ecd67ce9b414c8ef1128fe38a30650b55533a9f4dfb17d446baf3422d5` |
| `deploy/passive_publishers/g2_paste_block.sh` | bloc à coller : le shell (privilégié pour `apply`/`rollback`) écrit le script dans un répertoire qu'il est seul à pouvoir ouvrir, **re-hache cette copie**, n'exécute que cette copie, la supprime, affiche le code retour | `3117f492046bc0d9c840923c1eecac7058d3f8264ace3f6235866c2c181e2803` (470 lignes, 23 110 o) |
| unités embarquées (identiques à G1) | `crypto-publish-{runtime-service,storage}.{service,timer}` | voir G1 §5 ; les empreintes sont gravées dans le script et revérifiées après installation |
Les unités d'events ne sont **pas** dans ce paquet.

### Ce que `apply` fait (liste complète, journal d'intentions dans `/var/lib/crypto-publishers-g2/manifest`)
1. refuse sans écrire si : le script n'est pas une **copie protégée** (fichier ordinaire, non lien symbolique, propriétaire root, sans écriture groupe/autres, dans un dossier qui l'est aussi) ; `NeedDaemonReload` ≠ `no` sur Advisor, API ou web (le `daemon-reload` appliquerait un changement en attente qui n'est pas le nôtre) ; une unité cible est déjà `enabled`/`linked` ou `active` ; le dossier de sortie existe avec un autre propriétaire/mode que `mathieu 700` (il n'est jamais `chmod`é) ; l'utilisateur `mathieu` manque ; moins de 10 Mio libres ; empreinte d'une unité embarquée ≠ empreinte revue ; `systemd-analyze verify` ≠ 0 ; un manifeste existe (déjà appliqué) ;
2. crée `/var/lib/crypto-publishers-g2` (0700) et `backup/` ;
3. **journal d'intentions** : chaque étape est inscrite dans le manifeste et synchronisée sur disque **avant** d'être faite (`intent-created`, `intent-replaced`), puis marquée faite après vérification (`created`, `replaced`). Si l'écriture du manifeste échoue, l'étape n'est pas exécutée ;
4. crée `/home/mathieu/operator_presentation` (`install -d -m 0700 -o mathieu -g mathieu`) s'il est absent ;
5. pour chaque unité : identique → intacte ; différente → **copiée dans `backup/`** et la copie est re-hachée ; absente ou différente → copie vers un nom caché du même dossier (`.<unité>.g2tmp`), empreinte vérifiée, puis `mv` (renommage **atomique**), empreinte re-vérifiée. Un fichier d'unité n'est donc jamais partiellement écrit sous son vrai nom ;
6. `systemctl daemon-reload` (la seule interaction avec le gestionnaire) ;
7. vérifie : empreintes installées = empreintes revues, propriétaire/mode, `systemd-analyze verify` sur les fichiers installés, `LoadState=loaded`, `ActiveState=inactive`, `UnitFileState` = `disabled` (timers) / `static` (services), jamais exécutées (`ExecMainStartTimestampMonotonic=0`), **aucun** `WantedBy`/`RequiredBy`/`BoundBy`/`UpheldBy`, aucun lien symbolique `crypto-publish-*` ;
8. compare Advisor, API et web **avant/après** (état, PID, `NRestarts`, `InvocationID`, date de démarrage, drop-ins) : `UNCHANGED` exigé.
**Comptabilité des échecs** : chaque `install`, `cp`, `mv`, `rm`, `mkdir`, écriture du manifeste et `daemon-reload` est testé ; tout échec est compté, affiché (`!!`) et rappelé dans le résumé ; au premier échec d'écriture le script s'arrête sans rien défaire, conserve l'état et affiche la commande de rollback. Code retour : 0 seulement si tout passe.
**Interruption** (SIGINT/SIGTERM/SIGHUP, ou arrêt brutal) : l'état partiel est conservé et récupérable ; sur signal le script le dit et affiche `G2_MODE=rollback`. Les cas « arrêt avant le renommage » (un fichier temporaire caché reste), « arrêt entre le renommage et l'enregistrement » (le fichier est installé, seule l'intention est notée) et « échec d'écriture » sont testés, suivis d'un rollback complet.

### Pourquoi rien ne démarre indirectement
- Les services n'ont aucun `[Install]`, `Wants`, `Requires`, `BindsTo`, `PartOf` ni `Upholds` (test).
- Les timers ont `WantedBy=timers.target` : cela n'agit que sur `systemctl enable`, que le script n'appelle jamais ; `daemon-reload` ne démarre pas une unité inactive. Un test parcourt le code du script : seuls `systemctl show` et `systemctl daemon-reload` y figurent ; ni `enable`, `start`, `restart`, `--now`, `link`, `mask`, ni `sudo`.
- Les dépendances d'installation d'un paquet (`apt`/`pip`) : **aucune** n'est utilisée.
- Réserve honnête : `daemon-reload` est un rechargement global du gestionnaire ; il ne redémarre rien mais relit toutes les unités. D'où la garde `NeedDaemonReload`.

### Rollback (ne supprime que ce que G2 a créé, et ne prétend jamais plus que ce qui est vérifié)
Mode `rollback` : refusé tant qu'une unité est `enabled`/`active` (défaire d'abord G5). Sinon, pour la dernière trace de chaque chemin, dans l'ordre inverse de la création :
- fichier **créé** (ou intention de créer) : supprimé seulement si son sha256 est celui installé ; absent → rien à faire ; modifié depuis → **DIVERGED**, laissé en place, compté comme échec ; un fichier temporaire caché laissé par une interruption est supprimé ;
- fichier **remplacé** : si le contenu courant est déjà l'original → rien ; si c'est le contenu installé → restauré depuis `backup/` par le même chemin atomique (copie cachée, empreinte, renommage, empreinte) ; sauvegarde absente ou altérée, ou contenu courant tiers → échec compté, rien n'est écrasé ;
- dossier de sortie **créé par G2** : `rmdir` seulement s'il est vide ; non vide → **laissé en place par construction** (les artefacts ne sont jamais supprimés), sans compter comme échec.
Puis `daemon-reload`, contrôle que chaque unité retirée a `LoadState=not-found`, et comparaison avant/après d'Advisor/API/web.
**Verdict** : `RESULT: OK (rollback complete and verified)` seulement si **aucun** échec n'a été compté (suppression, restauration, rename, reload, contrôle d'absence). Sinon : `RESULT: FAILED — ROLLBACK INCOMPLETE … the previous state is NOT confirmed restored`, avec la liste des échecs, et `/var/lib/crypto-publishers-g2` (manifeste et sauvegardes) est **conservé** pour une reprise manuelle. `/var/lib/crypto-publishers-g2` n'est retiré qu'après un rollback entièrement vérifié.

### Étapes opérateur
Exécution depuis le **compte administrateur avec sudo** (celui d'où vous ouvrez `sudo -u mathieu -i`), **pas** depuis la session `mathieu`. Le bloc est collé tel quel ; la ligne `G2_MODE=…` qui le précède choisit le mode (par défaut `plan`, qui n'écrit rien ; `G2_MODE` est effacée par le bloc après lecture, donc chaque lancement doit la redéclarer).
1. **Contrôle d'empreinte du bloc (recommandé)** : enregistrer le bloc dans un fichier de staging privé, vérifier `3117f492…` avec `sha256sum -c`, puis lancer `G2_MODE=plan sh ./g2_paste_block.sh` (lancer le fichier avec `sh`, jamais avec `.`) ; sinon coller directement et consigner que l'empreinte externe n'est pas contrôlée (le script interne l'est toujours). Le bloc se termine par `exit` : collé dans une session interactive, il la ferme (comme G1).
2. `G2_MODE=plan` : lecture seule. Preuve attendue : `RESULT: OK`, les 4 cibles `absent (will be created)`, `NeedDaemonReload=no` ×3, `verify exit status: 0`, `nothing was written`.
3. Revue de la sortie du plan par Mathieu, puis autorisation G2.
4. `G2_MODE=apply` : preuve attendue : `RESULT: OK`, 4 fichiers `created`, `daemon-reload exit status: 0`, `LoadState=loaded ActiveState=inactive UnitFileState=static|disabled` pour les 4, `UNCHANGED`, `G2 apply exit status: 0`.
5. `G2_MODE=verify` (lecture seule) : mêmes preuves, rejouable à tout moment.
6. En cas d'écart : `G2_MODE=rollback`, preuve attendue : fichiers supprimés, dossier de sortie retiré s'il est vide, `UNCHANGED`, `/var/lib/crypto-publishers-g2` retiré.
Pas de sudo dans le script ; le bloc n'appelle `sudo` que pour `apply` et `rollback`, et le shell privilégié re-hache sa propre copie (répertoire 0700 de root sous `/run`) avant de l'exécuter : aucun chemin modifiable par un utilisateur ne sépare la vérification de l'exécution. Un `HASH MISMATCH OF THE PROTECTED COPY` arrête tout, sans écriture.

## 3. G3 — essais ponctuels sous systemd (plan, non exécuté)
Un publisher à la fois, **timers désactivés**. Ordre : runtime-service, puis storage. Pour chacun, trois lancements espacés d'au moins 5 s.
```
# 0. G2_MODE=verify : doit être RESULT: OK (précondition)
# 1. avant (lecture)
umask 077; B=$(mktemp); systemctl show crypto-advisor.service crypto-operator-api.service crypto-operator-web.service \
  -p Id -p ActiveState -p MainPID -p NRestarts -p InvocationID -p ActiveEnterTimestamp > "$B"
curl -s -o /dev/null -w 'healthz %{http_code}\n' http://127.0.0.1:8090/healthz
# 2. lancement unique (root ; revient quand le oneshot est terminé)
sudo systemctl start crypto-publish-runtime-service.service; echo "start rc=$?"
# 3. mesures (lecture)
systemctl show crypto-publish-runtime-service.service -p Result -p ExecMainStatus -p ExecMainCode \
  -p ExecMainStartTimestamp -p ExecMainExitTimestamp -p MemoryPeak -p CPUUsageNSec
sudo journalctl -u crypto-publish-runtime-service.service --since -5min --no-pager -o short-iso
ls -l --time-style=full-iso /home/mathieu/operator_presentation/
# 4. contrat de l'artefact (sous mathieu, validateurs du dépôt déployé, comme G1)
S=/opt/crypto-ai-terminal/operator/staging-src/1728b3ad952b87d903ccb7442579000da292b848
P=/opt/crypto-ai-terminal/operator/staging-envs/1728b3ad952b87d903ccb7442579000da292b848/bin/python
cd "$S" && env -i PATH=/usr/bin:/bin PYTHONPATH="$S" PYTHONDONTWRITEBYTECODE=1 "$P" -c '
import json
from observability.runtime_service_contract import validate_runtime_service_snapshot as ok
d = json.load(open("/home/mathieu/operator_presentation/runtime_service_snapshot.json"))
print("contract-valid=%s" % bool(ok(d)), {k: d["service"].get(k) for k in ("query_status","load_state","active_state")})'
# 5. après : comparer à l'état d'avant, puis supprimer le fichier temporaire
systemctl show crypto-advisor.service crypto-operator-api.service crypto-operator-web.service \
  -p Id -p ActiveState -p MainPID -p NRestarts -p InvocationID -p ActiveEnterTimestamp | diff "$B" - && echo UNCHANGED; rm -f "$B"
```
Pour storage : même séquence avec `crypto-publish-storage.service`, `storage_snapshot.json` et `observability.storage_contract.validate_storage_snapshot` (champs `source_status`, `entries_observed`, `matched_file_count`, `total_bytes`).

**Preuves attendues** : `Result=success`, `ExecMainStatus=0`, durée (exit − start) de l'ordre de la seconde au pire, `MemoryPeak` bien sous 128 Mio (`[not set]`/`infinity` se note `NOT_AVAILABLE`, jamais 0), un seul fichier d'artefact par publisher (aucun fichier temporaire résiduel), `contract-valid=True`, Advisor/API/web `UNCHANGED`, `healthz` 200 avant/après, les routes `runtime-service`/`storage` toujours 503 `*_MISSING` (l'API ne lit pas encore le dossier).
**Sources absentes ou limitées** : états explicites attendus (storage `PRESENT` avec ses compteurs ; runtime-service `OK`/`loaded`/`active`) ; tout état `UNKNOWN`/`NOT_AVAILABLE` est relevé tel quel, jamais converti en zéro.
**Diagnostic d'un blocage de sandbox** (jamais de retrait global) :
| Constat | Cause à vérifier | Action |
|---|---|---|
| `status=226/NAMESPACE` | dossier de sortie absent ou propriétaire/mode inattendu (`ReadWritePaths`, `ProtectHome=read-only`) | vérifier `stat` du dossier ; corriger le dossier, pas l'unité |
| `status=203/EXEC` ou `200/CHDIR` | chemin de release (`/opt/.../staging-*`) lisible par `mathieu` ? | `namei -l` du chemin ; ne pas élargir `ProtectSystem` |
| `status=218/CAPABILITIES` | `CapabilityBoundingSet=` vide incompatible avec l'hôte | relever le message, proposer le plus petit ajout, **avec preuve**, pour cette unité seule |
| `SIGSYS`/`SIGSEGV` ou `Operation not permitted` côté `systemctl show` | `MemoryDenyWriteExecute`, `PrivateNetwork` (accès au bus), `PrivateDevices` | journal + `systemd-analyze security <unité>` ; isoler la directive fautive, la tester sur cette unité seule |
| `Result=timeout` | > 20 s | mesurer ; ne pas allonger sans réexaminer 2×30+20 < 90 |
Toute levée d'une restriction est une proposition **séparée**, avec la preuve du blocage, pour une unité et une directive, soumise à Mathieu avant d'agir.
Un script G3 unique peut être généré après revue de G2 ; ces commandes courtes suffisent pour les essais.

## 4. G4 — raccordement de l'API (plan, non exécuté)
- **Compatibilité vérifiée dans le code déployé** (`git show 1728b3ad:observability/operator_api/…`) : `runtime_service_reader.py` lit `RUNTIME_SERVICE_SNAPSHOT_PATH`, `storage_reader.py` lit `STORAGE_SNAPSHOT_PATH`, `event_center_reader.py` lit `EVENT_CENTER_SNAPSHOT_PATH`, tous à l'**import** : un redémarrage de l'API est donc nécessaire, et l'API seule suffit. Seuil de péremption 90 s.
- **Drop-in préparé** : `API_DROPIN_30-presentation-paths-rt-storage.conf` (sha256 `6e1d3afb75de75377ed5206152c6d47075b46dfafc535a148ce405013a95eb45`), **deux** variables seulement ; `EVENT_CENTER_SNAPSHOT_PATH` n'est pas posée : `/events` répond comme avant.
- **Prérequis lus avant d'agir** (sans valeurs sensibles) :
```
systemctl show crypto-operator-api.service -p User -p WorkingDirectory -p FragmentPath -p DropInPaths -p EnvironmentFiles -p MainPID -p NRestarts -p ActiveEnterTimestamp
systemctl show crypto-operator-api.service -p Environment | tr ' ' '\n' | grep -E '(RUNTIME_SERVICE|STORAGE|EVENT_CENTER)_SNAPSHOT_PATH' || echo "aucune des trois variables n'est déjà posée"
```
  Attendu : `User=mathieu` (même propriétaire que le dossier 0700 ; sinon l'API ne le lirait pas : arrêt), aucune des trois variables déjà posée, drop-ins existants relevés (un drop-in postérieur dans l'ordre alphabétique l'emporterait).
- **Avant** : PID/dates d'Advisor, API, web ; codes HTTP de `/healthz`, `/api/operator/v1/{runtime-service,storage,events,system-health,snapshot,burn-in,market}` (relevés notés).
- **Action** (root, après autorisation G4) :
```
sudo install -d -m 0755 -o root -g root /etc/systemd/system/crypto-operator-api.service.d   # seulement si absent : le noter
sudo install -m 0644 -o root -g root API_DROPIN_30-presentation-paths-rt-storage.conf /etc/systemd/system/crypto-operator-api.service.d/30-presentation-paths.conf
sha256sum /etc/systemd/system/crypto-operator-api.service.d/30-presentation-paths.conf   # attendu : 6e1d3afb…
sudo systemctl daemon-reload && sudo systemctl restart crypto-operator-api.service
# aussitôt (les timers sont encore désactivés) : produire des artefacts frais, un publisher à la fois
sudo systemctl start crypto-publish-runtime-service.service; sudo systemctl start crypto-publish-storage.service
```
- **Après** (dans les 90 s qui suivent le dernier `start`) : `runtime-service` et `storage` → 200, contrat valide, état `FRESH` ; `events` → inchangé (503 `*_MISSING`) ; les autres codes **identiques** aux relevés d'avant ; Advisor et web : PID/`InvocationID`/dates **inchangés** ; API : nouveau PID, `NRestarts=0`, `active`. Puis, plus de 90 s après, `runtime-service`/`storage` doivent passer `STALE` (timers désactivés) : c'est la preuve que la péremption est honnête.
- **Conditions d'arrêt** : API non `active` 20 s après le redémarrage, `NRestarts` > 0, un code HTTP inattendu, Advisor ou web touché, `User` ≠ `mathieu`, drop-in existant qui redéfinit une variable.
- **Rollback API** (rétablit la configuration précédente) :
```
sudo rm /etc/systemd/system/crypto-operator-api.service.d/30-presentation-paths.conf
sudo rmdir /etc/systemd/system/crypto-operator-api.service.d 2>/dev/null   # seulement si le dossier a été créé par G4 et est vide
sudo systemctl daemon-reload && sudo systemctl restart crypto-operator-api.service
```
  Attendu : `runtime-service`/`storage` de nouveau 503 `*_MISSING`, autres routes identiques. Le redémarrage coupe l'API quelques secondes (la PWA voit un 5xx bref) ; il est annoncé avant d'agir.

## 5. G5 — timers et observation (plan, non exécuté)
Précondition : G3 et G4 réussis, autorisation G5 explicite.
```
sudo systemctl enable --now crypto-publish-runtime-service.timer crypto-publish-storage.timer
systemctl list-timers 'crypto-publish-*' --no-pager
```
Observation ≥ **5 périodes** (≥ 150 s ; je recommande 10 min pour voir aussi un cycle Advisor) :
- **cadence réelle** : `journalctl -u crypto-publish-storage.service --since -10min -o short-iso | grep Started` → intervalles ≈ 30 s (±1 s) ; idem runtime-service ;
- **chevauchement** : `Type=oneshot` l'interdit ; vérifier que chaque `Finished` précède le `Started` suivant et qu'aucun `Job … canceled`/`skipped` n'apparaît ;
- **fraîcheur** : échantillonner `/api/operator/v1/runtime-service` et `/storage` toutes les ~30 s ; âge maximal relevé < 90 s ; état `FRESH` ;
- **erreurs** : `systemctl --failed` sans unité `crypto-publish-*` ; `Result=success` à chaque run ; `NRestarts` inchangé ;
- **durées** : `ExecMainExitTimestamp − ExecMainStartTimestamp` ; critère d'arrêt si un run > 10 s (moitié du timeout) ;
- **charge** : `uptime`/`systemctl show` d'Advisor avant/après ; Advisor, API, web `UNCHANGED` ;
- **navigateur mobile** : ouvrir les vues Système ; **Services** et **Stockage** affichent des valeurs fraîches avec leur provenance ; **Événements** reste indisponible, honnêtement (503 `*_MISSING`) ; rien n'est affiché en zéro.
**Arrêts** : deux échecs consécutifs d'un publisher, un run > 10 s, l'artefact passe `STALE` en fonctionnement normal, charge visible, Advisor touché. **Rollback G5** : `sudo systemctl disable --now crypto-publish-runtime-service.timer crypto-publish-storage.timer` (les artefacts vieillissent puis passent `STALE`, honnêtement), puis G4 et G2 si nécessaire, dans cet ordre inverse.
Le coût mesuré (≤ 0,13 s) justifie de poursuivre ; il ne garantit pas les délais sous charge : c'est G5 qui les observe.

## 6. Events : deux options, une recommandation
Constat : en 1.0.0, `p12_alerts` sort `OUTPUT_LIMIT` (G1) — la cause (> 2 MiB ou > 10 000 lignes) n'est pas discriminée ; `ppl_lifecycles` reste `MISSING` (pas de producteur burn-in) ; `supervision_alerts` `NOT_CONFIGURED`.
- **A. Raccordement provisoire en 1.0.0** : installer l'unité events (même code déployé), poser `EVENT_CENTER_SNAPSHOT_PATH`. Gain : la vue Événements passe de 503 à un document valide où `p12_alerts` indique `OUTPUT_LIMIT` explicite. Coûts : aucune donnée de P12 n'est visible tant que le journal dépasse la limite (donc rien d'utile pour l'opérateur) ; une unité et une variable de plus à exploiter, puis à **remplacer** lors de B (changement du code de l'`ExecStart`, deuxième redémarrage API) ; le journal ne fait que grossir.
- **B. Release compatible API + frontend + publisher** (contrat 1.1.0, `PARTIAL_TAIL`) : un seul changement coordonné qui porte aussi #441 (réponses 503 structurées) et #443 (libellé Finance historique). Gain : fin de journal explicite (`coverage`, `window_bytes`), plus de `OUTPUT_LIMIT` sur P12, une seule bascule events. Coûts : une release sur trois composants sous #286 (exception propre, hors de ce plan), validation de bout en bout.
**Recommandation : B**, préparée séparément ; **ne pas installer A** : elle double les opérations et n'apporte pas d'information exploitable. D'ici là, `/events` reste `MISSING` et n'est pas câblé. Si Mathieu veut malgré tout une vue plus tôt, A reste réversible et peut être ajoutée par un G2 d'events distinct, sans toucher à G2–G5 ci-dessus.
**Règles de la release B** : ne **jamais** publier du 1.1.0 vers un lecteur qui le refuse. Ordre : (1) API + frontend qui acceptent 1.0.0 **et** 1.1.0 (validateurs déjà ainsi dans #442), vérifiés sur le document 1.0.0 existant ; (2) seulement ensuite, bascule du publisher events vers le code 1.1.0. Rollback en ordre inverse : d'abord le publisher (retour à 1.0.0), puis API/frontend. Le document n'est en 1.1.0 que si une source est partielle ; sinon il reste 1.0.0.
La préparation de B (inventaire #441/#443/#442, validations, chemin de release, gate d'exception) est une mission séparée, non commencée ici.

## 7. Limites de ce plan
- Les sorties du plan et de G2 sont **des preuves opérateur** ; un agent ne les vérifie pas sur la machine. Une confirmation en lecture seule par `chatgpt-ro` n'est possible que pour ce qui n'est pas sous `/home/mathieu` (unités dans `/etc/systemd/system`, états systemd).
- Les tests de G2 utilisent un faux `systemctl` : ils prouvent la logique du script (écritures, refus, rollback, absence d'`enable`/`start`), **pas** le comportement de systemd sur l'hôte. Les propriétés `UpheldBy`, `ExecMainStartTimestampMonotonic` et `MemoryPeak` dépendent de la version de systemd de l'hôte ; une propriété absente ressort vide et est traitée sans faux succès (`ActiveState`, `LoadState`, `UnitFileState` restent exigés).
- Les durées sous systemd et sous charge sont encore inconnues (G3, G5).

## Lancer `G2_MODE=plan` (sans sudo) — commande courte
Le fichier `g2_paste_block.sh` (sha256 `3117f492046bc0d9c840923c1eecac7058d3f8264ace3f6235866c2c181e2803`) doit être présent sur le VPS (même méthode de transfert que G1). Sous `mathieu` :

```sh
echo "3117f492046bc0d9c840923c1eecac7058d3f8264ace3f6235866c2c181e2803  $HOME/g2_paste_block.sh" | sha256sum -c - && G2_MODE=plan sh "$HOME/g2_paste_block.sh"
```
Le mode `plan` ne passe pas par sudo et n'écrit rien dans `/etc`, `/var/lib`, systemd ni le dossier de sortie. **Il n'est pas strictement sans écriture** : il crée, sous `${TMPDIR:-/tmp}`, deux dossiers temporaires `0700` (`g2priv.*` : copie du script ; `g2.*` : unités mises en place pour `systemd-analyze verify`), supprimés en sortie ; si le processus est tué, ils peuvent subsister dans `/tmp` (inoffensifs, supprimables à la main). Le bloc affiche le code retour final.
