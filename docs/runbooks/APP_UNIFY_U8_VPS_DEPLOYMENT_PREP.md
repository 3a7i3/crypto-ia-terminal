# APP-UNIFY U8 — préparation du déploiement VPS isolé

Issue : #342
Parent : #323
Freeze : #286 — `ACTIVE_BURN_IN_IMMUTABILITY_GUARD`
Baseline historique de préparation : `main@bb3ac3bfc940423225dfb472a7762761bec59e3f`

Réconciliation sécurité finale : `main@042b229477a7c314e0e547709b46140f67fe7e69`, après fusion #344 et du complément #346 / clôture finale #257. Lockfile conservé sans reconstruction : SHA-256 `56f2c88d3ef112c395574c8e7962391305f531875ee02d21b7d0f41d2453c1ac`. La CI U8 exige désormais zéro vulnérabilité, sans tolérance d'échec audit.

## 0. Statut

Ce document prépare l'implémentation VPS. Il **n'autorise aucune exécution**.

Verdict de préparation visé :

`APP_UNIFY_U8_VPS_PREPARED_NOT_AUTHORIZED`

Le verdict runtime `APP_UNIFY_01_RUNTIME_CERTIFIED` ne peut être émis qu'après une mission d'exécution séparée et des preuves sur le VPS.

Référence runtime consignée sous #286 : `116634be0d3c015cce1cfa58be7da7255414fbfd`. Cette valeur n'est pas une nouvelle observation VPS.

## 1. Invariant principal

Le code Operator App ne doit jamais être déployé en avançant le checkout Advisor.

Architecture cible :

```text
/home/mathieu/crypto_ai_terminal
  └── runtime Machine gouverné
      └── databases/...                       lecture uniquement

/opt/crypto-ai-terminal/operator/
  ├── releases/<EXACT_40_HEX_SHA>/
  │   ├── source exact du SHA
  │   ├── .venv/                              venv propre à la release
  │   └── frontend/dist/                      build propre à la release
  └── current -> releases/<EXACT_40_HEX_SHA>

crypto-operator-api.service
  code: /opt/.../current
  facts: chemins absolus /home/mathieu/crypto_ai_terminal/databases/...
  bind: 127.0.0.1:8090

crypto-operator-web.service
  code: /opt/.../current/frontend
  bind: 127.0.0.1:8181
  proxy: 127.0.0.1:8090

Tailscale Serve
  HTTPS tailnet-only -> 127.0.0.1:8181
```

Le lien `current` est le seul pointeur de release. Un rollback revient au précédent lien et ne touche jamais au checkout Advisor.

## 2. Paquet source U8

- `deploy/app_unify_u8/crypto-operator-api.service`
- `deploy/app_unify_u8/crypto-operator-web.service`
- `deploy/app_unify_u8/requirements-operator-api.txt`
- `scripts/app_unify_u8_preflight.py`
- lecteurs Operator avec overrides de chemins explicites
- tests U8 associés

Le préflight est local uniquement : zéro SSH, zéro réseau, zéro systemd, zéro écriture runtime.

Exécution source attendue après fusion sur le SHA exact :

```bash
python scripts/app_unify_u8_preflight.py --expected-sha <EXACT_40_HEX_SHA>
pytest -q tests/test_app_unify_u8_preflight.py
cd frontend
npm ci
npm audit --audit-level=low
npm run build
npm test -- --run
npm run test:runtime
```

## 3. Gates avant toute mutation VPS

Toutes doivent être vraies.

| Gate | Exigence |
|---|---|
| G0 | #286 levée/clôturée pour l'epoch active, ou exception U8 bornée explicitement |
| G1 | APP-UNIFY U7 source certifié |
| G2 | SHA de déploiement exact, 40 hex, fusionné ; checks requis verts |
| G3 | #202 : disposition explicite du boundary permissions/secrets |
| G4 | #257 résolue dans la source retenue ; audit courant à zéro capturé sur le lockfile exact ; aucun `--force` |
| G5 | préflight U8 source PASS sur le SHA exact |
| G6 | checkpoint VPS READ-ONLY frais : services, ports, Tailscale, espace disque, versions |
| G7 | rollback revu avec précédente release identifiable |
| G8 | autorisation opérateur explicite d'exécution |

Échec d'une gate = `NO_DEPLOY`.

## 4. Checkpoint VPS READ-ONLY à collecter avant exécution future

Ne jamais afficher de secrets ni faire `env`, `systemctl show Environment` ou équivalent.

À capturer :

