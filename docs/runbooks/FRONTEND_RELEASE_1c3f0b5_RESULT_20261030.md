# Publication frontend du 30 octobre 2026 et correctif du vérificateur

État observé jusqu'à `2026-10-30T09:37:02Z`.
La publication opérateur a eu lieu à `09:26:25Z` sous
[l'exception de cette tentative](https://github.com/3a7i3/crypto-ia-terminal/issues/286#issuecomment-6518985419).
**Frontend installé, démarré et réellement vérifié au SHA1c3f0b5 ; aucun rollback.**
Le refus initial du vérificateur reste conservé dans les preuves et n'est pas
requalifié rétroactivement comme une exécution réussie de ce script.

## Résultat runtime

| Objet | Résultat indépendant |
|---|---|
| Hôte / acteur de lecture | crypto-restore-01, lecanada26 UID1001/GID1002, connecteur nommé |
| Source frontend servie | `1c3f0b5c6f7d7ab553106f4788f66d9c7c9e67ab` |
| Archive frontend | `1cf7d3ef9da134f6655c538951b646f3b2cc161cb77b7426fdd5b5bfcaf57d3c`, inchangée |
| Web | PID108817, active/running depuis09:26:25Z, NRestarts0, disabled au boot |
| API | PID79546, active/running depuis02:48:04Z, ExecMainStartTimestamp identique, NRestarts0, disabled au boot |
| Chemin / commande web réels | Nouvelle release1c3f0b5, cwd et argv kernel conformes ; nouveau BindReadOnlyPaths et seul drop-in attendu |
| Chemin / commande API réels | Ancienne release82cd63e, cwd et argv kernel complets inchangés |
| Drop-in installé | `/etc/systemd/system/crypto-operator-web.service.d/90-ui-modules-1c3f0b5.conf` ; root:root0644, SHA867b846d…f594e |
| Contenu HTTP | Huit nouveaux fichiers dist à leurs empreintes exactes, index SPA et index privé HTTPS conformes |
| API / proxy | healthz200, snapshot/market503 attendus avec présentation vide |
| Ancienne release / unités originales | 13 empreintes protégées inchangées |
| Source candidate / build / manifeste | Inchangés ; pas de nouveau build ni changement applicatif |
| Serve / réseau applicatif | Mapping privé conservé, pas de Funnel ; loopback8090/8181 conservé |
| Données / moteurs / expérience | Aucun raccordement, activation ou mutation |

Le journal09:25:50–09:27:10Z contient le changement de commande configurée du
web, puis un cycle stop/start du web à09:26:25Z et son écoute8181. Aucun cycle
API dans cette fenêtre ; PID et dates API concordent aussi avec le précontrôle.
NRestarts0 compte les redémarrages automatiques, pas tous les actes manuels.

## Refus original et cause

Sortie transmise par l'opérateur après les deux préflights réussis :
`READ_ONLY_CHECK_REFUSED / live / crypto-operator-api.service changed: ExecStart`.

Le vérificateur comparait toute la chaîne structurée rendue par
`systemctl show -p ExecStart`, y compris l'état d'exécution interne de cette
commande. Dans l'observation après reload :

| Champ | Avant | Après |
|---|---|---|
| ExecStart path, argv[], ignore_errors | Commande API épinglée, ignore_errors=no | Identiques |
| ExecStart.start_time | 2026-10-30 02:48:04 UTC | n/a |
| ExecStart.pid | 79546 | 0 |
| MainPID | 79546 | 79546 |
| ActiveEnterTimestamp / ExecMainStartTimestamp | 02:48:04 UTC | 02:48:04 UTC |
| /proc/79546/cmdline et cwd | Ancienne commande API | Ancienne commande API |

Les métadonnées dans ExecStart avaient changé ; le processus API ne présentait
pas de redémarrage ni de changement de commande. Le contrôle trop large était
un défaut du vérificateur, pas une preuve d'altération du runtime API.
Le message web « Current command vanished from the unit file » de09:26:24Z est
conservé ; il précède la bascule de commande et le redémarrage web autorisés.

## Correctif source, uniquement en lecture seule

Le comparateur extrait strictement `path`, `argv[]` et `ignore_errors` de la
représentation reconnue ; un format inconnu ou plusieurs entrées sont refusés.
Les champs volatils start_time/stop_time/pid/code/status ne sont plus assimilés
à la configuration. La comparaison de MainPID, ActiveEnterTimestamp, NRestarts,
cwd, bind, drop-ins, fichiers et protections reste stricte et indépendante.
Le argv kernel API est maintenant comparé intégralement ; son heure réelle de
démarrage est aussi confrontée à la baseline. Les identités des deux unités
restent relues après les GET.

15 tests stdlib passent : transition réelle avant/après reload, changements de
binaire/arguments/ignore_errors, formats inconnus/multiples, PID/date/restarts,
protections/chemins, nouvelle release indue et altérations du argv kernel.
Ils n'accèdent pas à une VM en CI et ne simulent aucune autorité privilégiée.

L'original `verify_frontend_release.py` de staging garde SHA
`f48a30e6ad514c14fe404a9c694d4b302c1d7a9b16f389dc986bcd0842b11296`.
Le manifeste, l'archive, le drop-in et les blocs d'activation d'origine sont
conservés sans changement. Version corrigée distincte en staging :
`verify_frontend_release_v2.py`, SHA
`02ce10b272b12dc62790d780fdf6725ee5eaa910da4a270f486f60d547bd91cb`.

Cette version a exécuté un contrôle `live` en lecture seule avec succès ;
[reçu final](evidence/frontend_1c3f0b5_20261030/POST_ACTIVATION_V2_FINAL.json).
Le correctif source n'a ni installé une unité ni redémarré quoi que ce soit.
Il n'accorde aucune nouvelle permission d'activation, de retry ou de passerelle.

## Audit du frontend réellement servi

[Résultats du navigateur](evidence/frontend_1c3f0b5_20261030/ACTUAL_PRIVATE_BROWSER.json) :
44 vues (11 routes ×2 largeurs393/1440 ×2 thèmes) et234 assertions PASS.
Zéro erreur de page, requête externe ou mutation de page, débordement horizontal.
Chaque réponse HTML privée est comparée à l'index du build exact.
Navigation mobile, settings, retour de focus, persistance clair/sombre après
reload, pagination8/avant/arrière/recherche/reset, et anciennes redirections
exercées. Six sources indisponibles et dates non disponibles restent visibles.
Les appels API observés répondent503 conformément à la présentation vide.
Aucune lecture GitHub réelle n'a été lancée depuis le tableau des travaux.

Playwright1.64.1 / Chromium156 avec sandbox, TLS normal, contextes neufs et
service workers bloqués. Résolution du seul hostname privé vers son IP Tailscale
connue dans ce navigateur ; aucune préférence DNS système modifiée. Les requêtes
autorisées sont GET/HEAD sur l'origine privée, avec les vraies réponses du
frontend/API ; **aucune fixture**. Identités API/web inchangées avant/après.
Deux captures réellement servies ont été inspectées : Accueil clair mobile,
Projet sombre desktop. Une première lecture de PNG mobile a expiré, puis sa
lecture suivante a réussi ; ce n'était pas un échec du navigateur ou de l'app.

Preuves VM :
- `~/crypto-install/validations/1c3f0b5…/POST_ACTIVATION_DIAGNOSIS_20261030T0926.json` ;
- `POST_ACTIVATION_V2_FINAL.json`, `VERIFIER_V2_REGRESSION.log`, `ACTUAL_PRIVATE_BROWSER.log` ;
- `~/crypto-install/audit-browser/published-1c3f0b5-20261030/captures/` ;
- RESULTS.json SHA`df8029ba6ff64ea20641a3e554e5495b33a10a79baa7b92d868be3cce27e6f8f`.

## Portée, consommation et prochaine action

L'exception d'activation est consommée. **Ne pas relancer publish_web_once.sh,
ne pas supprimer la custody et ne pas redémarrer de nouveau le web.**
Aucun rollback n'est justifié par les observations présentes. S'il devient
nécessaire pour cette tentative, appliquer uniquement le protocole borné déjà
autorisé, après inspection, puis utiliser le vérificateur corrigé pour la preuve.

Les vérifications depuis la VM ne prouvent pas la mise à jour du client Android
ou de sa PWA habituelle. Le prochain contrôle utilisateur est l'ouverture de
[l'URL privée](https://crypto-restore-01.tailfebca3.ts.net/), puis l'engrenage et les
deux thèmes. Le registre Projet reste éditorial, daté, distinct de l'état du VPS.

Aucune admission de données réelles, certification U8/L4, challenge d'egress
externe ou reprise après reboot n'est déduite de ces preuves. #286 reste ACTIVE
hors cette tentative ; aucun moteur, Telegram, collecteur, expérience, secret,
port public, paramètre scientifique ou sauvegarde n'a été modifié.
L'ancienne VM crypto-advisor-2 n'a pas été redémarrée.
