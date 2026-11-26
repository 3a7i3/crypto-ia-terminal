# CAT S4-B-RV1 — Réconciliation production ↔ GitHub (2026-11-25)

Mission opérateur 2026-11-25 21:45Z. Statut : **PLAN PRÉSENTÉ, RIEN N'EST RÉCUPÉRÉ NI MODIFIÉ.**
Aucune récupération de source, aucune modification runtime, aucun redémarrage, aucun déploiement.
Règles appliquées : CAT-DATA-01 et CAT-PREPROD-01 telles que publiées
(#578 commentaire 7174275262, #568 commentaire 7174278673). SOURCE PROOF ≠ RUNTIME PROOF.

## 0. Réserves source de #613 (traitées dans ce lot)

| Réserve | Correction | Preuve |
|---|---|---|
| Script d'inventaire : risque de divulgation | `deploy/preprod/cat_prod_inventory_readonly.sh` réécrit en **liste fermée** : aucune ligne de configuration n'est recopiée. ExecStart réduit au programme, au module (`-m`) ou au script, et à `--host`/`--port` ; Environment réduit aux **noms**, plus la valeur des seules variables `*_PATH` qui ont la forme d'un chemin absolu simple et des `*_S`/`*_MS`/`*_PORT` entières ; drop-ins réduits aux **noms de directives** et à leur empreinte git ; EnvironmentFiles : chemins seulement, jamais lus ; codes de route filtrés par forme. Toute autre valeur devient `<REDACTED>`. | `tests/test_cat_prod_inventory_readonly.py` : secrets plantés dans ExecStart, Environment (y compris valeur entre guillemets avec espaces), drop-in et `.env` ; aucun n'apparaît. |
| Script : fichiers servis mal localisés | Le web servi est **monté par-dessus** son WorkingDirectory (`BindReadOnlyPaths` des drop-ins Scanner) : les fichiers présents sous `CAT-FOOTPRINT-FINANCE-V6-RC1/frontend` ne sont pas ceux servis. Le script traduit maintenant chaque chemin vu par le service en fichier hôte via ses montages avant d'en calculer l'empreinte. | même test : dist et serveur servis ≠ fichiers sur disque sous WorkingDirectory. |
| `bounded_file.py` : substitution concurrente d'un parent | Le contrôle `is_symlink()` puis `open(chemin)` laissait une fenêtre. Le chemin est maintenant ouvert **composant par composant** depuis un descripteur de répertoire : parents en `O_DIRECTORY \| O_NOFOLLOW`, dernier composant en `O_NOFOLLOW \| O_NONBLOCK`, chacun relatif au descripteur précédent. Un composant qui est un lien au moment de son ouverture est refusé par le noyau (`ELOOP`/`ENOTDIR` → `INVALID_PATH`). `..` est refusé. | `test_s4b_service.py` : 4 tests (parent remplacé par un lien après tout contrôle, dernier composant remplacé, contrôle par nom neutralisé, `..`). Les 4 échouent avec l'ancienne version, réussissent avec la nouvelle. |

## 1. Lignée de l'API servie (établie par la source et par les faits VPS transmis)

Faits VPS (lecture seule, transmis par l'opérateur) : `app.py` servi = blob `88ebace1…`, `app.py` de
`main` = `8ca1d4fd…` ; `scanner_universe_reader.py` identique (`38075b89…`) ; `storage-inventory` 200,
`lab-experiments` 200, `scanner-universe` 200, `radar-projection` 404, `market-microstructure` 503.

Release servie (scripts `deploy/scanner_universe/*`) :
`85376c5e-agent-invocation-c823cec1-storage-v1.hiA7Jf-reports.kxGnag-lab-sync.kNQ7rm-dpa-8872f635-market-ea6d077a-scanner-bc259b23`
(+ Scanner 1.1.0 : `universe.py`, `schema.py` seulement).

| Couche | Source GitHub | Dans `main` | `app.py` de la couche |
|---|---|---|---|
| base `85376c5e` | oui | oui | `39592cdd` |
| agent-invocation `c823cec1` | oui | oui | `f68dcd71` |
| **storage-v1** (`hiA7Jf`) | **non** (fabriquée sur le VPS) | non | inconnu |
| **reports** (`kxGnag`) | **non** | non | inconnu |
| **lab-sync** (`kNQ7rm`) | **non** | non | inconnu |
| DPA `8872f635` | oui, branche `claude/project-thread-ylbw7g` (PR #601 ouverte) | **non** | inchangé (`f68dcd71`) |
| Market Observer `ea6d077a` | même branche, PR #601 | **non** | inchangé (`f68dcd71`) |
| Scanner `bc259b23` → 1.1.0 `979b450b` | oui | oui | appliqué **en greffe** (`prep.sh`) : une ligne d'import + bloc `# SCANNER-V1` ajoutés à l'`app.py` servi |

**Preuve que les couches VPS ont modifié `app.py`.** La greffe Scanner de `prep.sh`, rejouée
exactement sur `f68dcd71` (dernier `app.py` connu de la lignée), donne `8a38b51a…`, et sur `39592cdd`
donne `7ae8a06b…` ; aucun n'est `88ebace1`. Donc `88ebace1` = `app.py` des couches storage/reports/lab-sync
(source absente) + greffe Scanner. L'objet `88ebace1` n'existe dans **aucune** des 453 branches ni des
444 refs de PR.

**Ce que `main` a de plus et de moins.** Routes de `main` = routes de `c823cec1` + `scanner-universe`
(25 au total, dont le POST gouverné du programmateur d'agents). `main` **n'a pas** `storage-inventory`,
`lab-experiments`, ni la route éventuelle de la couche `reports`, ni les agents DPA et Market Observer
(`agent_invocation_reader.py`, `agent_schedule.py` et `agent_bench/observation/*` de `ea6d077a`).

## 2. Lignée du web servi

| Élément | Chemin vu par le service | Fichier réellement servi | Source GitHub |
|---|---|---|---|
| WorkingDirectory | `/opt/cat-app/releases/CAT-FOOTPRINT-FINANCE-V6-RC1/frontend` | — | RC `328be7e3` (branche `release/cat-footprint-finance-v6-rc1`), source `16a9d697`, PR #589 fusionnée ; contenu repris dans `main` (ex. `paper-balance-history.mjs`) |
| Serveur | `…/V6-RC1/frontend/scripts/web01_local_frontend_server.mjs` | monté depuis `CAT-SYSTEM-AGENTS-599-891e1865/server/web01_local_frontend_server.mjs` | `891e1865`, dans `main` (à confirmer par l'empreinte) |
| dist | `…/V6-RC1/frontend/dist` | monté depuis `CAT-SCANNER-REFONTE-<sha>/dist` | construit sur le VPS depuis `~/cat-market-block/web/frontend` (source Web du bloc Market) + fichiers Scanner de la PR ; le bundle appelle `storage-inventory`, `data-provenance-auditor`, `market-observer` (contrôle de `prep.sh`), que le frontend de `main` n'appelle pas |

Conséquence : l'information « frontend = V6-RC1 » décrit le WorkingDirectory, **pas** le dist servi.
La source du dist servi (bloc Market) n'est pas identifiée dans GitHub : `UNKNOWN` jusqu'à l'inventaire.

## 3. Composants servis absents de GitHub (liste précise à ce stade)

| # | Composant | Statut | Fichiers concernés |
|---|---|---|---|
| A1 | `observability/operator_api/app.py` servi (`88ebace1`) | **ABSENT** (prouvé) | 1 fichier |
| A2 | Lecteur(s) et route `storage-inventory` (couche storage-v1) | **ABSENT** (aucune occurrence Python dans l'historique) | inconnus : à lister par l'inventaire (`api_tree` classé `ABSENT`) |
| A3 | Lecteur(s) et route `lab-experiments` (couche lab-sync) | **ABSENT** | idem |
| A4 | Couche `reports` | **ABSENT**, route non identifiée | idem ; `openapi_paths` de l'inventaire la nommera |
| A5 | DPA `8872f635` + Market Observer `ea6d077a` | dans GitHub, **hors `main`** (PR #601 ouverte) | `agent_invocation_reader.py`, `agent_schedule.py`, `agent_bench/observation/{agents,change_mission,common,market_observer,observability_cartographer,repo_architect,runtime_observer}.py`, registre et vues agents du frontend |
| A6 | Source du web servi (bloc Market + Scanner refonte), dont la vue stockage | **UNKNOWN** | `~/cat-market-block/web/frontend`, `~/cat-scanner-universe-block/web-refonte/frontend` (classés par `build_sources`) |

## 4. Compléter l'inventaire (lecture seule, opérateur)

1. Sur `crypto-restore-01`, utilisateur normal, sans sudo :
   `bash cat_prod_inventory_readonly.sh > cat-prod-inventory.json` (version de ce lot, `inventory_schema` 2.0.0).
   Relire le fichier avant transmission : il ne contient que des noms, chemins, empreintes et codes.
2. Sur un poste avec le dépôt à jour :
   `python3 -I deploy/preprod/cat_inventory_match.py cat-prod-inventory.json --ref origin/main`.
   Chaque fichier servi est classé `SAME_AS_REF`, `IN_GITHUB_OTHER` ou `ABSENT`. La liste A1–A6 devient
   exacte (fichier par fichier).

## 5. Plan minimal de récupération et de réconciliation (À VALIDER, NON EXÉCUTÉ)

Principe : **ne rien reconstruire**. Récupérer les fichiers servis tels quels, les publier sur une
branche dédiée, puis les réconcilier avec `main` par PR. La production reste intacte à chaque étape.

| Étape | Action | Qui | Écrit où | Réversible |
|---|---|---|---|---|
| P1 | Inventaire + rapprochement (section 4) | opérateur, puis Claude | rien sur le VPS ; rapport dans le dépôt | oui |
| P2 | Exporter **uniquement** les fichiers classés `ABSENT` (liste fermée issue de P1), en archive avec SHA-256 par fichier, **après relecture par l'opérateur** (aucun `.env`, aucune donnée, aucun journal) | opérateur | `~` de l'opérateur, puis transfert | oui |
| P3 | Publier ces fichiers **à l'octet près** sur une branche `recovery/prod-api-<date>` à partir de la base de lignée connue (`ea6d077a`), un commit par couche (storage-v1, reports, lab-sync, `app.py` servi), en vérifiant que chaque blob = empreinte de l'inventaire | Claude | GitHub (branche, PR Draft) | oui |
| P4 | Réconcilier avec `main` dans une PR distincte : fusionner #601 (DPA, Market Observer) ou ses fichiers servis, puis la branche de récupération ; conflit attendu dans `app.py` seulement (routes Scanner déjà dans `main`) | Claude, GO opérateur | PR | oui |
| P5 | Rebaser #613 (S4-b) sur cette base réconciliée ; préproduction CAT-PREPROD-01 refaite sur la base **exacte** de production (mêmes paquets : Starlette 1.10.0, Pydantic 2.14.3, AnyIO 4.16.0) ; comparaison route par route avec l'inventaire | Claude | conteneur isolé | oui |
| P6 | Release candidate = production actuelle + S4-b seulement ; GO runtime G7 distinct | opérateur | — | — |

Fichiers concernés par P3–P4 (connus à ce jour) : `observability/operator_api/app.py`, les modules
storage/reports/lab-sync à nommer par P1, `observability/operator_api/agent_invocation_reader.py`,
`observability/operator_api/agent_schedule.py`, `agent_bench/observation/*.py` de `ea6d077a`, et pour le
web les sources du bloc Market (P1, `build_sources`). Aucun fichier PAPER, PPL, FIN ou Advisor.

## 6. Fonctionnalités à préserver dans la release candidate

| Domaine | Fonctionnalité servie | Contrôle de non-régression |
|---|---|---|
| API | les 24 routes GET de `main` avec leurs codes actuels (dont `market-microstructure` 503 typé) | codes HTTP = inventaire |
| API | `storage-inventory` 200, `lab-experiments` 200, route `reports` (à identifier) | idem, `schema` identique |
| API | `agent-invocations/{repository-cartographer, data-provenance-auditor, market-observer}` + `history`, `schedule` et POST gouverné du programmateur | idem ; POST non exercé |
| API | `scanner-universe` 1.1.0 (actifs par base, classes) | publication réelle lue, statut et compte de paires |
| API | `radar-projection` (S4-b) : **seul ajout** | 503 `RADAR_PROJECTION_NOT_CONFIGURED` tant que non alimenté |
| Web | serveur `891e1865` : relais GET/HEAD, `paper-balance-history` | codes via le web = codes API |
| Web | Finance/Wallet V6 : solde PAPER 1/7/30 j, ordres en attente, carnet BTC/ATOM, aperçu BBO, synchro Workboard, Footprint | `verify_rc_preservation.mjs` (18 contrôles) |
| Web | Marché → Scanner (refonte), registre d'agents avec mini-terminal DPA et Market Observer, vue stockage, laboratoire | captures 384 px et 1440 px avant/après |

Hors RC : S4-c (interface Radar), observation approfondie, Décision, agents nouveaux.

## 7. Décisions demandées à l'opérateur

1. Lancer l'inventaire révisé (section 4) et transmettre le JSON.
2. Valider P2–P3 (export et publication à l'octet près des seuls fichiers `ABSENT`) ou choisir une autre voie.
3. Choisir la voie de réconciliation de #601 (fusion de la PR, ou reprise des seuls fichiers servis).

#613 reste en Draft jusqu'à ces décisions.
