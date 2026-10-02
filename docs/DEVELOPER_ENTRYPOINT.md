# Entrée développeur canonique

Lire cette page avant de reprendre Crypto AI Terminal, puis
[CLAUDE.md](../CLAUDE.md) et la mission applicable. Reconstruction documentaire
DOC-CANON-01 / [#340](https://github.com/3a7i3/crypto-ia-terminal/issues/340), depuis
`main@053c8540a012b2c2c7a9bc5e76585a1425858f73`, le 2026-10-02.
Aucune observation VPS n'est réalisée par cette page.

## 1. Ce qu'est le projet

Une infrastructure quantitative expérimentale : observations marché,
expérience PAPER, lifecycle PPL, finances FIN, datasets immuables, recherche
reproductible et application opérateur. L'objectif est de comprendre la machine
et ses preuves depuis une app, sans confondre présentation et autorité.

## 2. Où sont les autorités

| Document / mission | Fonction |
|---|---|
| [README](../README.md) | découvrir le projet et trouver les entrées |
| [CLAUDE](../CLAUDE.md) | invariants et méthode de travail |
| [CURRENT_TASK](../CURRENT_TASK.md) | petit pointeur de tranche ; vérifier l'état GitHub |
| [#285](https://github.com/3a7i3/crypto-ia-terminal/issues/285) | priorisation actuelle |
| [#148](https://github.com/3a7i3/crypto-ia-terminal/issues/148), [ROADMAP](../ROADMAP.md) | archive / chronologie, pas priorisation actuelle |
| [#323](https://github.com/3a7i3/crypto-ia-terminal/issues/323) | cockpit unifié et séquence source/UI |
| [#282](https://github.com/3a7i3/crypto-ia-terminal/issues/282), [#286](https://github.com/3a7i3/crypto-ia-terminal/issues/286) | observations burn-in datées / garde-fou |
| [#315](https://github.com/3a7i3/crypto-ia-terminal/issues/315) | OperatorDecision : Gate S source accepté, Gate O ouvert à cette base |

Lire les mises à jour, commentaires et verdicts réels ; une issue OPEN ne
signifie pas que toutes ses phases sont autorisées. Une vieille page racine ne
remplace ni la décision opérateur ni les gates du domaine.

## 3. Machine et Laboratoire

**Machine** répond « que fait mon expérience ? » : Direction (`/direction`),
portfolio/FIN, lifecycle, burn-in, services, CryptoRadar Scanner/LMI et provenance
sous `/paper-live`. **Lab** répond « qu'ai-je appris ? » : datasets, replay,
diagnostics et `/research/strategies` sous `/research`.
Les routes profondes historiques sont conservées ; les autorités sont séparées.

Les critères et rangs du tableau Lab sont des résultats prépubliés, pas des
calculs React. Sans assessment, aucun vert implicite ; sans source, aucun
catalogue vide certifié. Les fixtures visuelles ne prouvent aucune stratégie
active, performance réelle ou publication scientifique admise.

## 4. Source et runtime : deux preuves distinctes

| Référence à cette reconstruction | Valeur | Nature |
|---|---|---|
| Base source | `053c8540a012b2c2c7a9bc5e76585a1425858f73` | merge #339, après U4 #337 ; base historique de ce document, pas HEAD perpétuel |
| Runtime source | `116634be0d3c015cce1cfa58be7da7255414fbfd` | référence consignée sous #286 |
| Epoch | `BURN-IN-EPOCH-01-20260926T064144Z` | identité consignée sous #282/#286 |
| Config hash | `9d9de1af4ac5aa5afc030ff64b08eeada0e1388a5d87c6475cb39c042be230d4` | identité consignée sous #286 |

**SOURCE STATE ≠ DEPLOYED RUNTIME STATE**. Ne pas aligner ces SHAs par un
déploiement. Pour une preuve, noter : producteur/autorité, HEAD, epoch/config,
timestamp, boundary/population, freshness, limitations et verdict. Ne pas
présenter un checkpoint historique comme état instantané du VPS.

Vérification source locale/read-only :

```bash
git status --short
git rev-parse HEAD
git ls-remote origin refs/heads/main
```

Vérifier ensuite le HEAD exact de la PR, ses checks/reviews/threads et la gate.
Aucun verdict source ne certifie l'alimentation des artifacts en production.

## 5. Ce qui est gelé

Sous #286 : runtime déployé, stratégies/signaux/seuils, calibration, risk/sizing,
`PB_MAX_POSITIONS`, config, capital, manifest, epoch et autorités PPL/FIN.
Aucun restart Advisor, systemd/VPS, Watchdog/FIN activation, TESTNET/LIVE,
écriture exchange ou retrait du dashboard/notifications dans une mission
source/UI. Les checkpoints VPS restent READ-ONLY dans leur mission séparée.
Ne pas ouvrir `.env` ou imprimer des clés pour comprendre l'architecture.

Research travaille offline sur des datasets immuables et prépare une **future**
epoch ; jamais de feedback vers l'epoch qui produit ces données. UNRESOLVED IS
DATA. Un freeze ne se lève ni avec un nombre de trades, ni avec un merge, ni
avec une hypothèse rentable, mais par clôture gouvernée et décision explicite.

## 6. Où modifier le code

| Domaine | Chemins / contrats utiles |
|---|---|
| Runtime PAPER | `core/advisor_loop.py`, `paper_trading/` — zone sensible gelée |
| FIN | `financial_institute/`, `observability/financial_reconciliation.py` |
| Research | `research_data/`, `research_replay/`, `research_diag/`, `research_candidate/` |
| Publications passives | `observability/research_publication_builder.py`, `observability/research_strategy_board_builder.py` |
| API présentation | `observability/operator_api/app.py`, readers du même package |
| App | `frontend/src/`, routes Machine/Research, contrats/validateurs frontend |
| Gouvernance | `governance/`, [docs/contracts](contracts/), [docs/adr](adr/) |
| Inventaire / suite produit | [matrice des capacités](plans/APP_UNIFY_FUNCTIONS_AND_OUTPUTS_INVENTORY.md), [plan Machine/Lab](plans/APP_UNIFY_MACHINE_LAB_PRODUCT_PLAN.md) |

Flux : `producteur gouverné → artifact/projection → reader/API GET → app`.
Les readers ne doivent pas importer/activer le runtime ou un writer métier
pour afficher une donnée. L'API ne lance pas replay, calibration ou promotion.
Ne pas refactoriser les trois arbres runtime ou le monolithe Advisor comme
« nettoyage » d'une mission documentaire/UI.

## 7. Choisir la mission et préserver le travail existant

Lire #285, le scope du parent et les sous-gates. U4 #337 et #338/#339 sont
fusionnés en source ; ne pas les traiter comme PR ouvertes. U7 global, les
écarts CryptoRadar, l'admission réelle Lab et U8 demeurent des tranches distinctes.

#266 n'est pas à merger/rebaser/cherry-pick : ses enseignements documentaires
sont reconstruits depuis la base actuelle. BUGS, #297 et #260 sont hors scope
DOC-CANON-01. Le nettoyage administratif des cinq PR Research déjà absorbées
vient ensuite, avec traçabilité ; il n'autorise aucun cleanup des preuves.

Créer une branche ou worktree isolé depuis une base vérifiée. Préserver les
changements préexistants et les artifacts locaux ; aucun reset/clean destructif.
Classifier les composants avant retrait et vérifier leurs consommateurs.

## 8. Développement local

Il n'existe pas de commande « lancer toute la machine » dans cette entrée.
Les commandes suivantes préparent uniquement un environnement local isolé de
validation, pas le VPS ni l'epoch active. Utiliser Python 3.11 et Node 20 comme
les workflows de cette base ; les dépendances viennent des fichiers suivis.

```bash
python3.11 -m venv /tmp/crypto-terminal-dev-venv
source /tmp/crypto-terminal-dev-venv/bin/activate
python -m pip install -r requirements-ci.txt
python -m pip install ruff==0.15.8
npm ci --prefix frontend
```

Pour l'UI locale : `npm run dev --prefix frontend -- --host 127.0.0.1`.
Sans artifact/proxy configuré dans un environnement autorisé, des vues peuvent
être indisponibles ; ne pas fabriquer des zéros pour remplir l'écran. Pour
valider le transport avec données synthétiques, suivre la workflow cross-stack
ci-dessous. Ne pas brancher cette preview au VPS comme effet implicite.

## 9. Contrôles de validation

La CI et ses versions suivies font foi ; ne pas copier un count historique
comme résultat de sa propre PR. Adapter les preuves locales au scope, puis
vérifier les checks requis au **HEAD réel** avant une fusion source autorisée.

Pour une modification documentaire : contrôler liens, frontières d'autorité,
références historiques/actuelles et liste exacte des fichiers modifiés.
Aucun nouveau test qui ne ferait que refléter le texte n'est requis.

Pour une modification Python/contrats :

```bash
python scripts/ci/ruff_baseline_gate.py check
pytest -q -m 'not performance and not slow' tests/
pytest -q tests/cross_stack/
```

Exécuter le corpus depuis une copie propre quand les dépendances locales UI
font apparaître des répertoires non suivis dans les tests d'architecture. Ne
pas modifier un baseline pour cacher cet effet. La CI long-run et la couverture
ont des gates distinctes dans [ci.yml](../.github/workflows/ci.yml).

Pour frontend : `npm run build --prefix frontend`,
`npm run test:runtime --prefix frontend` et Vitest. Les tests dépendant des fixtures peuvent être
skipped sans leur génération : ce n'est pas une preuve cross-stack complète.
Pour celle-ci, suivre exactement les générateurs et commandes de
[cross-stack-compat.yml](../.github/workflows/cross-stack-compat.yml) : artifacts
synthétiques issus des vrais producers/publishers/readers/API, puis
`CROSS_STACK_FIXTURES_DIR` vers leur répertoire et les tests Vitest concernés.

Pour une modification visuelle, exécuter les workflows/scripts de preuves
concernés, notamment [Machine/Lab U6](../.github/workflows/machine-lab-u6-visual-proof.yml),
avec desktop/tablette/mobile, erreurs/indisponibilité, overflow, contraste,
focus et détails/provenance. Les captures sont des preuves de présentation,
jamais de données ou d'activité runtime réelles.

Les checks requis incluent `integrity`, `LINT REGRESSION GATE`,
`TEST REGRESSION GATE` et `CROSS-STACK COMPATIBILITY GATE` dans la protection
observée lors de la fusion #339 ; revérifier leur état/périmètre pour la PR
courante. Ne pas confondre rapports de couverture, tests et approbation de gate.

## 10. Interdictions et livraison

Pas de déploiement implicite, mutation de données scientifiques, nouveau
classement/verdict frontend, UNKNOWN converti en zéro, promotion ou action
OperatorDecision pendant Gate O OPEN. Pas de suppression d'un module parce
qu'il semble ancien, de `npm audit fix --force`, de bypass de protection ou de
secrets dans les artifacts. Le merge source n'est pas une autorisation U8.

La PR doit expliquer problème/résultat, scope, base/HEAD, preuves et limites.
Conserver la provenance historique ; la nouvelle façade ne modifie aucun
protocole scientifique ni gate. Les anciens états et règles datées sont
consultables via les liens immuables de [ROADMAP](../ROADMAP.md).
