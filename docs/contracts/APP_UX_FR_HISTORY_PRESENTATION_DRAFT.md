# Historiques et répartition — proposition de contrat de présentation

2026-10-07 · **DRAFT, non implémenté et non raccordé au runtime**. Parent #323,
UX #283, #286 actif. Les contrats et noms de champs API existants restent inchangés.

## Constat vérifié

`OperatorSnapshot.portfolio` et `FIN02FinancialCockpit.financial` publient des
observations isolées. Aucun de leurs schémas ne publie une série de portefeuille
ou de résultat réalisé cumulé. Le polling ne crée pas un historique gouverné.
`book_capital_at_cost` peut être publié dans les records de rapprochement FIN-02,
mais ce fait ne fournit pas des parts de capital attestées.

ResearchStrategyBoardSnapshot publie une évaluation sélectionnée par candidat,
avec population, métriques, critères et cohorte. Il ne publie pas un historique
d’évaluations ni une filiation versionnée entre candidats.

L’interface affiche donc « Historique non disponible » et une répartition
proportionnelle indisponible. La démonstration autonome porte des séries et parts
explicitement fictives, indépendantes des snapshots synthétiques exposés par l’API
locale. Aucune extraction PPL/JSONL, aucun collecteur ni cache de polling n’est ajouté.

## Proposition : séries financières publiées

Un futur producteur gouverné doit publier une projection versionnée distincte,
après admission et revue de contrat. Aucun endpoint n’est créé ici.

| Champ proposé | Sens attendu |
|---|---|
| `schema_version`, `product`, `authority` | Schéma fermé et autorité de publication identifiée |
| `paper_epoch_id`, `financial_model`, `asset` | Une seule expérience, modèle et unité par série |
| `metric_id`, `metric_semantics_version` | Portefeuille valorisé ou résultat réalisé cumulé ; convention brut/net et frais explicites |
| `generated_at_utc`, `freshness_classification` | Temps et fraîcheur propres à la publication |
| `source_boundary_id`, `source_stream_digest`, `producer_source_sha` | Frontière et provenance gouvernées |
| `coverage`, `limitations` | Bornes, couverture partielle, fréquence et limites publiées |
| `samples[]` | Ordre temporel publié, dates UTC uniques, valeurs décimales exactes ou null, sémantique et références par point |

Chaque point doit porter sa date de valorisation, son état de preuve, ses
références financières et sa frontière/sequence source. Une valeur inconnue
reste `null` avec état explicite ; le tracé est interrompu à cet endroit.
Deux points doivent réellement exister avant une courbe. Une seule observation
est un point isolé, jamais une série. Aucune interpolation de faits, bougie,
conversion de devise, agrégation financière ou connexion entre epochs côté React.
Les coordonnées SVG seraient une projection visuelle des valeurs publiées,
pas une recomputation de PnL, d’equity ou de rendement.

## Proposition : répartition publiée

Le producteur doit fournir un `denominator_metric_id`, son montant décimal,
sa définition, son unité, sa date et sa provenance, ainsi que les catégories
et leurs montants/parts déjà calculés et validés. Le frontend ne les calcule pas.

Dans PAPER_LINEAR_PRINCIPAL_V1, une proposition à valider est le capital au coût
historique avec trois compartiments disjoints : capital disponible, principal
réservé, principal non résolu. Le principal non résolu ne certifie pas une valeur
économique récupérable. Le total et les parts doivent être attestés par FIN.

Capital déployé : mesure d’exposition, jamais une quatrième part additive du
principal réservé. PnL réalisé, latent, frais et financement restent hors des
parts de capital. Le capital disponible n’est pas la liquidité du marché.
Un dénominateur absent, nul ou invalide, ou une part inconnue, rend la répartition
non disponible : aucun segment zéro ou remplacement silencieux ne sera fabriqué.

## Proposition : évolution Research

Une publication historique devrait admettre plusieurs runs explicitement liés
à la même identité de stratégie/version ; les liens parent/enfant doivent être
publiés et gouvernés. Une comparaison nécessite les mêmes dimensions de cohorte
que le contrat existant : dataset, frontière, protocole, population, coûts,
univers/régimes, rôle, métrique et politique. Les ruptures doivent être visibles.
Aucun lien entre candidats indépendants, aucun rang global, aucun PnL positif
transformé en validation. Une succession de runs ne prouve pas une amélioration.

## Admission future

Il restera à faire revoir le schéma fermé et ses validations, choisir le
producteur, admettre les publications et établir les preuves nécessaires.
Cette proposition n’autorise aucune mutation, exécution, collecte ou publication
runtime. U8, la certification L4 et la fin du burn-in demeurent distincts.
