# 3B — Première tranche : noyau pur privé

SOURCE_ONLY / LAB_ONLY / INTEGRATION_PENDING. Autorisation d'implémentation
obtenue après validation du contrat et revue indépendante de #505. Contrat
fusionné en `c1cb6efd3120e316bb57f7afdce2dd8d6b30569e`, tree
`c488d92022f3f74cabd624fad333d5b836c83fb2`. Sa CI main et celle de cette
implémentation sont des gates distincts de sa CI pré-fusion.

Cette livraison suit le découpage §5 du [plan](P4_3B_PLAN_AND_REUSE_V0.md) :
petite PR de comparaisons pures avant l'acquisition. Elle ne fournit pas encore
`AttestationObserver` ni `scan_attestations`. Aucun résultat positif de scan ou
agrégat `branch_attestations` complet n'est exposé. L'API publique existante et
ses lecteurs restent inchangés.

## Comparaisons livrées

- Branche complète fondateur→parent, identité A1 et `lineage.verify_record` ;
  admission/qualification et exclusions locales adaptées des règles registrar.
- Dérivation des besoins DECISION par clé incluant le hash du record, sans
  modifier PREPARED ni authentifier la partition POPULATION.
- Adaptation immuable de `trust.classify_envelope` : propriétés distinctes,
  copies d'enveloppes exigées, révocation jamais transformée en authentification.
- Lien d'un ancêtre à exactement une opération COMMITTED inventoriée et à son
  entrée `/1` exacte. Aucun helper de bundle ou consommation path-based.
- Grammaire fermée de statement, deux scopes exacts et liaisons auteur/version.
  Profil R8/C9 : comparaison des artefacts épinglés, lien du digest q à raw C9
  et du digest historique signé à raw R8. PC2 reste non pris en charge.
- Encodage de hash de code sur bytes détachés. Le helper n'affirme jamais que
  la liste fournie constitue une fermeture complète ; cette preuve appartient
  au prochain propriétaire d'acquisition.

Les types et fonctions résident dans deux modules privés. Un PASS de fonction
ne prouve que la comparaison nommée sur ses entrées détachées. Il ne prouve ni
origine/stabilité des bytes, ni acquisition complète, ni installation de trust,
ni authenticité historique de R8, ni fraîcheur de campagne ou provenance Git.
`accepted=false` et les limites globales non évaluées sont conservés.

## Vérification et suite

107 nouveaux tests paramétrés couvrent la branche, les besoins/items et les
bindings de statement/source. Ils ne remplacent pas les 75 cas contractuels de
scan : ces derniers restent SPECIFICATION_ONLY tant que leur entrée complète
n'est pas implémentée et testée. Les suites normales et `python -O` se recouvrent
et ne s'additionnent pas. Les résultats exacts et la revue du tree final sont
consignés dans la PR, sans transférer une revue d'un arbre modifié.

Le test d'architecture des projections lexicales garde son périmètre initial ;
seuls les deux nouveaux modules ont une liste d'importation supplémentaire
explicite. Leurs tests vérifient aussi l'absence d'appels IO/bundle/spend et
l'absence d'API de scan publique.

Prochaine tranche, après les gates de cette PR : un seul propriétaire L1→L2,
inventaire historique et snapshot ledger unique, branches et enveloppes acquises
une fois, fermeture checkout bornée, revalidation et invalidation totale en cas
d'échec de lecture/limite/close ; puis agrégats complets et API du contrat.
Les fonctions pures ne doivent pas être directement branchées à une décision.

Pins P1, politique g0 et sources `colony_lab`, `sentinel_activity`, `colony_pilot`
inchangés. Aucun writer, campagne, VPS/runtime/déploiement/systemd/PPL/FIN/epoch/
production/TESTNET/LIVE/secret/Replay/Diagnostic lancé. #286 reste ACTIVE.
Population/plafonds 3C non évalués. Cette tranche ne clôture pas 3B.
