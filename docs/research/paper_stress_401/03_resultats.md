# Rapport 3 — Résultats offline et validité

Verdict scientifique : **INSUFFICIENT_EVIDENCE** pour la performance A/B/C,
nombre de positions, sizing, horizons, fenêtres et robustesse des stratégies.
Aucun dataset réel n’est fourni à l’exécution de cette livraison. Aucune nouvelle
métrique de marché ni aucun trade observé n’est produit. Les métriques O5 de #282
restent historiques et ne sont pas recopiées comme résultats de cette mission.

## Résultats analytiques reproductibles

`analytic_report.json` et son manifest embarqué sont produits par le runner sur
le protocole versionné, sans données de marché. Identité : SHA code, hash canonique
protocole, méthode versionnée, classe d’entrée NO_DATASET. L’envelope porte SHA256
du rapport complet ; `source_manifest.json` porte les empreintes des sources.
Ce sont des résultats sous hypothèses, non des mesures de marché.

| Bras | Exposition notionnelle au cap | Fraction capital | Perte sous choc commun 10 %, coûts de base inclus |
|---|---:|---:|---:|
| A | 20 USDT | 2 % | 2,064 USDT |
| B | 200 USDT | 20 % | 20,64 USDT |
| C | 500 USDT | 50 % | 51,60 USDT |

Coûts de base : 10 bps frais/jambe, 5 bps slippage/jambe, spread 2 bps round-trip.
Ces valeurs viennent de la formule exécutée, pas d’un trade. Grille complète :
9 cellules × 72 scénarios = 648 points analytiques ; pas 648 observations.
Pour C, choc de 30 % avec ces coûts : 151,60 USDT, dépassement du budget de perte
proposé de 100 USDT. Choc de 100 % : 501,60 USDT. Même symbole à cap plein :
concentration 50 %, au-delà du seuil proposé 20 %. C n’est donc pas déclaré sûr
par son simple cap de cinq positions. Ces stress n’attestent pas la probabilité
ou la perte ultime d’une campagne réelle/simulée dynamique.

Chaque point conserve frais, spread, slippage, choc et hypothèse de dépendance.
Aucune liquidité empirique, capacité de fill ou distribution probabiliste n’est
inférée d’une grille. Les coûts en fin de vie sont conservateurs à notionnel fixe.
Financement, levier, shorts, gaps et liquidation ne sont pas couverts par une
borne universelle ; le choc plein peut dépasser le principal avec les coûts.

## Comparaisons non identifiables

| Question | Résultat actuel | Evidence requise |
|---|---|---|
| Admissions/lifecycles à cap 4/5 | UNKNOWN | décisions/rejets complets, état/cash et trajectoires |
| WR/PF/expectancy/PnL A/B/C | NOT_AVAILABLE | exécutions contrefactuelles causalement reconstructibles |
| Timeout/horizons alternatifs | NOT_AVAILABLE | baseline certifiée et chemin TP/SL/timeout/recovery |
| Effet de fenêtres horaires | NOT_AVAILABLE | mêmes jours/régimes et signal tape complet |
| DD MTM et exposition moyenne | NOT_AVAILABLE | marks synchronisés/frais/réservations dans le temps |
| Corrélation, liquidité/spread observés | UNKNOWN | rendements/carnets certifiés avec fraîcheur |
| IC, N indépendant et OOS | NOT_AVAILABLE | clusters, régimes, puissance, partition verrouillée |

## Preuve synthétique et limites

Tests réutilisant les fixtures RL-REPLAY : copie immuable, PPL contrôlé,
replay factuel, distributions brutes PnL/frais/durée, UNRESOLVED non compté comme
trade à zéro, hashes déterministes, corruption refusée, aucune mutation des
sources et d’une racine protégée synthétique. Input_class SYNTHETIC_TEST_ONLY
reste dans l’identité. Ces tests prouvent le comportement du logiciel, pas la
performance financière. La liste exacte des contrôles/versions figure dans
`validation.md` ; aucun succès historique ne remplace ces exécutions.

Avec une future copie immuable admissible, le même runner peut rendre les
métriques factuelles de RL-REPLAY et les distributions des trades fermés. Il ne
fera toujours pas de reconstruction de signaux rejetés ou de timeout alternatif.
Les intervalles de confiance restent indisponibles jusqu’au plan de clusters
validé ; aucune indépendance IID implicite.
