# MARKET-TIMING-01 — protocole de recherche, sans score déployable

Mission source #533. Statut : DRAFT / NON_DEPLOYED.
Ce protocole ne modifie aucun classement, seuil, régime, stratégie ou calibration.
Aucune performance ou rentabilité n’est établie par ces propositions.

## Ce que les mesures actuelles représentent

Source primaire : `scripts/radar_bot.compute_symbol_stats`.

| Champ | Définition | Ce qu’il ne démontre pas |
| --- | --- | --- |
| Score moyen | Moyenne des confidences des paquets retenus, arrondie à une décimale | Probabilité de gain, prix ou pression d’achat actuelle |
| Score maximal | Maximum des confidences de ces paquets | Un breakout confirmé |
| Signaux | Nombre de DecisionPackets retenus | Nombre d’indicateurs indépendants, d’ordres ou de transactions |
| Dominance | Part des paquets de biais acheteur/vendeur, sur tous les paquets retenus | Part de volume, flux institutionnel ou carnet d’ordres |
| Régime | Régime modal des paquets de ce symbole | Heure de transition, durée d’une tendance ou épuisement |

65 paquets ne prouvent donc pas une bataille d’ordres ou une anomalie de volume.
100 % de dominance ne constitue pas un « scanner institutionnel ».
Le score de confiance peut décrire un biais vendeur ; une hausse de confiance
ne signifie pas une hausse de prix ou un flux d’achat.

Le régime de synthèse du marché est le mode des régimes des symboles agrégés,
avec départage déterministe. Il n’est pas un détecteur instantané de cassure.

## Variation du score : prérequis avant calcul

Il faut, pour chaque symbole et population, des points datés comparables :
score courant, référence vers 5/15 minutes, heures effectives et provenance.
Publier aussi la méthode d’agrégation, la tolérance de rapprochement, la
couverture temporelle, les doublons, les trous et l’état de fraîcheur.
Les points doivent conserver le même modèle, calibration, seuil, horizon,
venue et convention de direction ; aucun mélange d’epochs.

Le delta en points est `score(t) - score(t-h)`.
Un passage de 65 à 78 représente **+13 points**, soit **+20 % relatifs** ;
ces deux unités ne sont pas interchangeables. La variation relative exige
une référence strictement positive et une définition distincte.
Un point absent, trop ancien ou incompatible donne `NOT_AVAILABLE`, jamais 0.
L’arrondi et l’incertitude de mesure doivent rester visibles.

Une différence de moyennes de fenêtres glissantes peut venir de l’entrée ou
de la sortie de paquets ; elle ne prouve pas un nouveau flux de marché.
Une capture agrégée unique de 24 h ne permet aucun delta 5/15 min.
Un changement de fichier ou son heure de lecture ne constitue pas un point score.

## Régime volatil et transition

Une vue filtrée sur `VOLATILE` est une sélection observationnelle.
Détecter `RANGE → TREND_BULL/BEAR` exige des états successifs horodatés,
une durée minimale/confirmation préspécifiée et un traitement des oscillations.
Sans cette série, transition et âge du régime restent `NOT_AVAILABLE`.
Ni un régime volatile ni une première bougie ne garantissent un gain.
Ne pas supprimer une tendance supposée « épuisée » sans critère daté et validé.

## Densité et volume relatif

Une densité descriptive peut être définie en **paquets par minute** uniquement
avec dates, durée effective couverte et cadence du producteur. Les doublons
et trous doivent être publiés. Une hausse du rythme du collecteur suffit à
gonfler ce compteur ; il ne doit pas être présenté comme flux d’ordres.
Aucun multiplicateur du score ou tri prioritaire n’est introduit ici.

Le RVOL exige de vrais volumes de marché et une référence :
même symbole/venue, unité explicite (base ou notionnel), intervalle et historique.
Publier numérateur, dénominateur, bornes, qualité et traitement des volumes
nuls/absents. Il ne peut pas être déduit du nombre de DecisionPackets.
La projection actuelle ne contient ni volume, ni spread, ni profondeur.

## Validation avant un usage de timing

Une future mission devra définir à l’avance ses hypothèses et sorties :
horizon 5/15 min, population, sélection, mesures, comparaison et critères
d’échec. Éviter les fuites du futur et les biais de sélection/survivance.
Tester hors échantillon, par régimes et avec coûts, spread, liquidité,
latence et slippage documentés, avant toute interprétation de performance.

Les catégories « explosif » / « flux lourd » restent des hypothèses.
Le frontend peut exposer des mesures disponibles et leurs limites ;
il ne doit pas fabriquer un verdict d’exécution ni promouvoir une hypothèse
Research dans le runtime.

## Séquence proposée

1. Admettre séparément un catalogue historique complet et borné, si ses sources
   brutes sont autorisées ; conserver dates et périmètre réels.
2. Définir un contrat de série temporelle observationnelle avec états indisponibles,
   et ses preuves de cadence/couverture.
3. Évaluer les mesures et visualisations hors runtime avec fixtures puis données
   autorisées, sans modifier les archives originales.
4. Décider séparément de toute collecte, actualisation, notification ou activation.

L’extension v1.1 rend possibles des publications 1 h/4 h bornées à la production ;
elle ne fournit pas encore de séries temporelles ni de données fraîches.
