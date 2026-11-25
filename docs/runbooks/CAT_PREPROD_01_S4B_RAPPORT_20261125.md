# CAT-PREPROD-01 — Préproduction HTTP isolée de S4-b (2026-11-25)

Règle CAT-PREPROD-01 (opérateur, 2026-11-25 20:47Z). Environnement : conteneur cloud Claude
isolé, **hors des deux VPS**, en boucle locale (127.0.0.1) seulement. Aucun secret, aucun
identifiant, aucun ledger PAPER, aucune donnée privée copiés. Données : fixtures et preuves
SYNTHETIC du dépôt uniquement.

## Résultat en une ligne

La route `GET /api/operator/v1/radar-projection` fonctionne de bout en bout derrière le serveur
web réel de l'application, et les 24 routes existantes répondent comme avant. **Mais la base de
production n'a pas pu être reconstituée à l'identique**, faute d'inventaire runtime de
`crypto-restore-01` : les étapes 1 à 3 restent **BLOQUÉES** jusqu'à l'exécution du script
d'inventaire lecture seule par l'opérateur.

## Étapes 1 et 2 — versions installées et comparaison avec `main`

> **Mise à jour S4-B-RV1 (2026-11-25).** Faits VPS transmis par l'opérateur et lignée exacte :
> voir [CAT_S4B_RV1_RECONCILIATION_PRODUCTION_20261125.md](../audits/CAT_S4B_RV1_RECONCILIATION_PRODUCTION_20261125.md).
> Le script d'inventaire a été révisé (liste fermée, montages du web résolus).

**Non observées.** Ce conteneur n'a aucun accès au VPS (ni SSH ni secret, conformément aux règles).
Ce que la source permet d'établir (preuves dans le dépôt, datées) :

| Élément | Dernier état connu par la source | Source |
|---|---|---|
| API servie | release composite `85376c5e-…-market-ea6d077a-scanner-<sha>` : base `85376c5e` + couches `agent-invocation c823cec1`, `storage-v1`, `reports`, `lab-sync`, `dpa 8872f635`, `market ea6d077a`, `scanner bc259b23`, puis Scanner 1.1.0 | `deploy/scanner_universe/cat-scanner-v11-root.sh`, `prep-v11.sh` |
| Python de l'API | CPython 3.11.17, venv de la release `85376c5e` | `docs/runbooks/evidence/frontend_1c3f0b5_20261030/RELEASE_MANIFEST.json`, scripts de déploiement |
| Web servi | `dist` de `/opt/cat-app/releases/CAT-SCANNER-REFONTE-<sha>` ; serveur `CAT-SYSTEM-AGENTS-599-891e1865/server/web01_local_frontend_server.mjs` | `cat-scanner-universe-root.sh` |
| Écarts connus avec `main` | `8872f635` (DPA) et `ea6d077a` (Market Observer) **ne sont pas dans `main`** ; routes `storage-inventory` et `lab-experiments` servies mais **absentes de tout commit GitHub** | `git merge-base`, `git log --all -S` sur 453 branches |

Conséquence : une API construite depuis `main` seul ne serait pas la production ; elle perdrait au
moins `storage-inventory` et `lab-experiments`. **Aucune fusion vers la production ne doit partir
de `main` sans cet inventaire.**

**Action demandée à l'opérateur (lecture seule, sans sudo, sans redémarrage)** :

```bash
bash deploy/preprod/cat_prod_inventory_readonly.sh > cat-prod-inventory.json
```

Le script imprime la configuration systemd (noms des variables seulement, plus les chemins
`OPERATOR_*_PATH`), l'identifiant git de chaque fichier source de l'API et du web servis, les
versions Python et paquets, et le code HTTP de chaque route connue. Aucun corps de réponse ni
donnée PAPER. Avec ce fichier, chaque fichier servi est retrouvé dans l'historique GitHub ou
prouvé absent, et la base de production est reconstituée exactement.

## Étape 3 — base compatible reconstituée (approximation déclarée)

Deux variantes, faute de mieux :

| Variante | Contenu | Résultat |
|---|---|---|
| A | `main@a2ec703` + S4-b | serveurs démarrés, 25 routes testées en HTTP (ci-dessous) |
| B | A + `agent_invocation_reader.py` et `agent_schedule.py` de `ea6d077a` (lignée production connue) | `test_s4b_service.py` + `tests/scanner_universe` : 92 réussis |

