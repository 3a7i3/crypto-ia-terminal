# Publication frontend 1c3f0b5 — dossier préparé, non activé

Mission opérateur du 2026-10-30 : préparer la publication du frontend #525 au
SHA exact, sans toucher aux services actifs. Suite de la
[passation #526](../handoffs/PASSATION_CONVERSATION_VM_APP_20261030.md).
Gouvernance relue : [#285](https://github.com/3a7i3/crypto-ia-terminal/issues/285),
[#286](https://github.com/3a7i3/crypto-ia-terminal/issues/286),
[#430](https://github.com/3a7i3/crypto-ia-terminal/issues/430),
[#432](https://github.com/3a7i3/crypto-ia-terminal/issues/432) et
[#445](https://github.com/3a7i3/crypto-ia-terminal/issues/445).

**PREPARED / NOT PUBLISHED / NO RUNTIME AUTHORIZATION.**
Cette PR est nécessaire au dossier de publication ; sa fusion n'installe aucune
configuration et ne redémarre rien. Une décision opérateur distincte reste
nécessaire avant tout bloc administrateur ci-dessous. Les anciennes exceptions,
roadmaps et permissions de premier démarrage ne sont pas réutilisées.

## 1. Source et accès réellement vérifiés

| Élément | Preuve / état |
|---|---|
| Appareil Remote Desktop Commander | `bc07f523-ad34-4c2e-9af1-0105f66d5783` |
| Identité exécutée | `hostname=crypto-restore-01` ; `id=lecanada26`, UID1001, GID1002 |
| Première lecture VM | `/home/lecanada26/crypto-install/ACCESS_HANDOFF.md` |
| Instructions | CLAUDE.md, docs/DEVELOPER_ENTRYPOINT.md, CURRENT_TASK.md ; aucun AGENTS.md dans le tree exact ni dans les ancêtres concernés inspectés |
| Source #525 fusionnée | `1c3f0b5c6f7d7ab553106f4788f66d9c7c9e67ab` |
| HEAD de PR testé | `2085fe2a65c0259bb09a8bd60949baa52f3154df` |
| Tree des deux commits | `c3fa07c323852c937c6c7ac4cc74bad86c52eba1`, identique |
| CI post-fusion #525 | 20 workflows `push`, tous completed/success, au SHA fusionné ; API Actions, page100/total20, sans filtre pull_request |
| Passation #526 | Fusionnée en `d6fd88bea24ec124a2de3c82d1ff2d18a256180a` après revue du seul fichier, HEAD c0104fa7 exact, 25 checks success / 2 skipped, quatre requis success, aucune review ni thread bloquant |
| Cible de ce build | Toujours `1c3f0b5…` ; la fusion documentaire de #526 ne change pas la cible |

[CI datée et URLs des 20 runs](evidence/frontend_1c3f0b5_20261030/CI_POST_MERGE.json).
Ruleset actif `main-history-safety` n°21989939 relu : PR obligatoire, résolution
des threads, pas de force-push/suppression, aucun bypass ; requis :
`integrity`, `LINT REGRESSION GATE`, `TEST REGRESSION GATE`,
`CROSS-STACK COMPATIBILITY GATE`. L'endpoint de l'ancienne branch protection
répond 403 au connecteur ; aucune tentative de contournement. La décision de
fusion utilise le ruleset lisible et les contrôles du HEAD exact.

## 2. État courant et frontière source/runtime

Contrôle en lecture seule à `2026-10-30T08:20:02Z` et précontrôle final conservé
dans le répertoire de validations ; ces observations sont ponctuelles.

| Objet | Préparé | Installé / sélectionné | Démarré | Vérification actuelle |
|---|---|---|---|---|
| Ancien frontend 82cd63e… | Oui | Oui, unité web originale sans drop-in | PID79556, depuis 02:48:06Z, NRestarts0 | 8 fichiers dist servis conformes ; index privé HTTPS conforme |
| API sur 82cd63e… | Oui | Oui | PID79546, depuis 02:48:04Z, NRestarts0 | /healthz200 ; snapshot/market503 attendus |
| Frontend 1c3f0b5… | Oui, build isolé sur VM | Fichiers isolés présents ; pas sélectionné par l'unité | Non | Tests/build/fixtures et navigateur isolé uniquement |
| Nouveau drop-in web | Oui | NON | Sans objet | Composition et analyse systemd, pas de reload |
| Données de présentation | Répertoire existant vide | Aucun raccordement | Aucun producteur démarré | Vide avant/après |
| Boot API/web | Sans changement | Deux unités disabled | Pas d'enable | Vérifié |

Ancienne release : `/home/lecanada26/crypto-install/releases/82cd63e202e09ff52e00372cb9d9f3eb65cc8345`.
Nouvelle copie indépendante : `/home/lecanada26/crypto-install/releases/1c3f0b5c6f7d7ab553106f4788f66d9c7c9e67ab`.
Aucun checkout partagé/gelé, worktree de Claude ou fichier de l'ancienne release
n'a été modifié. Les 13 empreintes protégées couvrent les deux unités installées,
les huit anciens fichiers dist, le serveur web et package/lock.

Le serveur web reste loopback `127.0.0.1:8181`, proxy GET/HEAD vers
`127.0.0.1:8090`. Tailscale Serve conserve l'unique proxy HTTPS443 vers8181,
sans Funnel. URL privée :
[crypto-restore-01](https://crypto-restore-01.tailfebca3.ts.net/).
Le contrôle HTTPS depuis la VM utilise --resolve vers100.118.215.88 avec TLS
normal, sans -k ; il ne démontre pas le parcours actuel du téléphone.

## 3. Paquet exact et preuves

Staging :
`/home/lecanada26/crypto-install/staging/frontend-1c3f0b5c6f7d7ab553106f4788f66d9c7c9e67ab`.

| Artifact | SHA-256 |
|---|---|
| `frontend-1c3f0b5.tar.gz`, 167970 octets | `1cf7d3ef9da134f6655c538951b646f3b2cc161cb77b7426fdd5b5bfcaf57d3c` |
| `RELEASE_MANIFEST.json` | `21838846782410e258177ae0885b60a294068304e35b20df54e12f655cf723af` |
| `90-ui-modules-1c3f0b5.conf` | `867b846d0567ae8f62f3d11709b41bf43e168a5a1fda42f29b04350a552f594e` |
| `verify_frontend_release.py` | `f48a30e6ad514c14fe404a9c694d4b302c1d7a9b16f389dc986bcd0842b11296` |
| Nouvel `dist/index.html` | `e16d8fe8767ce798acc5eb3151703492ec46735ac38781f55b69e7aebb1e8dde` |

[Manifeste complet](evidence/frontend_1c3f0b5_20261030/RELEASE_MANIFEST.json),
[drop-in candidat](../../deploy/frontend_release_20261030/90-ui-modules-1c3f0b5.conf)
et [vérificateur en lecture seule](../../deploy/frontend_release_20261030/verify_frontend_release.py).

L'archive contient seulement huit fichiers dist, le serveur web .mjs, package.json,
package-lock.json et leur reçu RUNTIME_FILES.json. Aucun .env, secret, node_modules,
venv, artifact scientifique ou base. Horodatages tar/gzip déterministes, fichiers
réguliers ; pas de lien symbolique dans le lot. Le dossier de source complet reste
une copie indépendante de validation, sans activation de backend.

Package et lock sont identiques à l'ancienne release ; npm ci --ignore-scripts
utilisé. Le serveur web est identique octet pour octet. L'arbre
observability/operator_api reste `bfecb44199958a5b7666272aaa2260b040192146`
dans les deux sources : aucune mise à niveau API requise par cette refonte.

| Validation VM au SHA exact | Résultat |
|---|---|
| Node / npm | 24.22.2 / 11.19.1, aucun upgrade |
| Frontend Vitest | 492 PASS, 0 skip |
| Contrats runtime web/PWA | 16 PASS, 0 skip ; serveurs fixtures éphémères terminés |
| Build production | PASS, Vite8.3.5 ; aucun build démo publié |
| npm audit | 0 vulnérabilité |
| Source | HEAD/tree exacts, tree suivi propre, diff --check PASS |
| Analyse systemd de l'équivalent composé | Exit0 ; aucune installation ou prise en charge par PID1 |
| Navigateur de la nouvelle dist | 154 contrôles PASS, zéro pageerror/requête externe de page/débordement, thèmes persistés, 1440/820/390px, états présents/absents/périmés/invalides/erreur réseau |
| Contraste sémantique testé | Minimum5.274:1 |
| Contrôle courant HTTP/TLS | Ancienne dist vérifiée, pas la nouvelle |
| Garde négative | Mode `live` refusé avec « Wrong served web directory » tant que 82cd63e est servi |

Les 19 fichiers fixtures générés lors de #525 sont réutilisés et hachés dans le
manifeste, sans nouvelle lecture de données récupérées. Les 113 tests Python
cross-stack historiques ne sont pas revendiqués comme relancés ici.
Playwright1.64.1 / Chromium156.0.8078.4, sandbox activée, contextes éphémères,
service workers bloqués. La page reçoit dist+fixtures par interception : aucun
serveur d'app d'audit ni accès à l'API active pour cette preuve. Deux captures
clair/mobile et sombre/desktop avec sources absentes ont été inspectées.

Preuves locales :
- `~/crypto-install/validations/1c3f0b5c6f7d7ab553106f4788f66d9c7c9e67ab/` ;
- `~/crypto-install/audit-browser/release-1c3f0b5-20261030/captures/checks.json` et captures PNG ;
- BASELINE_BEFORE.json, PREFLIGHT_READ_ONLY.json, LIVE_NEGATIVE_CHECK.json et logs de commandes.

Avertissements conservés : Vite annonce une future évolution du chargement
CommonJS de sa configuration ; aucun masquage ni changement de source.
systemd-analyze signale aussi netplan-ovs-cleanup non lisible et une clé
RestartMode de snapd non reconnue, déjà hors des unités candidates. Exit0,
aucune correction système ni redémarrage de ces services.

## 4. Changement de configuration proposé

Unique destination future :
`/etc/systemd/system/crypto-operator-web.service.d/90-ui-modules-1c3f0b5.conf`.

Le drop-in change Description, ConditionPathExists, WorkingDirectory, ExecStart et
BindReadOnlyPaths du web ; les trois directives à liste sont réinitialisées avant
leur valeur candidate. API, deux unités originales, port, proxy et toutes les
protections restent conservés. Aucun Wants/Requires vers l'API ou un moteur ajouté.

La nouvelle source et la dist existent au chemin exact. L'équivalent composé et
un tree d'unités/drop-in sont dans staging/verify et staging/units ; analyse
systemd effectuée hors configuration active. Les fichiers présents sous /etc
n'ont pas été remplacés. Ne pas écraser la dist active pour éviter un redémarrage.

## 5. Décision distincte requise avant publication

Proposition d'exception, **NON ÉMISE / NON AUTORISÉE** :
`GOV-286-WEB-FRONTEND-1c3f0b5`, à consigner sur #286/#430 si l'opérateur l'accorde.
L'approbation doit lier source, archive/digest, ancien chemin, drop-in et checker
ci-dessus, acteur humain administrateur, expiration et usage unique.

Périmètre proposé : installer le seul drop-in revu, daemon-reload, un redémarrage
manuel du web seul, contrôles, puis rollback borné de cette même tentative si
nécessaire. Pas d'autorisation Advisor/API, moteur, Telegram, collecteur, donnée,
expérience, boot, secret, port public ou ancienne VM crypto-advisor-2.

Le connecteur bloque sudo ; aucun helper privilégié, ticket, daemon, sudoers,
permission ou configuration du connecteur n'a été installé. L'activation reste
l'exécution manuelle par l'opérateur. Le vérificateur n'accorde aucun privilège :
il fait des lectures, des GET et des vérifications de fichiers/processus.
Ce n'est pas l'admission d'une passerelle #432/#445.

## 6. Précontrôle accessible maintenant, en lecture seule

Sur la VM, sous lecanada26 :

```bash
stage=/home/lecanada26/crypto-install/staging/frontend-1c3f0b5c6f7d7ab553106f4788f66d9c7c9e67ab
printf '%s  %s\n' f48a30e6ad514c14fe404a9c694d4b302c1d7a9b16f389dc986bcd0842b11296 "$stage/verify_frontend_release.py" | sha256sum --check -
python3 -B "$stage/verify_frontend_release.py" preflight
```

Toute divergence impose un diagnostic et un nouveau dossier/protocole si les
octets changent. Pas de modification du manifeste pour faire passer la garde.
La preuve est ponctuelle et doit être refaite immédiatement avant l'acte autorisé.

## 7. Bloc administrateur préparé — NE PAS EXÉCUTER sans la décision `5

Effet : garde fraîche, copie du seul drop-in dans une custody root neuve,
re-hachage, publication exclusive du fichier, reload et redémarrage web seul.
Le lien dur depuis la copie root évite de relire le staging utilisateur entre
la vérification root et l'installation ; /root et /etc sont sur le même volume
sur cette VM. Une erreur ou un chemin préexistant interdit de rejouer le bloc.

```bash
set -euo pipefail
stage=/home/lecanada26/crypto-install/staging/frontend-1c3f0b5c6f7d7ab553106f4788f66d9c7c9e67ab
custody=/root/frontend-1c3f0b5-20261030
dest=/etc/systemd/system/crypto-operator-web.service.d/90-ui-modules-1c3f0b5.conf
printf '%s  %s\n' f48a30e6ad514c14fe404a9c694d4b302c1d7a9b16f389dc986bcd0842b11296 "$stage/verify_frontend_release.py" | sha256sum --check -
python3 -B "$stage/verify_frontend_release.py" preflight
sudo test ! -e "$custody"
sudo test ! -L "$custody"
sudo install -d -o root -g root -m 0700 "$custody"
sudo install -o root -g root -m 0644 "$stage/units/crypto-operator-web.service.d/90-ui-modules-1c3f0b5.conf" "$custody/drop-in.conf"
test "$(sudo sha256sum "$custody/drop-in.conf" | cut -d ' ' -f1)" = 867b846d0567ae8f62f3d11709b41bf43e168a5a1fda42f29b04350a552f594e
python3 -B "$stage/verify_frontend_release.py" preflight
sudo install -d -o root -g root -m 0755 /etc/systemd/system/crypto-operator-web.service.d
sudo ln -T "$custody/drop-in.conf" "$dest"
sudo systemctl daemon-reload
sudo systemctl restart crypto-operator-web.service
python3 -B "$stage/verify_frontend_release.py" live
```

Le reload de PID1 est global. La garde refuse les reloads déjà en attente des
unités chargées ; cela ne prouve pas l'absence de changements dans une unité
non chargée. Refaire cette revue au moment de la décision.

Acceptation après acte : web nouveau PID/cwd/cmdline et bind au bon SHA,
8 nouveaux assets HTTP et index privé au manifeste, API PID79546/config/dates
inchangés, protections identiques, loopback seulement, boot disabled, présentation
vide et anciens fichiers intacts. Puis parcours privé mobile/desktop, modules,
engrenage, clair/sombre persistant, dates/provenances/indisponibilités visibles.
Une session neuve prouve les octets actuels ; vérifier aussi la mise à jour du
client/PWA habituel avant de déclarer le téléphone réellement à jour.
Ne pas fermer #430 ou déclarer U8/L4 sur la seule preuve synthétique.

## 8. Rollback concret préparé — uniquement pour la tentative autorisée

Précondition : le fichier dest appartient bien à cette tentative et a encore
l'empreinte revue ; aucune suppression d'un fichier inconnu. Si l'installation
n'a pas atteint dest, ne rien retirer et diagnostiquer l'étape atteinte.
Si l'approbation distincte inclut ce rollback :

```bash
set -euo pipefail
stage=/home/lecanada26/crypto-install/staging/frontend-1c3f0b5c6f7d7ab553106f4788f66d9c7c9e67ab
dest=/etc/systemd/system/crypto-operator-web.service.d/90-ui-modules-1c3f0b5.conf
test "$(sudo sha256sum "$dest" | cut -d ' ' -f1)" = 867b846d0567ae8f62f3d11709b41bf43e168a5a1fda42f29b04350a552f594e
sudo rm -- "$dest"
sudo systemctl daemon-reload
sudo systemctl restart crypto-operator-web.service
printf '%s  %s\n' f48a30e6ad514c14fe404a9c694d4b302c1d7a9b16f389dc986bcd0842b11296 "$stage/verify_frontend_release.py" | sha256sum --check -
python3 -B "$stage/verify_frontend_release.py" rollback
```

Résultat attendu : ancienne unité sans drop-in, cwd/commande web82cd63e,
8 anciens assets et index privé conformes ; API inchangée, boot disabled,
présentation vide. Ancienne release, custody, source candidate, logs et archives
restent conservés. Aucun restore de base, backup, secret ou fichier scientifique.

Le mode rollback du vérificateur ne dépend pas de l'intégrité de la release
candidate : il vérifie les anciens fichiers, l'ancienne présentation servie,
l'API et les frontières préservées. Régression testée en refusant en mémoire toute
lecture de hash de la candidate/archive : rollback checker PASS sur l'ancien
frontend, préflight REFUSED. Aucun fichier n'a été corrompu ou supprimé ; reçu
ROLLBACK_CHECKER_REGRESSION.json dans le répertoire de validations. Les identités
API/web sont relues après les GET pour détecter un changement pendant le contrôle.

Le rollback runtime n'a pas été exécuté ni testé en production pendant cette
préparation. Échec de rollback, interruption ou garde refusée : état inconnu
à diagnostiquer, pas de boucle d'essais ni nouveau restart implicite.

## 9. Prochaine action unique

Faire la revue et la CI de ce dossier au HEAD exact puis le fusionner en source
dans le périmètre autorisé. Ensuite présenter la décision de publication du
paquet 1c3f0b5 à l'opérateur. Jusqu'à sa réponse explicite et l'exécution
administrateur : ancien frontend toujours servi, **NO DEPLOY**.
