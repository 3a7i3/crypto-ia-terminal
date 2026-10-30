# UI-MODULES-THEMES-01 — modules et apparence

Mission opérateur : refonte de présentation approuvée après l’audit des 14 routes
sur la nouvelle VM, puis demande explicite d’implémenter le plan et un sélecteur
clair/sombre. Base source : `82cd63e202e09ff52e00372cb9d9f3eb65cc8345`.

**SOURCE ONLY / NON DÉPLOYÉ.** Aucun droit de fusion, de redémarrage, de
raccordement des données récupérées ou d’activation expérimentale par ce document.
Les services API/frontend déjà actifs sur la VM conservent leur release.

## Résultat

Une seule navigation : Accueil, Marché, Décisions, Positions, Finance,
Laboratoire, Système. Projet / Travaux reste une entrée secondaire. Sur mobile,
le bouton Modules déplie la navigation ; les sous-vues n’apparaissent que dans
leur famille. Aucun moteur ni réglage scientifique n’est commandable.

L’accueil présente six disponibilités datées, sans recopier montants ou positions.
Il lit cinq sources : Décisions et Positions partagent la même capture opérateur.
Chaque disponibilité porte sur la publication indiquée, jamais sur la santé
complète du module. Research n’acquiert aucun seuil de fraîcheur inventé.

Le panneau Paramètres d’affichage propose deux thèmes, mémorisés localement dans
`crypto-terminal.theme`. Sans préférence valide, le choix initial suit le système.
Le stockage indisponible est signalé ; il n’empêche pas le changement dans la
session. Aucun appel API, cookie applicatif ou secret n’est requis. Les icônes SVG
et polices système ne chargent aucun CDN. Le panneau se ferme par Échap, bouton
ou clic extérieur ; Échap et Fermer rendent le focus à l’engrenage.

## Propriétaires des informations

Le préfixe des endpoints est `/api/operator/v1/`. Le frontend ne lit aucun
fichier de la VM et ne reconstitue aucune autorité depuis un libellé de module.

| Emplacement principal | Champs / sortie | Publication / endpoint | Limite conservée |
|---|---|---|---|
| Marché | `market_regime`, `universe_size`, `top_opportunities`, couverture et seuil publiés | `cryptoradar_market_snapshot.json` / `market` | Observation, jamais autorisation d’exécution ; ordre et valeurs source préservés |
| Marché, détail Microstructure | `rows`, groupes flux/liquidité/résistance et dates par symbole | `market_microstructure_snapshot.json` / `market-microstructure` | Source indépendante, chargée à l’ouverture du détail ; pas de substitution au scanner |
| Décisions | `decision_pipeline.per_symbol_decisions`, actionable, trade_allowed, first_blocker et leurs autorités | `operator_snapshot.json` / `snapshot` | Aucun recalcul de décision ; filtres descriptifs et inconnus conservés |
| Positions | `portfolio.open_positions`, compteur publié, prix et PnL observés par position | `operator_snapshot.json` / `snapshot` | Projection opérateur, pas promotion implicite à une vérité PPL ; états PRESENT/EMPTY/UNKNOWN/STALE distincts |
| Positions, comparaison PPL | `comparisons`, `positions`, quiescence et autorités source | `ppl_comparison_snapshot.json` / `ppl-comparison` | Comparaison observationnelle ; valeurs brutes et divergences conservées, date absolue rendue visible |
| Finance | `financial`, `reconciliation`, `records`, asset, epoch | `financial_reconciliation_snapshot.json` / `financial-reconciliation` | FIN porte les montants ; null ne devient pas zéro ; décimales exactes consultables |
| Finance, historique | échantillons comptables PPL, propre date/epoch | `ppl_accounting_history.json` / `ppl-accounting-history` | Une nouvelle capture PPL ne rafraîchit pas FIN et ne certifie pas leur rapprochement |
| Laboratoire, évaluations | population, performance, risques, coûts, limites et artifacts admis | `research_lab_snapshot.json` / `research-lab` | Research non autoritaire, métriques prépubliées ; aucun replay ou classement React |
| Laboratoire, stratégies | rows et critères publiés, preuves de chaque évaluation | `research_strategy_board.json` / `research-strategies` | Catalogue et rang publiés ne prouvent pas activation ; aucune promotion |
| Système, service | service query_status/active_state, observation et preuve de déploiement | `runtime_service_snapshot.json` / `runtime-service` | Service actif ≠ santé ; état historique explicitement inconnu au présent ; PID et détails repliés |
| Système, stockage | matched_file_count, total_bytes, métadonnées et couverture | `storage_snapshot.json` / `storage` | Aucun contenu de journal, aucun compteur de packets déduit ; volume ≠ espace disque libre |
| Système, diagnostic volontaire | `system_health`, identité du snapshot | `operator_snapshot.json` / `snapshot` | Lecture montée uniquement quand le diagnostic est ouvert ; pas de synthèse de santé globale |
| Système, journal | événements et disponibilité de chaque source | `event_center_snapshot.json` / `events` | Alertes historiques ≠ incident actuel ; couverture partielle toujours visible |
| Projet | registre éditorial, filtres et relevé GitHub volontaire | registre suivi ; lecteur GitHub GET existant | Huit missions par page ; filtre sur tout le registre ; source, certification et déploiement restent distincts |

