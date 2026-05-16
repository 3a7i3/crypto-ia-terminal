# CURRENT_TASK

## Focus actuel

Rendre le pilotage du depot plus concret et maintenir une reprise rapide du contexte, en partant de l'etat reel du projet.

## Contexte utile

- Le depot contient plusieurs systemes distincts, avec `quant-hedge-ai` comme priorite principale
- La documentation est abondante, mais une partie des liens du `README.md` racine doit etre corrigee
- L'audit des tests racine est bien avance, avec seulement quelques fichiers encore a revoir
- Des notes d'architecture existent deja sur les zones fragiles autour de `DecisionPacket`, des regimes et de la gouvernance risque

## Definition de termine

- Les fichiers de pilotage existent a la racine
- Leur role est clair et complete le reste de la documentation
- Ils peuvent etre mis a jour au fil du travail sans friction
- Ils aident a choisir la prochaine action sans relire tout le depot

## Chantiers actifs

1. Documenter l'etat reel du projet dans ces fichiers de pilotage
2. Corriger ensuite les liens et references les plus visibles du `README.md` racine
3. Continuer la revue des tests racine encore ambigus

## Points d'attention

- Pas de blocage majeur identifie a ce stade
- Principal risque court terme : derive entre documentation racine, docs dans `docs\`, et priorites reelles
- Principal risque technique : contrats implicites entre moteur de signal, regimes, conviction et risk gate

## Prochaines actions

1. Maintenir cette page avec la priorite active
2. Reporter dans `BUGS.md` les problemes confirmes et visibles
3. Corriger les liens casses ou placeholders du `README.md`
4. Revoir les tests racine encore en zone grise
5. Deplacer les idees non prioritaires dans `IDEAS_PARKING.md`
6. Faire vivre `ROADMAP.md` quand les priorites changent

## Notes

Cette page doit rester courte, concrete et orientee execution.