```bash
date -u
hostname
git -C /home/mathieu/crypto_ai_terminal rev-parse HEAD
git -C /home/mathieu/crypto_ai_terminal status --short

systemctl is-active crypto-advisor.service
systemctl show crypto-advisor.service \
  -p MainPID -p NRestarts -p ExecMainStartTimestamp -p ActiveState -p SubState --no-pager

systemctl is-active crypto-operator-api.service || true
systemctl is-active crypto-operator-web.service || true
systemctl is-active crypto-dashboard.service || true

ss -ltnp | grep -E ':(8090|8181|8050) ' || true
tailscale serve status
df -h / /opt /home
python3 --version
node --version
npm --version
```

Le SHA du checkout Advisor observé doit être enregistré comme un fait séparé. Il ne doit pas être déplacé par U8.

## 5. Construction future d'une release exacte

Variables opérateur :

```bash
SHA=<EXACT_40_HEX_SHA>
BASE=/opt/crypto-ai-terminal/operator
RELEASE="$BASE/releases/$SHA"
```

Prérequis de build : Node 20.19+ (ou version supportée par Vite 8) ; vérifier la version exacte du runner et de la future machine dans leurs preuves respectives. Aucun logiciel VPS n'est installé dans cette préparation.

La release est construite **directement à son chemin final** `$RELEASE`, jamais dans un répertoire temporaire renommé ensuite : un venv Python embarque des chemins absolus (shebangs, `pyvenv.cfg`) et un venv déplacé ou renommé n'est pas réutilisable sans reconstruction et vérification complète. Refuser tout `$RELEASE` préexistant, ainsi que tout `$RELEASE.FAILED-*` non examiné : un dossier partiel n'est jamais réutilisé silencieusement, jamais supprimé automatiquement (un échec le renomme `$RELEASE.FAILED-<horodatage>` pour inspection).

Procédure cible :

