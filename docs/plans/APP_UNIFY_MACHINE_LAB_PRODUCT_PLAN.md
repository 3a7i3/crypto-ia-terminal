# Crypto AI Terminal — une machine, une app, deux espaces

Décision produit opérateur, 2026-10-02. Parent #323. Plan source/UI ; #286 ACTIVE.
Ce document suit le chantier source #338 : inventaire, navigation Machine/Lab,
lisibilité et projection passive du tableau des stratégies. Le runtime et les
contrats opérationnels restent inchangés. La PR U4 #337 est fusionnée en source.

## 1. Cible décidée

La machine produit les observations, décisions, états du portefeuille et
résultats Research. L'app devient son interface opérateur unique, agréable et
lisible sur téléphone comme sur desktop. CryptoRadar rejoint cette app.
Le socle du code décrit par l'opérateur tourne sur VPS Google Cloud ; ce plan
ne certifie pas l'état réel de ce déploiement.

Deux espaces principaux dans la même application :

| Espace | Question principale | Contenu |
|---|---|---|
| Machine | Que fait la machine et où en est mon expérience ? | Synthèse Direction, état des services, fraîcheur, portefeuille/positions/capital, finance/réconciliation, décisions/lifecycles, burn-in, marché/Scanner/LMI, alertes et preuves opérationnelles |
| Laboratoire quantitatif | Quelles stratégies sont étudiées et que montrent les évaluations ? | Catalogue de stratégies/candidats, expériences, datasets/replays/diagnostics, résultats, classement comparable, limites, tableau de critères et détail par stratégie |

Direction devient une synthèse accessible du côté Machine. Research devient
le Laboratoire. Leur regroupement visuel ne fusionne pas leurs autorités.
La progression de l'epoch/burn-in reste côté Machine ; ses datasets et analyses
scientifiques restent consultables côté Laboratoire, liés par leurs IDs exacts.

Référence Binance pour la navigation, la hiérarchie et les tableaux ; les
commandes de trading, promotions et mutations humaines sont un futur périmètre
séparé, pas une conséquence de cette ressemblance visuelle.

## 2. Une surface opérateur, sans détruire les preuves

Cible : machine → projections gouvernées → API canonique → application.
Toute nouvelle présentation opérateur doit converger vers l'app plutôt que
créer un nouveau site, dashboard ou canal de reporting autonome.

L'expression « plus aucune sortie vers d'autres types de données » est traitée
ici comme une consolidation des surfaces de consultation et de reporting.
Les fichiers scientifiques, logs, journaux, datasets, snapshots et sauvegardes
restent nécessaires comme preuves internes ; leur suppression n'est pas prévue.
Les échanges nécessaires aux données de marché et à l'exécution ne sont pas
supprimés par cette décision produit.

Les autres surfaces existantes (CryptoRadar autonome, notifications/panneaux,
anciens dashboards) sont à inventorier. Aucun arrêt, suppression ou reroutage
runtime pendant cette planification. Leur retrait nécessite une preuve de
parité, l'identification des consommateurs, un rollback et une gate séparée
compatible avec #286.

## 3. Inventaire complet à mener avant les nouvelles projections

Une ligne par fonction utile : source, producteur/autorité, artifact, contrat,
consommateurs actuels, vue app, provenance/fraîcheur, limites, statut source et
preuve runtime séparée, manque à combler et décision de migration.

Inventorier au minimum :

- Advisor/runtime/services, santé, stockage et disponibilité des sources ;
- portefeuille, positions, capital, événements PPL et réconciliation FIN ;
- signal/décision, contraintes/blocages et lifecycle ;
- burn-in/epoch/checkpoints/frontière/dataset ;
- CryptoRadar Scanner, détail symbole, LMI, événements et transports historiques ;
- stratégies/features/régimes, générateurs, backtests/replays/diagnostics,
  catalogues, évaluations, classements et historiques d'expériences ;
- alertes, Telegram/rapports, dashboards et consommateurs externes.

Séparer fonctions prouvées, source-only non déployée, historique/legacy,
démonstration/simulation et projection manquante. La présence d'un module dans
le dépôt ne prouve pas qu'il tourne sur VPS ni qu'il possède des résultats admis.

## 4. Point de départ vérifié dans le code

- U0/U1/U2/U2b/U3a/U3b fusionnés en source ; U4 #337 fusionnée, merge `de8281f3fa2a7994e2836b4139cc8457d389030a`. Aucun déploiement autorisé par ces certifications.
- Scanner : recherche/filtres, top 50, détail observationnel safe.
- LMI : projection passive, métriques/états/fraîcheur/couverture. Historique
  d'événements détaillé et certains champs restent hors tranche U3b : parité à
  compléter depuis de vrais producteurs, sans inventer de journal.
- Research : publication Replay/Diag explicitement admise, provenance/limites,
  builder sans calcul scientifique. Catalogue candidate NOT_AVAILABLE en U4 ;
  zéro lignes publiées ne signifie pas registre vide.
