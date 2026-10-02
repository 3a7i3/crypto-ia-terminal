# ResearchStrategyBoardSnapshot — publication passive du Laboratoire

2026-10-02 · #338 · SOURCE ONLY · #286 ACTIVE. Domaine distinct de WEB-RL 1.0.0.

## Frontière

Une sélection Research explicitement admise lie des artifacts immuables
`RL_CANDIDATE`, leurs évaluations et, facultativement, un assessment de critères.
Le builder vérifie chemins, limites, JSON strict, hashes exacts, identités et
liaisons du protocole ; il recopie les résultats. Il n'exécute ni stratégie,
Replay/Diag, scoring, seuil scientifique, classement ou promotion.

La valeur `admission=CERTIFIED` et la référence de certification sont des
entrées de gouvernance. Le builder ne délivre ni n'authentifie une certification.
Les attestations O7, l'admission de vraies publications et l'alimentation
opérationnelle restent des étapes distinctes. Aucun fichier réel n'est publié
par cette PR ; les fixtures CI sont identifiées comme synthétiques.

## Sélection et assessment

Sélection fermée `app-unify.research-strategy-selection.v1` : `schema_version`,
`admission`, `certification_ref`, `candidates`. Maximum 100 candidats explicites.
Une entrée contient `candidate_id`, `label`, `candidate`, `evaluation`,
`assessment`. Chaque référence non nulle contient exactement `path`, `sha256`.
Les chemins sont relatifs à la racine de preuves, sans symlinks, traversal ou
lecture hors racine. Pas de découverte du répertoire « latest ».

Assessment facultatif fermé `research-strategy-assessment.v1` :
`schema_version`, `candidate_id`, `evaluation_run_id`, `policy_id`, `policy_ref`,
`criteria`, `ranking`. Il est lié au candidat et au run sélectionnés.
La politique est identifiée par SHA256 et référence ; les six verdicts et les
rangs doivent être prépubliés par Research, avec leurs raisons et métriques.
L'app ne produit aucune politique ou appréciation scientifique.

Critères : PERFORMANCE, POPULATION, VALIDATION, STABILITY, COSTS, DRAWDOWN.
Chaque critère contient `criterion_id`, `status`, `reason`, `metric_refs`.
PASS vert, FAIL rouge, PARTIAL jaune, NOT_AVAILABLE gris, toujours avec texte
et icône. PASS/FAIL nécessitent un run COMPLETE et des métriques référencées
COMPLETE avec N strictement positif. Cela vérifie la présence de preuves ;
cela ne certifie pas une puissance statistique ou une robustesse.

Sans assessment, même une évaluation COMPLETE avec PnL positif reste sans
verdict et sans rang. Sans évaluation, aucun résultat n'est fabriqué.
Les étapes du registre et l'activation runtime restent NOT_AVAILABLE : aucun
journal de transitions n'est admis par ce profil.

## Publication et comparaison

Le contrat fermé et exécutable est
`observability/research_strategy_board_contract.py`, miroir structurel frontend
`frontend/src/lib/researchStrategyValidation.ts` ; les interfaces TypeScript
sont dans `researchStrategyTypes.ts`. Schema 1.0.0, produit
ResearchStrategyBoardSnapshot, autorité RESEARCH_NON_AUTHORITATIVE.

Chaque ligne garde l'identité/version de la proposition, hypothèse, limites,
références config/code, identité du run, rôle DISCOVERY/EVALUATION/VALIDATION,
dataset/frontière, protocole, population, métriques, N et force statistique.
Baseline/candidat/delta/dérivation sont recopiés ; la validation pure existante
de l'évaluation vérifie leur cohérence. Ce profil admet uniquement les
exigences EXACT_DATASET : aucune future liaison dataset/config/epoch implicite.

Un classement est un rang publié dans une cohorte identifiée par le hash
canonique de : dataset, frontière, rôle, méthode, sémantique des métriques,
config d'évaluation, baseline, SHA du moteur d'évaluation, population,
politique de verdict, métrique et sens de tri. La gouvernance doit fixer les
périodes, coûts, univers et régimes dans ces preuves avant admission.
Le serveur vérifie ce hash, les tailles de groupes et l'unicité des rangs.
Le frontend vérifie formats et cohérence des membres ; il ne recalcule pas
le SHA256 ni les résultats. Aucun classement entre cohortes différentes.
Le filtre de cohorte trie uniquement sur les positions déjà publiées.

Les références d'artifacts et SHA256 exacts des bytes d'entrée restent dans
la provenance. `catalog_state=EMPTY` signifie sélection explicitement vide,
pas registre global vide. Les dates de publication et d'évaluation restent
visibles ; un résultat historique ne décrit pas l'état courant de la machine.

## Transport et affichage

Artifact autonome `databases/research_presentation/research_strategy_board.json`,
maximum 1 MiB. Sortie atomique hors répertoires de sources/admission.
GET `/api/operator/v1/research-strategies` lit uniquement cet artifact.
Manquant/invalide : 503 structuré, sans zéro ni faux catalogue vide. POST : 405.
Les erreurs de transport/contrat remplacent la publication précédemment affichée.
Polling sérialisé, délai 60 s après résolution, timeout 5 s, abort à l'unmount.

Route `/research/strategies` : grille desktop, cartes mobile, recherche/type/
cohorte, fiche cliquable et focus clavier, fermeture avec bouton ou Échap.
Une fiche montre les raisons publiées, N, limites et valeurs exactes ; elle
ne présente pas une association comme cause démontrée de gain ou de perte.
WEB-RL `/research` et ses artifacts Replay/Diag restent indépendants.

## Preuves

`tests/cross_stack/generate_strategy_board_fixture.py` utilise le publisher
immutable existant, des évaluations et assessments synthétiques prépubliés,
puis le vrai builder, reader et GET. Le frontend lit le corps réel sans mutation.
Les tests couvrent identités/hashes, zéro population, métriques manquantes,
cohortes incompatibles, rangs dupliqués, JSON strict, limites, sources inchangées,
publication atomique, absence de PnL ⇒ vert implicite et erreurs de disponibilité.
La workflow `machine-lab-u6-visual-proof.yml` capture trois largeurs et la
workflow cross-stack exécute aussi les tests du tableau.
