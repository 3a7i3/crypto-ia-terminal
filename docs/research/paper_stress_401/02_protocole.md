# Rapport 2 — Protocole PAPER-STRESS prospectif

État : PROPOSED_OFFLINE_ONLY / NOT_AUTHORIZED_FOR_ACTIVATION.
`protocol.json` est le pré-enregistrement source de recherche v1 ; il n’est ni
une configuration Advisor, ni un manifest d’epoch active. Toute modification
après admission des données doit produire une nouvelle identité et être déclarée.
Capital indépendant fixé pour cette étude : **1 000 USDT fictifs**. Aucun lien
avec le solde, les réservations ou le capital initial de production.

| Bras hypothétique | Notionnel par position | Cap | Exposition au cap / capital |
|---|---:|---:|---:|
| A | 10 USDT | 2 | 20 / 1 000 = 2 % |
| B | 50 USDT | 4 | 200 / 1 000 = 20 % |
| C | 100 USDT | 5 | 500 / 1 000 = 50 % |

Ce sont des hypothèses #401, pas une certification des paramètres historiques.
A/B/C combinent deux facteurs : ne pas attribuer leur écart au sizing seul.

## Comparabilité et séparation des variables

1. Grille factorielle 3×3 : notionnels 10/50/100 × caps 2/4/5, mêmes signaux,
   marché, coûts, capital, priorités et stratégie. Comparer chaque facteur à
   l’intérieur d’un niveau fixe de l’autre ; interactions rapportées séparément.
2. Horizons : baseline timeout UNKNOWN à extraire d’une copie config certifiée.
   Multiplicateurs proposés 0,5 / 1 / 2, en gardant sizing/cap/fenêtre fixes.
   Aucune stratégie active modifiée. Interdire une conversion arbitraire en heures.
3. Fenêtres UTC [0,24), [0,8), [8,16), [16,24), entrée filtrée uniquement ; gestion
   des positions déjà ouvertes continue hors fenêtre. Même horizon calendaire,
   mêmes jours, stratification des régimes ; filtrage change la sélection et doit
   être explicitement comptabilisé, jamais présenté comme effet temporel pur.
4. Stratégies existantes figées avant évolution ; aucun nouveau signal. Chaque
   évolution future exige un protocole distinct avec baseline et OOS identiques.

## Gates d’admission de données pour une reconstruction future

Exiger copies Research immuables autorisées, hashes source/config/dataset,
population de décisions incluant rejets et motifs, règles d’admission et état
initial, trajectoires multi-actifs/marks synchronisés et causalement datés,
spread/profondeur/liquidité et périodes manquantes, TP/SL/timeout/recovery,
précision/tick size/contract size et financement si applicable. Vérifier IDs et
hashes avec RL-DATA/RL-REPLAY, provenance gouvernée et autorisation d’usage.
Un label `DECLARED_IMMUTABLE_RESEARCH_COPY` n’est pas une certification.

Les signaux rejetés ne sont pas des trades observés. Un replay futur peut
simuler leur admission uniquement si le motif et la trajectoire sont disponibles,
en conservant l’identité et le label COUNTERFACTUAL. Le modèle devra préciser la
priorité des événements simultanés, latence, ordre de sélection, fills partiels,
capacité partagée entre bras, absence de lookahead et capital+réservations.
Changement d’état de portefeuille peut changer les signaux : hypothèse de tape
exogène à tester, pas considérée acquise. Sinon rejeu causal du générateur requis.

## Simulations actuellement exécutables

Enveloppes analytiques, long sans levier, cap plein, notionnels constants :
`exposition = notionnel × cap`, choc adverse commun 10/30/50/100 %.
Frais par jambe 10/20 bps ; slippage par jambe 5/25/100 bps ; spread complet
round-trip 2/20/100 bps (demi-spread par jambe).
`coût = exposition × (2×frais + 2×slippage + spread) / 10 000`.
`perte = exposition × choc + coût`.
Coût conservateur calculé sur le même notionnel aux deux jambes, sans financement.
Corrélation adverse parfaite = scénario de stress, pas estimation ni probabilité.
Ce n’est pas une borne universelle short/levier/liquidation, ni un modèle de fills.
Liquidité/spread empirique restent UNKNOWN ; ces grilles sont des hypothèses.

Les neuf cellules × 72 scénarios donnent 648 calculs, **zéro observation de
marché indépendante**. Aucun WR/PF/expectancy de campagne n’en est dérivé.
Un dataset explicite permet uniquement le replay factuel existant et distributions
brutes des trades fermés, sans transformer UNRESOLVED en PnL nul.

## Métriques et statistiques à pré-enregistrer

Décisions/admissions/rejets par motif, lifecycles OPEN/CLOSED/UNRESOLVED,
PnL brut/net, frais/slippage séparés, WR/PF/expectancy, DD réalisé et MTM distincts,
exposition max et moyenne pondérée en temps, concentration par symbole/régime,
corrélations estimées sur rendements synchronisés, durée/censure, coverage.
Rapporter séries/distributions, quantiles et N par symbole/cohorte/régime/horizon,
jours et clusters ; N trades n’est pas N indépendant. Zéro perte au dénominateur
PF reste statut explicite ; pas de JSON Infinity. Positions non closes sont
censurées ; aucun forward-fill de mark stale vers une preuve de MTM.

Plan proposé (non exécuté sans données) : différence appariée par jour UTC,
cluster commun à tous les symboles ; bootstrap de blocs contigus en jours,
2 000 réplications, seed 401, intervalle 95 %. Longueur de bloc déterminée sur
training par dépendance observée, fixée avant OOS. Minimum proposé 30 clusters
par comparaison ; revue de puissance nécessaire et minimum non suffisant.
Derniers 30 % chronologiques en OOS verrouillé, purge et embargo au moins au plus
long horizon ; régimes définis exclusivement avec information passée.
Rapporter autocorrélation, couverture de régime, sensibilité au bloc et multiplicité
(Holm sur famille pré-enregistrée). Aucun seuil de significativité seul ne valide
une campagne. Si OOS/clusters/régimes insuffisants : INSUFFICIENT_EVIDENCE.

## Critères proposés de passage et d’arrêt

Ces nombres sont des **propositions Research non certifiées**, pas des limites
Advisor et pas une autorisation : arrêt à perte cumulée ≥10 % du capital Research,
DD MTM ≥15 %, exposition >50 %, concentration d’un symbole >20 %.
Zéro décision manquante/dupliquée non résolue, zéro mark stale utilisé, aucun drift
source/config/dataset ou bilan capital non réconcilié. Interruption : geler
l’admission simulée, garder les positions censurées/UNRESOLVED ; ne pas liquider
au dernier prix supposé. Reprise seulement avec état reconstruisible et preuve.
Gap pouvant franchir un seuil avant fill : rapporter dépassement ; stop n’assure
aucune perte maximale. Les stress du bras C peuvent franchir ces arrêts proposés.

Passage au stade de revue : hashes déterministes, intégrité/capital exacts,
comparabilité démontrée, coverage/puissance revues, robustesse aux coûts/stress,
OOS non utilisé pour choisir les paramètres, risques inconnus visibles.
Pas de critère profit fabriqué : budgets de perte, différence minimale pertinente
et couverture de régimes à ratifier avant une future expérience. Si non ratifiés,
aucun verdict de lancement. Rollback Research : conserver les résultats immuables,
revenir au code précédent dans la branche de recherche ; aucune opération VPS.
