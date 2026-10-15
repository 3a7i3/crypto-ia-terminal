# D1_C_CLASSIFICATION_REPORT

Méthode `D1_C_V1`, contrat source et auditeur hérités de #406
`b99c2ed4f38ebeff481b5f470ed2d08e8e852257`. Identités des fichiers et SHA du
commit d'implémentation : voir D1_C_TEST_REPORT et la PR D1-C exacte.

## Résultat synthétique, non réel

Fixture minimale isolée : cinq packets REJECTED, cinq identités causales, une
observation. Résultat déterministe : LINKED=1 ; PROVEN_NOT_ELIGIBLE=2
(non-actionable=1, HOLD=1) ; ELIGIBLE_WITHOUT_OBSERVED_RECORD=1 ;
UNKNOWN_ELIGIBILITY=1. Total 1+2+1+1=5 ; toutes les matrices totalisent 5.
La permutation des entrées ne modifie pas le rapport ; aucune entrée n'est mutée.
Ces valeurs valident la méthode, jamais les données D1 historiques.

## Référence historique D1-B, sans requalification

[Preuve #404](https://github.com/3a7i3/crypto-ia-terminal/issues/404#issuecomment-6105687514)
observée le 2026-10-11 05:02 UTC sur copie de la fenêtre du 10 octobre :
10824 packets = 9672 REJECTED + 1152 EXECUTION_PENDING ; 5486 observations,
5486 liens REJECTED, 4186 REJECTED sans lien ; premier blocker Gate=4654,
Meta=832 ; 105 ATTEMPT + 105 OUTCOME appariés. Manifest historique attendu :
`a57d64a69aa4c65df5d5c601a5d56b169a8e31e7f81fd9b39de6a277bfeeb657`.
Auditeur historique :
`11d3e13e90e04446f6d1fc5bff4840103fa4f23e2865a211e8b5f77771b94494`.
Dataset_id et source_boundary_id de cette custody capture : NOT_PROVEN,
ne pas emprunter ceux du dataset O4/O6-B. Epoch/source/config de référence
ne sont pas liés scientifiquement aux octets par ce manifest UNVERIFIED.

La nouvelle répartition des 4186 est NOT_OBSERVED tant qu'une exécution D1-C
sur cette copie n'a pas abouti. Rien ici ne signifie 4186 écritures perdues.
Ni perte certifiée, ni performance contrefactuelle, ni couverture complète
producteur, ni checkpoint courant de l'epoch ne sont déduits de D1-B.

## Interprétation

Une exclusion native prouvée est une différence sémantique attendue selon
contrat source. Les filtres identifiables satisfaits sans record donnent une
anomalie candidate, car la validité complète de l'observation et sa chaîne
publication→livraison→validation→fsync ne sont pas capturées. Un défaut n'est
démontré qu'avec la preuve de cette chaîne et de son boundary complet. UNKNOWN
signifie preuve insuffisante. REJECTION_STORE_COVERAGE n'est ni un taux de perte,
ni un taux de réussite ; aucun WR/PF ou rendement n'est calculé.

`COUNTERFACTUAL_PERFORMANCE_ELIGIBILITY=NOT_PROVEN`
`PAPER_STRESS_RUNTIME_GO=DENIED`
`ACTIVE_BURN_IN_IMMUTABILITY_GUARD=ACTIVE`

## Disponibilité réelle D1-C — 2026-10-11 05:18–05:19 UTC

Remote Desktop Commander list_devices signale crypto-advisor-2 Offline
(dernière présence environ 17 minutes avant le relevé). La racine historique
n'existe pas dans le workspace Research local. Aucun preflight de compte,
permissions ou hashes des datasets n'a donc été exécuté sur l'appareil.
`REAL_BYTES_NOT_AVAILABLE` ; population D1-C réelle et quatre catégories
réelles = NOT_OBSERVED. Aucun ID d'appareil ni record publié. Aucune demande
de sudo, relance de connexion, accès production ou installation distante.

Verdict source sous réserve des tests finaux et revue :
`D1_C_SOURCE_READY_FOR_REVIEW`. Verdict données réelles :
`D1_C_BLOCKED_INSUFFICIENT_EVIDENCE` ; pas de D1_C_REAL_SUBSET_CLASSIFIED.