1. créer `$BASE/releases` avec ownership contrôlé ;
2. refuser si `$RELEASE` ou un `$RELEASE.FAILED-*` existe ;
3. cloner le dépôt directement dans `$RELEASE` sans utiliser le checkout Advisor ;
4. checkout détaché du SHA exact ; vérifier `git rev-parse HEAD == $SHA` et que le SHA est un ancêtre de `origin/main` ;
5. vérifier worktree propre ;
6. exécuter le préflight U8 avec ce SHA ;
7. créer `$RELEASE/.venv` (chemin final) ;
8. installer uniquement `deploy/app_unify_u8/requirements-operator-api.lock.txt` avec `--no-deps`, puis `pip check` (le fichier `requirements-operator-api.txt` reste la source des dépendances directes ; le verrou fige les transitives ; interpréteurs vérifiés : voir l'en-tête du verrou) ;
9. importer l'application avec `python -I` depuis le venv de la release ;
10. `npm ci` dans `frontend/` ;
11. exiger un audit npm courant à zéro et capturer le résultat de sécurité #257 ;
12. lancer tests/build frontend ;
13. écrire `PROVENANCE.txt` (SHA, versions, hash du lockfile npm, `pip freeze`, hash de chaque fichier de `dist`) ;
14. rendre la release non modifiable par le service applicatif.

Aucun `git pull` n'est autorisé dans `/home/mathieu/crypto_ai_terminal`.

## 6. Boundary de données runtime

L'API U8 lit explicitement les artefacts Machine via variables systemd. Aucune vérité n'est reconstruite depuis le frontend.

Chemins attendus :

- `operator_snapshot.json`
- `operator_runtime_manifest.json`
- `cryptoradar_market_snapshot.json`
- `ppl_comparison_snapshot.json`
- `financial_reconciliation_snapshot.json`
- `burn_in_status_snapshot.json`
- `runtime_service_snapshot.json`
- `market_microstructure_snapshot.json`
- `research_presentation/research_lab_snapshot.json`
- `research_presentation/research_strategy_board.json`

Tous restent sous le runtime Machine. Le service API reçoit `ProtectHome=read-only` et un `ReadOnlyPaths` explicite pour `databases/`.

Aucune `.env`, `.env.secrets`, clé exchange, token Telegram ou mot de passe n'est chargé par les unités U8.

## 7. Installation systemd future

Avant installation :

```bash
systemd-analyze verify "$RELEASE/deploy/app_unify_u8/crypto-operator-api.service"
systemd-analyze verify "$RELEASE/deploy/app_unify_u8/crypto-operator-web.service"
```

Sauvegarder les unités existantes si elles existent. Ne jamais sauvegarder de contenu secret dans les preuves GitHub.

Installer uniquement :

- `crypto-operator-api.service`
- `crypto-operator-web.service`

Le changement de lien `current` doit être atomique. En cas de mise à jour, capturer auparavant la cible précédente pour rollback.

Seuls les deux services Operator peuvent être démarrés/redémarrés dans la mission U8. **Advisor ne doit jamais être redémarré.**

## 8. Transport privé

Conserver la règle WEB-01B :

`tailnet HTTPS -> 127.0.0.1:8181`

Interdits :

- `tailscale funnel` ;
- bind `0.0.0.0:8181` ou `0.0.0.0:8090` ;
- ouverture publique d'un port Operator ;
- changement de la route Tailscale existante sans preuve fraîche et scope explicite.

Si le checkpoint montre que la route HTTPS tailnet vers 8181 existe déjà, U8 la conserve sans la recréer.

## 9. Preuves runtime requises après future exécution

### Processus et listeners

```bash
systemctl is-active crypto-operator-api.service
systemctl is-active crypto-operator-web.service
systemctl show crypto-operator-api.service -p MainPID -p NRestarts -p Result --no-pager
systemctl show crypto-operator-web.service -p MainPID -p NRestarts -p Result --no-pager
ss -ltnp | grep ':8090 '
ss -ltnp | grep ':8181 '
```

Exigence : 8090 et 8181 uniquement sur `127.0.0.1`.

### API GET-only

Vérifier au minimum :

- `GET /healthz`
- `GET /api/operator/v1/snapshot`
- `GET /api/operator/v1/portfolio`
- `GET /api/operator/v1/decision-pipeline`
- `GET /api/operator/v1/system-health`
- `GET /api/operator/v1/ppl-comparison`
- `GET /api/operator/v1/financial-reconciliation`
- `GET /api/operator/v1/market`
- `GET /api/operator/v1/burn-in`
- `GET /api/operator/v1/runtime-service`
- `GET /api/operator/v1/market-microstructure`
- `GET /api/operator/v1/research-lab`
- `GET /api/operator/v1/research-strategies`
- `GET /api/operator/v1/ppl-accounting-history` (artefact publié à part : `PPL_ACCOUNTING_HISTORY_PATH`, épinglé dans l'unité)

Une source présente et valide doit produire HTTP 200 ; une source absente ou invalide produit le 503 gouverné propre à sa route ; une source périmée reste lisible avec `freshness_classification` correcte. « HTTP 200 ou 503 » n'est donc **pas** un critère de succès : la matrice `route → source → précondition → statut → contenu` fait foi (dossier de revue PR #395). Les routes `/events` et `/storage` lisent `EVENT_CENTER_SNAPSHOT_PATH` / `STORAGE_SNAPSHOT_PATH`, non épinglés par l'unité : leur défaut relatif est résolu sous `WorkingDirectory` et répond 503 tant qu'une décision de provisionnement n'a pas été prise.

Les états `UNKNOWN`, `NOT_AVAILABLE`, `STALE` ou HTTP 503 gouvernés restent des résultats honnêtes ; ils ne doivent jamais être transformés en succès.

Un POST vers une route métier doit rester refusé.

### Non-interférence Advisor

Reprendre exactement les mêmes propriétés Advisor qu'au checkpoint préalable :

- PID ;
- `NRestarts` ;
- `ExecMainStartTimestamp` ;
- Active/SubState.

Toute modification inattendue = arrêt de la certification et rollback Operator.

### Browser/PWA

Depuis un client tailnet autorisé :

- Machine et Laboratoire chargent ;
- navigation mobile/desktop ;
- données API non mises en cache ;
- aucune route runtime servie depuis Cache Storage ;
- perte du transport -> état indisponible explicite ;
- aucune donnée synthétique ou recalcul frontend.

## 10. Rollback

Préconditions : cible précédente du lien `current` et backups des unités connus avant mutation.

Rollback U8 :

1. arrêter uniquement les services Operator si nécessaire ;
2. restaurer les unités Operator précédentes si elles ont changé ;
3. repointer atomiquement `current` vers la release précédente ;
4. `systemctl daemon-reload` ;
5. redémarrer uniquement `crypto-operator-api.service` et `crypto-operator-web.service` ;
6. revérifier 8090/8181, API et navigateur ;
7. revérifier Advisor inchangé.

Ne jamais :

- repointer le checkout Advisor ;
- restaurer une écoute publique ;
- supprimer un dataset ;
- supprimer CryptoRadar standalone ;
- redémarrer Advisor.

## 11. CryptoRadar standalone

Le retrait de `crypto-dashboard.service` n'appartient pas à U8.

Conditions minimales d'une future mission séparée :

- matrice de parité complète ;
- consommateurs réels inventoriés ;
- preuve navigateur Operator App ;
- rollback ;
- autorisation opérateur dédiée.

Verdict distinct requis pour le retirement.

## 12. Critère de sortie de #342

#342 peut être considérée préparée lorsque :

- paquet source complet ;
- tests ciblés PASS ;
- CI requise PASS au HEAD exact ;
- revue confirme zéro autorité trading/runtime ajoutée ;
- runbook et rollback cohérents ;
- aucune action VPS effectuée.

Verdict :

`APP_UNIFY_U8_VPS_PREPARED_NOT_AUTHORIZED`

L'étape suivante reste une gate d'exécution séparée, pas un déploiement automatique.
