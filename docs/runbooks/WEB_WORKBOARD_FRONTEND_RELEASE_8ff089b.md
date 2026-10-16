# Release frontend 8ff089b — synchronisation GitHub (#451) + registre de 32 missions

Statut : **PRÉPARÉE · NON ACTIVÉE**. Aucune installation, aucune écriture systemd, aucun redémarrage n'a été faite
ni n'est autorisée par ce document. [#286](https://github.com/3a7i3/crypto-ia-terminal/issues/286) reste actif.
Une activation exige une **nouvelle exception #286** (l'exception GOV-286-WEB-FRONTEND-bdca77f est consommée) et
l'exécution par l'opérateur. Ce runbook complète `WEB_WORKBOARD_FRONTEND_RELEASE.md` (release bdca77f, historique).

## Contenu du paquet

| Élément | Valeur |
|---|---|
| Source frontend (`SOURCE_SHA`, aussi `source_merge_sha`) | `8ff089b26cd15190e8be34c11b75b0b17c471ef6` (merge de #451) |
| Archive | `workboard-frontend-8ff089b.tar.gz`, 149 789 octets, 9 fichiers |
| SHA-256 de l'archive | `a9a17e8b0a994ccf7aed90c187ec90ce8fedcbaad527db37cb1a052a3f683136` |
| Portée | `FRONTEND_ONLY` : `frontend/dist/*` + `frontend/scripts/web01_local_frontend_server.mjs` |
| Dossier de release | `/opt/crypto-ai-terminal/operator/releases/8ff089b26cd15190e8be34c11b75b0b17c471ef6/` |
| Drop-in créé | `/etc/systemd/system/crypto-operator-web.service.d/99-workboard2.conf` (création exclusive) |

Ce que la release apporte par rapport au paquet bdca77f : le bouton « Actualiser depuis GitHub » (relevé à la demande,
aperçu des différences, dernier relevé complet conservé), les quatre statuts séparés (GitHub / intégration source /
déploiement / certification) et le registre corrigé de **32 missions** (au lieu de 29). Rien d'autre : pas de backend,
pas de dépendance, pas d'environnement.

Empreintes par fichier (manifeste de l'archive) :

```
9a11a602…  frontend/dist/assets/index-BXikawIc.css
01b0066d…  frontend/dist/assets/index-CfyC7Dvh.js
bc969e04…  frontend/dist/icons/operator-192.png
9fa2842f…  frontend/dist/icons/operator-512.png
95ecf1af…  frontend/dist/index.html
aa7204dc…  frontend/dist/manifest.webmanifest
ff9d4dbc…  frontend/dist/pwa-policy.js
8acfc518…  frontend/dist/sw.js
bcf42a66…  frontend/scripts/web01_local_frontend_server.mjs
```
(valeurs complètes dans `manifest.json` de l'archive.)

## Provenance et vérifications faites (source, pas VPS)

- Deux worktrees propres de `8ff089b`, chacun `npm ci` + `npm run build` (Node v22.22.0, npm 10.9.4, Python 3.13) :
  **même SHA-256** d'archive. La reproductibilité avec d'autres versions de Node/npm n'est pas revendiquée.
- `scripts/build_workboard_frontend_package.py` refuse un checkout `frontend/` sale ; il n'installe ni ne déploie rien.
- Répétition en bac à sable : serveur Node du paquet extrait sur `127.0.0.1:8181`, puis `verify_served` du helper : les 8
  assets `dist` et `/direction/travaux` correspondent octet pour octet. **C'est une répétition locale, pas une preuve VPS.**
- Préflight du helper simulé avec un état hôte moqué : sortie `INSPECT_ONLY_NO_MUTATION` (exemple plus bas).
- Le service worker n'intercepte que l'origine de l'application (`pwa-policy.js`, `url.origin !== scopeOrigin`) : les
  réponses de `api.github.com` ne sont jamais mises en cache par lui. L'unité web n'envoie pas de CSP : les appels
  navigateur vers GitHub ne sont pas bloqués par elle.
- Tests : `tsc --noEmit`, `vitest` (401 passent), `npm run build`, `pytest tests/test_workboard_frontend_release.py` (10).

## Aperçu

Captures de la source (GitHub **simulé**, aucune preuve runtime) : `docs/roadmap/github_roadmap_sync_01/captures/`
(avant relevé, aperçu du premier relevé, tableau avec statuts séparés, échec réseau avec dernier relevé conservé). Elles
proviennent du même code frontend que l'archive (le PR de cette release ne modifie pas `frontend/`).

## Limite de l'accès GitHub anonyme (à lire avant d'activer)

La synchronisation lit `api.github.com` **sans jeton, depuis le navigateur de chaque lecteur**.

- Quota GitHub anonyme : **60 requêtes/heure par adresse IP**. Un relevé complet coûte **≈ 45-50 requêtes** (budget dur 55).
  Un relevé consomme donc l'essentiel de l'heure ; un second dans la même heure, ou un autre lecteur derrière la même
  IP (tailnet, NAT), est refusé (`RATE_LIMIT_INSUFFICIENT` / `RATE_LIMITED`) : l'erreur est affichée, rien n'est
  effacé, le dernier relevé complet reste affiché.
- La limite n'a **pas été mesurée en conditions réelles** : le bac à sable passe par un proxy authentifié (quota 15 000).
  Elle est lue dans la documentation GitHub et gérée par le lecteur (`/rate_limit` non décompté, refus à moins de 12
  requêtes restantes ou si le coût dépasse le quota).
- Le poste du lecteur doit joindre `api.github.com` (le tailnet privé n'implique pas un accès sortant). Sinon : erreur
  `NETWORK` visible, tableau éditorial intact.
- Usage visé : ponctuel, une personne. Palier suivant si cela ne suffit pas : route serveur GET-only avec jeton en
  lecture seule gardé côté serveur et cache ETag. **Non implémenté, non inclus dans cette release** (il toucherait
  l'unité web : gate distincte).
- La synchronisation montre l'état **GitHub**. Elle n'établit ni déploiement VPS, ni certification : ces colonnes
  restent celles du registre éditorial (activation bdca77f « rapportée par l'opérateur », jamais « observée »).

## Préflight (lecture seule, aucun root)

1. Récupérer l'archive et le helper depuis les sources revues ; `sha256sum` des deux sur l'hôte, comparer aux valeurs
   de l'exception. Toute différence arrête la procédure.
2. Baseline lecture seule : `hostname`, `date -u`,
   `systemctl show crypto-operator-web.service crypto-advisor.service crypto-operator-api.service --property=Id,ActiveState,SubState,MainPID,NRestarts,ExecMainStartTimestamp`,
   `systemctl show crypto-operator-web.service --property=FragmentPath,WorkingDirectory,DropInPaths`,
   `readlink /opt/crypto-ai-terminal/operator/current`, `ls /etc/systemd/system/crypto-operator-web.service.d/`.
   Attendu : WorkingDirectory = `…/releases/bdca77f9bcf306c17846985faef870844fdd1334/frontend`, `99-workboard.conf`
   présent, **ni** `99-workboard2.conf` **ni** dossier `releases/8ff089b…`.
3. `python3 activate_workboard_frontend.py --archive <archive> --sha256 a9a17e8b…3136` → attendu
   `"disposition": "INSPECT_ONLY_NO_MUTATION"`, `previous_web` = release bdca77f, `source_merge_sha` = 8ff089b…
   Sinon : `PREVIOUS_RELEASE_OR_OVERRIDE_CHANGED`, `WRONG_RELEASE_SCOPE`, `ARCHIVE_HASH_OR_SIZE_MISMATCH`,
   `PROTECTED_SERVICE_NOT_RUNNING` : **stop**, rapporter. Le helper ne croit pas le rapport d'activation précédente :
   il refuse si l'hôte ne sert pas réellement bdca77f.

## Activation (hors périmètre de ce message, nécessite l'exception)

`--activate` (root, opérateur) crée la release, crée `99-workboard2.conf` (trie après `99-workboard.conf`, donc prend
le dessus), recharge systemd, redémarre **uniquement** `crypto-operator-web.service`, vérifie chaque asset servi et
`/direction/travaux` octet pour octet sur `127.0.0.1:8181`, compare Advisor/API/`current` avant/après. En cas d'échec,
il retire `99-workboard2.conf`, recharge et redémarre le web seul : retour à bdca77f.

Le bloc `final_block.sh` v4 est **épinglé à bdca77f** et ne doit pas être réutilisé tel quel. Un bloc v5 (mêmes phases,
nouvelles empreintes, nouveaux noms) n'est pas préparé ici : il le sera après accord de l'opérateur sur ce paquet et
ce helper, puis relu avant toute exception.

## Rollback

- Automatique : voir ci-dessus (échec du helper ou d'une vérification de bytes).
- Manuel (root, web seul) : supprimer `/etc/systemd/system/crypto-operator-web.service.d/99-workboard2.conf` (et
  **uniquement** celui-ci ; `99-workboard.conf` et `90-ux-fr.conf` restent), `systemctl daemon-reload`,
  `systemctl restart crypto-operator-web.service`, puis vérifier `WorkingDirectory` = release bdca77f, HTTP 200 sur
  `/direction/travaux`, et PID/heure de démarrage d'API et d'Advisor inchangés. Garder le dossier `8ff089b…` pour
  analyse (il bloque une nouvelle tentative tant qu'il existe).
- Hors tâche du rollback : API, Advisor, `current`, données, epoch, PPL/FIN, stratégie, sizing.
- Limite : si bdca77f n'est pas réellement le répertoire servi (activation seulement rapportée), le préflight s'arrête
  avant toute mutation ; le rollback reviendrait de toute façon à l'état servi avant l'ajout de `99-workboard2.conf`.

## Après activation (preuves séparées)

Preuve navigateur sur la page tailnet : 32 lignes, filtres, navigation mobile, panneau de synchronisation (un seul
relevé réel, en notant l'erreur de quota éventuelle). Consignée sur #430 comme résultat à part. Cette release ne
certifie ni U8/L4 ni le runtime.
