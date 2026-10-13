# Livre blanc — pilotage visuel de l’infrastructure de recherche

Mission #428, parents #323/#285. Route Operator App : `/direction/travaux`.

## Objet

Un seul espace Direction pour suivre les travaux, lire leurs limites et ouvrir
leurs preuves GitHub. La synthèse runtime existante reste `/direction` ; le
tableau est un registre éditorial de gouvernance versionné, pas de la télémétrie.

La machine produit des faits PAPER sous une expérience gouvernée. Research
consomme des datasets immuables, rejoue, diagnostique et propose des candidats.
Ces candidats ne peuvent modifier l’epoch active. Une future expérience exige
ses propres gates scientifiques, ressources, autorisation et activation.

## Lecture du tableau

| Couleur | Libellé | Signification |
|---|---|---|
| Vert | Terminé | Sortie acquise dans le périmètre écrit dans la ligne |
| Jaune | En cours | Travail actif ou revue/CI non achevée |
| Rouge | À faire | Étape suivante non réalisée ; pas un incident runtime |
| Rouge | Bloqué | Preuve ou gate manquante explicitement identifiée |
| Gris | En pause | Travail volontairement différé |

Un libellé et un périmètre accompagnent chaque couleur. Une PR source intégrée
ne devient pas une certification runtime. Une issue parent peut rester ouverte
alors qu’un de ses mécanismes de laboratoire est terminé. Les totaux comptent
les lignes éditoriales, pas les issues ni un pourcentage de certification.

## Frontières acquises et prochaines gates

Registre consolidé du 2026-10-13T01:34:16Z : L3 est formellement certifié ; U7 est
certifié en source dans son périmètre historique. Le burn-in #282 reste non
finalisé et #286 actif. La complétude producteur et la durabilité par packet
D1-D/E ne sont pas prouvées. Les mécanismes natifs de laboratoire ne certifient
pas la population Advisor réelle. #425 et #427 sont intégrées dans main.

Ordre de travail : qualification d’observation, clôture scientifique du burn-in,
gates U8/L4 distinctes, puis future expérience admise. Observatoire multi-venue,
agents/AIC et Treasury réel restent soumis à leurs dépendances. Les voies source
et lecture seule peuvent avancer en parallèle sans modifier l’expérience.

## Mise à jour et provenance

Le registre `frontend/src/lib/machineWorkboardRegister.ts` porte sa date et le SHA
main de référence. Avant une mise à jour : relire les issues, leurs derniers
checkpoints et les PR pertinentes ; actualiser preuve, prochaine action et
périmètre. Conserver les preuves anciennes comme historiques. La date du registre
n’est pas celle d’un checkpoint scientifique ni de chaque certification citée.
Les changements GitHub ultérieurs ne sont pas automatiquement synchronisés.
Un futur producteur live serait une mission et un contrat distincts.

La vue ne fait aucun fetch et ne lit pas de fichiers VPS, PPL, database, exchange
ou secret. Pas de boutons merge/restart/activation, pas de mutation API ni de
calcul financier. Elle est lisible même si les APIs runtime sont indisponibles.

## Livraison et rollback

Source isolée, build frontend, tests de routage/non-fetch/filtres et captures
desktop/mobile. Aucune dépendance produit ajoutée ; Playwright est un outil CI.
Mise en ligne et preuve du bundle effectivement servi restent une release
distincte ; cette mission ne redémarre pas Advisor ni le VPS et ne modifie pas
la configuration burn-in. Rollback : revert des fichiers de #428 uniquement.

FUTURE_CAPTURE_ACTIVATION=DENIED ; PAPER_STRESS_RUNTIME_GO=DENIED ; #286 ACTIVE.