Les couches `storage-v1`, `reports` et `lab-sync` ne sont pas reconstituables : leur source n'est
pas dans GitHub.

## Étapes 4 à 6 — intégration et serveur HTTP isolé

| Élément | Valeur |
|---|---|
| Python / paquets | CPython 3.11.18 ; FastAPI 0.136.1, Starlette 1.0.0, Uvicorn 0.46.0, httpx 0.28.1, Pydantic 2.13.4 (versions de `requirements-vps-frozen-20260718.txt` ; les versions réelles du VPS restent à confirmer par l'inventaire) |
| API | `python -B -m uvicorn observability.operator_api.app:app --host 127.0.0.1 --port 8090 --no-access-log` (même commande que l'unité de production) |
| Web | `node frontend/scripts/web01_local_frontend_server.mjs`, `CAT_WEB_PORT=18181`, `dist` construit depuis `main@a2ec703` (Node 22.23.5 ; `index.html` sha256 `80d2c37f…a546d`) |
| Données | `OPERATOR_RADAR_EXPORT_PATH` = export du lot R1-B (`r1b_syn_01_btc_atom`, DEEP_OBSERVATION) ; `OPERATOR_SCANNER_UNIVERSE_PATH` = rejeu du producteur Scanner (`collect --replay`) sur le relevé synthétique `tests/radar_selection/evidence/scanner/runs/20261117T163500Z`, c'est-à-dire **les mêmes octets de catalogues** que le lot |

## Étapes 6 et 7 — routes servies et compatibilité

Preuve : [`evidence/preprod_s4b_20261125/HTTP_CHECKS.json`](evidence/preprod_s4b_20261125/HTTP_CHECKS.json)
(script `http_checks.py` dans le même dossier).

- **25 routes GET** interrogées directement (API) puis par le serveur web : mêmes codes HTTP,
  `Cache-Control: no-store` partout. Corps identiques, sauf `radar-projection` et
  `scanner-universe`, qui ne diffèrent que par l'heure de service (`served_ms`, `age_ms`).
- Routes sans publication configurée : **503 avec leur code typé habituel** (`SNAPSHOT_MISSING`,
  `MARKET_FLOW_NOT_CONFIGURED`…), comme avant S4-b.
- `radar-projection` : 200, `radar-projection-service/1.0.0`, `SYNTHETIC`,
  `runtime_proof: false`, publication `FRESH`, **E1 `CATALOGUE_PROVENANCE_MATCH`** (4 ×
  `SAME_CATALOGUE_BYTES`), `scanner_universe.sha256` de la projection toujours `null`, candidats
  `1 kraken:spot:ATOM/USDT`, `2 mexc:spot:ATOM/USDT`. POST par le web : 405.
- `spot-radar/*` : 502 `OPERATOR_API_UNAVAILABLE`, attendu : ce service n'existe pas dans `main`.

## Étape 8 — preuves navigateur

Chromium (Playwright), 384 × 832, échelle 2, données réellement servies (aucune route simulée).
Captures dans le dossier du projet `s4b_preprod/` :
1. `1-accueil.png` : accueil servi ;
2. `2-marche-scanner.png` : Marché → Scanner, inchangé, lit la publication Scanner servie ; le
   relevé du 2026-11-19 est correctement affiché **périmé** (« Indisponible », aucune paire courante) ;
3. `3-route-radar-projection.png` : réponse JSON de la nouvelle route via le serveur web.

Aucune interface Radar n'est ajoutée (S4-c non ouvert).

## Étape 9 — non-régression

| Contrôle (Python 3.11.18, FastAPI de production) | Résultat |
|---|---|
| `tests/test_operator_api*.py`, `tests/test_web01*.py`, `tests/radar_projection`, `tests/radar_selection`, `tests/scanner_universe`, `tests/radar_composite`, `tests/market_flow` | **1 169 réussis, 0 échec** (après correction d'une docstring qui citait un module surveillé par un test d'isolation de Market Flow) |
| `tests/radar_projection` seul | 413 réussis (358 S4-a + 55 S4-b) |

## Limites

- Base de production **non reconstituée à l'identique** (étapes 1 à 3 bloquées, voir ci-dessus).
- Données SYNTHETIC uniquement ; aucune preuve runtime. SOURCE PROOF ≠ RUNTIME PROOF.
- Le relevé Scanner rejoué est daté : la route Scanner sert donc un univers périmé, ce qui est le
  comportement attendu.
