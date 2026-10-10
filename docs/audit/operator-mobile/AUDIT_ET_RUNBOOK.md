# UX opérateur mobile et disponibilité des données

## Périmètre et preuves source

Audit effectué depuis GitHub, avant les modifications : `main` =
`8c0dc27fbe456834423e8543c8ff30d657ec2d86` ; release déclarée par
l’opérateur = `1728b3ad952b87d903ccb7442579000da292b848` (PR #394).
Les écarts pertinents entre release et main concernent le bootstrap local du
frontend, pas les vues Finance, Décisions ou les contrats de publication.
PR ouvertes vérifiées : #397 (clôture anticipée, distincte), #396 et #374.
Aucune de ces branches n’est intégrée à cette mission.
Branche isolée : `feat/operator-mobile-data-availability`.

L’observation Android, FIN du 26 septembre et PPL du 7 octobre provient de
l’opérateur. Aucun accès VPS, aucune inspection du système de fichiers de
production, aucun redémarrage, publication runtime ou changement d’autorité.
GitHub apporte des preuves source ; il ne prouve pas l’état actuel du VPS.

## Architecture et tableau des anomalies

| Anomalie | Cause démontrée dans la source | Cause runtime / limite |
|---|---|---|
| Historique comptable dupliqué | `DirectionOverview` et `FinancialReconciliationView` montaient `FinancialHistory` | Correction de présentation seulement |
| Décisions illisibles | Tableau unique large, sans recherche ni filtres | Lecture Android déclarée ; tests navigateur synthétiques ajoutés |
| Vue générale technique | Identités et statuts bruts au premier niveau | Pas de preuve suffisante pour affirmer une santé globale |
| Portefeuille | Cartes mobiles existantes ; longues identités et preuves insuffisamment contraintes | Risque de débordement vérifié sur fixtures locales, pas sur Android réel |
| Research 503 | Route frontend et API concordantes ; lecteur strict renvoie `RESEARCH_LAB_SNAPSHOT_MISSING` lorsque son chemin n’existe pas | Publication absente au chemin lu selon l’erreur déclarée ; mauvaise configuration, montage, lien cassé ou absence du producteur restent inconnus |
| Burn-in 503 | Route frontend et API concordantes ; lecteur strict renvoie `BURN_IN_STATUS_MISSING` | Même limite : aucun mauvais chemin frontend démontré, configuration réelle non inspectée |
| FIN septembre / PPL octobre | Deux contrats, dates, populations et autorités distincts | Aucun montant comparable reçu : écart monétaire inconnu ; ne pas recalculer FIN depuis PPL dans le navigateur |

### Research

GET `/api/operator/v1/research-lab` →
`observability/operator_api/research_lab_reader.py` → schéma fermé WEB-RL
`observability/research_lab_schema.py`, version `1.0.0`, produit
`ResearchLabSnapshot`, autorité `RESEARCH_NON_AUTHORITATIVE`.
Chemin par défaut : `databases/research_presentation/research_lab_snapshot.json`.
Surcharge : `RESEARCH_LAB_SNAPSHOT_PATH`.
Le modèle de service API suivi dans
`deploy/app_unify_u8/crypto-operator-api.service` configure
`/home/mathieu/crypto_ai_terminal/databases/research_presentation/research_lab_snapshot.json`.
Il s’agit d’un modèle source, pas d’une configuration runtime attestée.

Producteur : `observability/research_publication_builder.py`, puis publication
atomique via `observability/research_lab_snapshot.py`.
Dépendances : sélection explicitement admise, identités/digests, résultats
Replay immuables (manifest, metrics, terminal), Diagnostic facultatif lié.
Pas de choix automatique du dernier répertoire, pas de moteur Research ni
lecture PPL dans l’API. Restaurer une publication passive est envisageable
uniquement si les entrées admises existent et satisfont le contrat. Leur
existence en production est inconnue. Aucun snapshot de secours ne doit être
fabriqué. Aucune activation Replay, Diagnostic ou rétroaction vers PAPER.
Le lecteur distingue missing, invalid path, unreadable, malformed et invalid
schema ; il ne fournit pas de classification temporelle API indépendante.
L’écran conserve l’horodatage publié, sans transformer le succès HTTP en
certification de fraîcheur scientifique.

### Burn-in

GET `/api/operator/v1/burn-in` →
`observability/operator_api/burn_in_status_reader.py` → contrat U2 fermé
`observability/burn_in_status_contract.py`, version `1.0.0`.
Chemin par défaut : `databases/burn_in_status_snapshot.json` ; surcharge
`BURN_IN_STATUS_SNAPSHOT_PATH` ; modèle de service :
`/home/mathieu/crypto_ai_terminal/databases/burn_in_status_snapshot.json`.
Le lecteur refuse les liens et chemins non réguliers. Il distingue fichier
absent, illisible, JSON mal formé et schéma incompatible. La fraîcheur de
publication utilise `generated_at_utc` et un seuil par défaut de 90 secondes
(`BURN_IN_STATUS_STALE_AFTER_S`), distinct de `source_updated_at_utc` PPL.

Producteur passif : `observability/burn_in_status_snapshot.py` :
`build_burn_in_status_snapshot`, `write_burn_in_status_snapshot`,
`publish_once`, boucle standalone. Lecture PPL/configuration figée avec
identités/digests cohérents et remplacement atomique de la publication.
Pas d’appel identifié depuis l’Advisor dans l’audit source. L’API ne construit
rien et n’importe pas le store PPL. L’absence de fichier ne signifie ni epoch
terminée ni zéro position. Epoch attendue pour cette mission :
`BURN-IN-EPOCH-01-20260926T064144Z`. Son identité actuelle est UNKNOWN sans
publication validée. La certification finale reste non disponible.
La PR #397 n’est ni utilisée ni activée.

### FIN et PPL

La synthèse FIN lit `/api/operator/v1/financial-reconciliation`, avec unité
`asset`, horodatage et statut de valorisation propres. Les courbes Finance
lisent `/api/operator/v1/ppl-accounting-history`, conservent leurs trois modes
et leurs preuves ; aucune transformation comptable n’a été modifiée.
Le handoff source `docs/handoffs/PPL_ACCOUNTING_CHARTS_PREPARATION.md` mentionne
une capture PPL au `2026-10-07T23:29:51Z`, 171 événements, replay validé mais
checkpoint non vérifié. Cela ne certifie pas une valorisation FIN actuelle.
Aucun artefact FIN du 26 septembre n’a été fourni dans cette mission : comparaison
quantitative BLOCKED. Il faut les deux réponses datées et leurs frontières de
source, epoch, unité, digests, populations, valuations et preuve checkpoint
avant de conclure à un écart. Aucun rapprochement synthétique affiché.

## Proposition UX présentée avant implémentation

Machine : synthèse FIN courte et lien Finance ; plus de graphique détaillé.
Finance : courbes complètes, trois modes, preuves et distinction dates FIN/PPL.
Décisions : comptes descriptifs de lignes publiées, admissibles/non admissibles/
inconnues, bloqueurs et provenance ; recherche et filtres ; cartes avec détails ;
tableau technique replié et défilement local. `trade_allowed` décrit
l’admissibilité, jamais une permission d’ordre ; `is_actionable` reste indépendant.
Une capture périmée indique explicitement que l’admission actuelle n’est pas
attestée. Aucun taux de performance, d’exécution ou de rejet calculé.
Vue générale : quelques observations et santé globale inconnue ; brut replié.
Sources absentes : cause lisible, UNKNOWN, dernière métadonnée validée dans la
session et action requise. Aucune métrique passée réaffichée après une erreur.
Burn-in : observation scientifique, frontières PPL, clôtures et certification
non disponible ; aucun pourcentage vers un objectif non fourni.
Portefeuille : cartes contraintes, données publiées, prix daté et provenance de
capture ; références et dates individuelles absentes restent inconnues.
Palette : cyan information, vert admissibilité observée, ambre périmé,
rouge rejet/erreur, gris inconnu ; libellés explicites et contrôles tactiles 44px.

## Runbook de diagnostic futur — aucune exécution runtime ici

1. Recueillir en lecture seule les réponses exactes des deux routes, UTC, statut
   HTTP et code. Ne pas assimiler HTTP 200 à une certification scientifique.
2. Après autorisation spécifique d’inspection runtime, vérifier la configuration
   effective du seul service API (variables, dossier courant, sandbox/montage),
   puis existence, type et droits de lecture du chemin effectif. Ne pas modifier
   les droits ou un service automatiquement.
3. Si le fichier existe, valider séparément JSON, version, schéma fermé et
   identités/digests. Distinguer publication périmée de source PPL ancienne.
   Enregistrer les preuves sans éditer les artefacts historiques.
4. Research : vérifier sélection admise et entrées immuables avant de proposer
   une publication passive. Si elles manquent : rester dégradé et demander ces
   entrées ; ne pas lancer le pipeline ou inventer un document.
5. Burn-in : vérifier epoch et empreinte de configuration, cohérence de capture
   PPL, chemin du producteur passif et mécanisme de publication attendu. Si une
   restauration est possible, présenter son action exacte et ses destinations
   pour une décision distincte. Aucun restart Advisor, changement PAPER ou FIN.
6. Après publication explicitement autorisée seulement, capturer les réponses,
   chemins/digests/identités et dates, puis contrôler l’affichage. Cette mission
   ne délivre aucune certification runtime.

## Risques et rollback

Les métadonnées de dernière preuve restent uniquement dans la session montée :
un rechargement repart UNKNOWN. Pas de cache durable ni d’artefact substitutif.
Les hooks restent des lectures GET sérialisées avec polling existant ; la
résilience réseau (timeout global, abort) n’est pas élargie par ce correctif.
Les snapshots peuvent être valides mais historiquement anciens. Les comptes
Décisions couvrent uniquement les lignes publiées, pas une population exhaustive.
Les états inconnus des bloqueurs sont conservés dans leur répartition.
Les cartes affichent uniquement les unités définies par les contrats existants ;
aucune conversion USD/USDT ni nouveau calcul PnL n’est introduit.
Les essais Chromium ne remplacent pas une validation Android/TalkBack réelle.
Les accès aux fichiers runtime et producteurs n’étant pas observés, les causes
racines des deux publications manquantes restent ouvertes.

Rollback source : revert du commit de cette branche, suivi de review/tests.
Rollback frontend éventuel après décision de déploiement distincte : rétablir
l’artefact web précédent, sans toucher API, Advisor, admission, configuration,
ledgers ou snapshots. Le retour UI peut réintroduire les défauts visuels, jamais
une autorité d’exécution. Aucun rollback runtime exécuté ou demandé ici.

Attention au futur merge : `.github/workflows/sphinx.yml` publie automatiquement
GitHub Pages lors d’un push main touchant `docs/**` et peut notifier des canaux
configurés. Cette PR contient de la documentation : le merge nécessite une
nouvelle décision tenant compte de cette publication ; aucun workflow ou
mécanisme de déploiement n’est changé ici. Les preuves présentées sont source.

SOURCE_PROOF ≠ RUNTIME_PROOF ; READY_FOR_REVIEW ≠ CERTIFIED.

## Vérification reproductible

Toutes les données visuelles sont synthétiques, marquées « DÉMONSTRATION ·
DONNÉES FICTIVES ». Aucun artefact de production n’est créé ni copié.

```bash
npm ci --prefix frontend
python -m tests.cross_stack.generate_fixtures --out frontend/.cross-stack-fixtures
python -m tests.cross_stack.generate_market_fixture --out frontend/.cross-stack-fixtures
python -m tests.cross_stack.generate_scanner_fixture --out frontend/.cross-stack-fixtures
python -m tests.cross_stack.generate_microstructure_fixture --out frontend/.cross-stack-fixtures
python -m tests.cross_stack.generate_ppl_comparison_fixture --out frontend/.cross-stack-fixtures
python -m tests.cross_stack.generate_research_lab_fixture --out frontend/.cross-stack-fixtures
python -m tests.cross_stack.generate_research_publication_fixture --out frontend/.cross-stack-fixtures
python -m tests.cross_stack.generate_strategy_board_fixture --out frontend/.cross-stack-fixtures
python -m tests.cross_stack.generate_financial_clarity_fixture --out frontend/.cross-stack-fixtures
python -m tests.cross_stack.generate_burn_in_fixture --out frontend/.cross-stack-fixtures
python -m tests.cross_stack.generate_runtime_service_fixture --out frontend/.cross-stack-fixtures
python -m tests.cross_stack.generate_event_center_fixture --out frontend/.cross-stack-fixtures
python -m tests.cross_stack.generate_storage_fixture --out frontend/.cross-stack-fixtures
CROSS_STACK_FIXTURES_DIR="$PWD/frontend/.cross-stack-fixtures" npm test --prefix frontend -- --run
npm run build --prefix frontend
npm run test:runtime --prefix frontend
python -m pytest -q tests/test_operator_api.py tests/test_operator_burn_in_api.py tests/test_web_rl_research_lab.py tests/test_operator_api_financial_reconciliation.py tests/test_ppl_accounting_history.py tests/test_pre_t1_c_portfolio_provider_read_only.py
```

Résultats locaux : 429 tests frontend (y compris compatibilité cross-stack,
Decimal, unités et trois modes comptables), 254 tests Python pertinents,
8 tests bootstrap/PWA ; build réussi. États loading, missing, stale,
degraded et available couverts par les suites et la preuve navigateur.
Avertissements existants : chargeur Vite/ESM et dépréciation Starlette/httpx.

Pour les images : installer Playwright uniquement comme outillage de test
hors lockfile, utiliser Chromium installé ou `playwright install chromium`.
Par exemple, après `npm ci` :

```bash
VISUAL_TOOLS_DIR=$(mktemp -d)
npm install --prefix "$VISUAL_TOOLS_DIR" playwright
ln -s "$VISUAL_TOOLS_DIR/node_modules/playwright" frontend/node_modules/playwright
```

Lancer `npm run dev:demo --prefix frontend` depuis la racine ; dans un autre
terminal, `CHROMIUM_PATH=/usr/bin/chromium node frontend/scripts/capture_operator_mobile_visual.mjs`.
L’aperçu bloque toutes les API hors fixtures locales, sans proxy de production.
La preuve complète est créée dans `artifacts/operator-mobile/`.
`preuves/checks.json` et une sélection d’images sont conservés dans cette PR.
Le script contrôle 360/390/412/1440 px, états absents/périmés, défilement local,
GET seuls, absence d’exceptions, clavier, cibles tactiles et contraste AA des
quatre couleurs sémantiques sur le fond des cartes (98 contrôles). Les images montrent les
fixtures, jamais une preuve de santé du VPS.