Les montants du snapshot opérateur restent consultables dans un diagnostic de
Positions, explicitement distinct de FIN. Ils ne sont plus des indicateurs
financiers concurrents au premier niveau. L’accueil renvoie vers les propriétaires.
Il ne fusionne pas des époques ou des captures indépendantes.

## Classification et compatibilité

| Élément | Décision |
|---|---|
| Lecteurs, validateurs, publications, autorités PPL/FIN/Research | KEEP, inchangés |
| Anciennes doubles navigations et synthèse détaillée | RETIRE de la façade active ; accueil compact à la place |
| `/paper-live` et `/paper-live/overview` | Redirection vers `/direction` |
| `/paper-live/burn-in` | Redirection vers Positions ; aucune requête burn-in dans l’app active |
| `/paper-live/scores` | Redirection vers Système ; placeholder retiré de la navigation |
| `DirectionOverview`, `BurnInStatusView`, `OverviewView`, `NotExposedView` et leurs contrats historiques | KEEP en source et tests ; aucune entrée de la nouvelle app ne les importe |
| Données scientifiques, sauvegardes, registre historique et certifications | KEEP, aucune suppression ou réécriture |
| Paragraphes techniques / paramètres du service / gouvernance Projet | MOVE vers détails volontaires, sans effacer leurs preuves |

Les scripts visuels de navigation suivent les nouveaux parcours. La preuve
historique burn-in reste exercée par les tests de composant, de validation et
le cas J généré par le vrai producteur/API ; son ancien script de navigation
vérifie désormais les redirections et l’absence de requête burn-in. Son verdict
ne prétend plus certifier l’ancien écran. Les critères de protection sont inchangés. En serveur Vite de développement,
React StrictMode répète les effets de montage : la preuve navigateur vérifie
les cinq sources uniques et borne les lectures de démarrage à deux par source.
La preuve Finance attend le DOM et ses valeurs validées plutôt qu’un réseau
globalement inactif, qui n’est pas un critère fiable avec le polling.

## Vérification reproductible

- `npm ci --prefix frontend`, `npm run build --prefix frontend`,
  `npm run build:demo --prefix frontend`.
- Générateurs `tests.cross_stack.generate_*` existants dans un venv isolé,
  puis `CROSS_STACK_FIXTURES_DIR=<fixtures> npm test --prefix frontend -- --run`.
  Aucun dataset récupéré n’est injecté dans ces tests.
- `pytest -q tests/cross_stack/` et `npm run test:runtime --prefix frontend`.
- `frontend/scripts/capture_module_workspace_visual.mjs` : clair/sombre,
  1440/820/390 px, sources présentes/absentes/périmées ; erreurs de contrat et
  réseau ; réglage mémorisé au rechargement ; focus et contraste des couleurs
  sémantiques ; contrôle des GET et de l’absence d’overflow. Scénarios remplis
  exclusivement synthétiques, marqués NON DÉPLOYÉ.
- `UI_PREVIEW_DIST=<build isolé>` permet au navigateur de fournir les fichiers
  par interception et de tester sans ouvrir de port ou lancer de service HTTP.
- Les autres scripts visuels conservent leurs assertions de domaines et
  leurs contrôles de valeurs exactes, d’UNKNOWN et de provenance ; seules les
  attentes des éléments de navigation retirés sont remplacées.

Résultats locaux : build production et démo réussis ; 492 tests frontend réussis
avec les fixtures (aucun ignoré) ; 113 tests Python cross-stack réussis ;
16 contrats runtime réussis. Node local 24.22.1, Python isolé 3.11.17.
Le navigateur d’audit de la VM utilise Playwright 1.64.1 / Chromium 156 ; la CI
visuelle existante utilise Playwright 1.56.1. Le navigateur de la VM conserve
son sandbox. Le runner GitHub jetable refuse les namespaces de ce binaire :
le nouveau script accepte uniquement dans GitHub Actions un opt-in explicite
`MODULE_VISUAL_SANDBOX=false`, identique à la politique de lancement des autres
preuves visuelles. Les requêtes de la page restent bornées au build local et
aux fixtures ; aucune configuration de sécurité de la VM n’est changée. La CI au SHA de PR demeure une
preuve distincte. 154 vérifications visuelles finales passent (clair/sombre, états sources et
responsive), dont la visibilité et le détail du scanner mobile. Les scripts
UX français (124 contrôles) et mobile (75 contrôles) passent aussi. Les reçus
détaillés accompagnent la passation, pas une certification runtime.

## Limites et retour arrière

Aucun raccordement des cinq artifacts récupérés ; la présentation active reste
vide. Aucun test avec des données migrées ou une nouvelle expérience.
La cartographie des familles concerne les sorties déjà exposées par les contrats
actuels ; elle n’invente pas une sortie supplémentaire pour chaque moteur interne.
Les données manquantes restent visibles et ne sont pas réparées par l’interface.

Cette mission ne déplace aucun service, lien de release, port, préférence
Tailscale ou unité. La mise à disposition de cette source sur la VM nécessitera
une décision de publication séparée. Tant qu’elle n’a pas lieu, la façade servie
reste celle du SHA de base. Un rollback source consiste à revenir à la PR
précédente par un commit revu ; les données et producteurs n’ont pas à être
restaurés. Le navigateur d’audit et ses fichiers sont séparés des releases.