- `research_candidate/` possède des contrats/identités/évaluations et un registre
  Research. `quant_hedge_ai/strategy_lab/` et les rankers historiques existent.
  Leur raccordement et leur validité actuels doivent être audités : le README
  Strategy Lab contient notamment un exemple de score de démonstration
  `n_buy - n_hold`, qui ne constitue pas une performance financière.
- ADR-0014 documente un problème historique d'alimentation du ranker. Ce n'est
  pas une preuve de l'état runtime actuel et ce plan ne modifie pas ce câblage.
- #315 Gate O reste ouvert : aucune file de décisions opérationnelles ou
  promotion/activation de stratégie ne peut être fabriquée par une nouvelle vue.

## 5. Tableau des stratégies

Chaque ligne représente une stratégie/version identifiée, pas un symbole.
La vue combine un catalogue lisible et une matrice de critères cliquables.

Colonnes proposées, uniquement quand des preuves admises les alimentent :
performance nette/frais, population, validation hors échantillon, stabilité
par régime/période, drawdown, statut d'évaluation et provenance.

Les pastilles sont liées à chaque critère et à une politique de verdict
versionnée côté producteur Research :

- vert : critère satisfait sur l'évaluation déclarée ;
- rouge : critère non satisfait sur cette évaluation ;
- jaune : résultat partiel, fragile ou population insuffisante ;
- gris : non évalué, indisponible ou inconnu ;
- données historiques/périmées : indication distincte, jamais un verdict rajeuni.

Chaque pastille porte un libellé/une icône ; la couleur seule ne suffit pas.
Un résultat positif, une validation réussie, un module actif et une stratégie
promue sont des faits différents. Aucun vert ne signifie « autorisée à trader ».

Le classement compare uniquement des évaluations compatibles : dataset/frontière,
période, protocole, coût, univers/régime et statut de validation explicites.
Pas de mélange backtest, simulation, burn-in et résultats runtime ni de score
universel synthétique. Les données absentes restent indisponibles.

Au clic : hypothèse, version/SHA, paramètres référencés, dataset/run/diagnostic,
population, résultats publiés, critères/verdicts, coûts/drawdown, contexte par
régime, facteurs observés, limites et comparaisons admises. Les associations
observées ne sont pas présentées comme des causes démontrées de gain/perte.
Aucun calcul scientifique dans React/API ; pas de relance de moteur au clic.

## 6. Séquence naturelle

État de la tranche #338 après validation locale : U4 fusionnée ; inventaire
structurel et matrice des capacités réalisés ; navigation deux espaces,
lisibilité Finance/Portfolio/Scanner/LMI/burn-in et tableau Lab implémentés en
source. Le tableau Lab utilise un domaine indépendant ; le catalogue U4
WEB-RL reste NOT_AVAILABLE. Les fixtures ne sont pas des résultats de production.

La suite CryptoRadar vise les manques de producteurs identifiés dans
[l'inventaire](APP_UNIFY_FUNCTIONS_AND_OUTPUTS_INVENTORY.md), notamment stockage
et détail des composantes non publiées. Aucun journal d'événements ne sera
inventé à partir du endpoint historique, qui liste des états notables courants.
L'admission des vraies évaluations/assessments Research reste à réaliser avant
qu'une grille de résultats réels soit disponible. U8 et le retrait des autres
surfaces restent soumis à leur gate runtime séparée.

1. Stabiliser/fusionner U4 source après vérification de son HEAD/CI/revue.
2. Inventaire transversal des fonctions et sorties, avec matrice Machine/Lab,
   consommateurs et manques CryptoRadar/Research.
3. U6a : navigation deux espaces, direction visuelle et prototypes Machine +
   tableau Laboratoire, desktop/mobile. Les prototypes de données manquantes
   portent un label démonstration ; pas de faux état réel.
4. U6b : appliquer la lisibilité au côté Machine : synthèse, finance/portfolio,
   burn-in, Scanner/LMI. Contraste/typo/espacement, chiffres lisibles, détails
   repliables, tables desktop et cartes mobile.
5. Compléter la parité CryptoRadar utile révélée par l'inventaire, via projections
   indépendantes. Les niveaux d'exécution restent dans Decisions/Portfolio,
   pas dans le Scanner observationnel.
6. Lab : contrat/catalogue des stratégies → résultats/évaluations admis →
   projection tableau/classement/critères → API read-only → grille/détail UI.
   Réutiliser les briques Research validées, sans activer ni modifier les moteurs.
7. U7 : preuves cross-stack, erreurs/fraîcheur, absence de faux zéros et de
   recomputation, accessibilité, captures et validation à la largeur du téléphone.
8. U8 distinct : gate de publication, identité du build, preuve sur appareil
   réel ; ensuite retrait des surfaces historiques après parité/rollback.

Les commandes futures dans l'app et U5 opérationnel restent des missions
séparées dépendant de leurs gates ; aucune mutation runtime/VPS/Advisor/PPL/
FIN/epoch/config/risk/sizing/Watchdog/exchange n'est autorisée par ce plan.
